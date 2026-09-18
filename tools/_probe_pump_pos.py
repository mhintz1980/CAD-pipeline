# Throwaway diagnostic: print pump object placements (owner-correction diff probe).
import bpy
import json

out = {"file": bpy.data.filepath, "pumps": []}
for coll in bpy.data.collections:
    if "pump" in coll.name.lower():
        for o in coll.all_objects:
            if o.type == "MESH":
                t = o.matrix_world.translation
                out["pumps"].append(
                    {"coll": coll.name, "obj": o.name, "loc": [round(t.x, 2), round(t.y, 2), round(t.z, 2)]}
                )
print("PUMPPROBE " + json.dumps(out))
