"""Export a GLB with the quarantine collection deleted (not merely hidden).

Blender's view-layer exclusion does NOT stop the glTF exporter - hidden
objects still reach the file. Deleting them is the only reliable way.

  blender --background IN.blend --python tools/blender_export_clean.py -- OUT.glb
"""
import bpy, os, sys
out = os.path.abspath(sys.argv[sys.argv.index("--") + 1])

removed = []
for c in list(bpy.data.collections):
    if "QUARANTINE" in c.name.upper() or "OUTLIER" in c.name.upper():
        for o in list(c.objects):
            removed.append(o.name)
            bpy.data.objects.remove(o, do_unlink=True)
        bpy.data.collections.remove(c)
print("removed:", removed)

bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", use_selection=False)
print("exported", out, os.path.getsize(out))
