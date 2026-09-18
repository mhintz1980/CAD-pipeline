"""Import a GLB into an empty scene, report world bbox / part count, render views."""
import bpy, os, sys, math
from mathutils import Vector
argv = sys.argv[sys.argv.index("--") + 1:]
glb, outdir, tag = os.path.abspath(argv[0]), os.path.abspath(argv[1]), argv[2]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=glb)
meshes = [o for o in bpy.data.objects if o.type == "MESH"]
lo = [math.inf] * 3; hi = [-math.inf] * 3
tri = 0
for o in meshes:
    mw = o.matrix_world
    for c in o.bound_box:
        p = mw @ Vector(c)
        for i in range(3):
            lo[i] = min(lo[i], p[i]); hi[i] = max(hi[i], p[i])
    o.data.calc_loop_triangles()
    tri += len(o.data.loop_triangles)
print(f"PARTS {len(meshes)}  TRIS {tri:,}")
print(f"BBOX min {[round(v,4) for v in lo]}")
print(f"BBOX max {[round(v,4) for v in hi]}")
print(f"BBOX size {[round(hi[i]-lo[i],4) for i in range(3)]}")

for o in meshes:
    o.color = (0.75, 0.75, 0.78, 1)
# colour the largest few distinctly so structure reads
meshes.sort(key=lambda o: -(o.dimensions.x * o.dimensions.y * o.dimensions.z))
pal = [(0.95, 0.35, 0.20, 1), (0.20, 0.55, 0.95, 1), (0.25, 0.80, 0.40, 1),
       (0.95, 0.75, 0.15, 1), (0.70, 0.35, 0.90, 1)]
for i, o in enumerate(meshes[:5]):
    o.color = pal[i]

sc = bpy.context.scene
sc.render.engine = "BLENDER_WORKBENCH"
sc.display.shading.light = "STUDIO"; sc.display.shading.color_type = "OBJECT"
sc.display.shading.show_shadows = True; sc.display.shading.show_cavity = True
sc.render.resolution_x = 1500; sc.render.resolution_y = 1100
sc.world = bpy.data.worlds.new("W"); sc.world.color = (0.16, 0.16, 0.18)
cd = bpy.data.cameras.new("C"); cam = bpy.data.objects.new("C", cd)
sc.collection.objects.link(cam); sc.camera = cam
ctr = Vector([(lo[i] + hi[i]) / 2 for i in range(3)])
rad = max(hi[i] - lo[i] for i in range(3))
os.makedirs(outdir, exist_ok=True)
def shoot(name, dirvec):
    d = Vector(dirvec).normalized()
    cam.location = ctr + d * rad * 2.2
    cam.rotation_euler = (ctr - cam.location).to_track_quat("-Z", "Y").to_euler()
    cd.type = "ORTHO"; cd.ortho_scale = rad * 1.15
    sc.render.filepath = os.path.join(outdir, f"{tag}-{name}.png")
    bpy.ops.render.render(write_still=True)
    print("rendered", name)
shoot("iso", (1, -1, 0.7))
shoot("front", (1, 0, 0))
shoot("side", (0, 1, 0))
shoot("top", (0, 0, 1))
