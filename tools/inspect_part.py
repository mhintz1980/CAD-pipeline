import bpy, sys
from mathutils import Vector
names = sys.argv[sys.argv.index("--") + 1:]
for nm in names:
    o = bpy.data.objects.get(nm)
    if o is None:
        cand = [x.name for x in bpy.data.objects if nm in x.name]
        print(f"{nm}: not found; near matches: {cand[:8]}")
        continue
    mw = o.matrix_world
    pts = [mw @ Vector(c) for c in o.bound_box]
    lo = Vector((min(p[i] for p in pts) for i in range(3)))
    hi = Vector((max(p[i] for p in pts) for i in range(3)))
    d = hi - lo
    print(f"\n=== {nm}")
    print(f"  verts={len(o.data.vertices)}  polys={len(o.data.polygons)}  parent={o.parent.name if o.parent else None}")
    print(f"  world min  X{lo.x*1000:9.1f} Y{lo.y*1000:9.1f} Z{lo.z*1000:9.1f} mm")
    print(f"  world max  X{hi.x*1000:9.1f} Y{hi.y*1000:9.1f} Z{hi.z*1000:9.1f} mm")
    print(f"  size       X{d.x*1000:9.1f} Y{d.y*1000:9.1f} Z{d.z*1000:9.1f} mm")
    print(f"  centre     X{(lo.x+hi.x)/2*1000:9.1f} Y{(lo.y+hi.y)/2*1000:9.1f} Z{(lo.z+hi.z)/2*1000:9.1f} mm")
    # vertex centroid + principal spread
    vs = [mw @ v.co for v in o.data.vertices]
    if vs:
        c = Vector((sum(v[i] for v in vs)/len(vs) for i in range(3)))
        sp = [max(v[i] for v in vs) - min(v[i] for v in vs) for i in range(3)]
        print(f"  vtx centroid X{c.x*1000:9.1f} Y{c.y*1000:9.1f} Z{c.z*1000:9.1f} mm  (n={len(vs)})")
        print(f"  vtx spread   X{sp[0]*1000:9.1f} Y{sp[1]*1000:9.1f} Z{sp[2]*1000:9.1f} mm")
