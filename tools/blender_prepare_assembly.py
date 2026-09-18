"""
blender_prepare_assembly.py - turn a converted CAD GLB into a render-ready
.blend without hand-polishing.

    blender --background --python blender_prepare_assembly.py -- \
        --input out/engine-and-pump.glb \
        --output out/engine-and-pump.blend \
        [--tri-budget 4000000] [--drop-outliers] [--materials]

What it does, in order:
  1. import the GLB (node names and hierarchy come straight from the STEP
     product names via OCCT XCAF)
  2. sort objects into collections by detected role
  3. optionally quarantine far-flung outlier occurrences into a disabled
     collection instead of deleting them - a stray part at 100 m wrecks
     camera framing, but it may also be real, so it stays recoverable
  4. normals: drop imported custom split normals, recalculate outward, then
     smooth-shade every face and mark edges sharper than 30 deg as sharp -
     done directly in bmesh, because bpy.ops.object.shade_auto_smooth() can
     fail silently headless and leave flat plates visibly faceted
  5. weld coincident verts and remove zero-area faces (tessellation debris)
  6. conservative decimation, only on objects above a per-object threshold,
     and only enough to hit the scene triangle budget
  7. optional flat role materials so the preview is readable
  8. save .blend

Every step is reported with before/after counts. Nothing is deleted silently.
"""

import json
import math
import os
import sys
from collections import defaultdict

import bmesh
import bpy
import mathutils

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from blender_validate import ROLE_PATTERNS, role_of
except Exception:                                    # keep standalone-usable
    ROLE_PATTERNS = [
        ("engine",     ("3336180", "ci510", "jd18", "-ema", "em-sp", "engine")),
        ("pump",       ("pp128-fta", "pp-fts", "pp-ftt", "pp128s22", "pp-fbs",
                        "part11", "pump")),
        ("controller", ("msp-cp", "cp750", "cpm-pp", "pp-cpm", "control")),
        ("bale",       ("lba-", "lbs-", "lbu-", "pp-lbb", "bale", "lift")),
        ("skid",       ("skid", "mc6x18", "mc channel", "tube rectangular",
                        "plt-mnt", "mnt-pe", "doubler", "-mfb")),
    ]

    def role_of(name):
        n = name.lower()
        for role, pats in ROLE_PATTERNS:
            if any(p in n for p in pats):
                return role
        return "unclassified"


ROLE_COLOR = {
    "engine":       (0.055, 0.075, 0.090, 1.0),
    "pump":         (0.520, 0.100, 0.090, 1.0),
    "controller":   (0.030, 0.035, 0.040, 1.0),
    "bale":         (0.480, 0.360, 0.040, 1.0),
    "skid":         (0.480, 0.360, 0.040, 1.0),
    "unclassified": (0.300, 0.300, 0.320, 1.0),
}


def argv():
    a = sys.argv
    return a[a.index("--") + 1:] if "--" in a else []


def tri_count(o):
    return sum(max(0, len(p.vertices) - 2) for p in o.data.polygons)


def world_centre(o):
    bb = [o.matrix_world @ mathutils.Vector(c) for c in o.bound_box]
    lo = mathutils.Vector((min(v.x for v in bb), min(v.y for v in bb),
                           min(v.z for v in bb)))
    hi = mathutils.Vector((max(v.x for v in bb), max(v.y for v in bb),
                           max(v.z for v in bb)))
    return (lo + hi) / 2.0, lo, hi


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--tri-budget", type=int, default=4_000_000)
    p.add_argument("--min-tris-to-decimate", type=int, default=20_000)
    p.add_argument("--weld", type=float, default=1e-5,
                   help="merge-by-distance threshold in metres")
    p.add_argument("--smooth-deg", type=float, default=30.0)
    p.add_argument("--drop-outliers", action="store_true")
    p.add_argument("--outlier-factor", type=float, default=3.0)
    p.add_argument("--materials", action="store_true")
    p.add_argument("--json")
    a = p.parse_args(argv())

    rep = {"input": a.input, "steps": []}

    def step(name, **kw):
        rep["steps"].append(dict(step=name, **kw))
        print(f"[{name}] " + "  ".join(f"{k}={v}" for k, v in kw.items()))

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=a.input)
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    t0 = sum(tri_count(o) for o in meshes)
    step("import", objects=len(meshes), triangles=t0)
    if not meshes:
        raise SystemExit("no meshes imported")

    # ---- 2. collections by role ----------------------------------------
    roles = defaultdict(list)
    for o in meshes:
        roles[role_of(o.name)].append(o)
    cols = {}
    for role in list(roles):
        c = bpy.data.collections.new(f"CAD_{role}")
        bpy.context.scene.collection.children.link(c)
        cols[role] = c
        for o in roles[role]:
            for oc in list(o.users_collection):
                oc.objects.unlink(o)
            c.objects.link(o)
    step("collections", **{k: len(v) for k, v in sorted(roles.items())})

    # ---- 3. outliers ----------------------------------------------------
    import statistics as st
    centres = {o: world_centre(o)[0] for o in meshes}
    med = mathutils.Vector([
        st.median([centres[o][i] for o in meshes]) for i in range(3)
    ])
    d = sorted((centres[o] - med).length for o in meshes)
    core = d[int(len(d) * 0.75)] or 1.0
    outliers = [o for o in meshes
                if (centres[o] - med).length > core * a.outlier_factor
                and (centres[o] - med).length > 1.0]
    if outliers:
        q = bpy.data.collections.new("CAD_QUARANTINE_outliers")
        bpy.context.scene.collection.children.link(q)
        for o in outliers:
            for oc in list(o.users_collection):
                oc.objects.unlink(o)
            q.objects.link(o)
            o.hide_render = bool(a.drop_outliers)
            o.hide_viewport = bool(a.drop_outliers)
        # Blender 3.x+: exclude via the view-layer child, not the collection
        lc = bpy.context.view_layer.layer_collection.children.get(q.name)
        if lc is not None and a.drop_outliers:
            lc.exclude = True
        step("quarantine_outliers", count=len(outliers),
             hidden=bool(a.drop_outliers),
             worst_m=round(max((centres[o] - med).length for o in outliers), 1))
        rep["outliers"] = [
            {"name": o.name, "role": role_of(o.name),
             "dist_m": round((centres[o] - med).length, 2)}
            for o in sorted(outliers,
                            key=lambda x: -(centres[x] - med).length)
        ]
    else:
        step("quarantine_outliers", count=0)

    active = [o for o in meshes if not (a.drop_outliers and o in outliers)]

    # ---- 4/5. normals + weld + degenerate cleanup ------------------------
    welded = degen = sharp = 0
    ang = math.radians(a.smooth_deg)
    for o in active:
        me = o.data
        # imported custom split normals fight recalculation; drop them first
        try:
            me.free_normals_split()
        except Exception:
            pass
        if me.has_custom_normals:
            try:
                with bpy.context.temp_override(object=o, active_object=o,
                                               selected_editable_objects=[o]):
                    bpy.ops.mesh.customdata_custom_splitnormals_clear()
            except Exception:
                pass
        bm = bmesh.new()
        bm.from_mesh(me)
        v0, f0 = len(bm.verts), len(bm.faces)
        bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=a.weld)
        # zero-area triangles: real tessellation debris, safe to drop
        bad = [f for f in bm.faces if f.calc_area() < 1e-14]
        if bad:
            bmesh.ops.delete(bm, geom=bad, context="FACES")
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        welded += v0 - len(bm.verts)
        degen += f0 - len(bm.faces) - (v0 - len(bm.verts)) * 0

        # Shading. Do NOT use bpy.ops.object.shade_auto_smooth() here: in
        # headless Blender it can fail without raising anything useful, and a
        # swallowed failure leaves every face smooth-shaded, which puts
        # visible facet banding across flat plates. Mark sharp edges
        # explicitly instead - Blender 4.1+ splits normals on sharp edges
        # natively, no modifier and no operator needed.
        for f in bm.faces:
            f.smooth = True
        for e in bm.edges:
            if len(e.link_faces) != 2:
                e.smooth = False          # boundary / non-manifold: hard
                sharp += 1
                continue
            try:
                hard = e.calc_face_angle() > ang
            except Exception:
                hard = True
            e.smooth = not hard
            sharp += hard
        bm.to_mesh(me)
        bm.free()

    smoothed = sum(
        1 for o in active for p in o.data.polygons if p.use_smooth
    )
    if not sharp:
        # Every mechanical assembly has hard edges. Zero means the pass did
        # nothing, and that must not pass silently a second time.
        raise SystemExit(
            "normals pass marked 0 sharp edges - shading would be wrong"
        )
    step("normals_weld_cleanup", verts_welded=welded,
         faces_removed=max(0, degen), sharp_edges=sharp,
         smooth_polys=smoothed, smooth_deg=a.smooth_deg)

    t1 = sum(tri_count(o) for o in active)
    step("after_cleanup", triangles=t1)

    # ---- 6. conservative decimation -------------------------------------
    if t1 > a.tri_budget:
        heavy = [o for o in active if tri_count(o) >= a.min_tris_to_decimate]
        heavy_tris = sum(tri_count(o) for o in heavy)
        light_tris = t1 - heavy_tris
        # only the heavy objects absorb the reduction
        target_heavy = max(a.tri_budget - light_tris, int(heavy_tris * 0.1))
        ratio = min(1.0, target_heavy / max(heavy_tris, 1))
        for o in heavy:
            m = o.modifiers.new("CADDecimate", "DECIMATE")
            m.decimate_type = "COLLAPSE"
            m.ratio = ratio
            m.use_collapse_triangulate = True
        step("decimate", objects=len(heavy), ratio=round(ratio, 4),
             from_tris=t1, target=a.tri_budget)
        rep["decimate_ratio"] = ratio
    else:
        step("decimate", skipped=True, triangles=t1, budget=a.tri_budget)

    # ---- 7. materials ----------------------------------------------------
    if a.materials:
        mats = {}
        for role, col in ROLE_COLOR.items():
            m = bpy.data.materials.new(f"MSP_{role}")
            m.use_nodes = True
            bsdf = m.node_tree.nodes.get("Principled BSDF")
            if bsdf:
                bsdf.inputs["Base Color"].default_value = col
                if "Roughness" in bsdf.inputs:
                    bsdf.inputs["Roughness"].default_value = (
                        0.35 if role in ("pump", "skid", "bale") else 0.55
                    )
                if "Metallic" in bsdf.inputs:
                    bsdf.inputs["Metallic"].default_value = (
                        0.8 if role in ("skid", "bale") else 0.2
                    )
            mats[role] = m
        for o in active:
            o.data.materials.clear()
            o.data.materials.append(mats[role_of(o.name)])
        step("materials", assigned=len(active), palette=len(mats))

    os.makedirs(os.path.dirname(os.path.abspath(a.output)), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=a.output)
    rep["output"] = a.output
    rep["output_bytes"] = os.path.getsize(a.output)
    rep["triangles_final_pre_modifier"] = t1
    step("saved", path=a.output, mb=round(rep["output_bytes"] / 1e6, 1))

    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(rep, fh, indent=1)


if __name__ == "__main__":
    main()
