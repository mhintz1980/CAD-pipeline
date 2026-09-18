"""Group an object's faces by normal and report each group's area-weighted centroid."""
import bpy, sys, math
from mathutils import Vector
names = sys.argv[sys.argv.index("--") + 1:]
for nm in names:
    o = bpy.data.objects.get(nm)
    if o is None:
        print(f"{nm}: NOT FOUND"); continue
    mw = o.matrix_world
    nrm = mw.to_3x3().inverted().transposed()
    g = {}
    for p in o.data.polygons:
        n = (nrm @ p.normal).normalized()
        key = (round(n.x, 2), round(n.y, 2), round(n.z, 2))
        c = mw @ p.center
        e = g.setdefault(key, {"a": 0.0, "n": 0, "cx": 0.0, "cy": 0.0, "cz": 0.0})
        e["a"] += p.area; e["n"] += 1
        e["cx"] += c.x * p.area; e["cy"] += c.y * p.area; e["cz"] += c.z * p.area
    print(f"\n=== {nm}  ({len(o.data.polygons)} polys)")
    print(f"  {'normal':>22} {'n':>6} {'area_mm2':>10} {'centroid X':>11} {'Y':>11} {'Z':>11}")
    for k, e in sorted(g.items(), key=lambda kv: -kv[1]["a"])[:8]:
        a = e["a"] or 1
        print(f"  ({k[0]:5.2f},{k[1]:5.2f},{k[2]:5.2f}) {e['n']:6} {e['a']*1e6:10.0f} "
              f"{e['cx']/a*1000:11.1f} {e['cy']/a*1000:11.1f} {e['cz']/a*1000:11.1f}")
