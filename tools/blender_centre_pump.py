"""Centre the pump's real rotor/shaft axis on the engine centreline.

The previous pass used the pump's BBOX centre as if it were the shaft - wrong.
The shaft is the line through the pump's own local origin (local y=0, z=0, the
rotor bores). The glTF root's matrix_world maps pump-local space to world, so
transforming local (0,0,0) lands exactly on that axis.

  blender --background v6.blend --python tools/blender_centre_pump.py -- OUT.blend OUT.glb
"""
import bpy, os, sys
from mathutils import Vector, Matrix
argv = sys.argv[sys.argv.index("--") + 1:]
out_blend, out_glb = os.path.abspath(argv[0]), os.path.abspath(argv[1])

pc = bpy.data.collections["CAD_pump_new"]
pc_names = {o.name for o in pc.objects}
roots = [o for o in pc.objects if o.parent is None or o.parent.name not in pc_names]
print(f"pump roots: {len(roots)}")

def shaft_point():
    """World position of the pump-local origin = a point on the rotor-shaft axis."""
    pts = [r.matrix_world @ Vector((0.0, 0.0, 0.0)) for r in roots]
    n = len(pts)
    return Vector((sum(p.x for p in pts) / n,
                   sum(p.y for p in pts) / n,
                   sum(p.z for p in pts) / n))

s0 = shaft_point()
print(f"shaft axis BEFORE: X={s0.x*1000:+.1f}  Z={s0.z*1000:+.1f} mm   (Y={s0.y*1000:+.1f})")

eng = bpy.data.objects["3336180ci510-interfaces-v5-64MB.001"]
elo = Vector((1e9,) * 3); ehi = Vector((-1e9,) * 3)
for c in eng.bound_box:
    p = eng.matrix_world @ Vector(c)
    for i in range(3):
        elo[i] = min(elo[i], p[i]); ehi[i] = max(ehi[i], p[i])
TARGET_X = (elo.x + ehi.x) / 2
print(f"engine centreline X = {TARGET_X*1000:+.1f} mm")

dx = TARGET_X - s0.x
T = Matrix.Translation((dx, 0.0, 0.0))
for r in roots:
    r.matrix_world = T @ r.matrix_world
bpy.context.view_layer.update()

s1 = shaft_point()
print(f"shift applied dx = {dx*1000:+.1f} mm")
print(f"shaft axis AFTER : X={s1.x*1000:+.1f}  Z={s1.z*1000:+.1f} mm")

lo = Vector((1e9,) * 3); hi = Vector((-1e9,) * 3)
for o in pc.objects:
    if o.type != "MESH":
        continue
    for c in o.bound_box:
        p = o.matrix_world @ Vector(c)
        for i in range(3):
            lo[i] = min(lo[i], p[i]); hi[i] = max(hi[i], p[i])
print(f"pump bbox: X[{lo.x*1000:.0f},{hi.x*1000:.0f}] Y[{lo.y*1000:.0f},{hi.y*1000:.0f}] Z[{lo.z*1000:.0f},{hi.z*1000:.0f}] mm")

bpy.ops.wm.save_as_mainfile(filepath=out_blend)
print("saved", out_blend)
bpy.ops.export_scene.gltf(filepath=out_glb, export_format="GLB", use_selection=False)
print("exported", out_glb, os.path.getsize(out_glb))
