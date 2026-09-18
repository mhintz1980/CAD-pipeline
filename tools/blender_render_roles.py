"""Colour-code objects by collection role and render framing views.

  blender --background SCENE.blend --python tools/blender_render_roles.py -- OUTDIR
"""
import bpy, os, sys
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
outdir = os.path.abspath(argv[0]) if argv else os.path.abspath("renders")
os.makedirs(outdir, exist_ok=True)

COLORS = {
    "CAD_bale":       (1.00, 0.15, 0.10, 1.0),   # red
    "CAD_skid":       (0.15, 0.40, 1.00, 1.0),   # blue
    "CAD_pump":       (0.10, 0.85, 0.25, 1.0),   # green
    "CAD_engine":     (0.60, 0.60, 0.60, 1.0),   # grey
    "CAD_controller": (1.00, 0.65, 0.05, 1.0),   # orange
}
for c in bpy.data.collections:
    if "QUARANTINE" in c.name.upper() or "OUTLIER" in c.name.upper():
        c.hide_render = True
        c.hide_viewport = True

for obj in bpy.data.objects:
    if obj.type != "MESH":
        continue
    col = (obj.users_collection[0].name if obj.users_collection else "")
    obj.color = COLORS.get(col, (0.85, 0.85, 0.85, 1.0))

sc = bpy.context.scene
sc.render.engine = "BLENDER_WORKBENCH"
sc.display.shading.light = "STUDIO"
sc.display.shading.color_type = "OBJECT"
sc.display.shading.show_shadows = True
sc.display.shading.show_cavity = True
sc.render.resolution_x = 1600
sc.render.resolution_y = 1100
sc.render.film_transparent = False
sc.world = sc.world or bpy.data.worlds.new("W")
sc.world.color = (0.16, 0.16, 0.18)

cd = bpy.data.cameras.new("C")
cam = bpy.data.objects.new("C", cd)
sc.collection.objects.link(cam)
sc.camera = cam


def shoot(name, loc, target, ortho=None):
    cam.location = Vector(loc)
    d = Vector(target) - Vector(loc)
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    if ortho:
        cd.type = "ORTHO"; cd.ortho_scale = ortho
    else:
        cd.type = "PERSP"; cd.lens = 45
    sc.render.filepath = os.path.join(outdir, name + ".png")
    bpy.ops.render.render(write_still=True)
    print("rendered", name)


shoot("roles-side-+X", (8.0, 0.0, 0.2), (0.0, 0.0, 0.2), ortho=5.6)
shoot("roles-end-+Y", (0.0, 8.0, 0.2), (0.0, 0.0, 0.2), ortho=2.6)
shoot("roles-top", (0.0, 0.0, 8.0), (0.0, 0.0, 0.0), ortho=5.6)
shoot("roles-3q", (4.2, -4.2, 3.0), (0.0, 0.0, 0.3))
shoot("roles-bale-iso", (3.0, -1.6, 1.6), (0.75, 0.0, 0.2))
print("DONE")
