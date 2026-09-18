import bpy, sys, os, time
p = sys.argv[sys.argv.index("--")+1]
t=time.time()
print("IMPORTING", p, os.path.getsize(p)/1e6, "MB", flush=True)
bpy.ops.import_scene.gltf(filepath=p)
ms=[o for o in bpy.context.scene.objects if o.type=="MESH"]
tri=sum(max(0,len(f.vertices)-2) for o in ms for f in o.data.polygons)
print(f"IMPORT OK objects={len(ms)} tris={tri:,} in {time.time()-t:.1f}s", flush=True)
