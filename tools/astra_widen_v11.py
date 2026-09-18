"""astra_widen_v11.py -- implement Astra's widening strategy on
out/engine-and-pump-v10.blend and save out/engine-and-pump-v11-wide.blend.

Strategy (Astra-owned; see ASTRA-WIDENING-PLAN-2026-09-18.md and
ASTRA-WIDENING-DOUBLER-DECISION.md):
  * 23 rigid world-X translations by +/-76.2 mm (20 outboard skid/bale parts
    + the 3 controller meshes, which follow the minus-X upright as one group),
  * 17 lengthened X-spanning members: vertices left of the minus cut plane move
    -76.2 mm, vertices right of the plus cut plane move +76.2 mm, the central
    band is untouched (nominal planes -680/+798 mm; DOUBLER pair -665/+665 mm),
  * 428 meshes entirely fixed (all CAD_pump_new, all CAD_engine, the central
    mount plates and the four PP128S22-MFB end mid-brackets).

Run:
  blender -b -noaudio --threads 4 out/engine-and-pump-v10.blend \
     --python-exit-code 1 --python tools/astra_widen_v11.py -- \
     reports/astra-widening-v11.json out/engine-and-pump-v11-wide.blend <sha256>
"""
import bpy, sys, os, json, math, time, hashlib
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

T0 = time.time()
def log(*a): print("[widen %6.1fs]" % (time.time() - T0), *a, flush=True)

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT_JSON = argv[0] if argv else "reports/astra-widening-v11.json"
SAVE_BLEND = argv[1] if len(argv) > 1 else "out/engine-and-pump-v11-wide.blend"
EXPECT_SHA = argv[2] if len(argv) > 2 else ""
DRY = "--dry" in argv
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAVE_ABS = SAVE_BLEND if os.path.isabs(SAVE_BLEND) else os.path.join(ROOT, SAVE_BLEND)

DX = 76.2                       # mm added per side
MM = 1000.0                     # mm per scene unit (Blender default: metres)
DATUM_X = 59.0                  # bale / sidewall datum (mm)
CUT = (-680.0, 798.0)           # nominal world-X cut planes for the 15 members
CUT_DOUB = (-665.0, 665.0)      # DOUBLER pair (engine footprint |X| <= 635 stays)
CENTRAL_KEEP = 635.5            # mm: doubler geometry inside this must not move
MOUNT_KEEP = 500.0              # mm: mount plates on the 15 members are inside this
FIXED_TOL = 1e-6
COORD_TOL = 0.01                # mm, float32 round-trip headroom
LEN_TOL = 0.05                  # mm, acceptance tolerance on the 152.4 change
MATE_TOL = 0.5                  # mm, max allowed growth of a mating separation

CTRL_ROOT = "CPM-PP-JD18"
LEN_MEMBERS = ["Copy of Copy of Part11^PP128-FTA", "Copy of Copy of Part11^PP128-FTA.001",
               "Part1^PP128-PP108-SKID", "Part1^PP128-PP108-SKID.001",
               "PP-FTS-1008", "PP-FTS-1008.001", "PP-FTS-1008.002", "PP-FTS-1008.003",
               "PP-FTS-1008.004", "PP-FTS-1008.005",
               "PP-FTT", "PP-FTT.001",
               "tube rectangular_ai_TR12x6x0.25x80", "tube rectangular_ai_TR12x6x0.25x80.001",
               "LBA-CB"]
LEN_DOUB = ["DOUBLER", "DOUBLER.001"]
LEN = LEN_MEMBERS + LEN_DOUB                      # 17
RIG_SIDE = ["mc channel_ai_MC6x18x31.5", "mc channel_ai_MC6x18x31.001",
            "MC6X18-SKE_MC6x18x57", "MC6X18-SKE_MC6x18x57.001",
            "MC6X18-SKE1_MC6x18x57", "MC6X18-SKE1_MC6x18x57.001",
            "PP-FTS-1005", "PP-FTS-1005.001",
            "PP-FBS", "PP-FBS.001", "PP-FBS.002", "PP-FBS.003",
            "LBS-LG", "LBS-LG.001", "LBS-SH", "LBS-SH.001",
            "LBU-PP", "LBU-PP.001", "PP-LBB", "PP-LBB.001"]        # 20
RIG_CTRL = ["MSP-CP-CP750E", "PP-CPM-1001", "PP-CPM-1005"]          # 3
RIGID = RIG_SIDE + RIG_CTRL                                        # 23
FIXED_GUARD = ["MNT-PEB-CTF-PP12-WIDE", "PLT-MNT-6SL-PE-PP12",
               "PP128S22-MFB", "PP128S22-MFB.001", "PP128S22-MFB.002", "PP128S22-MFB.003"]
EXPECT_COLL = {"CAD_pump_new": 415, "CAD_engine": 7, "CAD_pump": 20,
               "CAD_skid": 14, "CAD_bale": 9, "CAD_controller": 3}

def coll_of(o):
    for c in o.users_collection:
        if c.name.startswith("CAD_"):
            return c.name
    return o.users_collection[0].name if o.users_collection else ""

def mesh_co(me):
    nv = len(me.vertices)
    co = np.empty(nv * 3, dtype=np.float32)
    me.vertices.foreach_get("co", co)
    return co.reshape(nv, 3)

def world_verts(o, co=None):
    me = o.data
    if co is None:
        co = mesh_co(me)
    mw = np.array(o.matrix_world, dtype=np.float64)
    return (co.astype(np.float64) @ mw[:3, :3].T + mw[:3, 3]) * MM

def mesh_topo(me):
    npoly, nl = len(me.polygons), len(me.loops)
    ls = np.empty(npoly, dtype=np.int64); me.polygons.foreach_get("loop_start", ls)
    lt = np.empty(npoly, dtype=np.int64); me.polygons.foreach_get("loop_total", lt)
    lv = np.empty(nl, dtype=np.int32); me.loops.foreach_get("vertex_index", lv)
    le = np.empty(nl, dtype=np.int32); me.loops.foreach_get("edge_index", le)
    ne = len(me.edges)
    ev = np.empty(ne * 2, dtype=np.int32); me.edges.foreach_get("vertices", ev); ev = ev.reshape(ne, 2)
    cnt = np.bincount(le, minlength=ne)
    boundary = int((cnt == 1).sum()); nonman = int((cnt > 2).sum()); wire = int((cnt == 0).sum())
    nv = len(me.vertices)
    par = np.arange(nv, dtype=np.int64)
    def find(x):
        while par[x] != x:
            par[x] = par[par[x]]; x = par[x]
        return x
    for a, b in ev:
        ra, rb = find(int(a)), find(int(b))
        if ra != rb: par[rb] = ra
    comps = len({find(i) for i in range(nv)}) if nv else 0
    return {"verts": nv, "edges": ne, "polys": npoly, "loops": nl,
            "boundary_edges": boundary, "nonmanifold_edges": nonman,
            "wire_edges": wire, "components": comps}

def geom_hash(me):
    h = hashlib.sha256()
    h.update(mesh_co(me).tobytes())
    nl = len(me.loops)
    lv = np.empty(nl, dtype=np.int32); me.loops.foreach_get("vertex_index", lv)
    h.update(lv.tobytes())
    npoly = len(me.polygons)
    for attr in ("loop_start", "loop_total"):
        a = np.empty(npoly, dtype=np.int64); me.polygons.foreach_get(attr, a)
        h.update(a.tobytes())
    h.update(np.asarray(me.vertices).shape.__str__().encode())
    return h.hexdigest()

def mat_list(o):
    return [[float(v) for v in r] for r in o.matrix_world]

def poly_normals(w, ls, lt, lv):
    """World-space polygon normals (Newell), robust for planar quads."""
    nl = len(lv)
    pol = np.repeat(np.arange(len(ls)), lt)
    idx = np.arange(nl)
    last = (idx - ls[pol]) == (lt[pol] - 1)
    nxt = np.where(last, ls[pol], idx + 1)
    acc = np.zeros((len(ls), 3))
    np.add.at(acc, pol, np.cross(w[lv], w[lv[nxt]]))
    n = np.linalg.norm(acc, axis=1)
    return acc / np.where(n > 0, n, 1)[:, None]

def vertex_free_runs(x, xmin, xmax, min_gap=12.0, binw=1.0):
    span = xmax - xmin
    if span < 2 * min_gap: return []
    nb = int(math.ceil(span / binw)) + 1
    idx = np.clip(((x - xmin) / binw).astype(np.int64), 0, nb - 1)
    occ = np.bincount(idx, minlength=nb) > 0
    runs, i = [], 0
    while i < nb:
        if occ[i]:
            i += 1; continue
        j = i
        while j < nb and not occ[j]: j += 1
        a, b = xmin + i * binw, xmin + j * binw
        if b - a >= min_gap: runs.append((float(a), float(b)))
        i = j
    return runs

def curved_transverse_edges(me, w):
    """Facet-boundary edges (curved surfaces: hole walls, fillets, rounds) whose
    world-X span <= 5 mm, with their world lengths.  Preserved by construction
    when a feature lies wholly outside a cut plane."""
    npoly, nl = len(me.polygons), len(me.loops)
    if npoly == 0 or nl == 0: return np.zeros(0), np.zeros(0)
    nrm = np.empty(npoly * 3); me.polygons.foreach_get("normal", nrm); nrm = nrm.reshape(-1, 3)
    nn = np.linalg.norm(nrm, axis=1); nrm = nrm / np.where(nn > 0, nn, 1)[:, None]
    ltot = np.empty(npoly, dtype=np.int32); me.polygons.foreach_get("loop_total", ltot)
    le = np.empty(nl, dtype=np.int32); me.loops.foreach_get("edge_index", le)
    lv = np.empty(nl, dtype=np.int32); me.loops.foreach_get("vertex_index", lv)
    pol = np.repeat(np.arange(npoly), ltot)
    order = np.argsort(le, kind="stable"); le_s = le[order]
    first = np.flatnonzero(np.r_[True, le_s[1:] != le_s[:-1]])
    counts = np.diff(np.r_[first, nl]); two = np.flatnonzero(counts == 2)
    if not len(two): return np.zeros(0), np.zeros(0)
    i0 = first[two]; a = order[i0]; b = order[i0 + 1]
    cos = (nrm[pol[a]] * nrm[pol[b]]).sum(1)
    sel = two[(cos > 0.5) & (cos < 0.9986)]
    if not len(sel): return np.zeros(0), np.zeros(0)
    i0 = first[sel]; a = order[i0]; b = order[i0 + 1]
    span = np.abs(w[lv[a], 0] - w[lv[b], 0])
    keep = span <= 5.0
    a, b = a[keep], b[keep]
    return np.linalg.norm(w[lv[a]] - w[lv[b]], axis=1), np.abs(w[lv[a], 0] - w[lv[b], 0])

def plane_safety(nm, o):
    """Direct geometric proof that both cut planes are safe for this part."""
    me = o.data
    co = mesh_co(me); w = world_verts(o, co)
    ls = np.empty(len(me.polygons), dtype=np.int64); me.polygons.foreach_get("loop_start", ls)
    lt = np.empty(len(me.polygons), dtype=np.int64); me.polygons.foreach_get("loop_total", lt)
    lv = np.empty(len(me.loops), dtype=np.int32); me.loops.foreach_get("vertex_index", lv)
    nrm = poly_normals(w, ls, lt, lv)
    ne = len(me.edges)
    ev = np.empty(ne * 2, dtype=np.int32)
    me.edges.foreach_get("vertices", ev)
    ev = ev.reshape(ne, 2)
    fx = w[lv, 0]
    pmn = np.minimum.reduceat(fx, ls); pmx = np.maximum.reduceat(fx, ls)
    cuts = CUT_DOUB if nm in LEN_DOUB else CUT
    mn, mx = float(w[:, 0].min()), float(w[:, 0].max())
    runs = vertex_free_runs(w[:, 0], mn, mx)
    rep = {"verts": len(w), "faces": len(ls), "bbox_x": [round(mn, 3), round(mx, 3)],
           "runs": [[round(a, 2), round(b, 2)] for a, b in runs], "planes": []}
    for p in cuts:
        band = next(((a, b) for a, b in runs if a + 1e-9 < p < b - 1e-9), None)
        rec = {"plane": p, "inside_run": band is not None,
               "run": [round(band[0], 2), round(band[1], 2)] if band else None,
               "margin_mm": round(min(p - band[0], band[1] - p), 3) if band else None}
        cross = (pmn < p - 1e-6) & (pmx > p + 1e-6)
        rec["crossing_faces"] = int(cross.sum())
        rec["max_abs_nx"] = round(float(np.abs(nrm[cross, 0]).max()), 8) if cross.any() else None
        rec["bridge_len_min"] = round(float((pmx[cross] - pmn[cross]).min()), 3) if cross.any() else None
        vl = w[:, 0] < p
        rec["crossing_edges"] = int((vl[ev[:, 0]] != vl[ev[:, 1]]).sum())
        rep["planes"].append(rec)
        # hard guards
        if band is None:
            raise RuntimeError("SAFETY %s plane %s is not inside a vertex-free run" % (nm, p))
        if rec["margin_mm"] < 5.0:
            raise RuntimeError("SAFETY %s plane %s margin %.2f mm < 5 mm" % (nm, p, rec["margin_mm"]))
        if rec["max_abs_nx"] is None or rec["max_abs_nx"] > 1e-3:
            raise RuntimeError("SAFETY %s plane %s: crossing face not X-parallel (|n_x|=%.5f)"
                               % (nm, p, rec["max_abs_nx"] or -1))
        if rec["bridge_len_min"] is not None and rec["bridge_len_min"] < 5.0:
            raise RuntimeError("SAFETY %s plane %s: bridge face only %.2f mm long"
                               % (nm, p, rec["bridge_len_min"]))
    moved = (w[:, 0] < cuts[0]) | (w[:, 0] > cuts[1])
    keep = CENTRAL_KEEP if nm in LEN_DOUB else MOUNT_KEEP
    inner_moved = int((np.abs(w[moved, 0]) <= keep).sum())
    rep["moved_verts"] = int(moved.sum())
    rep["moved_inside_keep_band"] = inner_moved
    rep["keep_band_mm"] = keep
    if inner_moved:
        raise RuntimeError("SAFETY %s would move %d vertices inside |X|<=%.1f mm"
                           % (nm, inner_moved, keep))
    rep["X_span_before"] = round(mx - mn, 3)
    rep["X_span_after"] = round(mx - mn + 2 * DX, 3)
    return rep

def lengthen(nm, o):
    """Move vertices outside the cut planes by +/-76.2 mm along world X."""
    me = o.data
    if me.users > 1:
        o.data = me = me.copy()
        log("   %s: mesh made single-user" % nm)
    co = mesh_co(me)
    mw = np.array(o.matrix_world, dtype=np.float64)
    R, t = mw[:3, :3], mw[:3, 3]
    w = co.astype(np.float64) @ R.T + t          # scene units
    wmm = w * MM                                 # mm, for classification
    cuts = CUT_DOUB if nm in LEN_DOUB else CUT
    dxw = np.zeros(len(co))
    dxw[wmm[:, 0] < cuts[0]] = -DX / MM
    dxw[wmm[:, 0] > cuts[1]] = DX / MM
    sel = dxw != 0.0
    new = co.astype(np.float64).copy()
    if sel.any():
        wnew = w[sel].copy(); wnew[:, 0] += dxw[sel]
        new[sel] = (wnew - t) @ np.linalg.inv(R).T
    out = new.astype(np.float32)
    me.vertices.foreach_set("co", out.ravel())
    me.update()
    return {"moved_verts": int(sel.sum()), "total_verts": len(co)}

# ------------------------------------------------------------------ geometry I/O
_BVH_CACHE = {}
def obj_tris(o):
    if o.name in _BVH_CACHE: return _BVH_CACHE[o.name]
    me = o.data
    me.calc_loop_triangles()
    nt = len(me.loop_triangles)
    t = np.empty(nt * 3, dtype=np.int32)
    if nt: me.loop_triangles.foreach_get("vertices", t)
    t = t.reshape(nt, 3)
    co = mesh_co(me)
    w = world_verts(o, co)
    ev = np.empty(len(me.edges) * 2, dtype=np.int32); me.edges.foreach_get("vertices", ev)
    ev = ev.reshape(len(me.edges), 2)
    pts = np.concatenate([w, 0.5 * (w[ev[:, 0]] + w[ev[:, 1]])], 0)
    val = (w, t, pts)
    _BVH_CACHE[o.name] = val
    return val

def to_bvh(w, tris):
    return BVHTree.FromPolygons([(float(p[0]), float(p[1]), float(p[2])) for p in w],
                                [(int(a), int(b), int(c)) for a, b, c in tris],
                                all_triangles=True)

def surface_separation(a, b, maxd=3000.0):
    """min point-to-triangle distance between two objects' surfaces, both ways."""
    wa, ta, pa = obj_tris(a)
    wb, tb, pb = obj_tris(b)
    dmin, info = None, {}
    for (src, pts, other_w, other_t) in ((a.name, pa, wb, tb), (b.name, pb, wa, ta)):
        if not len(other_t) or not len(pts): continue
        bv = to_bvh(other_w, other_t)
        for p in pts:
            loc, n, i, d = bv.find_nearest(Vector((float(p[0]), float(p[1]), float(p[2]))), maxd)
            if loc is not None and d is not None and (dmin is None or d < dmin):
                dmin = float(d)
                info = {"from": src, "point": [round(float(v), 3) for v in p],
                        "hit": [round(float(v), 3) for v in loc]}
    return (round(dmin, 4) if dmin is not None else None), info

MATE_PAIRS = [
    ("PP-FTS-1005", "Copy of Copy of Part11^PP128-FTA"),
    ("PP-FTS-1005.001", "Copy of Copy of Part11^PP128-FTA"),
    ("PP-FBS.001", "Copy of Copy of Part11^PP128-FTA"),
    ("PP-FBS", "Copy of Copy of Part11^PP128-FTA"),
    ("PP-FTS-1005", "PP-FTT"), ("PP-FTS-1005.001", "PP-FTT.001"),
    ("PP-FTS-1005", "PP-FTS-1008"), ("PP-FTS-1005.001", "PP-FTS-1008.001"),
    ("LBU-PP", "LBA-CB"), ("LBU-PP.001", "LBA-CB"),
    ("LBU-PP", "PP-FTT"), ("LBU-PP.001", "PP-FTT"),
    ("LBU-PP", "LBS-SH"), ("LBU-PP.001", "LBS-SH.001"),
    ("LBU-PP", "LBS-LG"), ("LBU-PP.001", "LBS-LG.001"),
    ("LBU-PP", "PP-LBB.001"), ("LBU-PP.001", "PP-LBB"),
    ("DOUBLER", "PP-FTT"), ("DOUBLER.001", "PP-FTT"),
    ("DOUBLER.001", "LBU-PP.001"), ("DOUBLER", "PLT-MNT-6SL-PE-PP12"),
    ("Part1^PP128-PP108-SKID", "PP128S22-MFB"),
    ("Copy of Copy of Part11^PP128-FTA.001", "PP128S22-MFB.002"),
    ("mc channel_ai_MC6x18x31.001", "PP-FTT.001"),
    ("mc channel_ai_MC6x18x31.5", "PP-FTT.001"),
    ("PP-FTT", "PP-FTS-1008"), ("PP-FTT.001", "PP-LBB"),
    ("PP-FTS-1008.001", "PP-LBB"),
]

def frame_all(o, mm=MM):
    co = mesh_co(o.data); w = world_verts(o, co)
    return {"min": [round(float(w[:, k].min()), 3) for k in range(3)],
            "max": [round(float(w[:, k].max()), 3) for k in range(3)]}

def aggregate_bbox(objs):
    lo = np.array([1e18] * 3); hi = -np.array([1e18] * 3)
    for o in objs:
        w = world_verts(o)
        for k in range(3):
            lo[k] = min(lo[k], float(w[:, k].min())); hi[k] = max(hi[k], float(w[:, k].max()))
    return lo, hi

def scene_summary():
    ms = [o for o in bpy.data.objects if o.type == "MESH"]
    lo, hi = aggregate_bbox(ms)
    return {"n_mesh": len(ms), "min": [round(float(v), 3) for v in lo],
            "max": [round(float(v), 3) for v in hi],
            "size": [round(float(hi[k] - lo[k]), 3) for k in range(3)],
            "centre": [round(float((hi[k] + lo[k]) / 2), 3) for k in range(3)]}

# --------------------------------------------------------------- clearance test
def engine_arrays():
    DG = bpy.context.evaluated_depsgraph_get()
    Vs, Ts, owner, off = [], [], [], 0
    for o in [x for x in bpy.data.objects if x.type == "MESH" and coll_of(x) == "CAD_engine"]:
        ev = o.evaluated_get(DG); me = ev.to_mesh()
        try:
            co = mesh_co(me); w = world_verts(o, co).astype(np.float32)
            me.calc_loop_triangles(); nt = len(me.loop_triangles)
            t = np.empty(nt * 3, dtype=np.int32)
            if nt: me.loop_triangles.foreach_get("vertices", t)
            t = t.reshape(nt, 3)
            Vs.append(w); Ts.append(t + off); owner.append((o.name, off, off + len(w))); off += len(w)
        finally:
            ev.to_mesh_clear()
    AV = np.concatenate(Vs).astype(np.float32) if Vs else np.zeros((0, 3), np.float32)
    AT = np.concatenate(Ts).astype(np.int32) if Ts else np.zeros((0, 3), np.int32)
    return AV, AT, owner

def measure_clearance(AV, AT, owner):
    DG = bpy.context.evaluated_depsgraph_get()
    MN = np.minimum(np.minimum(AV[AT[:, 0]], AV[AT[:, 1]]), AV[AT[:, 2]])
    MX = np.maximum(np.maximum(AV[AT[:, 0]], AV[AT[:, 1]]), AV[AT[:, 2]])
    def owner_of(g):
        for nm, a, b in owner:
            if a <= g < b: return nm
        return None
    out = []
    for uname in ("LBU-PP.001", "LBU-PP"):
        o = bpy.data.objects[uname]
        ev = o.evaluated_get(DG); me = ev.to_mesh()
        try:
            uw = world_verts(o, co := mesh_co(me))
            me.calc_loop_triangles(); nt = len(me.loop_triangles)
            ut = np.empty(nt * 3, dtype=np.int32); me.loop_triangles.foreach_get("vertices", ut)
            ut = ut.reshape(nt, 3)
        finally:
            ev.to_mesh_clear()
        umn = [float(uw[:, k].min()) for k in range(3)]
        umx = [float(uw[:, k].max()) for k in range(3)]
        rec = {"name": uname, "bbox_min": [round(v, 3) for v in umn],
               "bbox_max": [round(v, 3) for v in umx], "verts": int(len(uw)), "tris": int(len(ut)),
               "inner_face_X_mm": round(umx[0] if umx[0] < DATUM_X else umn[0], 3)}
        win = ((MX[:, 1] > umn[1]) & (MN[:, 1] < umx[1]) & (MX[:, 2] > umn[2]) & (MN[:, 2] < umx[2]))
        idxs = np.nonzero(win)[0]
        rec["engine_tris_in_yz_window"] = int(len(idxs))
        if len(idxs):
            if umx[0] < DATUM_X:   # minus upright: engine sits on its +X side
                inner, outer = umx[0], umn[0]
                sel = idxs[MN[idxs, 0] >= inner]
                if len(sel):
                    k = int(sel[np.argmin(MN[sel, 0])])
                    rec["x_slab_gap_engine_side_mm"] = round(float(MN[k, 0] - inner), 3)
                    rec["x_slab_feature_engine_side"] = {
                        "engine_object": owner_of(int(AT[k, 0])),
                        "X_mm": round(float(MN[k, 0]), 1),
                        "Y_mm": round(float(AV[AT[k]].mean(0)[1]), 1),
                        "Z_mm": round(float(AV[AT[k]].mean(0)[2]), 1)}
            else:                  # plus upright: engine sits on its -X side
                inner, outer = umn[0], umx[0]
                sel = idxs[MX[idxs, 0] <= inner]
                if len(sel):
                    k = int(sel[np.argmax(MX[sel, 0])])
                    rec["x_slab_gap_engine_side_mm"] = round(float(inner - MX[k, 0]), 3)
                    rec["x_slab_feature_engine_side"] = {
                        "engine_object": owner_of(int(AT[k, 0])),
                        "X_mm": round(float(MX[k, 0]), 1),
                        "Y_mm": round(float(AV[AT[k]].mean(0)[1]), 1),
                        "Z_mm": round(float(AV[AT[k]].mean(0)[2]), 1)}
            rec["inner_face_X_mm"] = round(float(inner), 3)
            rec["outer_face_X_mm"] = round(float(outer), 3)
            tight = None; zt, yt = uw[:, 2], uw[:, 1]
            nb = max(1, int((umx[2] - umn[2]) // 50) + 1)
            for zz in range(nb):
                a, b = umn[2] + zz * 50.0, umn[2] + (zz + 1) * 50.0
                m = (zt >= a) & (zt < b)
                if not m.any(): continue
                ylo, yhi = float(yt[m].min()), float(yt[m].max())
                s = ((MX[:, 2] > a) & (MN[:, 2] < b) & (MX[:, 1] > ylo) & (MN[:, 1] < yhi))
                if not s.any(): continue
                ii = np.nonzero(s)[0]
                v = (MN[ii, 0] - umx[0]) if umn[0] > DATUM_X else (umx[0] - MX[ii, 0])
                g = float(v.min())
                if tight is None or g < tight[0]:
                    tight = (g, round(a, 0), round(b, 0), round(ylo, 1), round(yhi, 1))
            if tight is not None:
                rec["x_slab_gap_tight_mm"] = round(tight[0], 3)
                rec["x_slab_gap_tight_band"] = {"Z_mm": [tight[1], tight[2]],
                                                "upright_Y_mm": [tight[3], tight[4]]}
        sub = np.zeros((0, 3), dtype=np.int32); margin = 100.0
        for MARGIN in (400.0, 250.0, 150.0, 100.0):
            lo = np.array([umn[0] - MARGIN, umn[1] - MARGIN, umn[2] - MARGIN])
            hi = np.array([umx[0] + MARGIN, umx[1] + MARGIN, umx[2] + MARGIN])
            sub = AT[np.all(MX > lo, 1) & np.all(MN < hi, 1)]
            margin = MARGIN
            if len(sub) <= 350000: break
        rec["engine_tris_in_roi"] = int(len(sub)); rec["roi_margin_mm"] = margin
        ubvh = to_bvh(uw, ut)
        rec["triangle_intersections"] = 0; rec["min_distance_mm"] = None
        if len(sub):
            used, inv = np.unique(sub.reshape(-1), return_inverse=True)
            vsub = AV[used]
            tri = inv.reshape(-1, 3).astype(np.int32)
            ebvh = to_bvh(vsub, tri)
            rec["triangle_intersections"] = int(len(ubvh.overlap(ebvh)))
            ev = np.empty(len(o.data.edges) * 2, dtype=np.int32)
            o.data.edges.foreach_get("vertices", ev); ev = ev.reshape(-1, 2)
            pts = np.concatenate([uw, 0.5 * (uw[ev[:, 0]] + uw[ev[:, 1]])], 0)
            if len(pts) > 60000:
                pts = pts[np.linspace(0, len(pts) - 1, 60000).astype(int)]
            dmin, dloc, dsrc, dgidx = None, None, None, None
            for pv in pts:
                loc, n, i, d = ebvh.find_nearest(
                    Vector((float(pv[0]), float(pv[1]), float(pv[2]))), 5000.0)
                if loc is not None and (dmin is None or d < dmin):
                    dmin, dloc, dsrc = d, list(loc), [float(v) for v in pv]
                    dgidx = int(used[tri[i][0]]) if i is not None else None
            vi = np.linspace(0, len(vsub) - 1, min(len(vsub), 40000)).astype(int)
            for k, pv in enumerate(vsub[vi]):
                loc, n, i, d = ubvh.find_nearest(
                    Vector((float(pv[0]), float(pv[1]), float(pv[2]))), 5000.0)
                if loc is not None and (dmin is None or d < dmin):
                    dmin, dloc, dsrc = d, [float(pv[0]), float(pv[1]), float(pv[2])], list(loc)
                    dgidx = int(used[vi[k]])
            if dmin is not None:
                rec["min_distance_mm"] = round(float(dmin), 3)
                rec["min_distance_method"] = ("sampled point-to-triangle BVH both directions "
                                              "(upper bound on the true separation)")
                rec["closest_point_on_upright"] = [round(v, 2) for v in dsrc]
                rec["closest_point_on_engine"] = [round(v, 2) for v in dloc]
                rec["nearest_engine_object"] = owner_of(dgidx) if dgidx is not None else None
        out.append(rec)
    return out

def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()

def main():
    src = os.path.abspath(bpy.data.filepath)
    want = os.path.join(ROOT, "out", "engine-and-pump-v10.blend")
    if os.path.normcase(src) != os.path.normcase(want):
        raise RuntimeError("refusing: source is %r, expected %r" % (src, want))
    if os.path.normcase(os.path.abspath(SAVE_ABS)) == os.path.normcase(src):
        raise RuntimeError("refusing to overwrite the source blend")
    if os.path.exists(SAVE_ABS) and not DRY:
        log("NOTE: %s already exists and will be replaced" % SAVE_ABS)
    sha_before = sha256_file(src)
    if EXPECT_SHA and sha_before != EXPECT_SHA:
        raise RuntimeError("source hash %s != expected %s" % (sha_before, EXPECT_SHA))
    log("source sha256", sha_before)

    R = {"script": "tools/astra_widen_v11.py", "source_blend": src, "source_sha256": sha_before,
         "blender": bpy.app.version_string, "mm_per_scene_unit": MM, "dry_run": DRY,
         "datum_X_mm": DATUM_X, "delta_per_side_mm": DX, "cut_planes_mm": list(CUT),
         "cut_planes_doubler_mm": list(CUT_DOUB), "checks": [], "failures": []}
    def chk(name, ok, detail=""):
        R["checks"].append({"check": name, "ok": bool(ok), "detail": detail})
        if not ok:
            R["failures"].append("%s: %s" % (name, detail))
            raise RuntimeError("CHECK FAILED %s: %s" % (name, detail))
        log("  OK %-46s %s" % (name, detail))

    meshes = sorted([o for o in bpy.data.objects if o.type == "MESH"], key=lambda o: o.name)
    R["n_mesh"] = len(meshes)
    chk("total mesh objects == 468", len(meshes) == 468, "got %d" % len(meshes))
    colls = {}
    for o in meshes: colls[coll_of(o)] = colls.get(coll_of(o), 0) + 1
    for c, n in EXPECT_COLL.items():
        chk("collection %s == %d" % (c, n), colls.get(c) == n, "got %s" % colls.get(c))
    missing = [n for n in LEN + RIGID + FIXED_GUARD if n not in bpy.data.objects]
    chk("all planned parts present", not missing, "missing %s" % missing)
    chk("17 lengthened", len(LEN) == 17 and len(set(LEN)) == 17, "%d unique" % len(set(LEN)))
    chk("23 rigid", len(RIGID) == 23 and len(set(RIGID)) == 23, "%d unique" % len(set(RIGID)))
    chk("rigid/lengthened disjoint", not (set(LEN) & set(RIGID)), "")
    fixed = [o for o in meshes if o.name not in set(LEN) | set(RIGID)]
    R["counts"] = {"lengthened": len(LEN), "rigid": len(RIGID), "fixed": len(fixed),
                   "total": len(meshes)}
    chk("428 entirely fixed", len(fixed) == 428, "got %d" % len(fixed))
    chk("fixed includes all CAD_pump_new + CAD_engine",
        all(coll_of(o) not in ("CAD_pump_new", "CAD_engine")
            or o.name not in set(LEN) | set(RIGID)
            for o in meshes), "")
    for n in FIXED_GUARD:
        chk("central mount %s fixed" % n, bpy.data.objects[n].name not in (set(LEN) | set(RIGID)), "")
    root = bpy.data.objects.get(CTRL_ROOT)
    chk("controller root %s is an EMPTY" % CTRL_ROOT, root is not None and root.type == "EMPTY", "")
    kids = sorted([c.name for c in root.children if c.type == "MESH"])
    chk("controller root children == 3 meshes", kids == sorted(RIG_CTRL), "%s" % kids)
    # sides derived from measured geometry (side of the X=59 datum)
    R["rigid_ops"] = {}
    for n in RIG_SIDE:
        o = bpy.data.objects[n]
        w = world_verts(o); cx = float((w[:, 0].min() + w[:, 0].max()) / 2)
        R["rigid_ops"][n] = {"side": "-76.2" if cx < DATUM_X else "+76.2",
                             "centre_X_before_mm": round(cx, 3)}
    nmin = sum(1 for v in R["rigid_ops"].values() if v["side"] == "-76.2")
    chk("rigid side split is 10 minus / 10 plus", nmin == 10, "minus=%d plus=%d" % (nmin, 20 - nmin))
    for n, want_side in (("PP-FBS", "-76.2"), ("PP-FBS.001", "+76.2"), ("PP-FBS.002", "+76.2"),
                         ("PP-FBS.003", "-76.2"), ("LBU-PP", "+76.2"), ("LBU-PP.001", "-76.2"),
                         ("mc channel_ai_MC6x18x31.5", "-76.2"), ("MC6X18-SKE_MC6x18x57.001", "+76.2")):
        chk("side of %s" % n, R["rigid_ops"][n]["side"] == want_side, R["rigid_ops"][n]["side"])
    R["lengthen_ops"] = {}
    for n in LEN:
        R["lengthen_ops"][n] = plane_safety(n, bpy.data.objects[n])
        log("  plane safety %-40s moved=%-4d runs=%s" % (
            n[:40], R["lengthen_ops"][n]["moved_verts"], R["lengthen_ops"][n]["runs"][:3]))
    chk("all 17 lengthened parts have safe cut planes",
        all(v["planes"] for v in R["lengthen_ops"].values()), "17 checked")

    # ---------------- baseline capture (before any edit)
    log("capturing baseline ...")
    base_geom = {o.name: geom_hash(o.data) for o in meshes}
    base_mat = {o.name: mat_list(o) for o in meshes}
    base_bb = {o.name: frame_all(o) for o in meshes}
    base_topo = {n: mesh_topo(bpy.data.objects[n].data) for n in LEN}
    base_curve = {}
    base_w = {}
    for n in LEN:
        o = bpy.data.objects[n]
        base_w[n] = world_verts(o)
        ln, _sp = curved_transverse_edges(o.data, base_w[n])
        base_curve[n] = np.sort(np.round(ln, 4))
    scene_before = scene_summary()
    R["scene_before"] = scene_before
    um = world_verts(bpy.data.objects["LBU-PP.001"]); up = world_verts(bpy.data.objects["LBU-PP"])
    minus_inner, plus_inner = float(um[:, 0].max()), float(up[:, 0].min())
    R["uprights_before"] = {"minus_inner_X_mm": round(minus_inner, 3),
                            "plus_inner_X_mm": round(plus_inner, 3),
                            "inner_spacing_mm": round(plus_inner - minus_inner, 3)}
    cmin = min(base_bb[n]["min"][0] for n in RIG_CTRL)
    cmax = max(base_bb[n]["max"][0] for n in RIG_CTRL)
    R["controller_before"] = {"group_X_min_mm": cmin, "group_X_max_mm": cmax,
                              "gap_to_minus_upright_inner_face_mm": round(cmax - minus_inner, 3)}
    log("capturing %d mating separations ..." % len(MATE_PAIRS))
    base_mate = {}
    for a, b in MATE_PAIRS:
        d, info = surface_separation(bpy.data.objects[a], bpy.data.objects[b])
        base_mate["%s | %s" % (a, b)] = d
    R["mating_before"] = base_mate
    log("  tightest baseline mates:", sorted([(v, k) for k, v in base_mate.items() if v is not None])[:6])

    # ---------------- apply
    log("applying %d rigid translations ..." % len(RIG_SIDE))
    for n in RIG_SIDE:
        o = bpy.data.objects[n]
        sign = -1.0 if R["rigid_ops"][n]["side"] == "-76.2" else 1.0
        o.matrix_world = Matrix.Translation((sign * DX / MM, 0.0, 0.0)) @ o.matrix_world
    log("translating controller root %s by -76.2 mm" % CTRL_ROOT)
    root.matrix_world = Matrix.Translation((-DX / MM, 0.0, 0.0)) @ root.matrix_world
    bpy.context.view_layer.update()
    log("lengthening %d members ..." % len(LEN))
    for n in LEN:
        res = lengthen(n, bpy.data.objects[n])
        R["lengthen_ops"][n]["moved_verts_actual"] = res["moved_verts"]
        R["lengthen_ops"][n]["total_verts"] = res["total_verts"]
    bpy.context.view_layer.update()
    _BVH_CACHE.clear()          # geometry moved: drop stale BVH/tris caches
    log("edit applied; verifying ...")

    # ---------------- post-edit structural guards
    post_geom = {o.name: geom_hash(o.data) for o in meshes}
    post_mat = {o.name: mat_list(o) for o in meshes}
    fixed_names = [o.name for o in fixed]
    bad = [n for n in fixed_names if post_geom[n] != base_geom[n]]
    chk("428 fixed meshes geometry bit-identical", not bad, "changed: %s" % bad[:5])
    bad = [n for n in fixed_names
           if max(abs(post_mat[n][r][c] - base_mat[n][r][c]) for r in range(4) for c in range(4)) > 1e-12]
    chk("428 fixed meshes matrices unchanged", not bad, "changed: %s" % bad[:5])
    bad = [n for n in RIGID if post_geom[n] != base_geom[n]]
    chk("23 rigid meshes local geometry bit-identical", not bad, "changed: %s" % bad[:5])
    worst_m, worst_b = 0.0, 0.0
    for n in RIGID:
        want = (-DX if (n in RIG_CTRL or R["rigid_ops"][n]["side"] == "-76.2") else DX)
        d = [post_mat[n][r][3] - base_mat[n][r][3] for r in range(3)]
        worst_m = max(worst_m, abs(d[0] * MM - want), abs(d[1] * MM), abs(d[2] * MM))
        bb0, bb1 = base_bb[n], frame_all(bpy.data.objects[n])
        for k in range(3):
            w = (bb1["min"][k] - bb0["min"][k], bb1["max"][k] - bb0["max"][k])
            worst_b = max(worst_b, abs(w[0] - (want if k == 0 else 0.0)),
                          abs(w[1] - (want if k == 0 else 0.0)))
        R["rigid_ops"].setdefault(n, {})["applied_delta_mm"] = [round(d[0] * MM, 4),
                                                                round(d[1] * MM, 4),
                                                                round(d[2] * MM, 4)]
    chk("23 rigid world matrices moved exactly +/-76.2 mm on X",
        worst_m <= 0.1, "worst deviation %.4f mm" % worst_m)
    chk("23 rigid bboxes shifted exactly +/-76.2 mm on X, 0 on Y/Z",
        worst_b <= 0.1, "worst deviation %.4f mm" % worst_b)
    for n in LEN:
        o = bpy.data.objects[n]
        cut_lo, cut_hi = (CUT_DOUB if n in LEN_DOUB else CUT)
        w1 = world_verts(o)
        chk("lengthen %s: geometry changed" % n, post_geom[n] != base_geom[n], "")
        chk("lengthen %s: topology unchanged" % n,
            mesh_topo(o.data) == base_topo[n], "%s vs %s" % (mesh_topo(o.data), base_topo[n]))
        w0 = base_w[n]
        d = np.where(w1[:, 0] < cut_lo, -DX, np.where(w1[:, 0] > cut_hi, DX, 0.0))
        dxerr = float(np.abs((w1[:, 0] - d) - w0[:, 0]).max())
        dyzerr = float(np.abs(w1[:, 1:3] - w0[:, 1:3]).max())
        chk("lengthen %s: X shift rule exact, Y/Z preserved" % n,
            dxerr <= COORD_TOL and dyzerr <= COORD_TOL,
            "dx err %.5f mm, yz err %.5f mm" % (dxerr, dyzerr))
        nmoved = int((d != 0).sum())
        chk("lengthen %s: moved vertex count matches plan" % n,
            nmoved == R["lengthen_ops"][n]["moved_verts"],
            "%d vs %d" % (nmoved, R["lengthen_ops"][n]["moved_verts"]))
        span0 = base_bb[n]["max"][0] - base_bb[n]["min"][0]
        span1 = float(w1[:, 0].max() - w1[:, 0].min())
        c0 = (base_bb[n]["max"][0] + base_bb[n]["min"][0]) / 2
        c1 = float((w1[:, 0].max() + w1[:, 0].min()) / 2)
        chk("lengthen %s: X span +152.4 mm" % n, abs(span1 - span0 - 2 * DX) <= LEN_TOL,
            "%.3f -> %.3f" % (span0, span1))
        chk("lengthen %s: X bbox centre unchanged" % n, abs(c1 - c0) <= LEN_TOL,
            "%.3f -> %.3f" % (c0, c1))
        yz0 = (base_bb[n]["min"][1:3], base_bb[n]["max"][1:3])
        yz1 = ([float(w1[:, k].min()) for k in (1, 2)], [float(w1[:, k].max()) for k in (1, 2)])
        chk("lengthen %s: Y/Z extents unchanged" % n,
            max(abs(yz1[i][k] - yz0[i][k]) for i in (0, 1) for k in (0, 1)) <= COORD_TOL,
            "%s -> %s" % (yz0, yz1))
        ln1, _sp = curved_transverse_edges(o.data, w1)
        a, b = base_curve[n], np.sort(np.round(ln1, 4))
        same = (len(a) == len(b)) and (len(a) == 0 or float(np.abs(a - b).max()) <= COORD_TOL)
        chk("lengthen %s: curved transverse feature lengths preserved" % n, same,
            "%d edges, max |d| %.5f mm" % (len(b), 0.0 if len(a) != len(b) else
                                           float(np.abs(a - b).max()) if len(a) else 0.0))
        R["lengthen_ops"][n].update({"X_span_after": round(span1, 3),
                                     "X_centre_after": round(c1, 3),
                                     "centre_shift_mm": round(c1 - c0, 4),
                                     "curved_transverse_edges": int(len(b))})

    # ---------------- scene-level invariants
    scene_after = scene_summary()
    R["scene_after"] = scene_after
    dw = scene_after["size"][0] - scene_before["size"][0]
    chk("assembly outside width +152.4 mm", abs(dw - 2 * DX) <= LEN_TOL, "%.3f mm" % dw)
    chk("assembly bbox centre X unchanged",
        abs(scene_after["centre"][0] - scene_before["centre"][0]) <= LEN_TOL,
        "%.4f -> %.4f" % (scene_before["centre"][0], scene_after["centre"][0]))
    chk("Y/Z scene extents unchanged",
        max(abs(scene_after["min"][k] - scene_before["min"][k]) for k in (1, 2)) <= COORD_TOL and
        max(abs(scene_after["max"][k] - scene_before["max"][k]) for k in (1, 2)) <= COORD_TOL,
        "Y %.2f..%.2f  Z %.2f..%.2f" % (scene_after["min"][1], scene_after["max"][1],
                                        scene_after["min"][2], scene_after["max"][2]))
    um2 = world_verts(bpy.data.objects["LBU-PP.001"]); up2 = world_verts(bpy.data.objects["LBU-PP"])
    m2, p2 = float(um2[:, 0].max()), float(up2[:, 0].min())
    chk("upright inner spacing +152.4 mm",
        abs((p2 - m2) - (plus_inner - minus_inner) - 2 * DX) <= LEN_TOL,
        "%.3f -> %.3f" % (plus_inner - minus_inner, p2 - m2))
    chk("upright inner faces moved -76.2 / +76.2",
        abs(m2 - (minus_inner - DX)) <= LEN_TOL and abs(p2 - (plus_inner + DX)) <= LEN_TOL,
        "%.3f %.3f" % (m2, p2))
    R["uprights_after"] = {"minus_inner_X_mm": round(m2, 3), "plus_inner_X_mm": round(p2, 3),
                           "inner_spacing_mm": round(p2 - m2, 3)}
    cmin2 = min(frame_all(bpy.data.objects[n])["min"][0] for n in RIG_CTRL)
    cmax2 = max(frame_all(bpy.data.objects[n])["max"][0] for n in RIG_CTRL)
    chk("controller follows minus upright rigidly",
        abs((cmax2 - m2) - (cmax - minus_inner)) <= LEN_TOL,
        "gap %.3f -> %.3f mm" % (cmax - minus_inner, cmax2 - m2))
    R["controller_after"] = {"group_X_min_mm": round(cmin2, 3), "group_X_max_mm": round(cmax2, 3),
                             "gap_to_minus_upright_inner_face_mm": round(cmax2 - m2, 3)}

    log("measuring %d mating separations after edit ..." % len(MATE_PAIRS))
    mate_after = {}
    for a, b in MATE_PAIRS:
        d, _ = surface_separation(bpy.data.objects[a], bpy.data.objects[b])
        mate_after["%s | %s" % (a, b)] = d
    R["mating_after"] = mate_after
    growth = {k: round(mate_after[k] - base_mate[k], 4) for k in mate_after
              if mate_after[k] is not None and base_mate[k] is not None}
    R["mating_growth_mm"] = growth
    bad = [k for k, v in growth.items() if v > MATE_TOL]
    chk("no mating interface opens by more than 0.5 mm", not bad, "offenders %s" % bad)
    R["mating_worst_growth"] = max(growth.items(), key=lambda kv: kv[1]) if growth else None

    # ---------------- save + reload verification
    if not DRY:
        try:
            bpy.context.preferences.filepaths.save_version = 0
        except Exception as e:
            log("save_version not settable:", e)
        bpy.ops.wm.save_as_mainfile(filepath=SAVE_ABS, compress=False)
        chk("v11 blend written", os.path.exists(SAVE_ABS) and os.path.getsize(SAVE_ABS) > 1e6,
            "%s (%.1f MB)" % (SAVE_ABS, os.path.getsize(SAVE_ABS) / 1e6))
        R["saved_blend"] = SAVE_ABS
        R["output_sha256"] = sha256_file(SAVE_ABS)
        log("saved v11:", R["output_sha256"])
        bpy.ops.wm.open_mainfile(filepath=SAVE_ABS)
        _BVH_CACHE.clear()
        ms2 = [o for o in bpy.data.objects if o.type == "MESH"]
        chk("reload: 468 mesh objects", len(ms2) == 468, "%d" % len(ms2))
        c2 = {}
        for o in ms2: c2[coll_of(o)] = c2.get(coll_of(o), 0) + 1
        chk("reload: collections unchanged", c2 == colls, "%s" % c2)
        sb = scene_summary()
        chk("reload: width/centre preserved",
            abs(sb["size"][0] - scene_after["size"][0]) <= 1e-6 and
            abs(sb["centre"][0] - scene_after["centre"][0]) <= 1e-6, "")
        bad = [n for n in fixed_names if geom_hash(bpy.data.objects[n].data) != base_geom[n]]
        chk("reload: fixed parts still identical to v10", not bad, "%s" % bad[:5])
        bad = [n for n in LEN if geom_hash(bpy.data.objects[n].data) != post_geom[n]]
        chk("reload: edited parts preserved exactly", not bad, "%s" % bad[:5])
        bad = [n for n in RIGID if geom_hash(bpy.data.objects[n].data) != base_geom[n]]
        chk("reload: rigid meshes still local-identical", not bad, "%s" % bad[:5])
        log("measuring engine/upright clearance on the reloaded v11 ...")
        AV, AT, owner = engine_arrays()
        clr = measure_clearance(AV, AT, owner)
        R["clearance_after"] = clr
        for rec in clr:
            chk("clearance %s: no engine/upright triangle intersection" % rec["name"],
                rec["triangle_intersections"] == 0, "%d" % rec["triangle_intersections"])
        for rec in clr:
            log("  %s: intersections=%d min_dist=%s mm tight_slab=%s mm inner_face=%s" % (
                rec["name"], rec["triangle_intersections"], rec.get("min_distance_mm"),
                rec.get("x_slab_gap_tight_mm"), rec.get("inner_face_X_mm")))
    try:
        insp = json.load(open(os.path.join(ROOT, "reports", "astra-widening-inspection.json")))
        R["baseline_clearance_v10"] = {u["name"]: {k: u.get(k) for k in
            ("triangle_intersections", "min_distance_mm", "x_slab_gap_tight_mm",
             "x_slab_gap_engine_side_mm", "closest_point_on_upright", "closest_point_on_engine")}
            for u in insp["clearance"]["uprights"]}
    except Exception as e:
        R["baseline_clearance_v10"] = "unavailable: %r" % e
    R["ok"] = not R["failures"]
    with open(OUT_PATH, "w") as f:
        json.dump(R, f, indent=1)
    log("WROTE", OUT_JSON)
    log("DONE  ok=%s  checks=%d  failures=%d" % (R["ok"], len(R["checks"]), len(R["failures"])))

OUT_PATH = OUT_JSON if os.path.isabs(OUT_JSON) else os.path.join(ROOT, OUT_JSON)
try:
    main()
except Exception as exc:
    import traceback
    tb = traceback.format_exc()
    print(tb, flush=True)
    log("ABORTED:", repr(exc))
    try:
        fail = {"script": "tools/astra_widen_v11.py", "status": "FAILED", "ok": False,
                "error": repr(exc), "traceback": tb.splitlines()[-25:],
                "source_blend": bpy.data.filepath, "blend_saved": False,
                "note": "no v11 was saved; source v10 untouched"}
        with open(OUT_PATH, "w") as f:
            json.dump(fail, f, indent=1)
        log("wrote failure report", OUT_PATH)
    except Exception as e2:
        log("could not write failure report:", repr(e2))
    raise SystemExit(1)
