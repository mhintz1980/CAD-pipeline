"""Independent verifier: immutable v9 vs candidate v10 controller relocation.

Loads BOTH blends in one Blender process, snapshots every mesh (local-space
geometry hash, material keys, world matrix, world bbox, collection, parent),
and allows ONLY:
  (1) a common pure rigid TRANSLATION of the controller subtree
      (MSP-CP-CP750E, PP-CPM-1001, PP-CPM-1005; mesh data bit-identical,
       rotation part of matrix identical, one shared delta), and
  (2) deletion of the CAD_QUARANTINE_outliers duplicate collection.
Everything else must be exactly unchanged, including pump shaft 1207517913.
Also asserts bracket PP-CPM-1005 bottom is 48 in above skid bottom in v10,
and reports the engine-side mating plane vs upright LBU-PP.001.

  blender --background -t 4 --python tools/astra_verify_v10.py -- ^
      --baseline out/engine-and-pump-v9.blend ^
      --candidate out/engine-and-pump-v10.blend ^
      --report reports/astra-independent-verification.json
Exits 0 PASS, 3 FAIL (violations).
"""
import bpy, sys, os, json, hashlib
import numpy as np
from mathutils import Vector, Matrix

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
A = {k: v for k, v in zip(argv[0::2], argv[1::2])}
BASE = os.path.abspath(A["--baseline"]); CAND = os.path.abspath(A["--candidate"])
OUT = os.path.abspath(A["--report"])
CTRL = {"MSP-CP-CP750E", "PP-CPM-1001", "PP-CPM-1005"}
MM = 1000.0; INCH = 0.0254
viol = []; R = {"baseline": BASE, "candidate": CAND, "violations": [], "checks": []}

def chk(name, ok, detail):
    R["checks"].append({"assertion": name, "ok": bool(ok), "detail": detail})
    print(("  [OK]   " if ok else "  [FAIL] ") + name + ": " + detail)
    if not ok: viol.append(name + ": " + detail)

def digest_mesh(me):
    n = len(me.vertices)
    co = np.empty(n * 3, dtype=np.float32); me.vertices.foreach_get("co", co)
    li = np.empty(len(me.loops), dtype=np.int32); me.loops.foreach_get("vertex_index", li)
    ps = np.empty(len(me.polygons), dtype=np.int32); me.polygons.foreach_get("loop_start", ps)
    ms = np.empty(len(me.polygons), dtype=np.int32); me.polygons.foreach_get("material_index", ms)
    h = hashlib.sha256()
    for a in (co, li, ps, ms): h.update(a.tobytes())
    return h.hexdigest()

def snapshot(path, tag):
    bpy.ops.wm.open_mainfile(filepath=path)
    snap = {}
    for o in bpy.data.objects:
        if o.type != "MESH": continue
        mw = o.matrix_world
        lo = Vector((1e18,)*3); hi = Vector((-1e18,)*3)
        for c in o.bound_box:
            p = mw @ Vector(c)
            for i in range(3):
                lo[i] = min(lo[i], p[i]); hi[i] = max(hi[i], p[i])
        snap[o.name] = {
            "coll": sorted(c.name for c in o.users_collection),
            "parent": o.parent.name if o.parent else None,
            "mats": [m.name if m else None for m in o.data.materials],
            "digest": digest_mesh(o.data),
            "matrix": [round(v, 9) for row in mw for v in row],
            "min": [round(v, 7) for v in lo], "max": [round(v, 7) for v in hi]}
    colls = sorted(c.name for c in bpy.data.collections)
    print("[" + tag + "] " + str(len(snap)) + " meshes, collections=" + str(colls))
    return snap, colls

print("PASS 1/2: baseline", BASE)
s9, c9 = snapshot(BASE, "v9")
print("PASS 2/2: candidate", CAND)
s10, c10 = snapshot(CAND, "v10")
R["census"] = {"v9_meshes": len(s9), "v10_meshes": len(s10),
               "v9_collections": c9, "v10_collections": c10}

n9, n10 = set(s9), set(s10)
gone = sorted(n9 - n10); new = sorted(n10 - n9)
chk("no_unexpected_new_objects", not new, "new in v10: " + str(new))
chk("removed_only_quarantine", all("QUAR" in x.upper() for x in gone),
    "removed from v9: " + str(gone))
common = n9 & n10

moved, rot_bad, geom_bad, mat_bad, mixed = [], [], [], [], []
for n in sorted(common):
    a, b = s9[n], s10[n]
    is_ctrl = n in CTRL
    if a["digest"] != b["digest"]: (geom_bad if is_ctrl else mixed).append(n)
    if a["mats"] != b["mats"]: mat_bad.append(n)
    if a["coll"] != b["coll"] or a["parent"] != b["parent"]: mixed.append(n + ":coll")
    M9 = Matrix([a["matrix"][0:4], a["matrix"][4:8], a["matrix"][8:12], a["matrix"][12:16]])
    M10 = Matrix([b["matrix"][0:4], b["matrix"][4:8], b["matrix"][8:12], b["matrix"][12:16]])
    if is_ctrl:
        D = M10 @ M9.inverted()
        if D.to_3x3() != Matrix.Identity(3): rot_bad.append(n)
        moved.append((n, D.to_translation()))
    else:
        if M9 != M10: mixed.append(n + ":matrix")
chk("non_controller_untouched", not mixed, "changed non-controller objects: " + str(mixed[:8]))
chk("all_materials_unchanged", not mat_bad, "objects with changed materials: " + str(mat_bad[:8]))
chk("controller_geometry_unchanged", not geom_bad, "controller meshes edited: " + str(geom_bad))
chk("controller_no_rotation", not rot_bad, "controller rotation change: " + str(rot_bad))
chk("controller_all_moved", len(moved) == 3 and all(
    max(abs(t[i]) for _, t in moved) > 0.001 for i in range(3)),
    "moved pairs: " + str([(n, [round(v*MM, 2) for v in t]) for n, t in moved]))
t0 = None
if len(moved) == 3:
    t0 = moved[0][1]
    dev = max((t - t0).length for _, t in moved)
    chk("controller_single_shared_translation", dev <= 1e-6,
        "max deviation between part deltas %.2e m; delta_mm=%s" %
        (dev, [round(v*MM, 3) for v in t0]))

# ---- 48 in bracket height, measured fresh in v10
bpy.ops.wm.open_mainfile(filepath=CAND)
brk = bpy.data.objects.get("PP-CPM-1005")
chk("bracket_present", brk is not None, "PP-CPM-1005")
skid = [o for o in bpy.data.objects if o.type == "MESH"
        and any(c.name == "CAD_skid" for c in o.users_collection)]
sb = min((o.matrix_world @ Vector(c)).z for o in skid for c in o.bound_box)
bb = min((brk.matrix_world @ Vector(c)).z for c in brk.bound_box)
h_in = (bb - sb) / INCH
chk("bracket_bottom_48in_above_skid", abs(h_in - 48.0) <= 0.02,
    "bracket bottom Z=%.2f mm, skid bottom Z=%.2f mm -> %.4f in" % (bb*MM, sb*MM, h_in))

# ---- mate plane: bracket face antiparallel & coincident with upright LBU-PP.001 face
up = bpy.data.objects.get("LBU-PP.001")
def best_face(o, sign_y, want_pos_z):
    """Largest-area face with outward normal mostly +/-Y, tilted with/against +Z.
    Upright engine-side face: normal (0,-1,+0.05) -> sign_y=-1, want_pos_z=True.
    Bracket mating face:     normal (0,+1,-0.05) -> sign_y=+1, want_pos_z=False."""
    mw = o.matrix_world; nrm = mw.to_3x3().inverted().transposed()
    best = None
    for p in o.data.polygons:
        if p.area <= 0: continue
        n = (nrm @ p.normal).normalized()
        if n.y * sign_y < 0.98: continue
        if (n.z > 0) != want_pos_z or abs(n.z) > 0.3: continue
        if best is None or p.area > best[0]: best = (p.area, n, mw @ p.center)
    return best
fu = best_face(up, -1.0, True)
fb = best_face(brk, +1.0, False)
chk("mate_faces_found", fu is not None and fb is not None,
    "upright n=%s, bracket n=%s" %
    ([round(v, 4) for v in fu[1]] if fu else None,
     [round(v, 4) for v in fb[1]] if fb else None))
if fu and fb:
    dot = fu[1].dot(fb[1])
    sep = abs(fu[1].dot(fu[2] - fb[2])) * MM
    chk("mate_normals_antiparallel", dot <= -0.9999,
        "-Nu.Nb=%.8f (%.4f deg off; upright taper ~2.87 deg off vertical)" %
        (-dot, np.degrees(np.arccos(min(1.0, -dot)))))
    chk("mate_planes_coincident", sep <= 0.5, "plane separation %.4f mm" % sep)

# ---- pump shaft 1207517913 unchanged
a, b = s9["1207517913"], s10["1207517913"]
chk("pump_shaft_unchanged",
    a["digest"] == b["digest"] and a["matrix"] == b["matrix"] and a["min"] == b["min"],
    "digest/matrix/bbox identical; bbox_min_v9=%s" % a["min"])

R["verdict"] = "PASS" if not viol else "FAIL"
R["summary"] = {"controller_delta_mm": [round(v*MM, 3) for v in t0] if t0 else None,
                "bracket_height_in": round(h_in, 4), "violations": viol}
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(R, f, indent=1)
print("REPORT ->", OUT)
print("VERDICT", R["verdict"])
sys.stdout.flush(); os._exit(0 if not viol else 3)