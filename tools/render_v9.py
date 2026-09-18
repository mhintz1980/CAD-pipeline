import bpy, os, sys
from mathutils import Vector
argv = sys.argv[sys.argv.index("--") + 1:]
outdir = os.path.abspath(argv[0])
COLORS = {"CAD_bale": (1.00, 0.15, 0.10, 1), "CAD_skid": (0.15, 0.40, 1.00, 1),
          "CAD_pump": (0.10, 0.80, 0.90, 1), "CAD_pump_new": (0.15, 0.90, 0.25, 1),
          "CAD_engine": (0.62, 0.62, 0.62, 1), "CAD_controller": (1.00, 0.65, 0.05, 1)}
for o in bpy.data.objects:
    if o.type == "MESH":
        c = o.users_collection[0].name if o.users_collection else ""
        o.color = COLORS.get(c, (0.85, 0.85, 0.85, 1))
sc = bpy.context.scene
sc.render.engine = "BLENDER_WORKBENCH"
sc.display.shading.light = "STUDIO"; sc.display.shading.color_type = "OBJECT"
sc.display.shading.show_shadows = True; sc.display.shading.show_cavity = True
sc.render.resolution_x = 1700; sc.render.resolution_y = 1050
sc.world = bpy.data.worlds.new("W"); sc.world.color = (0.16, 0.16, 0.18)
cd = bpy.data.cameras.new("C"); cam = bpy.data.objects.new("C", cd)
sc.collection.objects.link(cam); sc.camera = cam
os.makedirs(outdir, exist_ok=True)
def shoot(name, loc, tgt, ortho=None):
    cam.location = Vector(loc)
    cam.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    if ortho: cd.type = "ORTHO"; cd.ortho_scale = ortho
    else: cd.type = "PERSP"; cd.lens = 42
    sc.render.filepath = os.path.join(outdir, name + ".png")
    bpy.ops.render.render(write_still=True)
    print("rendered", name)
shoot("v9-iso",       (5.2, -5.6, 3.6), (0.0, 0.2, 0.4))
shoot("v9-side",      (9.0,  0.0, 0.35), (0.0, 0.0, 0.35), ortho=5.6)
shoot("v9-top",       (0.059, 0.0, 9.0), (0.059, 0.0, 0.0), ortho=5.6)
shoot("v9-junction",  (3.4,  3.0, 1.5), (0.06, 0.75, 0.1))
shoot("v9-pumpend",   (5.0,  4.2, 1.2), (0.06, 1.3, 0.1))
print("DONE")
