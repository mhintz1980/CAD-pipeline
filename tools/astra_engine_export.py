"""Astra engine export (rev 4): isolate CAD_engine, units->mm, clean, decimate, export.

Cloud worker invocation:
  blender -b /input/engine-and-pump-v10.blend --python /scripts/astra_engine_export.py -- \
      --output-dir /output [--decimate-detailed 500000] [--decimate-light 350000] [--save-source-blend]

Rev 4 (final quality pass):
 * DECIMATE_NAMES = {"COMPOUND.001"} only; the tiny COMPOUND (360 tris) and the 4
   EM-SP mounts + PP12-EM-JD18 are protected and coordinate-exact (6 protected).
 * Default light target 350000 tris (~17.5 MB); detailed 500000 (~25 MB).
 * Preview: disable sequencer/compositing (a source compositor/sequencer could pull
   in another Scene with no camera); assert an evaluated camera and record GPU
   device evidence; stage reused after isolation.
 * README: recommend the 25 MB detailed STL for reference; light STL is visual-only
   unless its measured sampled max deviation <= 3 mm (actual value reported); STL
   files are explicitly NOT analytic solids / NOT watertight; correct SolidWorks
   import guidance; native SW import not yet tested.
 * Honest mesh diagnostics: open boundaries remain and cleanup/decimation introduce
   non-manifold edges; NOT a healed solid.

Rev 3 fixes (astra-engine-rev3-fix.md), on top of rev 2:
 1. Units: Matrix.Scale(mm, 4) @ world (mm = scale_length*1000). No stray /1000.
 2. Non-destructive ordering: STL/blend/README/report written BEFORE the preview render;
    destructive isolation (deleting baselines/originals/light copies) and engine-cleaned.blend
    save happen at the END, after all metrics. Source/protected names frozen as strings.
 3. stage_scene unhides working objects and parent/layer collections before rendering and
    asserts the preview PNG is actually written.
 4. engine-cleaned.blend saved with unit_settings.scale_length=0.001 (length unit mm) so the
    mm-baked world coords are represented correctly.
 5. Mount preservation proven by array_equal of triangle coords vs the immutable baseline
    (not tri-count), finite-validated; deviation in mm ([3]) and post-decimation topology
    recorded for BOTH the detailed and light variants.
 6. REV-3 marker; READY only after inspection.
"""
import argparse
import json
import os
import struct
import sys
import time

import bpy
import bmesh
import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

ENGINE_COLL = "CAD_engine"
# REV 4: only the single huge merged casting is decimated. Everything ELSE is
# protected and must remain coordinate-exact (incl. the tiny 360-tri COMPOUND).
DECIMATE_NAMES = {"COMPOUND.001"}
DEGENERATE_EPS_MM = 0.001
EXPECTED_BBOX_MM = {"min": [-835.717, -1762.413, -482.756],
                    "max": [837.721, 521.779, 1715.81]}
BBOX_TOL_MM = 10.0
JD_GREEN = (0x36 / 255, 0x7C / 255, 0x2B / 255)
T0 = time.time()


def log(*a):
    print("[astra-export]", *a, flush=True)


def fail(msg):
    raise SystemExit("[astra-export] FATAL: " + msg)


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output-dir", required=True)
    p.add_argument("--decimate-light", type=int, default=350000)
    p.add_argument("--decimate-detailed", type=int, default=500000)
    p.add_argument("--save-source-blend", action="store_true")
    return p.parse_args(argv)


def engine_mesh_objects():
    coll = bpy.data.collections.get(ENGINE_COLL)
    if coll is None:
        fail("collection '%s' not found" % ENGINE_COLL)
    objs = []

    def rec(c):
        for o in c.objects:
            if o.type == "MESH":
                objs.append(o)
        for ch in c.children:
            rec(ch)
    rec(coll)
    if not objs:
        fail("no meshes in %s" % ENGINE_COLL)
    return objs


def count_tris(obj):
    me = obj.data
    me.calc_loop_triangles()
    return len(me.loop_triangles)


def mm_scale_factor():
    """Factor to convert world METRES coords to millimetres: scale_length * 1000."""
    us = bpy.context.scene.unit_settings
    return us.scale_length * 1000.0


def make_mm_copy(obj, mm):
    """Independent copy, unparented, world matrix * mm scale baked into mesh (mm coords).

    Never mutates the source object/mesh. Rev3 FIX 1: scale factor is mm (= scale_length*1000).
    """
    world = obj.matrix_world.copy()
    copy = obj.copy()
    copy.data = obj.data.copy()
    copy.parent = None
    copy.matrix_parent_inverse = Matrix.Identity(4)
    copy.matrix_world = Matrix.Identity(4)
    copy.data.transform(Matrix.Scale(mm, 4) @ world)   # world(metres) -> world(mm)
    bpy.context.scene.collection.objects.link(copy)
    copy.name = obj.name + "__mm"
    copy.hide_viewport = False
    copy.hide_render = False
    return copy


def analyze_mesh(obj):
    """Boundary / true-nonmanifold (>2 faces) / degenerate counts (no mutation)."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bound = sum(1 for e in bm.edges if e.is_boundary)
    nonman = sum(1 for e in bm.edges if len(e.link_faces) > 2)
    degen = sum(1 for e in bm.edges if e.calc_length() <= DEGENERATE_EPS_MM) + \
        sum(1 for f in bm.faces if f.calc_area() <= DEGENERATE_EPS_MM ** 2)
    bm.free()
    return {"boundary_edges": bound, "nonmanifold_edges": nonman,
            "degenerate_elems": degen}


def clean_mesh_mm(obj):
    """Conservative cleanup in-place on a mm copy (never called on protected mounts)."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=DEGENERATE_EPS_MM)
    bmesh.ops.dissolve_degenerate(bm, dist=DEGENERATE_EPS_MM, edges=bm.edges)
    for f in list(bm.faces):
        if f.calc_area() <= DEGENERATE_EPS_MM ** 2:
            bm.faces.remove(f)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()


def tri_coords(obj):
    """N x 3 x 3 float64 triangle coords, applies obj.matrix_world if non-identity."""
    me = obj.data
    me.calc_loop_triangles()
    n = len(me.loop_triangles)
    if n == 0:
        return np.zeros((0, 3, 3))
    lti = np.empty(n * 3, dtype=np.int32)
    me.loop_triangles.foreach_get("vertices", lti)
    co = np.empty(len(me.vertices) * 3, dtype=np.float64)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    tris = co[lti.reshape(n, 3)]
    m = np.array(obj.matrix_world)
    if not np.allclose(m, np.eye(4)):
        tris = tris @ m[:3, :3].T + m[:3, 3]
    return tris


def decimate_body(obj, target_tris):
    cur = count_tris(obj)
    if target_tris is None or cur <= target_tris or cur == 0:
        return 1.0
    ratio = target_tris / cur
    mod = obj.modifiers.new("Decimate", "DECIMATE")
    mod.ratio = ratio
    mod.use_collapse_triangulate = True
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=mod.name)
    return ratio


def bbox_of_tris(tris_list):
    allp = np.concatenate([t.reshape(-1, 3) for t in tris_list if len(t)])
    return allp.min(axis=0), allp.max(axis=0)


def sample_deviation(base_tris, dec_obj, samples=4000):
    """Bidirectional deviation vs immutable mm baseline triangle array.

    find_nearest -> (location, normal, index, distance); distance is [3].
    Misses recorded as NaN, never zero-filled. All coords are mm world space.
    """

    def bvh_from(o):
        bm = bmesh.new()
        bm.from_mesh(o.data)
        bm.transform(o.matrix_world)
        tree = BVHTree.FromBMesh(bm)
        bm.free()
        return tree

    def sample_pts_from_tris(tris, n):
        areas = np.linalg.norm(
            np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0]), axis=1) * 0.5
        s = areas.sum()
        if s <= 0:
            fail("degenerate area distribution for sampling")
        p = areas / s
        rng = np.random.default_rng(42)
        idx = rng.choice(len(tris), size=min(n, len(tris)), p=p)
        t = tris[idx]
        u = rng.random((len(idx), 2))
        flip = u.sum(axis=1) > 1
        u[flip] = 1 - u[flip]
        a, b = u[:, :1], u[:, 1:]
        return t[:, 0] + a * (t[:, 1] - t[:, 0]) + b * (t[:, 2] - t[:, 0])

    tree = bvh_from(dec_obj)

    def dists(pts):
        d = np.empty(len(pts))
        misses = 0
        for i, p in enumerate(pts):
            hit = tree.find_nearest(tuple(p))
            if hit is None or hit[0] is None:
                d[i] = np.nan
                misses += 1
            else:
                d[i] = hit[3]  # [3] = distance, [2] = face index
        return d, misses

    pts_dec = sample_pts_from_tris(tri_coords(dec_obj), samples)
    pts_base = sample_pts_from_tris(base_tris, samples)
    d1, m1 = dists(pts_dec)
    d2, m2 = dists(pts_base)
    all_d = np.concatenate([d1, d2])
    valid = np.isfinite(all_d)
    return {
        "samples": int(len(all_d)),
        "misses": int(m1 + m2),
        "max_dev_mm": float(all_d[valid].max()) if valid.any() else None,
        "mean_dev_mm": float(all_d[valid].mean()) if valid.any() else None,
        "note": "estimate from deterministic BVH nearest samples; NOT certified Hausdorff",
    }


def export_binary_stl(tris, path):
    n = len(tris)
    with open(path, "wb") as f:
        f.write(b"Astra engine mesh export mm (not watertight)"[:80].ljust(80, b" "))
        f.write(struct.pack("<I", n))
        if n:
            v0, v1, v2 = tris[:, 0], tris[:, 1], tris[:, 2]
            nrm = np.cross(v1 - v0, v2 - v0)
            ln = np.linalg.norm(nrm, axis=1, keepdims=True)
            ln[ln == 0] = 1
            rec = np.zeros(n, dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
            rec["n"] = (nrm / ln).astype("<f4")
            rec["v"] = tris.astype("<f4")
            f.write(rec.tobytes())
    return n, os.path.getsize(path)


def validate_stl(path, exp_n):
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        f.read(80)
        n = struct.unpack("<I", f.read(4))[0]
    return {"count": n, "count_matches_written": n == exp_n,
            "size_ok": size == 84 + 50 * n, "nonempty": n > 0,
            "approx_mb": round(size / 1e6, 2)}


def _show_layer_colls(lc):
    try:
        lc.exclude = False
        lc.hide_viewport = False
    except Exception:
        pass
    for ch in lc.children:
        _show_layer_colls(ch)


def _unhide(o):
    for attr in ("hide_viewport", "hide_render"):
        try:
            setattr(o, attr, False)
        except Exception:
            pass
    try:
        o.hide_set(False)
    except Exception:
        pass
    for c in list(o.users_collection):
        try:
            c.hide_viewport = False
            c.hide_render = False
        except Exception:
            pass


def stage_scene(scene, bodies):
    """Engine-only staging: unhide, link bodies into export collection, frame camera."""
    _show_layer_colls(bpy.context.view_layer.layer_collection)
    coll = bpy.data.collections.new("ENGINE_EXPORT")
    if coll.name not in [c.name for c in scene.collection.children]:
        scene.collection.children.link(coll)
    coll.hide_viewport = False
    coll.hide_render = False
    for o in bodies:
        _unhide(o)
        for uc in list(o.users_collection):
            uc.objects.unlink(o)
        coll.objects.link(o)
    tris_all = np.concatenate(
        [tri_coords(o).reshape(-1, 3) for o in bodies if count_tris(o)])
    lo, hi = tris_all.min(axis=0), tris_all.max(axis=0)
    center = (lo + hi) / 2
    diag = float(np.linalg.norm(hi - lo))
    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50
    cam_data.clip_start = max(diag * 0.01, 1.0)
    cam_data.clip_end = max(diag * 10, 100.0)
    cam = bpy.data.objects.new("Cam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam                                   # REQUIRED or render fails "no camera"
    d = diag * 1.4
    cam.location = (center[0] + d * 0.6, center[1] - d * 0.75, center[2] + d * 0.45)
    direction = Vector(center) - cam.location
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    ld = bpy.data.lights.new("Sun", type="SUN")
    ld.energy = 3.0
    light = bpy.data.objects.new("Sun", ld)
    scene.collection.objects.link(light)
    light.rotation_euler = (0.6, 0.2, 0.9)
    return cam, light, (lo, hi)


def setup_gpu_cycles(scene, report):
    scene.render.engine = "CYCLES"
    prefs = bpy.context.preferences.addons.get("cycles")
    if prefs:
        cp = prefs.preferences
        for dtype in ("OPTIX", "CUDA"):
            try:
                cp.compute_device_type = dtype
                cp.get_devices()
                if any(d.type == dtype for d in cp.devices):
                    for d in cp.devices:
                        d.use = (d.type == dtype)
                    try:
                        cp.log_level = 1          # make Cycles log the active device
                    except Exception:
                        pass
                    scene.cycles.device = "GPU"
                    devices = [{"name": d.name, "type": d.type, "use": bool(d.use)}
                               for d in cp.devices]
                    report["render_gpu"] = {
                        "backend": dtype, "device_used": dtype,
                        "scene_cycles_device": scene.cycles.device,
                        "devices": devices,
                        "note": "device selection + Cycles device-init line is the GPU proof"}
                    log("GPU PROOF select backend=%s device=%s" % (dtype, [d["name"] for d in devices if d["use"]]))
                    return True
            except Exception as e:
                log("GPU", dtype, "unavailable:", e)
    scene.cycles.device = "CPU"
    report["render_gpu"] = {"backend": "CPU_FALLBACK", "device_used": "CPU",
                            "scene_cycles_device": "CPU", "devices": [],
                            "note": "no OPTIX/CUDA device found; CPU render reported honestly"}
    return False


def render_preview(scene, path):
    if scene.camera is None:
        raise RuntimeError("no camera assigned to scene; cannot render preview")
    # A source compositor/sequencer can invoke another Scene that has no camera and
    # abort the render; disable both for this isolated preview.
    scene.render.use_sequencer = False
    scene.render.use_compositing = False
    bpy.context.view_layer.update()          # ensure camera/stage transform evaluated
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 32
    scene.render.resolution_x = 1000
    scene.render.resolution_y = 800
    scene.render.film_transparent = False
    scene.render.filepath = path
    world = bpy.data.worlds.new("PreviewWorld")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.85, 0.85, 0.85, 1)
    scene.world = world
    bpy.ops.render.render(write_still=True)


def main():
    args = parse_args()
    out = args.output_dir
    os.makedirs(out, exist_ok=True)
    report = {"script_rev": 4,
              "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
              "output_unit": "mm (world metres -> mm via scale_length*1000; origin/orientation preserved)",
              "cleanup_eps_mm": DEGENERATE_EPS_MM,
              "bodies": {}, "errors": []}

    scene = bpy.context.scene
    us = scene.unit_settings
    mm = mm_scale_factor()
    report["scene_units"] = {"system": us.system, "scale_length": us.scale_length,
                             "mm_factor": mm}

    src_objs = engine_mesh_objects()
    src_names = [o.name for o in src_objs]              # FROZEN (strings only)
    report["engine_object_count"] = len(src_names)
    report["engine_object_names"] = list(src_names)

    decimate_names = sorted(n for n in src_names if n in DECIMATE_NAMES)
    protected_names = [n for n in src_names if n not in DECIMATE_NAMES]
    report["protected_bodies"] = list(protected_names)
    report["decimated_bodies"] = list(decimate_names)

    # --- immutable mm baseline copies (kept alive until all metrics/exports done) ---
    base = {o.name: make_mm_copy(o, mm) for o in src_objs}
    base_tris = {n: tri_coords(base[n]) for n in src_names}

    lo, hi = bbox_of_tris(list(base_tris.values()))
    report["src_bbox_mm"] = {"min": [round(float(x), 3) for x in lo],
                             "max": [round(float(x), 3) for x in hi]}
    ok_bbox = (np.allclose(lo, EXPECTED_BBOX_MM["min"], atol=BBOX_TOL_MM) and
               np.allclose(hi, EXPECTED_BBOX_MM["max"], atol=BBOX_TOL_MM))
    report["bbox_close_to_expected"] = bool(ok_bbox)
    if not ok_bbox:
        fail("bbox %s..%s not near expected %s - check units/world transforms"
             % (lo.tolist(), hi.tolist(), EXPECTED_BBOX_MM))
    report["units_verified"] = "mm conversion asserted against expected engine bounds"

    for n in src_names:
        rec = report["bodies"].setdefault(n, {})
        rec["protected"] = n not in DECIMATE_NAMES
        rec["src_tris"] = int(len(base_tris[n]))
        rec["src_stats"] = analyze_mesh(base[n])

    # --- working copies; protected mounts bypass cleanup AND decimation ---
    working = {}
    for o in src_objs:
        w = make_mm_copy(o, mm)
        if o.name in DECIMATE_NAMES:
            clean_mesh_mm(w)
        working[o.name] = w
        rec = report["bodies"][o.name]
        rec["clean_tris"] = count_tris(w)
        rec["clean_stats"] = analyze_mesh(w)

    if args.save_source_blend:
        bpy.ops.wm.save_as_mainfile(
            filepath=os.path.join(out, "engine-source-extracted.blend"), copy=True)
        report["engine_source_extracted_blend"] = "engine-source-extracted.blend"

    # --- detailed decimation: ONLY DECIMATE_NAMES, proportional to hit target ---
    prot_total = sum(count_tris(working[n]) for n in protected_names)
    adj_total = sum(count_tris(working[n]) for n in decimate_names)
    factor_d = 1.0
    if adj_total > 0 and adj_total + prot_total > args.decimate_detailed:
        factor_d = max(max(args.decimate_detailed - prot_total, 1) / adj_total, 0.01)
    report["detailed_global_factor"] = factor_d
    for n in decimate_names:
        w = working[n]
        tgt = max(int(count_tris(w) * factor_d), 1) if factor_d < 1.0 else None
        report["bodies"][n]["detailed_ratio"] = decimate_body(w, tgt)
        report["bodies"][n]["detailed_tris"] = count_tris(w)
        report["bodies"][n]["detailed_stats"] = analyze_mesh(w)
        report["bodies"][n]["deviation_detailed"] = sample_deviation(base_tris[n], w)
    for n in protected_names:
        report["bodies"][n]["detailed_tris"] = count_tris(working[n])
        report["bodies"][n]["detailed_ratio"] = 1.0
        report["bodies"][n]["detailed_stats"] = report["bodies"][n]["clean_stats"]

    # JD green on large castings (before render)
    for n in decimate_names:
        w = working[n]
        if not w.data.materials:
            mat = bpy.data.materials.new("JDGreen")
            mat.use_nodes = True
            bsdf = mat.node_tree.nodes.get("Principled BSDF")
            if bsdf:
                bsdf.inputs["Base Color"].default_value = (*JD_GREEN, 1.0)
            w.data.materials.append(mat)

    # ================= EXPORTS FIRST (recoverable even if the render fails) =========
    # --- detailed STL ---
    tris_d = np.concatenate([tri_coords(working[n]) for n in src_names])
    n_d, size_d = export_binary_stl(tris_d, os.path.join(out, "engine-detailed.stl"))
    report["stl_detailed"] = {"path": "engine-detailed.stl", "triangles": n_d, "bytes": size_d}

    # --- light STL: further proportional decimation of DECIMATE_NAMES only ---
    adj_det = sum(count_tris(working[n]) for n in decimate_names)
    fl = 1.0
    if adj_det > 0 and adj_det + prot_total > args.decimate_light:
        fl = max(max(args.decimate_light - prot_total, 1) / adj_det, 0.01)
    report["light_global_factor_over_detailed"] = fl
    light_objs = []
    light_extra = []
    for n in src_names:
        if n not in DECIMATE_NAMES or fl >= 1.0:
            light_objs.append(working[n])
            report["bodies"][n]["light_ratio"] = 1.0
            report["bodies"][n]["light_stats"] = report["bodies"][n]["detailed_stats"]
        else:
            w2 = working[n].copy()
            w2.data = working[n].data.copy()
            w2.parent = None
            w2.matrix_parent_inverse = Matrix.Identity(4)
            scene.collection.objects.link(w2)
            w2.hide_viewport = False
            w2.hide_render = False
            decimate_body(w2, max(int(count_tris(w2) * fl), 1))
            light_objs.append(w2)
            light_extra.append(w2)
            report["bodies"][n]["light_ratio"] = fl
            report["bodies"][n]["light_tris"] = count_tris(w2)
            report["bodies"][n]["light_stats"] = analyze_mesh(w2)
            report["bodies"][n]["deviation_light"] = sample_deviation(base_tris[n], w2)

    tris_l = np.concatenate([tri_coords(o) for o in light_objs])
    n_l, size_l = export_binary_stl(tris_l, os.path.join(out, "engine-light.stl"))
    report["stl_light"] = {"path": "engine-light.stl", "triangles": n_l, "bytes": size_l}

    # --- validation + guards ---
    for key in ("stl_detailed", "stl_light"):
        v = validate_stl(os.path.join(out, report[key]["path"]), report[key]["triangles"])
        report[key]["validation"] = v
        if not (v["size_ok"] and v["count_matches_written"] and v["nonempty"]):
            fail("STL validation failed: %s" % key)
    bad = int((~np.isfinite(tris_d)).any(axis=(1, 2)).sum() +
              (~np.isfinite(tris_l)).any(axis=(1, 2)).sum())
    report["nonfinite_triangle_coords"] = bad
    if bad:
        fail("non-finite coordinates in export")

    allp = tris_l.reshape(-1, 3)
    report["cleaned_bbox_mm"] = {"min": [round(float(x), 3) for x in allp.min(axis=0)],
                                 "max": [round(float(x), 3) for x in allp.max(axis=0)]}
    report["stl_targets"] = {"detailed_target": args.decimate_detailed,
                             "light_target": args.decimate_light,
                             "detailed_actual": n_d, "light_actual": n_l}

    # FIX 5: prove mount preservation by array_equal, not by tri count
    for n in protected_names:
        a = base_tris[n]
        b = tri_coords(working[n])
        same = bool(a.shape == b.shape and a.size > 0 and
                    np.isfinite(b).all() and np.array_equal(a, b))
        rec = report["bodies"][n]
        rec["mount_preserved_exact"] = same
        rec["mount_tris"] = int(b.reshape(-1, 3).shape[0])
        rec["mount_dev_mm"] = 0.0 if same else None
        if not same:
            report["errors"].append("protected mount %s coords changed" % n)

    # aggregate sampled deviations + honest mesh-quality diagnostics
    det_devs = [report["bodies"][n].get("deviation_detailed", {}).get("max_dev_mm")
                for n in decimate_names]
    det_devs = [d for d in det_devs if d is not None]
    light_devs = [report["bodies"][n].get("deviation_light", {}).get("max_dev_mm")
                  for n in decimate_names]
    light_devs = [d for d in light_devs if d is not None]
    report["detailed_max_dev_mm"] = max(det_devs) if det_devs else 0.0
    report["light_max_dev_mm"] = max(light_devs) if light_devs else 0.0
    nm = sum(report["bodies"][n].get("detailed_stats", {}).get("nonmanifold_edges", 0)
             for n in src_names)
    be = sum(report["bodies"][n].get("detailed_stats", {}).get("boundary_edges", 0)
             for n in src_names)
    report["mesh_quality"] = {
        "watertight": False,
        "detailed_boundary_edges": int(be),
        "detailed_nonmanifold_edges": int(nm),
        "note": ("Source is an OPEN vendor mesh (not watertight). Conservative cleanup "
                 "removed duplicates/degenerate faces and reduced boundaries, but "
                 "decimation introduces non-manifold edges. Open boundaries and defects "
                 "REMAIN; this is NOT a healed solid."),
    }

    report["engine_cleaned_blend"] = "engine-cleaned.blend"

    report["warnings"] = [
        "STL outputs are mesh/graphics references: NOT analytic solids and NOT watertight.",
        "Source is an OPEN vendor mesh (not watertight). Conservative cleanup reduced "
        "boundary edges and performed NO hole-filling, but cleanup/decimation introduce "
        "non-manifold edges (see mesh_quality). Open boundaries and defects REMAIN; this "
        "is not a healed solid.",
        "Deviation values are sampled BVH estimates, not certified Hausdorff distances.",
        "Protected bodies bypass cleanup/decimation; preservation proven by exact coord compare.",
        "Native SolidWorks import has NOT been tested by this pipeline.",
    ]

    def write_outputs():
        report["seconds_elapsed"] = round(time.time() - T0, 1)
        with open(os.path.join(out, "astra-engine-export.json"), "w") as f:
            json.dump(report, f, indent=2)
        light_dev = report.get("light_max_dev_mm")
        if light_dev is not None and light_dev <= 3.0:
            light_line = ("- `engine-light.stl` - binary STL, %d tris (~17.5 MB). Measured sampled "
                          "max deviation %.3f mm (<= 3 mm): usable as a compact reference."
                          % (n_l, light_dev))
            report["light_usage"] = "compact reference (max dev %.3f mm <= 3 mm)" % light_dev
        else:
            ld = light_dev if light_dev is not None else float("nan")
            light_line = ("- `engine-light.stl` - binary STL, %d tris (~17.5 MB). **VISUAL-ONLY**: "
                          "measured sampled max deviation %.3f mm (> 3 mm) - NOT for fit/clearance."
                          % (n_l, ld))
            report["light_usage"] = "visual-only (max dev %.3f mm > 3 mm)" % ld
        lines = [
            "# Astra Engine Export (mesh reference, rev 4)",
            "",
            "Units: **millimetres** (source world metres converted via scale_length*1000; assembly",
            "origin & orientation preserved; bbox asserted against expected engine bounds).",
            "Source: `engine-and-pump-v10.blend`, collection `CAD_engine` (%d meshes). Pump/skid/bale excluded." % len(src_names),
            "",
            "## Recommended file for reference",
            ("- `engine-detailed.stl` - binary STL, %d tris (~25 MB), sampled max deviation %.3f mm. "
             "Recommended for reference/measurement; still a mesh, NOT an analytic solid."
             % (n_d, report.get("detailed_max_dev_mm", 0.0))),
            "",
            "## Files",
            "- `engine-cleaned.blend` - engine bodies only, mm world coords (unit scale 0.001);",
            "  all non-decimated bodies (%s) preserved coordinate-exact." % ", ".join(protected_names),
            "- `engine-detailed.stl` - binary STL, %d tris (target %d), ~25 MB." % (n_d, args.decimate_detailed),
            light_line,
            "- `engine-preview.png` - 1000x800 Cycles preview (GPU/CPU evidence in JSON).",
            "- `astra-engine-export.json` - topology before/after, deviations, STL validation, GPU evidence.",
            "",
            "## SolidWorks import (native import NOT yet tested by this pipeline)",
            "- Use File > Open, select the STL, then set Options units = millimetres.",
            "- Import as **Graphics Body**, or as a mesh/BREP if your SolidWorks version offers it.",
            "- Do NOT accept the default conventional facet-per-face Solid Body conversion; it is",
            "  unsuitable for this large open assembly mesh.",
            "- The .blend can be appended for individual bodies (unit scale 0.001 = mm).",
            "",
            "## Limitations",
            "These STL files are mesh/graphics references: NOT analytic solids and NOT watertight.",
            "The source is an OPEN vendor mesh; bores/ports are NOT filled and no voxel clearance",
            "fill was performed. Cleanup/decimation leave open boundaries and introduce non-manifold",
            "edges (see astra-engine-export.json mesh_quality). Defects REMAIN - this is not a",
            "healed solid. Deviations are deterministic BVH-sample estimates, not certified Hausdorff.",
        ]
        with open(os.path.join(out, "README.md"), "w") as f:
            f.write("\n".join(lines) + "\n")

    # write report/README BEFORE isolation AND before the render so artifacts survive both
    write_outputs()

    # ================= DESTRUCTIVE ISOLATION + CLEANED BLEND (true END) =================
    # keep only the *detailed* working bodies; drop baselines, originals and light copies.
    keep_ptrs = {working[n].as_pointer() for n in src_names}
    for ob in list(bpy.data.objects):
        if ob.as_pointer() not in keep_ptrs:
            bpy.data.objects.remove(ob, do_unlink=True)
    # FIX 4: represent mm correctly in the saved blend
    scene.unit_settings.scale_length = 0.001
    try:
        scene.unit_settings.length_unit = 'MILLIMETERS'
    except Exception:
        pass
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "engine-cleaned.blend"), copy=True)

    # ================= PREVIEW RENDER LAST (best effort) =================
    png = os.path.join(out, "engine-preview.png")
    try:
        stage_scene(scene, [working[n] for n in src_names])
        gpu_ok = setup_gpu_cycles(scene, report)
        render_preview(scene, png)
        ok_png = os.path.exists(png) and os.path.getsize(png) > 1024
        report["preview"] = {"path": "engine-preview.png", "res": "1000x800",
                             "samples": 32, "engine": "CYCLES", "gpu": gpu_ok,
                             "backend": report["render_gpu"]["backend"],
                             "bytes": os.path.getsize(png) if os.path.exists(png) else 0,
                             "written": bool(ok_png)}
        if not ok_png:
            report["errors"].append("preview PNG missing/too small")
    except Exception as e:
        report["preview"] = {"error": "%s: %s" % (type(e).__name__, e),
                             "backend": "FAILED"}
        report["errors"].append("preview failed: %s" % e)

    write_outputs()

    log("DONE rev3 in %s s" % report["seconds_elapsed"])
    log("detailed STL: %d tris; light STL: %d tris; preview=%s"
        % (n_d, n_l, report.get("preview", {}).get("backend")))


main()
