"""astra_shift_topside_v12.py -- move everything that sits ON the skid toward the
pump end by a fixed distance along world +Y, and prove nothing else changed.

Owner request (2026-09-18): "shift everything on top of the skid -- the engine,
the pump, and both tables they sit on, the mounts -- toward the pump's end of the
skid by approximately 12 inches."

  12 in = 304.8 mm, along world +Y.  +Y is the pump end: the pump occupies
  Y[266, 1363] mm and the engine Y[-1762, 522] mm, so the engine's radiator end
  is at -Y and its flywheel (which the pump's drive shaft enters) is at +Y.
  Cross-checked twice -- see ASTRA-HANDOFF-2026-09-18.md SS1.5.

WHAT MOVES (426 meshes) -- the payload:
  CAD_engine            7   vendor engine + PP12-EM-JD18 engine mount + EM-SP x4
  CAD_pump_new        415   the Vogelsang PP108C24 pump
  CAD_skid subset       4   DOUBLER, DOUBLER.001          <- the engine's table
                            PLT-MNT-6SL-PE-PP12,          <- the pump's table
                            MNT-PEB-CTF-PP12-WIDE

WHAT STAYS (42 meshes) -- the skid and what is welded to it:
  CAD_skid rest        10   base channels, rectangular tubes, both end caps
  CAD_pump             20   the fabricated deck: PP-FTT top/bottom plates,
                            PP-FTS webs, PP-FBS / PP128S22-MFB / PP128-FTA rails
  CAD_bale              9   lifting bale (its lift axis stays at Y = 0)
  CAD_controller        3   follows the bale upright, not the payload

METHOD.  Rigid translation of object transforms only.  No vertex is touched, so
every one of the 468 mesh datablocks keeps a bit-identical geometry hash -- the
"engine and pump geometry unchanged" invariant is proven, not asserted.  Only the
roots of the moved forest are translated; children inherit.  (ASTRA-HANDOFF
SS0.3: setting matrix_world on every object under a glTF root double-applies.)

Run:
  blender -b -noaudio --threads 4 <v11-wide.blend> --python-exit-code 1 \
     --python tools/astra_shift_topside_v12.py -- \
     --out-json reports/astra-shift-v12.json \
     --save-blend out/engine-and-pump-v12-shift.blend \
     --dy-mm 304.8

  Add --dry to measure and report without moving anything or saving.
"""
import bpy, sys, os, json, time, hashlib, argparse
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

T0 = time.time()


def log(*a):
    print("[shift %6.1fs]" % (time.time() - T0), *a, flush=True)


def fail(msg):
    raise RuntimeError(msg)


MM = 1000.0                 # mm per scene unit (Blender default: metres)
BBOX_TOL_MM = 0.01          # float32 round-trip headroom on a world bbox
FIXED_TOL_MM = 1e-4         # a fixed object must not move at all

# ---------------------------------------------------------------- the partition
# Explicit names, never fuzzy patterns -- astra_verify_wide.py was corrected for
# exactly this reason (see reports/astra-wide-geometry-final-worker.json).
MOVE_COLLECTIONS = {"CAD_engine", "CAD_pump_new"}
MOVE_FROM_SKID = {
    "DOUBLER", "DOUBLER.001",                 # engine table (transverse plates)
    "PLT-MNT-6SL-PE-PP12",                    # pump table base plate
    "MNT-PEB-CTF-PP12-WIDE",                  # pump table pedestal
}
FIXED_COLLECTIONS = {"CAD_pump", "CAD_bale", "CAD_controller"}
# CAD_skid is split: MOVE_FROM_SKID moves, the other 10 stay.

EXPECT_COLL = {"CAD_pump_new": 415, "CAD_engine": 7, "CAD_pump": 20,
               "CAD_skid": 14, "CAD_bale": 9, "CAD_controller": 3}
EXPECT_MOVE = 415 + 7 + 4      # 426
EXPECT_FIXED = 10 + 20 + 9 + 3  # 42

# The deck plate the two tables are bolted down to.  Moving the tables along it
# is the one change that has a manufacturing consequence -- see check_deck_landing.
DECK_TOP = "PP-FTT"
# The lifting bale's centre web: its Y is the lift axis the payload hangs from.
BALE_AXIS_PART = "LBA-CB"
BALE_UPRIGHTS = ("LBU-PP", "LBU-PP.001")


# ------------------------------------------------------------------ mesh access
def mesh_co(me):
    nv = len(me.vertices)
    co = np.empty(nv * 3, dtype=np.float32)
    me.vertices.foreach_get("co", co)
    return co.reshape(nv, 3)


def world_verts(o, co=None):
    """Vertices in world space, millimetres."""
    if co is None:
        co = mesh_co(o.data)
    mw = np.array(o.matrix_world, dtype=np.float64)
    return (co.astype(np.float64) @ mw[:3, :3].T + mw[:3, 3]) * MM


def geom_hash(me):
    """Bit-exact hash of mesh geometry + topology.  Must not change: this script
    only edits object transforms."""
    h = hashlib.sha256()
    h.update(mesh_co(me).tobytes())
    nl = len(me.loops)
    lv = np.empty(nl, dtype=np.int32)
    me.loops.foreach_get("vertex_index", lv)
    h.update(lv.tobytes())
    npoly = len(me.polygons)
    for attr in ("loop_start", "loop_total"):
        a = np.empty(npoly, dtype=np.int64)
        me.polygons.foreach_get(attr, a)
        h.update(a.tobytes())
    return h.hexdigest()


def mat_list(o):
    return [[float(v) for v in r] for r in o.matrix_world]


def bbox_mm(o):
    w = world_verts(o)
    return ([float(w[:, k].min()) for k in range(3)],
            [float(w[:, k].max()) for k in range(3)])


def coll_of(o):
    for c in o.users_collection:
        if c.name.startswith("CAD_"):
            return c.name
    return o.users_collection[0].name if o.users_collection else ""


def mesh_objects():
    return [o for o in bpy.data.objects if o.type == "MESH"]


# ------------------------------------------------------------------- partition
def partition():
    """Split every mesh object into moved / fixed.  Total, disjoint, asserted."""
    moved, fixed, unclassified = [], [], []
    for o in mesh_objects():
        c = coll_of(o)
        if c in MOVE_COLLECTIONS:
            moved.append(o)
        elif c == "CAD_skid":
            (moved if o.name in MOVE_FROM_SKID else fixed).append(o)
        elif c in FIXED_COLLECTIONS:
            fixed.append(o)
        else:
            unclassified.append(o)
    if unclassified:
        fail("unclassified meshes (collection not in the partition): %s"
             % sorted(x.name for x in unclassified)[:10])

    got = {}
    for o in mesh_objects():
        got[coll_of(o)] = got.get(coll_of(o), 0) + 1
    if got != EXPECT_COLL:
        fail("collection census mismatch\n  expected %s\n  actual   %s"
             % (EXPECT_COLL, got))

    missing = MOVE_FROM_SKID - {o.name for o in moved}
    if missing:
        fail("named skid parts to move are absent from the scene: %s" % sorted(missing))
    if len(moved) != EXPECT_MOVE or len(fixed) != EXPECT_FIXED:
        fail("partition size mismatch: moved=%d (expect %d), fixed=%d (expect %d)"
             % (len(moved), EXPECT_MOVE, len(fixed), EXPECT_FIXED))
    return moved, fixed


def ancestors(o):
    out, p = [], o.parent
    while p is not None:
        out.append(p)
        p = p.parent
    return out


def moved_roots(moved):
    """Only translate objects whose parent chain contains no other moved object;
    children inherit the translation.  Also proves no fixed object hangs off a
    moved one (which would drag it along invisibly)."""
    mset = set(moved)
    roots = [o for o in moved if not (set(ancestors(o)) & mset)]
    return roots


def guard_no_fixed_under_moved(moved, fixed):
    mset = set(moved)
    bad = [o.name for o in fixed if set(ancestors(o)) & mset]
    if bad:
        fail("these FIXED objects are parented under a MOVED object and would be "
             "dragged along: %s" % sorted(bad))
    # Non-mesh objects (empties, the glTF roots) parented under a moved mesh would
    # also travel.  Report them; empties carry no geometry so this is informational.
    nonmesh = [o.name for o in bpy.data.objects
               if o.type != "MESH" and (set(ancestors(o)) & mset)]
    return nonmesh


# --------------------------------------------------------------- measurements
def group_bbox(objs):
    lo = np.full(3, np.inf)
    hi = np.full(3, -np.inf)
    for o in objs:
        w = world_verts(o)
        lo = np.minimum(lo, w.min(axis=0))
        hi = np.maximum(hi, w.max(axis=0))
    return [round(float(v), 3) for v in lo], [round(float(v), 3) for v in hi]


def area_centroid(objs):
    """Triangle-area-weighted surface centroid, mm.

    This is a GEOMETRIC proxy, NOT a mass centre of gravity: it weights every
    square millimetre of surface equally and knows nothing about wall thickness,
    material density or the parts that are missing from the model (fluids,
    splined drive adapter, guarding, fuel).  It is reported because the payload's
    Y centroid relative to the lifting bale is the quantity this shift changes,
    and a 12 in move of the heaviest item on the skid is worth quantifying even
    approximately.  Treat it as an indicator, not a lift calculation.
    """
    num = np.zeros(3)
    den = 0.0
    for o in objs:
        me = o.data
        me.calc_loop_triangles()
        nt = len(me.loop_triangles)
        if nt == 0:
            continue
        t = np.empty(nt * 3, dtype=np.int32)
        me.loop_triangles.foreach_get("vertices", t)
        w = world_verts(o)
        tri = w[t.reshape(nt, 3)]
        a = 0.5 * np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0],
                                          tri[:, 2] - tri[:, 0]), axis=1)
        num += (tri.mean(axis=1) * a[:, None]).sum(axis=0)
        den += float(a.sum())
    if den <= 0:
        return None, 0.0
    return [round(float(v), 2) for v in (num / den)], round(den, 1)


def obj_tris_world(o):
    me = o.data
    me.calc_loop_triangles()
    nt = len(me.loop_triangles)
    t = np.empty(nt * 3, dtype=np.int32)
    if nt:
        me.loop_triangles.foreach_get("vertices", t)
    return world_verts(o), t.reshape(nt, 3)


CLEARANCE_SKIRT_MM = 250.0     # search radius around each upright
CLEARANCE_TRI_CAP = 400000     # refuse to build a BVH bigger than this


def bale_clearance(moved, skirt=CLEARANCE_SKIRT_MM):
    """Closest approach between the payload and each bale upright, mm.

    The Y shift slides a different engine cross-section past the uprights, so the
    clearance the +152.4 mm widening bought (v11) has to be re-measured, not
    assumed.  Min distance from upright vertices to payload triangles via BVH,
    with an AABB screen so the search stays bounded on the 2.27 M-triangle
    casting.  If a body still offers more than CLEARANCE_TRI_CAP candidate
    triangles the BVH is skipped for that body and an AABB lower bound is
    reported instead -- honestly labelled, never silently dropped.
    """
    out = {}
    payload = [o for o in moved if coll_of(o) in ("CAD_engine", "CAD_pump_new")]
    for uname in BALE_UPRIGHTS:
        u = bpy.data.objects.get(uname)
        if u is None:
            out[uname] = {"error": "object absent"}
            continue
        uw, _ = obj_tris_world(u)
        umn, umx = uw.min(axis=0), uw.max(axis=0)
        best, skipped = None, []
        for o in payload:
            w, t = obj_tris_world(o)
            if not len(t):
                continue
            # AABB screen: anything further than the skirt cannot win.
            if (w.min(axis=0) > umx + skirt).any() or (w.max(axis=0) < umn - skirt).any():
                continue
            tmn = np.minimum(np.minimum(w[t[:, 0]], w[t[:, 1]]), w[t[:, 2]])
            tmx = np.maximum(np.maximum(w[t[:, 0]], w[t[:, 1]]), w[t[:, 2]])
            keep = ~((tmn > umx + skirt).any(axis=1) | (tmx < umn - skirt).any(axis=1))
            idx = np.nonzero(keep)[0]
            if not len(idx):
                continue
            if len(idx) > CLEARANCE_TRI_CAP:
                gap = float(np.maximum(np.maximum(umn - tmx[idx].max(axis=0),
                                                  tmn[idx].min(axis=0) - umx), 0).max())
                skipped.append({"part": o.name, "candidate_tris": int(len(idx)),
                                "aabb_lower_bound_mm": round(gap, 2),
                                "note": "exceeded BVH cap; AABB lower bound only"})
                continue
            sub = t[idx]
            used = np.unique(sub)
            remap = {int(g): i for i, g in enumerate(used)}
            verts = [tuple(float(v) for v in w[g]) for g in used]
            polys = [(remap[int(a)], remap[int(b)], remap[int(c)]) for a, b, c in sub]
            bv = BVHTree.FromPolygons(verts, polys, all_triangles=True)
            for p in uw:
                loc, n, i, d = bv.find_nearest(Vector((float(p[0]), float(p[1]),
                                                       float(p[2]))), 3000.0)
                if loc is not None and d is not None and (best is None or d < best[0]):
                    best = (float(d), o.name,
                            [round(float(v), 2) for v in p],
                            [round(float(v), 2) for v in loc])
        rec = ({"min_distance_mm": round(best[0], 3), "payload_part": best[1],
                "upright_point": best[2], "payload_point": best[3]}
               if best else {"min_distance_mm": None,
                             "note": "no payload triangle within %.0f mm" % skirt})
        rec["search_skirt_mm"] = skirt
        if skipped:
            rec["bodies_over_bvh_cap"] = skipped
        out[uname] = rec
    return out


def check_deck_landing(moved, dy_mm):
    """Where the two tables land on the deck plate, before and after.

    The tables are currently fastened to PP-FTT at fixed hole positions.  Sliding
    them 304.8 mm along Y leaves the deck's existing holes orphaned and the tables
    sitting on blank plate.  This reports the footprint move and whether the new
    footprint is still fully supported by the deck; it CANNOT re-cut holes.
    """
    deck = bpy.data.objects.get(DECK_TOP)
    if deck is None:
        return {"error": "%s absent" % DECK_TOP}
    dw = world_verts(deck)
    dmn, dmx = dw.min(axis=0), dw.max(axis=0)
    rows = []
    for nm in sorted(MOVE_FROM_SKID):
        o = bpy.data.objects.get(nm)
        if o is None:
            continue
        lo, hi = bbox_mm(o)
        nlo = [lo[0], lo[1] + dy_mm, lo[2]]
        nhi = [hi[0], hi[1] + dy_mm, hi[2]]
        rows.append({
            "part": nm,
            "footprint_Y_before": [round(lo[1], 1), round(hi[1], 1)],
            "footprint_Y_after": [round(nlo[1], 1), round(nhi[1], 1)],
            "still_over_deck_Y": bool(nlo[1] >= dmn[1] - 1e-6 and nhi[1] <= dmx[1] + 1e-6),
            "deck_margin_minus_Y_mm": round(float(nlo[1] - dmn[1]), 1),
            "deck_margin_plus_Y_mm": round(float(dmx[1] - nhi[1]), 1),
        })
    return {"deck": DECK_TOP,
            "deck_Y_span_mm": [round(float(dmn[1]), 1), round(float(dmx[1]), 1)],
            "tables": rows,
            "WARNING": ("Existing fastener/weld positions on %s are NOT moved by this "
                        "script. Every table that slides along the deck needs its hole "
                        "pattern re-cut at the new Y, or the joint is unsupported."
                        % DECK_TOP)}


def bale_balance(moved, dy_mm):
    """How far the payload centroid sits from the lifting bale's axis."""
    bale = bpy.data.objects.get(BALE_AXIS_PART)
    axis_y = None
    if bale is not None:
        bw = world_verts(bale)
        axis_y = round(float(0.5 * (bw[:, 1].min() + bw[:, 1].max())), 2)
    c, area = area_centroid(moved)
    if c is None:
        return {"error": "no payload area"}
    return {
        "method": "triangle-area-weighted surface centroid (GEOMETRIC PROXY, not a "
                  "mass CG -- no densities, wall thicknesses or missing parts)",
        "bale_lift_axis_Y_mm": axis_y,
        "payload_centroid_before_mm": c,
        "payload_centroid_after_mm": [c[0], round(c[1] + dy_mm, 2), c[2]],
        "offset_from_lift_axis_before_mm": (round(c[1] - axis_y, 2)
                                            if axis_y is not None else None),
        "offset_from_lift_axis_after_mm": (round(c[1] + dy_mm - axis_y, 2)
                                           if axis_y is not None else None),
        "payload_surface_area_mm2": area,
        "WARNING": ("The lifting bale is fixed at Y ~ 0 and does NOT move. Shifting "
                    "the payload +%.1f mm moves its centroid the same distance off "
                    "the lift axis, so the package will hang further out of level. "
                    "A real lift check needs part masses, which this model does not "
                    "carry." % dy_mm),
    }


# ------------------------------------------------------------------- the move
def apply_shift(roots, dy_mm):
    d = Matrix.Translation(Vector((0.0, dy_mm / MM, 0.0)))
    for o in roots:
        o.matrix_world = d @ o.matrix_world
    bpy.context.view_layer.update()


# ------------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-json", default="reports/astra-shift-v12.json")
    ap.add_argument("--save-blend", default="out/engine-and-pump-v12-shift.blend")
    ap.add_argument("--dy-mm", type=float, default=304.8, help="12 in = 304.8 mm")
    ap.add_argument("--expect-sha", default="", help="sha256 of the input .blend")
    ap.add_argument("--dry", action="store_true", help="measure only; do not move or save")
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    args = ap.parse_args(argv)

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    absify = lambda p: p if os.path.isabs(p) else os.path.join(root, p)
    out_json, save_blend = absify(args.out_json), absify(args.save_blend)
    dy = float(args.dy_mm)

    src = bpy.data.filepath
    rep = {"script": "astra_shift_topside_v12.py", "script_rev": 1,
           "source_blend": src, "dy_mm": dy, "dy_in": round(dy / 25.4, 4),
           "direction": "+Y (pump end)", "dry_run": bool(args.dry),
           "blender": bpy.app.version_string, "started": time.strftime("%Y-%m-%dT%H:%M:%S")}

    if args.expect_sha:
        h = hashlib.sha256()
        with open(src, "rb") as f:
            for blk in iter(lambda: f.read(1 << 20), b""):
                h.update(blk)
        rep["source_sha256"] = h.hexdigest()
        if rep["source_sha256"] != args.expect_sha:
            fail("source sha mismatch: got %s expected %s"
                 % (rep["source_sha256"], args.expect_sha))
        log("source sha verified")

    us = bpy.context.scene.unit_settings
    rep["unit_scale_length"] = float(us.scale_length)
    if abs(us.scale_length - 1.0) > 1e-9:
        fail("scene unit scale_length is %r, expected 1.0 (metres); mm conversion "
             "would be wrong" % us.scale_length)

    # -------------------------------------------------- partition and guards
    moved, fixed = partition()
    roots = moved_roots(moved)
    nonmesh_riders = guard_no_fixed_under_moved(moved, fixed)
    log("partition: %d moved (%d roots), %d fixed" % (len(moved), len(roots), len(fixed)))
    rep["partition"] = {
        "moved_count": len(moved), "fixed_count": len(fixed),
        "moved_roots": len(roots),
        "moved_from_CAD_skid": sorted(MOVE_FROM_SKID),
        "nonmesh_objects_riding_along": sorted(nonmesh_riders),
        "moved_by_collection": {c: sum(1 for o in moved if coll_of(o) == c)
                                for c in sorted({coll_of(o) for o in moved})},
        "fixed_by_collection": {c: sum(1 for o in fixed if coll_of(o) == c)
                                for c in sorted({coll_of(o) for o in fixed})},
    }

    # ------------------------------------------------------------- baseline
    base = {o.name: {"hash": geom_hash(o.data), "bbox": bbox_mm(o),
                     "matrix": mat_list(o)} for o in mesh_objects()}
    rep["before"] = {
        "scene_bbox_mm": dict(zip(("min", "max"), group_bbox(mesh_objects()))),
        "payload_bbox_mm": dict(zip(("min", "max"), group_bbox(moved))),
        "skid_bbox_mm": dict(zip(("min", "max"), group_bbox(fixed))),
    }
    rep["deck_landing"] = check_deck_landing(moved, dy)
    rep["lift_balance"] = bale_balance(moved, dy)
    log("measuring bale clearance before ...")
    rep["bale_clearance_before"] = bale_clearance(moved)

    if args.dry:
        rep["verdict"] = "DRY RUN -- measured only, nothing moved, nothing saved"
        os.makedirs(os.path.dirname(out_json), exist_ok=True)
        with open(out_json, "w") as f:
            json.dump(rep, f, indent=1)
        log("DRY RUN report -> %s" % out_json)
        return

    # ----------------------------------------------------------------- move
    apply_shift(roots, dy)
    log("translated %d roots by +%.4f mm in Y" % (len(roots), dy))

    # --------------------------------------------------------------- verify
    errs = []
    moved_names = {o.name for o in moved}
    max_move_err = 0.0
    max_fixed_err = 0.0
    for o in mesh_objects():
        b = base[o.name]
        if geom_hash(o.data) != b["hash"]:
            errs.append("%s: MESH DATA CHANGED (this script must not touch vertices)"
                        % o.name)
        lo, hi = bbox_mm(o)
        want_dy = dy if o.name in moved_names else 0.0
        for k in range(3):
            exp = want_dy if k == 1 else 0.0
            for cur, ref in ((lo[k], b["bbox"][0][k]), (hi[k], b["bbox"][1][k])):
                e = abs((cur - ref) - exp)
                if o.name in moved_names:
                    max_move_err = max(max_move_err, e)
                    if e > BBOX_TOL_MM:
                        errs.append("%s: axis %d moved by %.4f mm, expected %.4f"
                                    % (o.name, k, cur - ref, exp))
                else:
                    max_fixed_err = max(max_fixed_err, e)
                    if e > FIXED_TOL_MM:
                        errs.append("%s: FIXED object moved %.6f mm on axis %d"
                                    % (o.name, e, k))

    rep["verification"] = {
        "mesh_hashes_unchanged": not any("MESH DATA CHANGED" in e for e in errs),
        "meshes_checked": len(base),
        "max_moved_bbox_error_mm": round(max_move_err, 6),
        "max_fixed_bbox_error_mm": round(max_fixed_err, 9),
        "bbox_tol_mm": BBOX_TOL_MM, "fixed_tol_mm": FIXED_TOL_MM,
        "errors": errs[:40], "error_count": len(errs),
    }
    if errs:
        fail("VERIFICATION FAILED (%d):\n  %s" % (len(errs), "\n  ".join(errs[:20])))
    log("verification PASS: %d meshes, all hashes identical, "
        "moved err <= %.4f mm, fixed err <= %.2e mm"
        % (len(base), max_move_err, max_fixed_err))

    rep["after"] = {
        "scene_bbox_mm": dict(zip(("min", "max"), group_bbox(mesh_objects()))),
        "payload_bbox_mm": dict(zip(("min", "max"), group_bbox(moved))),
        "skid_bbox_mm": dict(zip(("min", "max"), group_bbox(fixed))),
    }
    log("measuring bale clearance after ...")
    rep["bale_clearance_after"] = bale_clearance(moved)

    # payload-vs-skid end margins: did we run off either end?
    pb, sb = rep["after"]["payload_bbox_mm"], rep["after"]["skid_bbox_mm"]
    rep["end_margins_after_mm"] = {
        "minus_Y_radiator_end": round(pb["min"][1] - sb["min"][1], 1),
        "plus_Y_pump_end": round(sb["max"][1] - pb["max"][1], 1),
    }
    pb0, sb0 = rep["before"]["payload_bbox_mm"], rep["before"]["skid_bbox_mm"]
    rep["end_margins_before_mm"] = {
        "minus_Y_radiator_end": round(pb0["min"][1] - sb0["min"][1], 1),
        "plus_Y_pump_end": round(sb0["max"][1] - pb0["max"][1], 1),
    }
    if rep["end_margins_after_mm"]["plus_Y_pump_end"] < 0:
        rep["OVERHANG_WARNING"] = ("payload overhangs the +Y end of the skid by "
                                   "%.1f mm" % -rep["end_margins_after_mm"]["plus_Y_pump_end"])
        log("WARNING: %s" % rep["OVERHANG_WARNING"])

    # ------------------------------------------------------------------ save
    os.makedirs(os.path.dirname(save_blend), exist_ok=True)
    if os.path.exists(save_blend):
        fail("refusing to overwrite an existing scene: %s" % save_blend)
    bpy.ops.wm.save_as_mainfile(filepath=save_blend, compress=False)
    rep["saved_blend"] = save_blend
    rep["saved_bytes"] = os.path.getsize(save_blend)
    rep["verdict"] = "PASS"
    log("saved %s (%.1f MB)" % (save_blend, rep["saved_bytes"] / 1e6))

    os.makedirs(os.path.dirname(out_json), exist_ok=True)
    with open(out_json, "w") as f:
        json.dump(rep, f, indent=1)
    log("report -> %s" % out_json)


if __name__ == "__main__":
    main()
