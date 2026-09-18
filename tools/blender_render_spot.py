import bpy, os, sys
from mathutils import Vector
argv = sys.argv[sys.argv.index("--") + 1:]
outdir = os.path.abspath(argv[0]); name = argv[1]
loc = tuple(float(v) for v in argv[2:5]); tgt = tuple(float(v) for v in argv[5:8])
ortho = float(argv[8]) if len(argv) > 8 else None
COLORS = {"CAD_bale": (1.0, 0.15, 0.10, 1), "CAD_skid": (0.15, 0.40, 1.0, 1),
          "CAD_pump": (0.10, 0.80, 0.90, 1),
          "CAD_pump_new": (0.10, 0.85, 0.25, 1), "CAD_engine": (0.60, 0.60, 0.60, 1),
          "CAD_controller": (1.0, 0.65, 0.05, 1)}
for c in bpy.data.collections:
    if "QUARANTINE" in c.name.upper() or "OUTLIER" in c.name.upper():
        c.hide_render = True; c.hide_viewport = True
for o in bpy.data.objects:
    if o.type == "MESH":
        o.color = COLORS.get(o.users_collection[0].name if o.users_collection else "", (0.85, 0.85, 0.85, 1))
sc = bpy.context.scene
sc.render.engine = "BLENDER_WORKBENCH"
sc.display.shading.light = "STUDIO"; sc.display.shading.color_type = "OBJECT"
sc.display.shading.show_shadows = True; sc.display.shading.show_cavity = True
sc.render.resolution_x = 1600; sc.render.resolution_y = 1100
sc.world = sc.world or bpy.data.worlds.new("W"); sc.world.color = (0.16, 0.16, 0.18)
cd = bpy.data.cameras.new("C"); cam = bpy.data.objects.new("C", cd)
sc.collection.objects.link(cam); sc.camera = cam
cam.location = Vector(loc)
cam.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
if ortho: cd.type = "ORTHO"; cd.ortho_scale = ortho
else: cd.type = "PERSP"; cd.lens = 45
os.makedirs(outdir, exist_ok=True)
sc.render.filepath = os.path.join(outdir, name + ".png")
bpy.ops.render.render(write_still=True)
print("rendered", sc.render.filepath)
