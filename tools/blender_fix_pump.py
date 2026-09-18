"""Rotate the pump 180 deg about its own drive-shaft axis (parallel to Y), then
centre that axis on the machine width to match the engine.

  blender --background v5.blend --python tools/blender_fix_pump.py -- OUT.blend OUT.glb
"""
import bpy, os, sys, math
from mathutils import Vector, Matrix
argv = sys.argv[sys.argv.index("--") + 1:]
out_blend, out_glb = os.path.abspath(argv[0]), os.path.abspath(argv[1])

# ---- current pump shaft axis, from the pump's own rotor bores -------------
# established by measurement of the source STEP: in pump-local coords the rotor
# bores lie on the line (t, 0, 0).  The pump was rotated +90 deg about Z, so that
# line became an axis parallel to Y passing through world (0, *, 0) BEFORE the
# placement translation.  Recover it from the objects' known transform instead of
# re-deriving:  the previous run applied dx=-0.225 dy=+0.843 dz=+0.214.
SHAFT_X = -0.2255
SHAFT_Z = 0.2145

pc = bpy.data.collections.get("CAD_pump_new")
if pc is None:
    raise SystemExit("CAD_pump_new not found")
objs = [o for o in pc.objects if o.type == "MESH"]
pc_names = {o.name for o in pc.objects}
roots = [o for o in pc.objects if o.parent is None or o.parent.name not in pc_names]
print(f"pump: {len(objs)} meshes, {len(roots)} roots")

# engine reference: its bbox centre in X is the machine-width datum
eng = bpy.data.objects.get("3336180ci510-interfaces-v5-64MB.001")
elo = Vector((1e9,) * 3); ehi = Vector((-1e9,) * 3)
for c in eng.bound_box:
    p = eng.matrix_world @ Vector(c)
    for i in range(3):
        elo[i] = min(elo[i], p[i]); ehi[i] = max(ehi[i], p[i])
ENG_X = (elo.x + ehi.x) / 2
print(f"engine bbox X {elo.x*1000:.1f}..{ehi.x*1000:.1f} -> centre {ENG_X*1000:.1f} mm")

# ---- 180 deg about the shaft axis line (X=SHAFT_X, Z=SHAFT_Z, dir Y) ------
axis_pt = Vector((SHAFT_X, 0.0, SHAFT_Z))
R = Matrix.Rotation(math.radians(180.0), 4, 'Y')
P = Matrix.Translation(axis_pt) @ R @ Matrix.Translation(-axis_pt)
for o in roots:
    o.matrix_world = P @ o.matrix_world
bpy.context.view_layer.update()

# ---- slide along X so the shaft lands on the engine centreline -----------
dx = ENG_X - SHAFT_X
T = Matrix.Translation((dx, 0.0, 0.0))
for o in roots:
    o.matrix_world = T @ o.matrix_world
bpy.context.view_layer.update()
print(f"shaft X {SHAFT_X*1000:.1f} -> {ENG_X*1000:.1f} mm  (dx={dx*1000:+.1f} mm)")

lo = Vector((1e9,) * 3); hi = Vector((-1e9,) * 3)
for o in objs:
    for c in o.bound_box:
        p = o.matrix_world @ Vector(c)
        for i in range(3):
            lo[i] = min(lo[i], p[i]); hi[i] = max(hi[i], p[i])
print(f"pump bbox now: X[{lo.x*1000:.0f},{hi.x*1000:.0f}] Y[{lo.y*1000:.0f},{hi.y*1000:.0f}] Z[{lo.z*1000:.0f},{hi.z*1000:.0f}] mm")
print(f"shaft now at X={ENG_X*1000:.1f} mm, Z={SHAFT_Z*1000:.1f} mm")

bpy.ops.wm.save_as_mainfile(filepath=out_blend)
print("saved", out_blend)
bpy.ops.export_scene.gltf(filepath=out_glb, export_format="GLB", use_selection=False)
print("exported", out_glb, os.path.getsize(out_glb))
