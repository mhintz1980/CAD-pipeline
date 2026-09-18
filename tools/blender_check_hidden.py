import bpy
print("--- collections ---")
for c in bpy.data.collections:
    n = len(c.objects)
    print(f"  {c.name:28} objs={n:3} hide_render={c.hide_render} hide_viewport={c.hide_viewport} hide_viewport_layer={c.hide_viewport}")
print("--- objects hidden at object level ---")
for o in bpy.data.objects:
    if o.type == "MESH" and (o.hide_render or o.hide_viewport):
        print(f"  {o.name:40} hide_render={o.hide_render} hide_viewport={o.hide_viewport}")
print("--- view layer exclusion ---")
for lc in bpy.context.view_layer.layer_collection.children:
    print(f"  {lc.name:28} exclude={lc.exclude} hide_viewport={lc.hide_viewport}")
