"""Place the pump provisionally, coaxial with the engine crank (both shafts on Y).

  blender --background IN.blend --python tools/blender_place_pump.py -- PUMP.glb OUT.blend OUT.glb
"""
import bpy, os, sys, math
from mathutils import Vector, Matrix
argv = sys.argv[sys.argv.index("--") + 1:]
pump_glb, out_blend, out_glb = (os.path.abspath(argv[0]), os.path.abspath(argv[1]),
                                os.path.abspath(argv[2]))

# 1. drop the duplicate engine - it is only in the way
for c in list(bpy.data.collections):
    if "QUARANTINE" in c.name.upper() or "OUTLIER" in c.name.upper():
        for o in list(c.objects):
            bpy.data.objects.remove(o, do_unlink=True)
        bpy.data.collections.remove(c)

before = {o.name for o in bpy.data.objects}
bpy.ops.import_scene.gltf(filepath=pump_glb)
pump_objs = [o for o in bpy.data.objects if o.name not in before]
print(f"pump objects imported: {len(pump_objs)}")

pc = bpy.data.collections.new("CAD_pump_new")
bpy.context.scene.collection.children.link(pc)
for o in pump_objs:
    for c in list(o.users_collection):
        c.objects.unlink(o)
    pc.objects.link(o)

# 2. rigid move: rotate +90 deg about Z so the pump shaft (local X) becomes Y,
#    input-shaft end (-X) turning to face -Y, i.e. toward the engine.
#    Rotation is applied about the pump's own centroid, then translated.
lo = Vector((1e9,) * 3); hi = Vector((-1e9,) * 3)
for o in pump_objs:
    for c in o.bound_box:
        p = o.matrix_world @ Vector(c)
        for i in range(3):
            lo[i] = min(lo[i], p[i]); hi[i] = max(hi[i], p[i])
ctr = (lo + hi) / 2
print(f"pump bbox before: min={[round(v,3) for v in lo]} max={[round(v,3) for v in hi]}")

# glTF import parents the meshes under a root empty. Transforming every
# object would double-apply the move, so only the roots are touched.
roots = [o for o in pump_objs if o.parent not in pump_objs]
print(f"pump roots: {len(roots)} of {len(pump_objs)} objects")

R = Matrix.Rotation(math.radians(90.0), 4, 'Z')
P = Matrix.Translation(ctr) @ R @ Matrix.Translation(-ctr)

# target: shaft end sits just off the engine's +Y face, on the skid centreline,
# at crankshaft height. Provisional - Mark will correct from the render.
TARGET_SHAFT_Y = 0.509      # engine max Y (flywheel face), metres
TARGET_X = 0.059            # skid longitudinal centreline
TARGET_Z = 0.100            # provisional crank height

for o in roots:
    o.matrix_world = P @ o.matrix_world
bpy.context.view_layer.update()

lo2 = Vector((1e9,) * 3); hi2 = Vector((-1e9,) * 3)
for o in pump_objs:
    for c in o.bound_box:
        p = o.matrix_world @ Vector(c)
        for i in range(3):
            lo2[i] = min(lo2[i], p[i]); hi2[i] = max(hi2[i], p[i])
print(f"pump bbox after rotate: min={[round(v,3) for v in lo2]} max={[round(v,3) for v in hi2]}")

# after +90 deg the input end (was min X) is now min Y
dy = TARGET_SHAFT_Y - lo2[1]
dx = TARGET_X - (lo2[0] + hi2[0]) / 2
dz = TARGET_Z - (lo2[2] + hi2[2]) / 2
T = Matrix.Translation((dx, dy, dz))
for o in roots:
    o.matrix_world = T @ o.matrix_world
bpy.context.view_layer.update()

lo3 = Vector((1e9,) * 3); hi3 = Vector((-1e9,) * 3)
for o in pump_objs:
    for c in o.bound_box:
        p = o.matrix_world @ Vector(c)
        for i in range(3):
            lo3[i] = min(lo3[i], p[i]); hi3[i] = max(hi3[i], p[i])
print(f"pump bbox placed:  min={[round(v,3) for v in lo3]} max={[round(v,3) for v in hi3]}")
print(f"translation applied: dx={dx:.3f} dy={dy:.3f} dz={dz:.3f}")

bpy.ops.wm.save_as_mainfile(filepath=out_blend)
print("saved", out_blend)
bpy.ops.export_scene.gltf(filepath=out_glb, export_format="GLB", use_selection=False)
print("exported", out_glb, os.path.getsize(out_glb))
