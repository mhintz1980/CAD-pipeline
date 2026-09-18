"""Measure the lifting-bale upright's side taper: Y half-width vs height."""
import bpy, sys
from mathutils import Vector
obj_names = sys.argv[sys.argv.index("--") + 1:]
for nm in obj_names:
    o = bpy.data.objects.get(nm)
    if not o:
        print(f"{nm}: NOT FOUND"); continue
    mw = o.matrix_world
    pts = [mw @ v.co for v in o.data.vertices]
    zs = [p.z for p in pts]
    lo, hi = min(zs), max(zs)
    print(f"\n=== {nm}  verts={len(pts)}  Z {lo*1000:.0f}..{hi*1000:.0f} mm  X {min(p.x for p in pts)*1000:.0f}..{max(p.x for p in pts)*1000:.0f}")
    print(f"  {'Z band (mm)':>16} {'n':>5} {'|Y| max':>9} {'X min':>8} {'X max':>8}")
    NB = 12
    for i in range(NB):
        a = lo + (hi - lo) * i / NB
        b = lo + (hi - lo) * (i + 1) / NB
        band = [p for p in pts if a <= p.z < b]
        if not band:
            print(f"  {a*1000:7.0f}..{b*1000:7.0f} {0:5}      -        -        -"); continue
        ymax = max(abs(p.y) for p in band)
        print(f"  {a*1000:7.0f}..{b*1000:7.0f} {len(band):5} {ymax*1000:9.1f} "
              f"{min(p.x for p in band)*1000:8.1f} {max(p.x for p in band)*1000:8.1f}")
