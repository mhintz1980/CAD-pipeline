"""Shift the lifting-bale assembly along X so it centres on the skid.

The uprights are symmetric about X=0; the skid's side structure is symmetric
about X=+59 mm. Moving the whole bale +59 mm puts both bolt plates against the
inner faces of the skid side walls. Writes a NEW file - v3 is left untouched.

  blender --background IN.blend --python tools/blender_shift_bale.py -- DX_M OUT.blend OUT.glb
"""
import bpy, os, sys

argv = sys.argv[sys.argv.index("--") + 1:]
dx = float(argv[0]); out_blend = os.path.abspath(argv[1]); out_glb = os.path.abspath(argv[2])

for c in bpy.data.collections:
    if "QUARANTINE" in c.name.upper() or "OUTLIER" in c.name.upper():
        c.hide_render = True
        c.hide_viewport = True

bale = bpy.data.collections.get("CAD_bale")
if bale is None:
    raise SystemExit("CAD_bale collection not found")

moved = 0
for obj in bale.objects:
    if obj.type != "MESH":
        continue
    before = obj.matrix_world.translation.x
    m = obj.matrix_world.copy()
    m.translation.x += dx
    obj.matrix_world = m
    bpy.context.view_layer.update()
    print(f"  {obj.name:22} X {before:+.5f} -> {obj.matrix_world.translation.x:+.5f}")
    moved += 1
print(f"moved {moved} bale objects by {dx*1000:+.1f} mm")

bpy.ops.wm.save_as_mainfile(filepath=out_blend)
print("saved", out_blend)

bpy.ops.export_scene.gltf(filepath=out_glb, export_format="GLB",
                          use_selection=False, export_apply=False)
print("exported", out_glb, os.path.getsize(out_glb))
