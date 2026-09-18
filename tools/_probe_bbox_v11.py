import bpy, numpy as np
objs = [o for o in bpy.data.objects if o.type == "MESH"]
print("meshes", len(objs))
print("objects with modifiers:", [(o.name, [m.type for m in o.modifiers]) for o in objs if o.modifiers][:20])
for nm in ["Part1^PP128-PP108-SKID", "Part1^PP128-PP108-SKID.001", "PP-FTT"]:
    o = bpy.data.objects[nm]; me = o.data
    nv = len(me.vertices); co = np.empty(nv*3); me.vertices.foreach_get("co", co); co = co.reshape(nv,3)
    mw = np.array(o.matrix_world)
    w = co @ mw[:3,:3].T + mw[:3,3]
    bb = np.array([list(c) for c in o.bound_box])
    wbb = bb @ mw[:3,:3].T + mw[:3,3]
    print(nm, "verts", nv, "data verts", len(me.vertices))
    print("   vert world bbox mm", np.round(w.min(0)*1000,3), np.round(w.max(0)*1000,3))
    print("   obj.bound_box mm   ", np.round(wbb.min(0)*1000,3), np.round(wbb.max(0)*1000,3))
    print("   local vert bbox    ", np.round(co.min(0),4), np.round(co.max(0),4))
    print("   local bound_box    ", np.round(bb.min(0),4), np.round(bb.max(0),4))
    print("   matrix", np.round(mw,6).tolist())
