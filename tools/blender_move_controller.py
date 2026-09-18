"""Move the controller group onto the engine-side 2.87 deg face of bale upright
LBU-PP.001, with the bracket's bottom 48 in above the bottom of the skid.

Math: bracket mating face (normal -n) is brought onto the upright face plane
(normal +n) by a perpendicular translation, then slid in-plane to set the height,
then aligned in X to the upright face's centroid.

  blender --background v7.blend --python tools/blender_move_controller.py -- OUT.blend
"""
import bpy, os, sys, math
from mathutils import Vector, Matrix
argv = sys.argv[sys.argv.index("--") + 1:]
out_blend = os.path.abspath(argv[0])

N       = Vector((0.0, -1.0, 0.05)).normalized()   # upright face outward normal
P_UP    = Vector((-729.8, -233.7, 637.2))          # upright face centroid (mm->m below)
P_BR    = Vector((-624.5, -155.6, 338.6))          # bracket mating face centroid
SCALE   = 0.001
UP_FACE = P_UP * SCALE
BR_FACE = P_BR * SCALE

SKID_BOTTOM_Z = -0.9723                    # m, scene min Z
TARGET_BOTTOM_Z = SKID_BOTTOM_Z + 48 * 0.0254

GROUP = ["MSP-CP-CP750E", "PP-CPM-1001", "PP-CPM-1005"]
objs = [bpy.data.objects[n] for n in GROUP if n in bpy.data.objects]
print("moving:", [o.name for o in objs])
if len(objs) != len(GROUP):
    raise SystemExit(f"missing objects: {[n for n in GROUP if n not in bpy.data.objects]}")

def bbox(objs):
    lo = Vector((1e9,)*3); hi = Vector((-1e9,)*3)
    for o in objs:
        for c in o.bound_box:
            p = o.matrix_world @ Vector(c)
            for i in range(3):
                lo[i] = min(lo[i], p[i]); hi[i] = max(hi[i], p[i])
    return lo, hi

lo0, hi0 = bbox(objs)
print(f"before  bbox X[{lo0.x*1000:.0f},{hi0.x*1000:.0f}] Y[{lo0.y*1000:.0f},{hi0.y*1000:.0f}] Z[{lo0.z*1000:.0f},{hi0.z*1000:.0f}]")
print(f"        bracket bottom Z = {lo0.z*1000:+.1f} mm  (target {TARGET_BOTTOM_Z*1000:+.1f})")

# 1. perpendicular: close the gap between the two parallel face planes
d = UP_FACE - BR_FACE
gap = N.dot(d)
d1 = gap * N
print(f"perpendicular gap = {gap*1000:+.1f} mm  -> move {[round(v*1000,2) for v in d1]}")

# 2. in-plane slide to set the bracket bottom
S = Vector((0.0, 0.049938, 0.99875)).normalized()   # in-plane, perpendicular to N
bottom_after_perp = lo0.z + d1.z
t = (TARGET_BOTTOM_Z - bottom_after_perp) / S.z
d2 = t * S
print(f"in-plane slide t={t*1000:+.1f} mm -> {[round(v*1000,2) for v in d2]}")

# 3. X alignment to the upright face centroid
d3 = Vector(((UP_FACE.x - BR_FACE.x), 0.0, 0.0))
print(f"X align -> {d3.x*1000:+.1f} mm")

DT = d1 + d2 + d3
print(f"TOTAL translation: X{DT.x*1000:+.1f} Y{DT.y*1000:+.1f} Z{DT.z*1000:+.1f} mm")

T = Matrix.Translation(DT)
pc = objs[0].users_collection[0]
names = {o.name for o in pc.objects}
roots = [o for o in objs if o.parent is None or o.parent.name not in names]
print("roots to move:", [o.name for o in roots])
for o in roots:
    o.matrix_world = T @ o.matrix_world
bpy.context.view_layer.update()

lo1, hi1 = bbox(objs)
print(f"after   bbox X[{lo1.x*1000:.0f},{hi1.x*1000:.0f}] Y[{lo1.y*1000:.0f},{hi1.y*1000:.0f}] Z[{lo1.z*1000:.0f},{hi1.z*1000:.0f}]")
print(f"        bracket bottom Z = {lo1.z*1000:+.1f} mm   ({lo1.z*1000 - SKID_BOTTOM_Z*1000:.1f} mm above skid bottom = {(lo1.z - SKID_BOTTOM_Z)/0.0254:.2f} in)")

bpy.ops.wm.save_as_mainfile(filepath=out_blend)
print("saved", out_blend)
