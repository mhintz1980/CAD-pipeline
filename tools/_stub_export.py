import bpy, os
print("STUB: blender", bpy.app.version_string)
os.makedirs("/output", exist_ok=True)
open("/output/stub.txt","w").write("ok " + bpy.app.version_string)
