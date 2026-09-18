"""astra_inspect_widening.py -- read-only geometry + clearance evidence.

Baseline evidence for the 6 in (152.4 mm) symmetric skid/bale widening on
out/engine-and-pump-v10.blend.  NEVER writes a .blend.

Run:
  blender --background -noaudio --threads 4 out/engine-and-pump-v10.blend \
      --python-exit-code 1 --python tools/astra_inspect_widening.py -- \
      reports/astra-widening-inspection.json <source_sha256>
"""
import bpy, sys, os, json, time, math
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

T0 = time.time()
def log(*a):
    print("[inspect %6.1fs]" % (time.time() - T0), *a, flush=True)

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT_JSON = argv[0] if argv else "reports/astra-widening-inspection.json"
SRC_HASH = argv[1] if len(argv) > 1 else ""

SRC_BLEND = bpy.data.filepath
DG = bpy.context.evaluated_depsgraph_get()

# --- unit detection: v10 is authored in METRES (machine is ~2.07 x 4.74 x 2.93
# scene units).  All analysis below is done in MILLIMETRES.
_pre_lo = [1e18] * 3
_pre_hi = [-1e18] * 3
for _o in bpy.data.objects:
    if _o.type != "MESH":
        continue
    _bb = np.array([list(c) for c in _o.bound_box])
    _mw = np.array(_o.matrix_world)
    _wbb = _bb @ _mw[:3, :3].T + _mw[:3, 3]
    for _k in range(3):
        _pre_lo[_k] = min(_pre_lo[_k], float(_wbb[:, _k].min()))
        _pre_hi[_k] = max(_pre_hi[_k], float(_wbb[:, _k].max()))
_maxext = max(_pre_hi[_k] - _pre_lo[_k] for _k in range(3))
SCENE_TO_MM = 1000.0 if _maxext < 20.0 else 1.0
MM = SCENE_TO_MM
print("[inspect  0.0s] scene extent", round(_maxext, 4), "-> to_mm", MM, flush=True)

STRUCT_PAT = ["SKID", "MFB", "MC6X18", "MC6x18", "channel", "tube", "TR12",
              "PLT-MNT", "MNT-PEB", "PP-FTT", "PP-FTS", "PP-FBS", "DOUBLER",
              "EM-SP", "PP12-EM", "PP128-FTA", "PP-CPM", "LBS-", "LBA-",
              "LBU-", "PP-LBB", "4862"]


def coll_of(obj):
    cs = [c.name for c in obj.users_collection]
    for c in cs:
        if c.startswith("CAD_"):
            return c
    return cs[0] if cs else ""


def is_struct(obj):
    c = coll_of(obj)
    if c in ("CAD_skid", "CAD_bale", "CAD_controller"):
        return True
    if c == "CAD_pump":
        n = obj.name
        return any(p.lower() in n.lower() for p in STRUCT_PAT)
    return False


def eval_mesh(obj):
    ev = obj.evaluated_get(DG)
    return ev, ev.to_mesh()


def world_of(obj, me):
    n = len(me.vertices)
    co = np.empty(n * 3, dtype=np.float64)
    me.vertices.foreach_get("co", co)
    co = co.reshape(n, 3)
    mw = np.array(obj.matrix_world, dtype=np.float64)
    return (co @ mw[:3, :3].T + mw[:3, 3]) * MM


def bbox(w):
    return ([float(w[:, 0].min()), float(w[:, 1].min()), float(w[:, 2].min())],
            [float(w[:, 0].max()), float(w[:, 1].max()), float(w[:, 2].max())])


def tri_of(me):
    try:
        me.calc_loop_triangles()
        nt = len(me.loop_triangles)
        if nt == 0:
            return np.zeros((0, 3), dtype=np.int32)
        t = np.empty(nt * 3, dtype=np.int32)
        me.loop_triangles.foreach_get("vertices", t)
        return t.reshape(nt, 3)
    except Exception as e:
        log("tri_of failed:", e)
        return np.zeros((0, 3), dtype=np.int32)


def comps(nv, edges):
    parent = np.arange(nv, dtype=np.int64)
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for a, b in edges:
        ra, rb = find(int(a)), find(int(b))
        if ra != rb:
            parent[rb] = ra
    roots = {}
    for i in range(nv):
        r = find(i)
        roots[r] = roots.get(r, 0) + 1
    sz = sorted(roots.values(), reverse=True)
    return len(sz), sz[:12]


def topo(me):
    ne = len(me.edges)
    nl = len(me.loops)
    out = {"verts": len(me.vertices), "edges": ne, "polys": len(me.polygons), "loops": nl}
    if ne:
        e = np.empty(ne * 2, dtype=np.int32)
        me.edges.foreach_get("vertices", e)
        e = e.reshape(ne, 2)
        le = np.empty(nl, dtype=np.int32)
        me.loops.foreach_get("edge_index", le)
        cnt = np.bincount(le, minlength=ne)
        out["boundary_edges"] = int(np.count_nonzero(cnt == 1))
        out["nonmanifold_edges"] = int(np.count_nonzero(cnt > 2))
        out["wire_edges"] = int(np.count_nonzero(cnt == 0))
        out["closed_manifold"] = bool(out["boundary_edges"] == 0 and out["nonmanifold_edges"] == 0)
        if ne <= 400000:
            nc, sizes = comps(len(me.vertices), e)
            out["components"] = nc
            out["component_sizes_top12"] = sizes
        else:
            out["components"] = None
            out["components_note"] = "skipped (edges %d > 400000 cap)" % ne
    return out


def face_x_ranges(me, w):
    npoly = len(me.polygons)
    if npoly == 0:
        return None, None, None
    lstart = np.empty(npoly, dtype=np.int64)
    me.polygons.foreach_get("loop_start", lstart)
    loops = np.empty(len(me.loops), dtype=np.int32)
    me.loops.foreach_get("vertex_index", loops)
    fx = w[loops, 0]
    pmn = np.minimum.reduceat(fx, lstart)
    pmx = np.maximum.reduceat(fx, lstart)
    # WORLD-space face normal from the first three loops (object normals are
    # useless: several of these parts carry rotated matrices).
    lw = w[loops]
    tot = np.empty(npoly, dtype=np.int64)
    me.polygons.foreach_get("loop_total", tot)
    ok = tot >= 3
    nrm = np.zeros((npoly, 3))
    if ok.any():
        s = lstart[ok]
        p0, p1, p2 = lw[s], lw[s + 1], lw[s + 2]
        v = np.cross(p1 - p0, p2 - p0)
        vn = np.linalg.norm(v, axis=1)
        nrm[ok] = v / np.where(vn > 0, vn, 1)[:, None]
    return pmn, pmx, nrm


def x_bands(me, w, xmin, xmax, min_gap=12.0, binw=1.0):
    """Empty X runs (containing no vertices) + straight-prism check."""
    span = xmax - xmin
    if span < 2 * min_gap:
        return []
    nb = int(math.ceil(span / binw)) + 1
    idx = ((w[:, 0] - xmin) / binw).astype(np.int64)
    np.clip(idx, 0, nb - 1, out=idx)
    occ = np.bincount(idx, minlength=nb) > 0
    lo = xmin + 0.05 * span
    hi = xmax - 0.05 * span
    runs = []
    i = 0
    while i < nb:
        if occ[i]:
            i += 1
            continue
        j = i
        while j < nb and not occ[j]:
            j += 1
        a = max(xmin + i * binw, lo)
        b = min(xmin + j * binw, hi)
        if (b - a) >= min_gap:
            runs.append((a, b))
        i = j
    return runs


def curved_edge_x(me, w):
    """X positions of tessellation facet-boundary edges, i.e. the edges that only
    exist where a surface is curved (hole walls, fillets, rounds).  Flat chamfers
    (dihedral > 60 deg) are excluded.  Robust on any tessellated solid and needs
    no fitted axes; a drilled hole or fastener bore MUST produce these."""
    npoly = len(me.polygons)
    nl = len(me.loops)
    if npoly == 0 or nl == 0:
        return np.zeros(0), np.zeros(0)
    nrm = np.empty(npoly * 3)
    me.polygons.foreach_get("normal", nrm)
    nrm = nrm.reshape(-1, 3)
    nn = np.linalg.norm(nrm, axis=1)
    nrm = nrm / np.where(nn > 0, nn, 1)[:, None]
    ltot = np.empty(npoly, dtype=np.int32)
    me.polygons.foreach_get("loop_total", ltot)
    le = np.empty(nl, dtype=np.int32)
    me.loops.foreach_get("edge_index", le)
    lv = np.empty(nl, dtype=np.int32)
    me.loops.foreach_get("vertex_index", lv)
    pol_of_loop = np.repeat(np.arange(npoly), ltot)
    order = np.argsort(le, kind="stable")
    le_s = le[order]
    first = np.flatnonzero(np.r_[True, le_s[1:] != le_s[:-1]])
    counts = np.diff(np.r_[first, nl])
    two = np.flatnonzero(counts == 2)
    if not len(two):
        return np.zeros(0), np.zeros(0)
    i0 = first[two]
    a = order[i0]
    b = order[i0 + 1]
    cos = (nrm[pol_of_loop[a]] * nrm[pol_of_loop[b]]).sum(1)
    smooth = (cos > 0.5) & (cos < 0.9986)
    sel = two[smooth]
    if not len(sel):
        return np.zeros(0), np.zeros(0)
    i0 = first[sel]
    a = order[i0]
    b = order[i0 + 1]
    ex = 0.5 * (w[lv[a], 0] + w[lv[b], 0])
    span = np.abs(w[lv[a], 0] - w[lv[b], 0])
    return ex, span


def analyse_struct(obj):
    ev, me = eval_mesh(obj)
    try:
        w = world_of(obj, me)
        mn, mx = bbox(w)
        tri = tri_of(me)
        r = {
            "name": obj.name, "collection": coll_of(obj),
            "matrix_world": [[float(v) for v in row] for row in obj.matrix_world],
            "loc": [float(v) for v in obj.matrix_world.translation],
            "loc_mm": [float(v) * MM for v in obj.matrix_world.translation],
            "bbox_min": mn, "bbox_max": mx,
            "size": [mx[k] - mn[k] for k in range(3)],
            "verts": len(me.vertices), "polys": len(me.polygons),
            "tris": int(len(tri)),
            "centroid": [float(w[:, k].mean()) for k in range(3)],
            "topo": topo(me),
        }
        if (mx[0] - mn[0]) > 60:
            pmn, pmx, nrm = face_x_ranges(me, w)
            cex, cspan = curved_edge_x(me, w)
            tr = cspan <= 5.0            # transverse edge -> a LOCAL feature at that X
            r["curved_edges_total"] = int(len(cex))
            r["curved_edges_transverse"] = int(np.count_nonzero(tr))
            r["curved_edges_longitudinal"] = int(np.count_nonzero(~tr))
            ctx = cex[tr]                # X of transverse (hole/fillet/boss) features
            if len(ctx):
                r["curved_feature_X_positions"] = [round(float(x), 1)
                                                   for x in np.unique(np.round(ctx, 0))][:60]
            gaps = []
            if pmn is not None:
                for a, b in x_bands(me, w, mn[0], mx[0]):
                    m = (pmn <= a) & (pmx >= b)
                    cross_n = int(m.sum())
                    cross_x = int(np.count_nonzero(np.abs(nrm[m, 0]) > 0.05)) if cross_n else 0
                    inband = int(np.count_nonzero((ctx >= a) & (ctx <= b))) if len(ctx) else 0
                    gaps.append({"from": round(a, 2), "to": round(b, 2),
                                 "len": round(b - a, 2),
                                 "spanning_faces": cross_n,
                                 "spanning_faces_with_X_normal": cross_x,
                                 "local_features_inside": inband})
            r["x_gaps"] = gaps
            r["feature_free_bands"] = [g for g in gaps if g["local_features_inside"] == 0]
        return r
    finally:
        ev.to_mesh_clear()


def cylinders(obj, me, w, axis_names=(0, 1, 2), cell=4.0, min_faces=8):
    """Coarse bore detector: faces whose normal is perpendicular to a candidate
    axis, clustered in the plane perpendicular to that axis, fitted as a ring.
    Detects bores with axis near X, Y or Z only -- label as such."""
    npoly = len(me.polygons)
    if npoly < min_faces:
        return []
    nrm = np.empty(npoly * 3, dtype=np.float64)
    me.polygons.foreach_get("normal", nrm)
    nrm = nrm.reshape(-1, 3)
    cen = np.empty(npoly * 3, dtype=np.float64)
    me.polygons.foreach_get("center", cen)
    cen = cen.reshape(-1, 3)
    mw = np.array(obj.matrix_world, dtype=np.float64)
    R = mw[:3, :3]
    cen = cen @ R.T + mw[:3, 3]
    nrm = nrm @ R.T
    nn = np.linalg.norm(nrm, axis=1)
    nrm = nrm / np.where(nn > 0, nn, 1)[:, None]
    out = []
    for ax in axis_names:
        sel = np.abs(nrm[:, ax]) < 0.20
        if sel.sum() < min_faces:
            continue
        idx = np.nonzero(sel)[0]
        u = (ax + 1) % 3
        v = (ax + 2) % 3
        key = np.stack([np.floor(cen[idx, u] / cell), np.floor(cen[idx, v] / cell)], 1)
        _, inv = np.unique(key, axis=0, return_inverse=True)
        if int(inv.max()) + 1 > 40000:
            continue
        for g in range(int(inv.max()) + 1):
            m = idx[inv == g]
            if len(m) < min_faces:
                continue
            pu = cen[m, u] - cen[m, u].mean()
            pv = cen[m, v] - cen[m, v].mean()
            rad = np.sqrt(pu ** 2 + pv ** 2)
            rm = float(rad.mean())
            if rm < 2 or rm > 200 or rad.std() / max(rm, 1e-6) > 0.20:
                continue
            ang = np.sort(np.arctan2(pv, pu))
            if ang[-1] - ang[0] < math.radians(150):
                continue
            ctr = cen[m].mean(0)
            out.append({"axis": "XYZ"[ax],
                        "centre": [round(float(x), 1) for x in ctr],
                        "radius_mm": round(rm, 2), "faces": int(len(m)),
                        "axis_span_mm": round(float(cen[m, ax].max() - cen[m, ax].min()), 2)})
    ded = []
    for c in sorted(out, key=lambda d: (d["axis"], d["centre"][0], d["centre"][1])):
        if not any(d["axis"] == c["axis"] and
                   all(abs(d["centre"][k] - c["centre"][k]) < 6 for k in range(3)) for d in ded):
            ded.append(c)
    return ded


# ---------------------------------------------------------------- inventory
log("Blender", bpy.app.version_string, "| file", SRC_BLEND)
objects = []
coll_agg = {}
scene_lo = [1e18] * 3
scene_hi = [-1e18] * 3

for obj in bpy.data.objects:
    if obj.type != "MESH":
        continue
    bb = np.array([list(c) for c in obj.bound_box], dtype=np.float64)
    wbb = (bb @ np.array(obj.matrix_world)[:3, :3].T + np.array(obj.matrix_world)[:3, 3]) * MM
    mn = [float(x) for x in wbb.min(0)]
    mx = [float(x) for x in wbb.max(0)]
    mw = obj.matrix_world
    rec = {"name": obj.name, "collection": coll_of(obj),
           "parent": obj.parent.name if obj.parent else None,
           "loc": [float(mw[0][3]), float(mw[1][3]), float(mw[2][3])],
           "loc_mm": [float(mw[0][3]) * MM, float(mw[1][3]) * MM, float(mw[2][3]) * MM],
           "matrix_world": [[float(mw[r][c]) for c in range(4)] for r in range(4)],
           "bbox_min": mn, "bbox_max": mx,
           "size": [mx[k] - mn[k] for k in range(3)],
           "verts": len(obj.data.vertices), "polys": len(obj.data.polygons),
           "struct": is_struct(obj)}
    objects.append(rec)
    c = rec["collection"]
    a = coll_agg.setdefault(c, {"n": 0, "polys": 0, "lo": [1e18] * 3, "hi": [-1e18] * 3})
    a["n"] += 1
    a["polys"] += rec["polys"]
    for k in range(3):
        a["lo"][k] = min(a["lo"][k], mn[k])
        a["hi"][k] = max(a["hi"][k], mx[k])
        scene_lo[k] = min(scene_lo[k], mn[k])
        scene_hi[k] = max(scene_hi[k], mx[k])

log("objects:", len(objects), "colls:", {k: v["n"] for k, v in coll_agg.items()})

# ------------------------------------------------- structural detailed pass
struct = []
for obj in bpy.data.objects:
    if obj.type != "MESH" or not is_struct(obj):
        continue
    try:
        struct.append(analyse_struct(obj))
    except Exception as e:
        log("struct fail", obj.name, repr(e))
        struct.append({"name": obj.name, "error": repr(e)})
log("structural parts:", len(struct))

bore_targets = sorted([r for r in struct if "error" not in r],
                      key=lambda r: -r.get("polys", 0))[:12]
for r in bore_targets:
    obj = bpy.data.objects.get(r["name"])
    if not obj:
        continue
    try:
        ev, me = eval_mesh(obj)
        try:
            r["bores"] = cylinders(obj, me, world_of(obj, me))
        finally:
            ev.to_mesh_clear()
    except Exception as e:
        log("bore fail", r["name"], repr(e))
        r["bores_error"] = repr(e)
log("bore scan done on", len(bore_targets), "parts")

# ---------------------------------------------------------------- centrelines
skid = [r for r in struct if r.get("collection") == "CAD_skid" and "error" not in r]
skid_lo = min((r["bbox_min"][0] for r in skid), default=None)
skid_hi = max((r["bbox_max"][0] for r in skid), default=None)
skid_cx = (skid_lo + skid_hi) / 2.0 if skid_lo is not None else None

eng = [r for r in objects if r["collection"] == "CAD_engine"]
eng_lo = min((r["bbox_min"][k] for r in eng for k in [0]), default=None)
eng_hi = max((r["bbox_max"][k] for r in eng for k in [0]), default=None)
eng_cx = (eng_lo + eng_hi) / 2.0 if eng_lo is not None else None
eng_bmin = [min(r["bbox_min"][k] for r in eng) for k in range(3)] if eng else None
eng_bmax = [max(r["bbox_max"][k] for r in eng) for k in range(3)] if eng else None
log("skid centre X =", skid_cx, " engine centre X =", eng_cx)

# Widening datum = centre of the two bale uprights = the skid side-rail
# centreline (~+59 mm).  Kept deliberately separate from the engine centre.
bal_all = [r for r in struct if r.get("collection") == "CAD_bale" and "bbox_min" in r]
_up_c = sorted(((r["bbox_min"][0] + r["bbox_max"][0]) / 2.0, r["name"])
               for r in bal_all if r["size"][2] > 1500)
datum_x = (_up_c[0][0] + _up_c[-1][0]) / 2.0 if len(_up_c) >= 2 else skid_cx
log("widening datum X =", round(datum_x, 3), "mm  (skid agg centre", round(skid_cx, 3) if skid_cx else None, ")")

for r in struct:
    if "bbox_min" not in r or datum_x is None:
        continue
    mn, mx = r["bbox_min"], r["bbox_max"]
    if mx[0] < datum_x - 1:
        r["side"] = "minus_X_outboard"
    elif mn[0] > datum_x + 1:
        r["side"] = "plus_X_outboard"
    else:
        r["side"] = "spans_centreline"

# --- per-part widening action.  Side-structure inner faces are taken from the
# long Y-running rails so that inboard deck plates are NOT swept outwards.
def _rail_face(minus):
    best = None
    for r in struct:
        if "bbox_min" not in r or r.get("collection") not in ("CAD_skid", "CAD_pump"):
            continue
        if r["size"][1] < 1000:
            continue
        v = r["bbox_max"][0] if minus else r["bbox_min"][0]
        if minus and v < datum_x - 50:
            best = v if best is None else max(best, v)
        if (not minus) and v > datum_x + 50:
            best = v if best is None else min(best, v)
    return best

MINUS_RAIL_FACE = _rail_face(True)
PLUS_RAIL_FACE = _rail_face(False)
log("side-structure inner faces: minus", MINUS_RAIL_FACE, " plus", PLUS_RAIL_FACE)

for r in struct:
    if "bbox_min" not in r:
        continue
    mn, mx = r["bbox_min"], r["bbox_max"]
    coll = r.get("collection")
    if coll == "CAD_controller":
        r["action"] = "translate_X_-76.2 (rigid, with minus bale upright)"
    elif mn[0] <= MINUS_RAIL_FACE and mx[0] >= PLUS_RAIL_FACE:
        # X-spanning member: crosses BOTH side-structure inner faces, so it has to
        # grow at both ends.  This test MUST precede the CAD_bale test -- the bale
        # top cross beam (LBA-CB) is a bridging member that touches both uprights,
        # and rigidly translating it would break its minus-side joint.
        r["action"] = "extend_ends_+76.2_each (X-spanning member)"
        if coll == "CAD_bale":
            r["action_note"] = ("CAD_bale part that spans BOTH uprights (bridging "
                                "member): extend both ends; do NOT rigid-translate")
    elif coll == "CAD_bale":
        r["action"] = ("translate_X_-76.2 (rigid, minus upright group)"
                       if mx[0] < datum_x else "translate_X_+76.2 (rigid, plus upright group)")
    elif mx[0] <= MINUS_RAIL_FACE + 1.0:
        r["action"] = "translate_X_-76.2 (minus side structure)"
    elif mn[0] >= PLUS_RAIL_FACE - 1.0:
        r["action"] = "translate_X_+76.2 (plus side structure)"
    else:
        r["action"] = "STAY (inboard / engine-mounted; not skid side structure)"


# ---------------------------------------------------------------- clearance
bal = [r for r in struct if r.get("collection") == "CAD_bale" and "error" not in r]
uprights = [r["name"] for r in sorted(bal, key=lambda s: s["bbox_min"][0]) if r["size"][2] > 1500]
if not uprights:
    uprights = [r["name"] for r in sorted(bal, key=lambda s: s["bbox_min"][0])
                if r["name"].startswith("LBU")]
log("uprights:", uprights)

engine_objs = [o for o in bpy.data.objects if o.type == "MESH" and coll_of(o) == "CAD_engine"]
clear = {"uprights": [], "engine_objects": [o.name for o in engine_objs],
         "engine_bbox_min": eng_bmin, "engine_bbox_max": eng_bmax,
         "note": "AABB overlap is NOT a collision; triangle_intersections is the "
                 "authoritative overlap test; min_distance is a sampled bound."}

E_v, E_t, E_obj_of_tri = [], [], []
off = 0
for o in engine_objs:
    ev, me = eval_mesh(o)
    try:
        w = world_of(o, me)
        t = tri_of(me)
        E_v.append(w)
        E_t.append(t + off)
        E_obj_of_tri.append((o.name, off, off + len(w)))
        off += len(w)
    finally:
        ev.to_mesh_clear()
AV = np.concatenate(E_v, 0).astype(np.float32) if E_v else np.zeros((0, 3), np.float32)
AT = np.concatenate(E_t, 0).astype(np.int32) if E_t else np.zeros((0, 3), np.int32)
log("engine verts", len(AV), "tris", len(AT))
if len(AT):
    ATMN = np.minimum(np.minimum(AV[AT[:, 0]], AV[AT[:, 1]]), AV[AT[:, 2]])
    ATMX = np.maximum(np.maximum(AV[AT[:, 0]], AV[AT[:, 1]]), AV[AT[:, 2]])
else:
    ATMN = np.zeros((0, 3), np.float32)
    ATMX = np.zeros((0, 3), np.float32)

def nearest_obj_name(gidx):
    for nm, a, b in E_obj_of_tri:
        if a <= gidx < b:
            return nm
    return None

MARGINS = [400.0, 250.0, 150.0, 100.0]
ROI_TRI_CAP = 350000
for uname in uprights:
    uo = bpy.data.objects.get(uname)
    if not uo:
        continue
    ev, me = eval_mesh(uo)
    try:
        uw = world_of(uo, me)
        ut = tri_of(me)
        umn, umx = bbox(uw)
        rec = {"name": uname, "bbox_min": umn, "bbox_max": umx,
               "verts": len(uw), "tris": int(len(ut)),
               "sampling": "upright vertices + edge midpoints -> engine BVH"}
        rec["engine_aabb_overlap"] = bool(
            eng_bmin is not None and umn[0] <= eng_bmax[0] and umx[0] >= eng_bmin[0] and
            umn[1] <= eng_bmax[1] and umx[1] >= eng_bmin[1] and
            umn[2] <= eng_bmax[2] and umx[2] >= eng_bmin[2])
        # --- X-slab clearance inside the upright's (conservative) YZ window.
        # Valid LOWER bound on the true 3D separation: the window is the upright
        # bbox so it can only admit more engine geometry, never less.
        if len(AT):
            win = ((ATMX[:, 1] > umn[1]) & (ATMN[:, 1] < umx[1]) &
                   (ATMX[:, 2] > umn[2]) & (ATMN[:, 2] < umx[2]))
            idxs = np.nonzero(win)[0]
            Xo, Xi = umn[0], umx[0]
            rec["engine_tris_in_yz_window"] = int(len(idxs))
            if len(idxs):
                smin = ATMN[idxs, 0]
                smax = ATMX[idxs, 0]
                rec["engine_X_min_in_window_mm"] = round(float(smin.min()), 2)
                rec["engine_X_max_in_window_mm"] = round(float(smax.max()), 2)
                uc = 0.5 * (umn[0] + umx[0])
                if uc > datum_x:            # +X upright: engine lies on its -X side
                    inner, outer = umn[0], umx[0]
                    inb, outb = (smax <= inner), (smin >= outer)
                    if inb.any():
                        k = int(idxs[inb][np.argmax(smax[inb])])
                        rec["x_slab_gap_engine_side_mm"] = round(float(inner - ATMX[k, 0]), 2)
                        rec["x_slab_feature_engine_side"] = {
                            "engine_object": nearest_obj_name(int(AT[k, 0])),
                            "X_mm": round(float(AV[AT[k]].mean(0)[0]), 1),
                            "Y_mm": round(float(AV[AT[k]].mean(0)[1]), 1),
                            "Z_mm": round(float(AV[AT[k]].mean(0)[2]), 1)}
                    if outb.any():
                        k = int(idxs[outb][np.argmin(smin[outb])])
                        rec["x_slab_gap_far_side_mm"] = round(float(ATMN[k, 0] - outer), 2)
                else:                        # -X upright: engine lies on its +X side
                    inner, outer = umx[0], umn[0]
                    inb, outb = (smin >= inner), (smax <= outer)
                    if inb.any():
                        k = int(idxs[inb][np.argmin(smin[inb])])
                        rec["x_slab_gap_engine_side_mm"] = round(float(ATMN[k, 0] - inner), 2)
                        rec["x_slab_feature_engine_side"] = {
                            "engine_object": nearest_obj_name(int(AT[k, 0])),
                            "X_mm": round(float(AV[AT[k]].mean(0)[0]), 1),
                            "Y_mm": round(float(AV[AT[k]].mean(0)[1]), 1),
                            "Z_mm": round(float(AV[AT[k]].mean(0)[2]), 1)}
                    if outb.any():
                        k = int(idxs[outb][np.argmax(smax[outb])])
                        rec["x_slab_gap_far_side_mm"] = round(float(outer - ATMX[k, 0]), 2)
                rec["inner_face_X_mm"] = round(float(inner), 2)
                rec["outer_face_X_mm"] = round(float(outer), 2)
                # engine X envelope vs height, inside the upright's YZ window
                zb = 100.0
                z0 = math.floor(umn[2] / zb) * zb
                prof = []
                for zz in range(int((umx[2] - z0) // zb) + 1):
                    zlo, zhi = z0 + zz * zb, z0 + (zz + 1) * zb
                    if zhi < umn[2] or zlo > umx[2]:
                        continue
                    sel = win & (ATMN[:, 2] < zhi) & (ATMX[:, 2] > zlo)
                    if not sel.any():
                        continue
                    ii = np.nonzero(sel)[0]
                    prof.append([round(float(zlo), 0), round(float(zhi), 0),
                                 round(float(ATMN[ii, 0].min()), 1),
                                 round(float(ATMX[ii, 0].max()), 1)])
                rec["engine_X_envelope_by_Z_100mm"] = prof
                # tighter lower bound: restrict the engine window to the upright's
                # ACTUAL Y extent inside each 50 mm Z band (the upright tapers, so
                # the bbox window above is conservative and loose).
                tight = None
                zt, yt = uw[:, 2], uw[:, 1]
                nb = max(1, int((umx[2] - umn[2]) // 50) + 1)
                for zz in range(nb):
                    a, b = umn[2] + zz * 50.0, umn[2] + (zz + 1) * 50.0
                    m = (zt >= a) & (zt < b)
                    if not m.any():
                        continue
                    ylo, yhi = float(yt[m].min()), float(yt[m].max())
                    sel = ((ATMN[:, 2] < b) & (ATMX[:, 2] > a) &
                           (ATMN[:, 1] < yhi) & (ATMX[:, 1] > ylo))
                    if not sel.any():
                        continue
                    ii = np.nonzero(sel)[0]
                    if uc > datum_x:
                        sm = ATMX[ii, 0]
                        inb = sm <= inner
                        if not inb.any():
                            continue
                        g = float(inner - sm[inb].max())
                    else:
                        sm = ATMN[ii, 0]
                        inb = sm >= inner
                        if not inb.any():
                            continue
                        g = float(sm[inb].min() - inner)
                    if tight is None or g < tight[0]:
                        tight = (g, round(a, 0), round(b, 0), round(ylo, 1), round(yhi, 1))
                if tight is not None:
                    rec["x_slab_gap_tight_mm"] = round(tight[0], 2)
                    rec["x_slab_gap_tight_band"] = {
                        "Z_mm": [tight[1], tight[2]], "upright_Y_mm": [tight[3], tight[4]]}
                    rec["tight_vs_sampled_note"] = (
                        "tight slab (upright's own Y extent per 50 mm Z band) is a "
                        "stronger LOWER bound than the bbox-window value")
                rec["x_slab_method"] = ("engine tri AABB vs the upright's full YZ bbox -> "
                                        "LOWER bound on true 3D separation")
        sub = np.zeros((0, 3), dtype=np.int32)
        margin = MARGINS[-1]
        for MARGIN in MARGINS:
            lo = np.array([umn[0] - MARGIN, umn[1] - MARGIN, umn[2] - MARGIN])
            hi = np.array([umx[0] + MARGIN, umx[1] + MARGIN, umx[2] + MARGIN])
            if len(AT):
                mask = np.all(ATMX > lo, 1) & np.all(ATMN < hi, 1)
                sub = AT[mask]
            else:
                sub = np.zeros((0, 3), dtype=np.int32)
            margin = MARGIN
            if len(sub) <= ROI_TRI_CAP:
                break
        rec["engine_tris_in_roi"] = int(len(sub))
        rec["roi_margin_mm"] = margin
        log(uname, "ROI tris", len(sub))
        ubvh = BVHTree.FromPolygons([(float(p[0]), float(p[1]), float(p[2])) for p in uw],
                                    [(int(t[0]), int(t[1]), int(t[2])) for t in ut])
        rec["triangle_intersections"] = 0
        rec["min_distance_mm"] = None
        if len(sub):
            used, inv = np.unique(sub.reshape(-1), return_inverse=True)
            vsub = AV[used]
            polys = inv.reshape(-1, 3)
            ebvh = BVHTree.FromPolygons([(float(p[0]), float(p[1]), float(p[2])) for p in vsub],
                                        [(int(t[0]), int(t[1]), int(t[2])) for t in polys])
            ov = ubvh.overlap(ebvh)
            rec["triangle_intersections"] = int(len(ov))
            pts = uw
            ne = len(me.edges)
            if ne:
                e = np.empty(ne * 2, dtype=np.int32)
                me.edges.foreach_get("vertices", e)
                e = e.reshape(ne, 2)
                pts = np.concatenate([pts, 0.5 * (uw[e[:, 0]] + uw[e[:, 1]])], 0)
            if len(pts) > 60000:
                pts = pts[np.linspace(0, len(pts) - 1, 60000).astype(int)]
            dmin, dloc, dsrc, dgidx = 1e18, None, None, None
            for pv in pts:
                loc, n, i, d = ebvh.find_nearest(
                    Vector((float(pv[0]), float(pv[1]), float(pv[2]))), 5000.0)
                if loc is not None and d < dmin:
                    dmin = d
                    dloc = [float(loc[0]), float(loc[1]), float(loc[2])]
                    dsrc = [float(pv[0]), float(pv[1]), float(pv[2])]
                    dgidx = int(used[polys[i][0]]) if i is not None else None
            # reverse: engine ROI vertices -> upright BVH (tightens the bound)
            _vi = np.linspace(0, len(vsub) - 1, min(len(vsub), 40000)).astype(int)
            for k, pv in enumerate(vsub[_vi]):
                loc, n, i, d = ubvh.find_nearest(
                    Vector((float(pv[0]), float(pv[1]), float(pv[2]))), 5000.0)
                if loc is not None and d < dmin:
                    dmin = d
                    dloc = [float(pv[0]), float(pv[1]), float(pv[2])]
                    dsrc = [float(loc[0]), float(loc[1]), float(loc[2])]
                    dgidx = int(used[_vi[k]])
            if dmin < 1e17:
                rec["min_distance_mm"] = round(float(dmin), 3)
                rec["min_distance_method"] = (
                    "sampled point-to-triangle BVH query BOTH directions "
                    "(upright verts+edge-midpoints -> engine BVH, engine ROI verts -> "
                    "upright BVH); this is an UPPER bound on the true separation, not exact")
                rec["closest_point_on_upright"] = [round(v, 2) for v in dsrc]
                rec["closest_point_on_engine"] = [round(v, 2) for v in dloc]
                rec["nearest_engine_object"] = nearest_obj_name(dgidx) if dgidx is not None else None
                rec["expected_clearance_after_76_2mm"] = round(float(dmin) + 76.2, 3)
            # close-feature band: points within dmin+150
            band = []
            _step = max(1, len(pts) // 8000)
            for pv in pts[::_step]:
                loc, n, i, d = ebvh.find_nearest(
                    Vector((float(pv[0]), float(pv[1]), float(pv[2]))), dmin + 200.0)
                if loc is not None and d <= dmin + 150.0:
                    band.append((float(pv[2]), float(pv[1]), float(d)))
            if band:
                rec["close_band_Z_mm"] = [round(min(b[0] for b in band), 1),
                                          round(max(b[0] for b in band), 1)]
                rec["close_band_Y_mm"] = [round(min(b[1] for b in band), 1),
                                          round(max(b[1] for b in band), 1)]
                rec["close_band_points"] = len(band)
        clear["uprights"].append(rec)
    except Exception as e:
        log("clearance fail", uname, repr(e))
        clear["uprights"].append({"name": uname, "error": repr(e)})
    finally:
        ev.to_mesh_clear()


# ---------------------------------------------------------------- controller
ctrl = [r for r in struct if r.get("collection") == "CAD_controller" and "error" not in r]
cctrl = {"parts": [{"name": r["name"], "bbox_min": r["bbox_min"], "bbox_max": r["bbox_max"],
                    "loc": r["loc"], "size": r["size"]} for r in ctrl],
         "required_rigid_delta_X_mm": -76.2,
         "note": "whole group must translate -76.2 mm with the minus-X upright; "
                 "no re-orientation, attachment face relationship preserved"}
if ctrl:
    cctrl["group_bbox"] = [[min(r["bbox_min"][k] for r in ctrl) for k in range(3)],
                           [max(r["bbox_max"][k] for r in ctrl) for k in range(3)]]
    if uprights:
        ur = next((r for r in struct if r["name"] == uprights[0]), None)
        if ur:
            cctrl["gap_to_minus_upright_engine_face_mm"] = round(
                ur["bbox_max"][0] - cctrl["group_bbox"][1][0], 2)
clear["controller"] = cctrl

# ---------------------------------------------------------------- mating
from mathutils.kdtree import KDTree

def subsample(w, n=1200):
    if len(w) <= n:
        return w
    return w[np.linspace(0, len(w) - 1, n).astype(int)]

# build one world-space BVH per structural part (small meshes) so proximity is
# SURFACE-to-surface, not vertex-to-vertex
part_bvh = {}
part_pts = {}
for r in struct:
    if "bbox_min" not in r:
        continue
    try:
        o = bpy.data.objects.get(r["name"])
        ev, me = eval_mesh(o)
        try:
            w = world_of(o, me)
            t = tri_of(me)
            if len(t):
                part_bvh[r["name"]] = BVHTree.FromPolygons(
                    [(float(p[0]), float(p[1]), float(p[2])) for p in w],
                    [(int(x[0]), int(x[1]), int(x[2])) for x in t])
                part_pts[r["name"]] = subsample(w)
        finally:
            ev.to_mesh_clear()
    except Exception as e:
        log("bvh fail", r["name"], repr(e))

mates = []
srec = [r for r in struct if r["name"] in part_bvh]
for i in range(len(srec)):
    for j in range(i + 1, len(srec)):
        A, B = srec[i], srec[j]
        gap = max(max(A["bbox_min"][k], B["bbox_min"][k]) -
                  min(A["bbox_max"][k], B["bbox_max"][k]) for k in range(3))
        if gap > 3.0:
            continue
        try:
            d = 1e18
            for p in part_pts[A["name"]]:
                loc, n, idx, dd = part_bvh[B["name"]].find_nearest(
                    Vector((float(p[0]), float(p[1]), float(p[2]))), 60.0)
                if loc is not None and dd < d:
                    d = dd
            for p in part_pts[B["name"]]:
                loc, n, idx, dd = part_bvh[A["name"]].find_nearest(
                    Vector((float(p[0]), float(p[1]), float(p[2]))), 60.0)
                if loc is not None and dd < d:
                    d = dd
            if d < 1.0:
                mates.append({"a": A["name"], "b": B["name"],
                              "surface_proximity_mm": round(float(d), 3),
                              "a_side": A.get("side"), "b_side": B.get("side")})
        except Exception as e:
            log("mate fail", A["name"], B["name"], repr(e))
mates.sort(key=lambda m: m["surface_proximity_mm"])
log("surface-mating pairs (<1 mm):", len(mates))

# ---------------------------------------------------------------- write
result = {
    "meta": {
        "script": "tools/astra_inspect_widening.py",
        "source_blend": SRC_BLEND,
        "source_sha256": SRC_HASH,
        "blender": bpy.app.version_string,
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "duration_s": round(time.time() - T0, 1),
        "scene_to_mm": MM,
        "units_note": "v10 is authored in metres; all bbox/geometry values below "
                      "are MILLIMETRES (scene units x %g). Raw matrices are scene units." % MM,
        "scene_bbox_min": [round(v, 2) for v in scene_lo],
        "scene_bbox_max": [round(v, 2) for v in scene_hi],
        "assembly_width_mm_before": round(scene_hi[0] - scene_lo[0], 2),
        "assembly_width_mm_target": round(scene_hi[0] - scene_lo[0] + 152.4, 2),
        "blend_saved": False,
        "read_only": True,
    },
    "centrelines": {"widening_datum_X_mm": round(datum_x, 3) if datum_x is not None else None,
                    "skid_aggregate_centre_X_mm": round(skid_cx, 3) if skid_cx is not None else None,
                    "engine_centre_X_mm": round(eng_cx, 3) if eng_cx is not None else None,
                    "note": "widening_datum = centre of the two bale uprights (~+59 mm). "
                            "skid aggregate centre differs (deck/end-rail pieces sit on ~0). "
                            "Do NOT average the three."},
    "collections": {k: {"n": v["n"], "polys": v["polys"],
                        "bbox_min": [round(x, 2) for x in v["lo"]],
                        "bbox_max": [round(x, 2) for x in v["hi"]]}
                    for k, v in coll_agg.items()},
    "objects": objects,
    "structure": struct,
    "clearance": clear,
    "mating_pairs": mates,
}
os.makedirs(os.path.dirname(OUT_JSON) or ".", exist_ok=True)
with open(OUT_JSON, "w", encoding="utf-8") as f:
    json.dump(result, f, indent=1)
log("WROTE", OUT_JSON, os.path.getsize(OUT_JSON), "bytes")
log("DONE in %.1fs" % (time.time() - T0))
