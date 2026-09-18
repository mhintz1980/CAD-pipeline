"""Apply an explicit XYZ translation to the pump group. Writes a NEW file so the
previous version stays intact as a reference.

  blender --background IN.blend --python tools/blender_nudge_pump.py -- DX DY DZ OUT.blend OUT.glb
"""
import bpy, os, sys
from mathutils import Vector, Matrix
argv = sys.argv[sys.argv.index("--") + 1:]
dx, dy, dz = (float(argv[0]), float(argv[1]), float(argv[2]))
out_blend, out_glb = os.path.abspath(argv[3]), os.path.abspath(argv[4])

pc = bpy.data.collections["CAD_pump_new"]
names = {o.name for o in pc.objects}
roots = [o for o in pc.objects if o.parent is None or o.parent.name not in names]
print(f"pump roots: {[o.name for o in roots]}")

def bbox():
    lo = Vector((1e9,)*3); hi = Vector((-1e9,)*3)
    for o in pc.objects:
        if o.type != "MESH":
            continue
        for c in o.bound_box:
            p = o.matrix_world @ Vector(c)
            for i in range(3):
                lo[i] = min(lo[i], p[i]); hi[i] = max(hi[i], p[i])
    return lo, hi

def shaft():
    pts = [r.matrix_world @ Vector((0.0, 0.0, 0.0)) for r in roots]
    n = len(pts)
    return Vector((sum(p.x for p in pts)/n, sum(p.y for p in pts)/n, sum(p.z for p in pts)/n))

s0 = shaft(); lo0, hi0 = bbox()
print(f"before  shaft X={s0.x*1000:+.1f} Z={s0.z*1000:+.1f} mm   "
      f"bbox X[{lo0.x*1000:.0f},{hi0.x*1000:.0f}] Y[{lo0.y*1000:.0f},{hi0.y*1000:.0f}] Z[{lo0.z*1000:.0f},{hi0.z*1000:.0f}]")

T = Matrix.Translation((dx, dy, dz))
for r in roots:
    r.matrix_world = T @ r.matrix_world
bpy.context.view_layer.update()

s1 = shaft(); lo1, hi1 = bbox()
print(f"moved   dX={dx*1000:+.1f} dY={dy*1000:+.1f} dZ={dz*1000:+.1f} mm")
print(f"after   shaft X={s1.x*1000:+.1f} Z={s1.z*1000:+.1f} mm   "
      f"bbox X[{lo1.x*1000:.0f},{hi1.x*1000:.0f}] Y[{lo1.y*1000:.0f},{hi1.y*1000:.0f}] Z[{lo1.z*1000:.0f},{hi1.z*1000:.0f}]")

bpy.ops.wm.save_as_mainfile(filepath=out_blend)
print("saved", out_blend)
bpy.ops.export_scene.gltf(filepath=out_glb, export_format="GLB", use_selection=False)
print("exported", out_glb, os.path.getsize(out_glb))
