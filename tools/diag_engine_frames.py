import bpy, sys
from mathutils import Vector
tag = sys.argv[sys.argv.index("--") + 1]
objs = [o for o in bpy.data.objects if o.type == "MESH"]
eng = [o for o in objs if "3336180" in o.name.upper() or "3336180ci510" in o.name.upper()]
print(f"[{tag}] engine-ish objects: {[(o.name, o.parent.name if o.parent else None) for o in eng]}")
for o in eng[:2]:
    print(f"  {o.name}")
    print(f"    matrix_world:\n{o.matrix_world}")
    lo = Vector((1e9,)*3); hi = Vector((-1e9,)*3)
    for c in o.bound_box:
        p = o.matrix_world @ Vector(c)
        for i in range(3):
            lo[i] = min(lo[i], p[i]); hi[i] = max(hi[i], p[i])
    print(f"    world bbox X[{lo.x*1000:.0f},{hi.x*1000:.0f}] Y[{lo.y*1000:.0f},{hi.y*1000:.0f}] Z[{lo.z*1000:.0f},{hi.z*1000:.0f}]")
    print(f"    local bbox X[{min(c[0] for c in o.bound_box)*1000:.0f},{max(c[0] for c in o.bound_box)*1000:.0f}] "
          f"Y[{min(c[1] for c in o.bound_box)*1000:.0f},{max(c[1] for c in o.bound_box)*1000:.0f}] "
          f"Z[{min(c[2] for c in o.bound_box)*1000:.0f},{max(c[2] for c in o.bound_box)*1000:.0f}]")
