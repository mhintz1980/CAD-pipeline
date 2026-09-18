import bpy
from mathutils import Vector
pc = bpy.data.collections.get("CAD_pump_new")
def bb(objs):
    lo = Vector((1e9,)*3); hi = Vector((-1e9,)*3)
    for o in objs:
        if o.type != "MESH": continue
        for c in o.bound_box:
            p = o.matrix_world @ Vector(c)
            for i in range(3):
                lo[i] = min(lo[i], p[i]); hi[i] = max(hi[i], p[i])
    return lo, hi
if pc:
    lo, hi = bb(pc.objects)
    print(f"PUMP  X[{lo.x*1000:.0f},{hi.x*1000:.0f}] Y[{lo.y*1000:.0f},{hi.y*1000:.0f}] Z[{lo.z*1000:.0f},{hi.z*1000:.0f}] mm")
allm = [o for o in bpy.data.objects if o.type == "MESH" and "QUARANTINE" not in [c.name for c in o.users_collection]]
lo, hi = bb(allm)
print(f"SCENE X[{lo.x*1000:.0f},{hi.x*1000:.0f}] Y[{lo.y*1000:.0f},{hi.y*1000:.0f}] Z[{lo.z*1000:.0f},{hi.z*1000:.0f}] mm")
eng = [o for o in allm if "CAD_engine" in [c.name for c in o.users_collection]]
lo, hi = bb(eng)
print(f"ENGINE X[{lo.x*1000:.0f},{hi.x*1000:.0f}] Y[{lo.y*1000:.0f},{hi.y*1000:.0f}] Z[{lo.z*1000:.0f},{hi.z*1000:.0f}] mm")
tri = 0
for o in allm:
    o.data.calc_loop_triangles(); tri += len(o.data.loop_triangles)
print(f"TOTAL TRIANGLES {tri:,}   meshes={len(allm)}")
