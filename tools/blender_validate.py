"""
blender_validate.py - cheap pre-render validation of a converted CAD assembly.

Run headless:
    blender --background --python blender_validate.py -- \
        --input out/engine-and-pump.glb --outdir reports/validate \
        [--views 6] [--engine WORKBENCH] [--isolate]

Answers the questions that decide whether a render is worth paying for:
  * did every expected component arrive (engine / pump / skid / bale / controller)
  * is anything placed implausibly far from the machine (a stray occurrence
    at 100 m ruins camera framing and makes the product a speck)
  * what is the scene scale in metres - catches unit errors (inch vs mm vs m)
  * how heavy is it (objects, triangles) and where is the weight
  * per-component isolation renders, so a component that arrived as loose
    faces instead of a solid is visible at a glance rather than at 4am

Writes report.json + a contact sheet of turntable views. Uses Workbench by
default: a validation pass should cost seconds, not minutes.
"""

import json
import math
import os
import sys
from collections import defaultdict

import bpy
import mathutils

# Component name patterns for a Myers-Seth pump package. Order matters:
# first match wins, so put specific prefixes above generic ones.
ROLE_PATTERNS = [
    ("engine",     ("3336180", "ci510", "jd18", "-ema", "em-sp", "engine")),
    ("pump",       ("pp128-fta", "pp-fts", "pp-ftt", "pp128s22", "pp-fbs",
                    "part11", "pump")),
    ("controller", ("msp-cp", "cp750", "cpm-pp", "pp-cpm", "control")),
    ("bale",       ("lba-", "lbs-", "lbu-", "pp-lbb", "bale", "lift")),
    ("skid",       ("skid", "mc6x18", "mc channel", "tube rectangular",
                    "plt-mnt", "mnt-pe", "doubler", "-mfb")),
]


def argv():
    a = sys.argv
    return a[a.index("--") + 1:] if "--" in a else []


def parse_args():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--outdir", default="validate")
    p.add_argument("--views", type=int, default=6)
    p.add_argument("--engine", default="CYCLES")
    p.add_argument("--res", type=int, default=800)
    p.add_argument("--isolate", action="store_true",
                   help="also render one view per detected role")
    p.add_argument("--outlier-factor", type=float, default=3.0,
                   help="flag objects farther from the median centre than "
                        "this multiple of the core radius")
    return p.parse_args(argv())


def role_of(name: str) -> str:
    n = name.lower()
    for role, pats in ROLE_PATTERNS:
        if any(pat in n for pat in pats):
            return role
    return "unclassified"


def obj_stats(o):
    me = o.data
    tris = sum(max(0, len(p.vertices) - 2) for p in me.polygons)
    bb = [o.matrix_world @ mathutils.Vector(c) for c in o.bound_box]
    lo = mathutils.Vector((min(v.x for v in bb), min(v.y for v in bb),
                           min(v.z for v in bb)))
    hi = mathutils.Vector((max(v.x for v in bb), max(v.y for v in bb),
                           max(v.z for v in bb)))
    return tris, lo, hi, (lo + hi) / 2.0


def main():
    a = parse_args()
    # Blender resolves a bare relative render path against its own cwd,
    # and a failed write is silent - use absolute paths throughout.
    a.outdir = os.path.abspath(a.outdir)
    os.makedirs(a.outdir, exist_ok=True)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    ext = os.path.splitext(a.input)[1].lower()
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=a.input)
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=a.input)
    elif ext == ".stl":
        bpy.ops.wm.stl_import(filepath=a.input)
    elif ext == ".blend":
        bpy.ops.wm.open_mainfile(filepath=a.input)
    else:
        raise SystemExit(f"unsupported input: {ext}")

    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if not meshes:
        raise SystemExit("no mesh objects imported")

    rows = []
    for o in meshes:
        tris, lo, hi, ctr = obj_stats(o)
        rows.append({
            "name": o.name, "role": role_of(o.name), "tris": tris,
            "verts": len(o.data.vertices),
            "centre": [round(v, 4) for v in ctr],
            "size": [round(hi[i] - lo[i], 4) for i in range(3)],
            "loose_faces": bool(o.data.polygons) and not o.data.edges,
        })

    # --- outlier detection -------------------------------------------------
    # Median centre is robust to a handful of stray occurrences; the mean is
    # not, which is exactly how a 100 m outlier hides.
    import statistics as st
    med = mathutils.Vector([
        st.median([r["centre"][i] for r in rows]) for i in range(3)
    ])
    dists = sorted(
        (mathutils.Vector(r["centre"]) - med).length for r in rows
    )
    core = dists[int(len(dists) * 0.75)] or 1.0
    outliers = []
    for r in rows:
        d = (mathutils.Vector(r["centre"]) - med).length
        r["dist_from_median_m"] = round(d, 3)
        if d > core * a.outlier_factor and d > 1.0:
            outliers.append(r)

    inliers = [r for r in rows if r not in outliers]
    core_objs = [o for o in meshes
                 if any(r["name"] == o.name for r in inliers)]

    def bounds(objs):
        lo = mathutils.Vector((1e18,) * 3)
        hi = mathutils.Vector((-1e18,) * 3)
        for o in objs:
            _, l, h, _ = obj_stats(o)
            for i in range(3):
                lo[i] = min(lo[i], l[i])
                hi[i] = max(hi[i], h[i])
        return lo, hi

    lo_all, hi_all = bounds(meshes)
    lo, hi = bounds(core_objs) if core_objs else (lo_all, hi_all)
    ctr = (lo + hi) / 2.0
    radius = max((hi - lo).length / 2.0, 0.001)

    by_role = defaultdict(lambda: {"objects": 0, "tris": 0})
    for r in rows:
        by_role[r["role"]]["objects"] += 1
        by_role[r["role"]]["tris"] += r["tris"]

    report = {
        "input": a.input,
        "objects": len(meshes),
        "triangles": sum(r["tris"] for r in rows),
        "scene_bounds_all_m": {
            "min": [round(v, 3) for v in lo_all],
            "max": [round(v, 3) for v in hi_all],
            "size": [round(hi_all[i] - lo_all[i], 3) for i in range(3)],
        },
        "core_bounds_m": {
            "min": [round(v, 3) for v in lo],
            "max": [round(v, 3) for v in hi],
            "size": [round(hi[i] - lo[i], 3) for i in range(3)],
            "radius": round(radius, 3),
        },
        "outliers": [
            {"name": o["name"], "role": o["role"],
             "dist_from_median_m": o["dist_from_median_m"],
             "centre": o["centre"]}
            for o in sorted(outliers,
                            key=lambda r: -r["dist_from_median_m"])
        ],
        "by_role": {k: v for k, v in sorted(by_role.items())},
        "roles_missing": [
            role for role, _ in ROLE_PATTERNS if by_role[role]["objects"] == 0
        ],
        "objects_detail": sorted(rows, key=lambda r: -r["tris"]),
    }

    # --- render ------------------------------------------------------------
    sc = bpy.context.scene
    engines = {
        "WORKBENCH": "BLENDER_WORKBENCH",
        "EEVEE": "BLENDER_EEVEE_NEXT",
        "CYCLES": "CYCLES",
    }
    want = engines.get(a.engine.upper(), "BLENDER_WORKBENCH")
    avail = {i.identifier for i in
             sc.bl_rna.properties["render"].fixed_type.bl_rna
             .properties["engine"].enum_items} \
        if hasattr(sc, "render") else set()
    try:
        sc.render.engine = want
    except TypeError:
        sc.render.engine = "BLENDER_WORKBENCH"
    sc.render.resolution_x = sc.render.resolution_y = a.res
    sc.render.film_transparent = False
    sc.render.image_settings.file_format = "PNG"
    if sc.render.engine == "BLENDER_WORKBENCH":
        sh = sc.display.shading
        sh.light = "STUDIO"
        sh.color_type = "RANDOM"   # per-object colour: shows the part breakup
        sh.show_cavity = True
    elif sc.render.engine == "CYCLES":
        sc.cycles.samples = 24
        sc.cycles.device = "CPU"
        sc.cycles.use_denoising = True

    cam_data = bpy.data.cameras.new("ValCam")
    cam = bpy.data.objects.new("ValCam", cam_data)
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam_data.lens = 50

    world = bpy.data.worlds.new("ValWorld")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[1].default_value = 1.0
    sc.world = world

    sun = bpy.data.objects.new("ValSun", bpy.data.lights.new("ValSun", "SUN"))
    sun.data.energy = 3.0
    sun.rotation_euler = (math.radians(50), 0, math.radians(35))
    sc.collection.objects.link(sun)

    def shoot(path, elev_deg, azim_deg, target, rad, hide=None):
        d = rad * 3.0
        e, az = math.radians(elev_deg), math.radians(azim_deg)
        cam.location = target + mathutils.Vector((
            d * math.cos(e) * math.cos(az),
            d * math.cos(e) * math.sin(az),
            d * math.sin(e),
        ))
        direction = target - cam.location
        cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
        hidden = []
        if hide is not None:
            for o in meshes:
                if o.name in hide:
                    hidden.append((o, o.hide_render))
                    o.hide_render = True
        sc.render.filepath = os.path.abspath(path)
        bpy.ops.render.render(write_still=True)
        if not os.path.exists(os.path.abspath(path)):
            # A silent no-write means the engine could not get a context
            # (Workbench/EEVEE need GL, which headless Windows often lacks).
            raise SystemExit(
                f"render produced no file: {path} (engine="
                f"{sc.render.engine}). Try --engine CYCLES."
            )
        for o, prev in hidden:
            o.hide_render = prev

    shots = []
    for i in range(a.views):
        p = os.path.join(a.outdir, f"view_{i:02d}.png")
        shoot(p, 22 if i % 2 == 0 else 55, 360.0 * i / a.views, ctr, radius)
        shots.append(p)

    # A framing shot that includes outliers, so a stray occurrence is visible
    if outliers:
        ctr_all = (lo_all + hi_all) / 2.0
        rad_all = max((hi_all - lo_all).length / 2.0, 0.001)
        p = os.path.join(a.outdir, "view_ALL_with_outliers.png")
        shoot(p, 30, 45, ctr_all, rad_all)
        shots.append(p)

    if a.isolate:
        present = [r for r, _ in ROLE_PATTERNS if by_role[r]["objects"]]
        for role in present + (["unclassified"]
                               if by_role["unclassified"]["objects"] else []):
            hide = {r["name"] for r in rows if r["role"] != role}
            keep = [o for o in core_objs if role_of(o.name) == role]
            if not keep:
                continue
            l2, h2 = bounds(keep)
            p = os.path.join(a.outdir, f"isolate_{role}.png")
            shoot(p, 25, 45, (l2 + h2) / 2.0,
                  max((h2 - l2).length / 2.0, 0.001), hide=hide)
            shots.append(p)

    report["renders"] = shots
    with open(os.path.join(a.outdir, "report.json"), "w",
              encoding="utf-8") as fh:
        json.dump(report, fh, indent=1)

    print("\n=== VALIDATION SUMMARY ===")
    print(f"objects={report['objects']} triangles={report['triangles']:,}")
    print(f"core size (m) = {report['core_bounds_m']['size']}")
    print(f"all  size (m) = {report['scene_bounds_all_m']['size']}")
    print(f"missing roles: {report['roles_missing'] or 'none'}")
    for k, v in report["by_role"].items():
        print(f"  {k:14} objects={v['objects']:>5} tris={v['tris']:,}")
    if report["outliers"]:
        print(f"OUTLIERS ({len(report['outliers'])}):")
        for o in report["outliers"][:10]:
            print(f"  {o['dist_from_median_m']:>10.1f} m  "
                  f"{o['role']:12} {o['name'][:60]}")
    print(f"renders -> {a.outdir}")


if __name__ == "__main__":
    main()
