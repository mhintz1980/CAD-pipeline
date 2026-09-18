"""Render framing views of a .blend. Read-only (never saves the .blend).

  blender --background SCENE.blend --python tools/blender_render_views.py -- OUTDIR
"""
import bpy, math, sys, os
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
outdir = os.path.abspath(argv[0]) if argv else os.path.abspath("renders")
os.makedirs(outdir, exist_ok=True)

# Quarantined outliers must not appear in a framing render.
for c in bpy.data.collections:
    if "QUARANTINE" in c.name.upper() or "OUTLIER" in c.name.upper():
        c.hide_render = True
        c.hide_viewport = True
        print("hidden collection:", c.name)

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
sc.world.color = (0.18, 0.18, 0.2)

cam_data = bpy.data.cameras.new("FramingCam")
cam = bpy.data.objects.new("FramingCam", cam_data)
sc.collection.objects.link(cam)
sc.camera = cam


def shoot(name, loc, target, ortho=None):
    cam.location = Vector(loc)
    d = Vector(target) - Vector(loc)
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    if ortho:
        cam_data.type = "ORTHO"
        cam_data.ortho_scale = ortho
    else:
        cam_data.type = "PERSP"
        cam_data.lens = 50
    sc.render.filepath = os.path.join(outdir, name + ".png")
    bpy.ops.render.render(write_still=True)
    print("rendered", sc.render.filepath)


# Right-hand bale/skid junction: look along -X at the +X side.
shoot("bale-right-elev", (6.0, 0.0, 0.7), (0.88, 0.0, 0.7), ortho=1.6)
# Left-hand counterpart.
shoot("bale-left-elev", (-6.0, 0.0, 0.7), (-0.88, 0.0, 0.7), ortho=1.6)
# Close-up of the bolt-plate zone (PP-LBB sits Z -493..-302 mm).
shoot("plate-closeup", (4.0, 0.0, -0.40), (0.88, 0.0, -0.40), ortho=0.7)
# Three-quarter overview, bale end.
shoot("overview-3q", (4.6, -4.6, 3.4), (0.0, 0.0, 0.4))
# Long-side elevation to judge upright vs skid wall along the length.
shoot("side-elev-full", (6.5, 0.0, 0.4), (0.0, 0.0, 0.4), ortho=5.4)
print("DONE")
