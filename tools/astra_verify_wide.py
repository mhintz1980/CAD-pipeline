"""Independent wide-scene verifier: v10 baseline vs v11-wide candidate.
Usage: blender -b -P tools/astra_verify_wide.py -- --baseline X --candidate Y --report Z
Exit 0 only if every structural check passes. Never saves blends.
Internal units scene metres; all compared values in mm.
"""
import bpy, json, hashlib, os, sys
import numpy as np
from collections import Counter

TOL = 0.1
SHIFT = 76.2
GROW = 152.4
CUT_LO, CUT_HI = -680.0, 798.0
MM = 1000.0

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
def arg(name):
    return argv[argv.index(name) + 1] if name in argv else None
BASE = arg("--baseline"); CAND = arg("--candidate"); REPORT = arg("--report")
if not (BASE and CAND and REPORT):
    print("FATAL: --baseline/--candidate/--report required"); sys.exit(2)

def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

FAILS, CHECKS = [], []
def check(name, ok, detail=""):
    CHECKS.append({"check": name, "ok": bool(ok), "detail": detail})
    if not ok:
        FAILS.append(name + ": " + detail)
    print(("PASS " if ok else "FAIL ") + name + (" | " + detail if detail else ""))

def snapshot(path):
    bpy.ops.wm.open_mainfile(filepath=path)
    S = {"meta": {"path": path, "sha256": sha256(path)}, "objects": {}}
    for ob in bpy.data.objects:
        if ob.type != "MESH":
            continue
        me = ob.data
        verts = np.empty(len(me.vertices) * 3, dtype=np.float64)
        me.vertices.foreach_get("co", verts)
        verts = verts.reshape(-1, 3)
        loops = np.empty(len(me.loops), dtype=np.int32)
        me.loops.foreach_get("vertex_index", loops)
        me.calc_loop_triangles()
        lt = me.loop_triangles
        tris = None
        if len(lt):
            tris = np.empty(len(lt) * 3, dtype=np.int32)
            lt.foreach_get("vertices", tris)
            tris = tris.reshape(-1, 3)
        mw = np.array(ob.matrix_world, dtype=np.float64)
        world = (verts @ mw[:3, :3].T + mw[:3, 3]) * MM
        S["objects"][ob.name] = {
            "local": verts, "world": world,
            "loops_n": len(loops),
            "loops_sig": hashlib.sha256(loops.tobytes()).hexdigest(),
            "tris_n": 0 if tris is None else len(tris), "tris": tris,
            "matrix_world": mw.tolist(),
            "parent": ob.parent.name if ob.parent else None,
            "hidden": bool(ob.hide_get()),
            "hide_viewport": bool(ob.hide_viewport),
            "collections": sorted(c.name for c in ob.users_collection),
            "materials": [m.name if m else None for m in me.materials],
        }
    S["names"] = set(S["objects"])
    return S

print("Loading baseline", BASE)
A = snapshot(BASE)
base_hash = A["meta"]["sha256"]
print("Loading candidate", CAND)
B = snapshot(CAND)
cand_hash = B["meta"]["sha256"]

check("object sets identical", A["names"] == B["names"],
      "only-base=" + str(sorted(A["names"] - B["names"])[:5]) +
      " only-cand=" + str(sorted(B["names"] - A["names"])[:5]))
check("candidate differs from baseline file (not stale copy)",
      base_hash != cand_hash, base_hash[:12] + " vs " + cand_hash[:12])
check("expected mesh count 468", len(A["objects"]) == 468, "n=%d" % len(A["objects"]))

def is_sub(n, *subs):
    nl = n.lower()
    return any(s.lower() in nl for s in subs)

SIDE_PATTERNS = ["MC CHANNEL", "MC-CHANNEL", "MC_CHANNEL", "PP-FTS-1005", "PP-FBS"]
LEN_PATTERNS = ["PP-FTT", "PP-FTS-1008", "PART11^PP128-FTA", "PART1^PP128-PP108-SKID",
                "TR12X6X0.25X80", "LBA-CB"]
cls = {}
for n in A["names"]:
    o = A["objects"][n]
    cname = " ".join(o["collections"]) + " " + n
    if is_sub(cname, "CAD_controller"):
        cls[n] = "controller"
    elif is_sub(cname, *SIDE_PATTERNS):
        cls[n] = "side"
    elif is_sub(n, *LEN_PATTERNS):
        cls[n] = "lengthened"
    else:
        cls[n] = "fixed"
cnt = Counter(cls.values())
check("class counts side=20 lengthened=15 controller=3 fixed=430",
      cnt.get("side", 0) == 20 and cnt.get("lengthened", 0) == 15
      and cnt.get("controller", 0) == 3 and cnt.get("fixed", 0) == 430, str(dict(cnt)))

def wdelta(n):
    a, b = A["objects"][n], B["objects"][n]
    if a["world"].shape != b["world"].shape:
        return None
    return b["world"] - a["world"]

side_bad = []
for n in [k for k, v in cls.items() if v == "side"]:
    d = wdelta(n)
    if d is None:
        side_bad.append(n + ":vcount"); continue
    dx = d[:, 0]
    dyz = np.abs(d[:, 1:]).max()
    ok = bool(np.abs(np.abs(dx) - SHIFT).max() <= TOL
              and ((dx > 0).all() or (dx < 0).all()) and dyz <= TOL)
    if not ok:
        side_bad.append("%s:meandx=%.4f,dyz=%.4f" % (n, dx.mean(), dyz))
check("20 side meshes translate uniformly +/-76.2mm X, dYZ=0", not side_bad, str(side_bad[:5]))

ctrl_bad = []
for n in [k for k, v in cls.items() if v == "controller"]:
    d = wdelta(n)
    dx = d[:, 0]
    dyz = np.abs(d[:, 1:]).max()
    if not bool(np.abs(dx + SHIFT).max() <= TOL and dyz <= TOL):
        ctrl_bad.append("%s:meandx=%.4f" % (n, dx.mean()))
check("3 CAD_controller meshes translate -76.2mm X (left upright group), dYZ=0",
      not ctrl_bad, str(ctrl_bad[:5]))

fix_bad = []
for n in [k for k, v in cls.items() if v == "fixed"]:
    d = wdelta(n)
    if d is None or np.abs(d).max() > TOL:
        fix_bad.append(n)
check("fixed meshes (incl 415 pump, 7 engine, DOUBLER, MNT/PLT, PP128S22-MFB) unchanged",
      not fix_bad, str(fix_bad[:5]))

bad = []
for cname in ("CAD_pump_new", "CAD_engine"):
    for n in A["names"]:
        if is_sub(" ".join(A["objects"][n]["collections"]), cname):
            a, b = A["objects"][n], B["objects"][n]
            if a["local"].shape != b["local"].shape \
               or not np.array_equal(a["local"], b["local"]) \
               or a["matrix_world"] != b["matrix_world"]:
                bad.append(n)
check("engine/pump local vertex data + world matrices identical", not bad, str(bad[:5]))

bad = [n for n in A["names"]
       if A["objects"][n]["loops_n"] != B["objects"][n]["loops_n"]
       or A["objects"][n]["tris_n"] != B["objects"][n]["tris_n"]
       or A["objects"][n]["loops_sig"] != B["objects"][n]["loops_sig"]]
check("topology (loop vert indices, tri counts) unchanged for all meshes",
      not bad, str(bad[:5]))

len_bad = []
for n in [k for k, v in cls.items() if v == "lengthened"]:
    a, b = A["objects"][n], B["objects"][n]
    d = b["world"] - a["world"]
    dx = d[:, 0]
    dyz = np.abs(d[:, 1:]).max()
    good = (np.abs(np.abs(dx) - SHIFT) <= TOL) | (np.abs(dx) <= TOL)
    if not (bool(good.all()) and dyz <= TOL):
        len_bad.append(n + ":delta"); continue
    xmax = a["world"][:, 0].max(); xmin = a["world"][:, 0].min()
    top = a["world"][:, 0] >= xmax - TOL
    bot = a["world"][:, 0] <= xmin + TOL
    if not (top.any() and bot.any()):
        len_bad.append(n + ":noends"); continue
    if not (bool((np.abs(dx[top] - SHIFT) <= TOL).all()
                 and (np.abs(dx[bot] + SHIFT) <= TOL).all())):
        len_bad.append(n + ":ends")
check("15 lengthened meshes: deltas in {-76.2,0,+76.2}mm, dYZ=0, ends move outward",
      not len_bad, str(len_bad[:5]))

def cutplane_check(S, label):
    bad = []
    for n, o in S["objects"].items():
        t = o["tris"]
        if t is None or not len(t):
            continue
        w = o["world"]
        tri = w[t]
        for plane in (CUT_LO, CUT_HI):
            x = tri[:, :, 0]
            cross = (x.min(1) < plane) & (x.max(1) > plane)
            if not cross.any():
                continue
            ct = tri[cross]
            nrm = np.cross(ct[:, 1] - ct[:, 0], ct[:, 2] - ct[:, 0])
            ln = np.linalg.norm(nrm, axis=1)
            ln[ln == 0] = 1.0
            nx = np.abs(nrm[:, 0] / ln)
            if (nx > 0.05).any():
                bad.append("%s@%d:maxnx=%.3f(%d)" % (n, plane, nx.max(), int((nx > 0.05).sum())))
    check(label + ": triangles crossing X=%.0f/%.0fmm are planar X-extrusions (normalX~0)"
          % (CUT_LO, CUT_HI), not bad, str(bad[:5]))
cutplane_check(A, "baseline")
cutplane_check(B, "candidate")

def scene_bbox(S):
    lo = np.full(3, np.inf); hi = np.full(3, -np.inf)
    for o in S["objects"].values():
        lo = np.minimum(lo, o["world"].min(0))
        hi = np.maximum(hi, o["world"].max(0))
    return lo, hi
amin_a, amax_a = scene_bbox(A)
amin_b, amax_b = scene_bbox(B)
wa = amax_a[0] - amin_a[0]; wb = amax_b[0] - amin_b[0]
check("overall X width +152.4mm", abs((wb - wa) - GROW) <= TOL,
      "%.3f -> %.3f mm" % (wa, wb))
cen_a = (amax_a[0] + amin_a[0]) / 2; cen_b = (amax_b[0] + amin_b[0]) / 2
check("bbox centre X unchanged", abs(cen_b - cen_a) <= TOL,
      "%.3f -> %.3f mm" % (cen_a, cen_b))
check("scene Y/Z bbox unchanged",
      bool(np.abs(amin_a[1:] - amin_b[1:]).max() <= TOL
           and np.abs(amax_a[1:] - amax_b[1:]).max() <= TOL))

up = [n for n in A["names"] if is_sub(n, "PP128-FTA")]
if len(up) == 2:
    def cx(S, n):
        return S["objects"][n]["world"][:, 0].mean()
    spa = abs(cx(B, up[0]) - cx(B, up[1])) - abs(cx(A, up[0]) - cx(A, up[1]))
    check("upright spacing +152.4mm", abs(spa - GROW) <= TOL, "delta=%.3fmm" % spa)
    d0 = cx(B, up[0]) - cx(A, up[0]); d1 = cx(B, up[1]) - cx(A, up[1])
    check("uprights each exactly outward 76.2mm",
          set(round(v, 1) for v in (d0, d1)) == {-SHIFT, SHIFT},
          "%.2f,%.2f" % (d0, d1))
else:
    check("upright pair found (2x PP128-FTA)", False, "found=%d" % len(up))

check("bale/assembly top height (48in) preserved", abs(amax_a[2] - amax_b[2]) <= TOL,
      "%.2f -> %.2f mm" % (amax_a[2], amax_b[2]))

bad = []
for n in A["names"]:
    a, b = A["objects"][n], B["objects"][n]
    if (a["materials"] != b["materials"] or a["collections"] != b["collections"]
            or a["parent"] != b["parent"] or a["hidden"] != b["hidden"]
            or a["hide_viewport"] != b["hide_viewport"]):
        bad.append(n)
check("materials, collections, parents, visibility metadata unchanged", not bad, str(bad[:5]))

def rigid_bad(S):
    out = set()
    for n, o in S["objects"].items():
        R = np.array(o["matrix_world"])[:3, :3]
        s = np.linalg.norm(R, axis=0)
        if np.abs(s - 1).max() > 1e-4 or abs(np.linalg.det(R) - 1) > 1e-3:
            out.add(n)
    return out
check("no scale/rotation introduced vs baseline", not (rigid_bad(B) - rigid_bad(A)),
      "base_bad=%d cand_bad=%d" % (len(rigid_bad(A)), len(rigid_bad(B))))

grp = [n for n in A["names"] if cls[n] == "controller"]
badrel = []
if len(grp) >= 2:
    ref = grp[0]
    for n in grp[1:]:
        ra = A["objects"][ref]["world"][:, :3] - A["objects"][n]["world"][:, :3]
        rb = B["objects"][ref]["world"][:, :3] - B["objects"][n]["world"][:, :3]
        if np.abs(ra - rb).max() > TOL:
            badrel.append(n)
check("controller internal relative transforms unchanged (rigid group)", not badrel, str(badrel))

rep = {
    "verifier": "tools/astra_verify_wide.py",
    "baseline": {"path": BASE, "sha256": base_hash},
    "candidate": {"path": CAND, "sha256": cand_hash},
    "class_counts": dict(cnt),
    "checks": CHECKS,
    "failures": FAILS,
    "passed": not FAILS,
    "limitations": [
        "Connection/stress integrity, weld/bolt adequacy NOT certified; geometry/transform checks only.",
        "Cut-plane test is a heuristic (crossing tri world normal X~0, tol 0.05); curved longitudinal extrusions accepted when topology unchanged.",
        "No re-simulation of clearances/interference between moved parts.",
        "Baseline defects intentionally not rejected; before/after stats compared only.",
        "Remaining connection tests reported as UNVERIFIED - not full engineering certification.",
    ],
}
d = os.path.dirname(REPORT)
if d:
    os.makedirs(d, exist_ok=True)
with open(REPORT, "w") as f:
    json.dump(rep, f, indent=1)
print("REPORT", REPORT)
print("VERDICT:", "PASS" if not FAILS else "FAIL (%d)" % len(FAILS))
sys.exit(0 if not FAILS else 1)
