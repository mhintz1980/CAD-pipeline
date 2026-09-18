"""Replace the interface-only engine husk with the full vendor engine model.

The husk's scene frame is the engine's NATIVE frame rotated +90 deg about X
(the earlier --in-axis Y prep baked that into the mesh, leaving the object
matrix as pure translation, so composing matrices cannot recover it).
Verified numerically: scene Y = -native Z, scene Z = +native Y.

So: rotate the imported engine +90 deg about X, then translate its bbox centre
onto the husk's. The two differ by 5-26 mm per side because the husk lost its
curved surfaces - that residual is expected and accepted.

  blender --background v7.blend --python tools/blender_swap_engine.py -- ENGINE.glb OUT.blend OUT.glb
"""
import bpy, os, sys, math
from mathutils import Vector, Matrix
argv = sys.argv[sys.argv.index("--") + 1:]
eng_glb, out_blend, out_glb = (os.path.abspath(argv[0]), os.path.abspath(argv[1]),
                               os.path.abspath(argv[2]))

def bbox(objs):
    lo = Vector((1e9,)*3); hi = Vector((-1e9,)*3)
    for o in objs:
        for c in o.bound_box:
            p = o.matrix_world @ Vector(c)
            for i in range(3):
                lo[i] = min(lo[i], p[i]); hi[i] = max(hi[i], p[i])
    return lo, hi

husks = [o for o in bpy.data.objects if o.type == "MESH" and "3336180" in o.name]
if not husks:
    raise SystemExit("no husk found")
TLO, THI = bbox(husks)
TC = (TLO + THI) / 2
TLOCAL = husks[0].matrix_world.translation.copy()
print(f"husk world bbox X[{TLO.x*1000:.0f},{THI.x*1000:.0f}] "
      f"Y[{TLO.y*1000:.0f},{THI.y*1000:.0f}] Z[{TLO.z*1000:.0f},{THI.z*1000:.0f}]")
eng_coll = husks[0].users_collection[0]
for o in husks:
    bpy.data.objects.remove(o, do_unlink=True)

before = {o.name for o in bpy.data.objects}
bpy.ops.import_scene.gltf(filepath=eng_glb)
new = [o for o in bpy.data.objects if o.name not in before]
mnew = [o for o in new if o.type == "MESH"]
new_names = {o.name for o in new}
roots = [o for o in new if o.parent is None or o.parent.name not in new_names]
print(f"imported {len(mnew)} meshes, roots: {[o.name for o in roots]}")

ALO, AHI = bbox(mnew)
AC = (ALO + AHI) / 2
print(f"engine on import  X[{ALO.x*1000:.0f},{AHI.x*1000:.0f}] "
      f"Y[{ALO.y*1000:.0f},{AHI.y*1000:.0f}] Z[{ALO.z*1000:.0f},{AHI.z*1000:.0f}]")

# +90 deg about X, about the engine's own centre
R = Matrix.Rotation(math.radians(90.0), 4, 'X')
P = Matrix.Translation(AC) @ R @ Matrix.Translation(-AC)
for r in roots:
    r.matrix_world = P @ r.matrix_world
bpy.context.view_layer.update()

BLO, BHI = bbox(mnew)
BC = (BLO + BHI) / 2
print(f"after +90 about X X[{BLO.x*1000:.0f},{BHI.x*1000:.0f}] "
      f"Y[{BLO.y*1000:.0f},{BHI.y*1000:.0f}] Z[{BLO.z*1000:.0f},{BHI.z*1000:.0f}]")

T = Matrix.Translation(TC - BC)
for r in roots:
    r.matrix_world = T @ r.matrix_world
bpy.context.view_layer.update()

CLO, CHI = bbox(mnew)
print(f"engine placed     X[{CLO.x*1000:.0f},{CHI.x*1000:.0f}] "
      f"Y[{CLO.y*1000:.0f},{CHI.y*1000:.0f}] Z[{CLO.z*1000:.0f},{CHI.z*1000:.0f}]")
print(f"delta vs husk     X[{(CLO.x-TLO.x)*1000:+.0f},{(CHI.x-THI.x)*1000:+.0f}] "
      f"Y[{(CLO.y-TLO.y)*1000:+.0f},{(CHI.y-THI.y)*1000:+.0f}] "
      f"Z[{(CLO.z-TLO.z)*1000:+.0f},{(CHI.z-THI.z)*1000:+.0f}] mm (expect 5-26, husk lost surfaces)")

for o in new:
    for c in list(o.users_collection):
        c.objects.unlink(o)
    eng_coll.objects.link(o)

bpy.ops.wm.save_as_mainfile(filepath=out_blend)
print("saved", out_blend)
bpy.ops.export_scene.gltf(filepath=out_glb, export_format="GLB", use_selection=False)
print("exported", out_glb, os.path.getsize(out_glb))
