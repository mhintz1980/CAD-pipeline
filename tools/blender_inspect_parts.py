"""Dump world-space bboxes for objects in a .blend, grouped by collection.

Read-only. Used to locate the lifting-bale uprights and the skid side wall
before computing a repositioning delta.

    blender --background SCENE.blend --python tools/blender_inspect_parts.py -- OUT.json
"""
import bpy, json, sys
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
out_path = argv[0] if argv else "parts.json"

def coll_of(obj):
    cs = [c.name for c in obj.users_collection]
    return cs[0] if cs else ""

rows = []
for obj in bpy.data.objects:
    if obj.type != "MESH":
        continue
    mw = obj.matrix_world
    pts = [mw @ Vector(c) for c in obj.bound_box]
    lo = [min(p[i] for p in pts) for i in range(3)]
    hi = [max(p[i] for p in pts) for i in range(3)]
    rows.append({
        "name": obj.name,
        "collection": coll_of(obj),
        "verts": len(obj.data.vertices),
        "polys": len(obj.data.polygons),
        "loc": [round(v, 5) for v in mw.translation],
        "min": [round(v, 5) for v in lo],
        "max": [round(v, 5) for v in hi],
        "size": [round(hi[i] - lo[i], 5) for i in range(3)],
        "parent": obj.parent.name if obj.parent else None,
    })

rows.sort(key=lambda r: (r["collection"], r["name"]))
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(rows, f, indent=1)

print(f"OBJECTS {len(rows)} -> {out_path}")
by = {}
for r in rows:
    by.setdefault(r["collection"], []).append(r)
for c, rs in sorted(by.items()):
    tot = sum(x["polys"] for x in rs)
    print(f"  {c:22} n={len(rs):3} polys={tot:>9,}")

# Scene bounds
if rows:
    lo = [min(r["min"][i] for r in rows) for i in range(3)]
    hi = [max(r["max"][i] for r in rows) for i in range(3)]
    print("SCENE min", [round(v, 4) for v in lo])
    print("SCENE max", [round(v, 4) for v in hi])
    print("SCENE size", [round(hi[i] - lo[i], 4) for i in range(3)])
