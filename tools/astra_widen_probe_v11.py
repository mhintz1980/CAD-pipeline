"""Read-only validation probe for the v11 widening (DeepSeek widen worker).

Checks the Astra strategy before any deformation:
  * exact part sets / sides / transforms / shared mesh data / modifiers
  * non-mesh (empty) hierarchy for the controller + skid empties
  * unclipped vertex-free X runs vs the candidate cut planes -680 / +798
  * safety of each plane: crossing faces must lie in X-parallel planes
    (abs(n_x) near 0), no X-normal face spanning, feature-free run contains it
Never saves a .blend.
Run:
  blender -b -noaudio --threads 4 out/engine-and-pump-v10.blend \
    --python-exit-code 1 --python tools/astra_widen_probe_v11.py -- reports/astra-widen-v11-probe.json
"""
import bpy, sys, json, math, time
import numpy as np

T0 = time.time()
def log(*a): print("[probe %6.1fs]" % (time.time() - T0), *a, flush=True)

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else "reports/astra-widen-v11-probe.json"

_pre_lo = [1e18] * 3; _pre_hi = [-1e18] * 3
for _o in bpy.data.objects:
    if _o.type != "MESH": continue
    _bb = np.array([list(c) for c in _o.bound_box]); _mw = np.array(_o.matrix_world)
    _wbb = _bb @ _mw[:3, :3].T + _mw[:3, 3]
    for _k in range(3):
        _pre_lo[_k] = min(_pre_lo[_k], float(_wbb[:, _k].min()))
        _pre_hi[_k] = max(_pre_hi[_k], float(_wbb[:, _k].max()))
MM = 1000.0 if max(_pre_hi[k] - _pre_lo[k] for k in range(3)) < 20.0 else 1.0
log("scene extent", round(max(_pre_hi[k] - _pre_lo[k] for k in range(3)), 4), "-> to_mm", MM)

CTRL_ROOT = "CPM-PP-JD18"
LEN = ["Copy of Copy of Part11^PP128-FTA", "Copy of Copy of Part11^PP128-FTA.001",
       "Part1^PP128-PP108-SKID", "Part1^PP128-PP108-SKID.001",
       "PP-FTS-1008", "PP-FTS-1008.001", "PP-FTS-1008.002", "PP-FTS-1008.003",
       "PP-FTS-1008.004", "PP-FTS-1008.005",
       "PP-FTT", "PP-FTT.001",
       "tube rectangular_ai_TR12x6x0.25x80", "tube rectangular_ai_TR12x6x0.25x80.001",
       "LBA-CB",
       # H2 decision: doubler pair lengthened at their own cuts near -665 / +665
       "DOUBLER", "DOUBLER.001"]
DOUB = ["DOUBLER", "DOUBLER.001"]
CUT_DOUB = [-665.0, 665.0]
RIG_SKID_BALE = ["mc channel_ai_MC6x18x31.5", "mc channel_ai_MC6x18x31.001",
                 "MC6X18-SKE_MC6x18x57", "MC6X18-SKE_MC6x18x57.001",
                 "MC6X18-SKE1_MC6x18x57", "MC6X18-SKE1_MC6x18x57.001",
                 "PP-FTS-1005", "PP-FTS-1005.001",
                 "PP-FBS", "PP-FBS.001", "PP-FBS.002", "PP-FBS.003",
                 "LBS-LG", "LBS-LG.001", "LBS-SH", "LBS-SH.001",
                 "LBU-PP", "LBU-PP.001", "PP-LBB", "PP-LBB.001"]
CTRL_MESH = ["MSP-CP-CP750E", "PP-CPM-1001", "PP-CPM-1005"]
FIXED_EXTRA = ["DOUBLER", "DOUBLER.001", "MNT-PEB-CTF-PP12-WIDE", "PLT-MNT-6SL-PE-PP12",
               "PP128S22-MFB", "PP128S22-MFB.001", "PP128S22-MFB.002", "PP128S22-MFB.003"]
CUT = [-680.0, 798.0]

def coll_of(obj):
    for c in obj.users_collection:
        if c.name.startswith("CAD_"):
            return c.name
    return obj.users_collection[0].name if obj.users_collection else ""

def mesh_arrays(me):
    nv = len(me.vertices)
    co = np.empty(nv * 3, dtype=np.float64); me.vertices.foreach_get("co", co); co = co.reshape(nv, 3)
    npoly = len(me.polygons); nl = len(me.loops)
    ls = np.empty(npoly, dtype=np.int64); me.polygons.foreach_get("loop_start", ls)
    lt = np.empty(npoly, dtype=np.int64); me.polygons.foreach_get("loop_total", lt)
    lv = np.empty(nl, dtype=np.int32); me.loops.foreach_get("vertex_index", lv)
    ne = len(me.edges)
    ev = np.empty(ne * 2, dtype=np.int32); me.edges.foreach_get("vertices", ev); ev = ev.reshape(ne, 2)
    return co, ls, lt, lv, ev

def world_verts(obj):
    me = obj.data
    nv = len(me.vertices)
    co = np.empty(nv * 3, dtype=np.float64); me.vertices.foreach_get("co", co); co = co.reshape(nv, 3)
    mw = np.array(obj.matrix_world, dtype=np.float64)
    return (co @ mw[:3, :3].T + mw[:3, 3]) * MM

def poly_newell(w, ls, lt, lv):
    nl = len(lv)
    pol = np.repeat(np.arange(len(ls)), lt)
    idx = np.arange(nl)
    last = (idx - ls[pol]) == (lt[pol] - 1)
    nxt = np.where(last, ls[pol], idx + 1)
    c = np.cross(w[lv], w[lv[nxt]])
    acc = np.zeros((len(ls), 3))
    np.add.at(acc, pol, c)
    n = np.linalg.norm(acc, axis=1)
    return acc / np.where(n > 0, n, 1)[:, None]

def unclipped_bands(x, xmin, xmax, min_gap=12.0, binw=1.0):
    span = xmax - xmin
    if span < 2 * min_gap: return []
    nb = int(math.ceil(span / binw)) + 1
    idx = np.clip(((x - xmin) / binw).astype(np.int64), 0, nb - 1)
    occ = np.bincount(idx, minlength=nb) > 0
    runs = []; i = 0
    while i < nb:
        if occ[i]:
            i += 1; continue
        j = i
        while j < nb and not occ[j]: j += 1
        a, b = xmin + i * binw, xmin + j * binw
        if b - a >= min_gap: runs.append((float(a), float(b)))
        i = j
    return runs

rep = {"script": "tools/astra_widen_probe_v11.py", "source_blend": bpy.data.filepath,
       "mm": MM, "cut_planes_mm": CUT, "objects": {}, "empties": {}, "shared_mesh": {},
       "sets": {}, "width": {}, "hierarchy": {}}

meshes = [o for o in bpy.data.objects if o.type == "MESH"]
rep["n_mesh"] = len(meshes)
log("mesh objects", len(meshes))

missing = [n for n in LEN + RIG_SKID_BALE + CTRL_MESH + FIXED_EXTRA if n not in bpy.data.objects]
rep["sets"] = {"missing": missing, "n_len": len(LEN), "n_rig_skid_bale": len(RIG_SKID_BALE),
               "n_ctrl": len(CTRL_MESH), "n_fixed_extra": len(FIXED_EXTRA)}
log("missing names:", missing)

allw = [world_verts(o) for o in meshes]
lo = np.array([min(float(w[:, k].min()) for w in allw) for k in range(3)])
hi = np.array([max(float(w[:, k].max()) for w in allw) for k in range(3)])
rep["width"] = {"min": lo.tolist(), "max": hi.tolist(), "size": (hi - lo).tolist(),
                "centre": ((hi + lo) / 2).tolist()}
log("aggregate bbox", np.round(lo, 2), np.round(hi, 2), "width", round(hi[0] - lo[0], 3))
del allw

interest = {CTRL_ROOT, "PP128-PP108-SKID", "PP128-FTA", "JD18-EMA",
            "MNT-PEA-CTF-PP12-WIDE", "PP128-PP108-SKID.001"}
for o in bpy.data.objects:
    if (o.parent and o.parent.name in interest) or o.name in interest:
        rep["hierarchy"][o.name] = {"type": o.type,
                                    "parent": o.parent.name if o.parent else None,
                                    "collection": coll_of(o),
                                    "matrix_world": [[float(v) for v in r] for r in o.matrix_world]}
for nm in sorted(interest):
    o = bpy.data.objects.get(nm)
    if o is None:
        rep["empties"][nm] = None; continue
    rep["empties"][nm] = {"type": o.type, "parent": o.parent.name if o.parent else None,
                          "children": sorted(c.name for c in o.children),
                          "matrix_world": [[float(v) for v in r] for r in o.matrix_world]}
log("empties:", {k: (v["type"] if v else None) for k, v in rep["empties"].items()})
jr = bpy.data.objects.get(CTRL_ROOT)
if jr:
    log("CTRL_ROOT children:", sorted((c.name, c.type) for c in jr.children))
    log("CTRL_ROOT parent:", jr.parent.name if jr.parent else None)

for nm in LEN + RIG_SKID_BALE + CTRL_MESH:
    o = bpy.data.objects.get(nm)
    if not o: continue
    if o.data.users > 1 or o.modifiers:
        rep["shared_mesh"][nm] = {"data": o.data.name, "users": o.data.users,
                                  "shared_with": sorted(x.name for x in bpy.data.objects
                                                        if x.type == "MESH" and x.data == o.data),
                                  "modifiers": [m.type for m in o.modifiers]}
log("shared/multiuser:", json.dumps(rep["shared_mesh"])[:700])

for nm in LEN + CTRL_MESH + RIG_SKID_BALE:
    o = bpy.data.objects.get(nm)
    if not o: continue
    me = o.data
    w = world_verts(o)
    co, ls, lt, lv, ev = mesh_arrays(me)
    nrm = poly_newell(w, ls, lt, lv)
    fx = w[lv, 0]
    pmn = np.minimum.reduceat(fx, ls); pmx = np.maximum.reduceat(fx, ls)
    mn, mx = float(w[:, 0].min()), float(w[:, 0].max())
    runs = unclipped_bands(w[:, 0], mn, mx)
    rec = {"collection": coll_of(o), "verts": len(w), "polys": int(len(ls)), "edges": len(ev),
           "bbox_x": [round(mn, 3), round(mx, 3)], "bbox_centre_x": round((mn + mx) / 2, 3),
           "modifiers": [m.type for m in o.modifiers],
           "unclipped_feature_free_runs": [[round(a, 2), round(b, 2)] for a, b in runs],
           "det3x3": float(np.linalg.det(np.array(o.matrix_world)[:3, :3])),
           "plane_checks": []}
    for p in (CUT_DOUB if nm in DOUB else CUT):
        band = next(((a, b) for a, b in runs if a < p < b), None)
        pc = {"plane": p, "inside_run": band is not None}
        if band:
            pc["run"] = [round(band[0], 2), round(band[1], 2)]
            pc["margin_mm"] = round(min(p - band[0], band[1] - p), 2)
            cross = (pmn < p - 1e-6) & (pmx > p + 1e-6)
            pc["spanning_faces"] = int(cross.sum())
            if cross.any():
                nx = np.abs(nrm[cross, 0])
                pc["max_abs_nx"] = round(float(nx.max()), 6)
                pc["faces_nx_gt_0.001"] = int((nx > 0.001).sum())
                pc["faces_nx_gt_0.05"] = int((nx > 0.05).sum())
                span = pmx[cross] - pmn[cross]
                pc["bridge_len_min"] = round(float(span.min()), 2)
                pc["bridge_len_max"] = round(float(span.max()), 2)
        vl = w[:, 0] < p
        ecl = vl[ev[:, 0]] != vl[ev[:, 1]]
        pc["crossing_edges"] = int(ecl.sum())
        if ecl.any():
            e = ev[ecl]
            d = w[e[:, 1]] - w[e[:, 0]]
            L = np.linalg.norm(d, axis=1)
            rat = np.abs(d[:, 0]) / np.where(L > 0, L, 1)
            pc["edge_dx_ratio_min"] = round(float(rat.min()), 4)
            pc["edges_not_X_parallel"] = int((rat < 0.99).sum())
        pc["verts_left"] = int(vl.sum()); pc["verts_right"] = int((~vl).sum())
        pc["xmin_left_of_plane"] = round(float(w[vl, 0].min()), 3) if vl.any() else None
        pc["xmax_right_of_plane"] = round(float(w[~vl, 0].max()), 3) if (~vl).any() else None
        rec["plane_checks"].append(pc)
    rep["objects"][nm] = rec
    log("%-40s v%-6d f%-6d runs%s" % (nm[:40], len(w), len(ls),
        [(round(a, 1), round(b, 1)) for a, b in runs][:4]))

# --- H2 doubler specifics: curved transverse features vs the candidate cuts, and
# the untouched engine-mount footprint (PP12-EM-JD18 / EM-SP*).
def curved_edges(me, w):
    npoly = len(me.polygons); nl = len(me.loops)
    if npoly == 0 or nl == 0: return np.zeros(0), np.zeros(0)
    nrm = np.empty(npoly * 3); me.polygons.foreach_get("normal", nrm); nrm = nrm.reshape(-1, 3)
    nn = np.linalg.norm(nrm, axis=1); nrm = nrm / np.where(nn > 0, nn, 1)[:, None]
    ltot = np.empty(npoly, dtype=np.int32); me.polygons.foreach_get("loop_total", ltot)
    le = np.empty(nl, dtype=np.int32); me.loops.foreach_get("edge_index", le)
    lv = np.empty(nl, dtype=np.int32); me.loops.foreach_get("vertex_index", lv)
    pol = np.repeat(np.arange(npoly), ltot)
    order = np.argsort(le, kind="stable"); le_s = le[order]
    first = np.flatnonzero(np.r_[True, le_s[1:] != le_s[:-1]]); counts = np.diff(np.r_[first, nl])
    two = np.flatnonzero(counts == 2)
    if not len(two): return np.zeros(0), np.zeros(0)
    i0 = first[two]; a = order[i0]; b = order[i0 + 1]
    cos = (nrm[pol[a]] * nrm[pol[b]]).sum(1)
    sel = two[(cos > 0.5) & (cos < 0.9986)]
    if not len(sel): return np.zeros(0), np.zeros(0)
    i0 = first[sel]; a = order[i0]; b = order[i0 + 1]
    ex = 0.5 * (w[lv[a], 0] + w[lv[b], 0]); span = np.abs(w[lv[a], 0] - w[lv[b], 0])
    return ex, span

for nm in DOUB:
    o = bpy.data.objects.get(nm)
    me = o.data; w = world_verts(o)
    ex, span = curved_edges(me, w)
    trans = ex[span <= 5.0]
    rec = rep["objects"][nm]
    rec["curved_transverse_edge_X"] = sorted({round(float(x), 1) for x in trans})
    rec["H2"] = {}
    for p in CUT_DOUB:
        near = sorted({round(float(x), 2) for x in trans if abs(x - p) <= 120.0})
        vl = w[:, 0] < p
        rec["H2"]["cut_%d" % p] = {
            "curved_transverse_features_within_120mm": near,
            "nearest_curved_feature_dist_mm": (round(min(abs(x - p) for x in trans), 3)
                                               if len(trans) else None),
            "verts_moved": int(vl.sum()),
            "verts_moved_outside_635.5": int((np.abs(w[vl, 0]) > 635.5).sum()),
            "verts_inside_635.5_that_would_move": int((np.abs(w[vl, 0]) <= 635.5).sum()),
        }
eng_mounts = {}
for o in bpy.data.objects:
    if o.type != "MESH": continue
    n = o.name
    if n.startswith("EM-SP") or "PP12-EM-JD18" in n or n.startswith("PLT-MNT") or n.startswith("MNT-PEB") or n.startswith("PP128S22"):
        w = world_verts(o)
        eng_mounts[n] = {"collection": coll_of(o), "x": [round(float(w[:, 0].min()), 3), round(float(w[:, 0].max()), 3)],
                         "y": [round(float(w[:, 1].min()), 3), round(float(w[:, 1].max()), 3)],
                         "z": [round(float(w[:, 2].min()), 3), round(float(w[:, 2].max()), 3)]}
rep["engine_mount_footprint"] = eng_mounts
mx = max((abs(v["x"][0]) for v in eng_mounts.values()), default=None)
log("engine mount footprint |X| max:", mx)
for nm in DOUB:
    log(nm, "H2:", json.dumps(rep["objects"][nm]["H2"]))


with open(OUT, "w") as f:
    json.dump(rep, f, indent=1)
log("WROTE", OUT)
log("DONE")
