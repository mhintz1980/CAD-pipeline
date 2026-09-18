"""Report dominant face-normal directions (and their tilt from vertical) per object."""
import bpy, sys, math
from mathutils import Vector
names = sys.argv[sys.argv.index("--") + 1:]
for nm in names:
    o = bpy.data.objects.get(nm)
    if not o:
        print(f"{nm}: NOT FOUND"); continue
    mw = o.matrix_world
    nrm = mw.to_3x3().inverted().transposed()
    groups = {}
    for p in o.data.polygons:
        n = (nrm @ p.normal).normalized()
        a = p.area
        key = (round(n.x, 2), round(n.y, 2), round(n.z, 2))
        g = groups.setdefault(key, {"area": 0.0, "n": 0})
        g["area"] += a; g["n"] += 1
    print(f"\n=== {nm}  polys={len(o.data.polygons)}  verts={len(o.data.vertices)}")
    print(f"  {'normal (x,y,z)':>22} {'count':>7} {'area_mm2':>11}   tilt from Z-axis")
    for k, g in sorted(groups.items(), key=lambda kv: -kv[1]["area"])[:10]:
        nz = max(-1.0, min(1.0, k[2]))
        tilt = math.degrees(math.acos(abs(nz)))
        print(f"  ({k[0]:5.2f},{k[1]:5.2f},{k[2]:5.2f}) {g['n']:7} {g['area']*1e6:11.0f}   {tilt:6.2f} deg")
