"""astra_controller_v10.py -- relocate the controller + bale bracket group onto the
engine-side tapered face of the -X lifting-bale upright (LBU-PP.001), for scene v10.

Everything is MEASURED from the loaded .blend; no placement constant is assumed.
Every numeric post-condition is enforced by an assertion that terminates the
process with a non-zero exit status when violated.

Modes (the .blend is given on the Blender command line):
  measure : read-only. Measure datums and target planes, write JSON, never save.
  apply   : measure -> assert -> rigid translation -> assert invariants -> save v10.
  verify  : read-only. Re-check a produced blend against a baseline census JSON.

Usage:
  blender --background -t 4 IN.blend --python tools/astra_controller_v10.py -- measure OUT.json
  blender --background -t 4 IN.blend --python tools/astra_controller_v10.py -- apply OUT.blend OUT.json SRC_SHA256
  blender --background -t 4 IN.blend --python tools/astra_controller_v10.py -- verify BASELINE.json OUT.json
"""
import bpy, os, sys, json, math, hashlib, time
import numpy as np
from mathutils import Vector, Matrix

# ---------------------------------------------------------------- args
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
MODE = argv[0] if argv else "measure"
THREADS = 4
MM = 1000.0
INCH = 0.0254

# ---------------------------------------------------------------- report / assertions
REPORT = {}
CHECKS = []


def check(name, ok, detail):
    ok = bool(ok)
    CHECKS.append({"assertion": name, "ok": ok, "detail": detail})
    print(("  [OK]   " if ok else "  [FAIL] ") + name + ": " + detail)
    if not ok:
        raise AssertionError("ASSERTION FAILED: " + name + ": " + detail)


def die(msg):
    print("FATAL: " + msg)
    sys.stdout.flush()
    os._exit(2)


def write_report(path):
    REPORT["assertions"] = CHECKS
    bad = [c for c in CHECKS if not c["ok"]]
    REPORT["verdict"] = "PASS" if (CHECKS and not bad) else "FAIL"
    if path:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(REPORT, f, indent=1)
        print("REPORT -> " + path + " (" + str(os.path.getsize(path)) + " bytes)")
    print("VERDICT " + REPORT["verdict"])


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(1 << 22), b""):
            h.update(blk)
    return h.hexdigest()


# ---------------------------------------------------------------- geometry helpers
def mesh_objs():
    return [o for o in bpy.data.objects if o.type == "MESH"]


def wbox(objs):
    lo = Vector((1e18,) * 3)
    hi = Vector((-1e18,) * 3)
    for o in objs:
        for c in o.bound_box:
            p = o.matrix_world @ Vector(c)
            for i in range(3):
                if p[i] < lo[i]:
                    lo[i] = p[i]
                if p[i] > hi[i]:
                    hi[i] = p[i]
    return lo, hi


def box_mm(objs):
    lo, hi = wbox(objs)
    return {"min_mm": [round(v * MM, 3) for v in lo],
            "max_mm": [round(v * MM, 3) for v in hi],
            "size_mm": [round((hi[i] - lo[i]) * MM, 3) for i in range(3)]}


def face_groups(o):
    """Group polygons by rounded world normal; area-weighted centroid and normal."""
    mw = o.matrix_world
    nrm = mw.to_3x3().inverted().transposed()
    g = {}
    for p in o.data.polygons:
        n = (nrm @ p.normal).normalized()
        a = p.area
        if a <= 0.0:
            continue
        c = mw @ p.center
        key = (round(n.x, 2), round(n.y, 2), round(n.z, 2))
        e = g.get(key)
        if e is None:
            e = g[key] = {"area": 0.0, "count": 0, "c": Vector((0.0, 0.0, 0.0)),
                          "n": Vector((0.0, 0.0, 0.0))}
        e["area"] += a
        e["count"] += 1
        e["c"] += c * a
        e["n"] += n * a
    for e in g.values():
        e["centroid"] = e["c"] / e["area"]
        e["normal"] = e["n"].normalized()
    return g


def tilted_faces(o, sign_y, min_area):
    """Faces whose outward normal is mostly -/+Y: the bale-upright taper faces."""
    out = []
    for e in face_groups(o).values():
        n = e["normal"]
        if e["area"] < min_area:
            continue
        if n.y * sign_y > 0.90 and abs(n.z) < 0.30 and abs(n.x) < 0.30:
            out.append(e)
    out.sort(key=lambda e: -e["area"])
    return out


def mesh_digest(o):
    """Hash of the mesh data in object-local space: invariant under rigid moves."""
    me = o.data
    co = np.empty(len(me.vertices) * 3, dtype=np.float32)
    me.vertices.foreach_get("co", co)
    li = np.empty(len(me.loops), dtype=np.int32)
    me.loops.foreach_get("vertex_index", li)
    pi = np.empty(len(me.polygons), dtype=np.int32)
    me.polygons.foreach_get("loop_start", pi)
    h = hashlib.sha256()
    for a in (co, li, pi):
        h.update(a.tobytes())
    return h.hexdigest()


def snapshot(objs):
    return {o.name: {"matrix": [round(v, 10) for row in o.matrix_world for v in row],
                     "digest": mesh_digest(o)} for o in objs}


def mat_eq(a, b, tol=1e-7):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def mat_mul_before(m, T):
    M = Matrix([m[0:4], m[4:8], m[8:12], m[12:16]])
    return [round(v, 10) for row in (T @ M) for v in row]


def world_verts(o):
    n = len(o.data.vertices)
    co = np.empty(n * 3, dtype=np.float32)
    o.data.vertices.foreach_get("co", co)
    co = co.reshape(n, 3)
    m = np.array(o.matrix_world)
    pts = co @ m[0:3, 0:3].T + m[0:3, 3]
    return pts


def taper_from_envelope(o):
    """Taper of the upright from its own vertex envelope (Y half-width vs Z)."""
    pts = world_verts(o)
    z = pts[:, 2]
    lo, hi = float(z.min()), float(z.max())
    span = hi - lo
    b = pts[z <= lo + 0.05 * span]
    t = pts[z >= hi - 0.05 * span]
    yb = float(np.abs(b[:, 1]).max())
    yt = float(np.abs(t[:, 1]).max())
    deg = math.degrees(math.atan2(yb - yt, hi - lo))
    return {"deg": deg, "ymax_low_mm": round(yb * MM, 1), "ymax_high_mm": round(yt * MM, 1),
            "z_low_mm": round(lo * MM, 1), "z_high_mm": round(hi * MM, 1)}


# ---------------------------------------------------------------- scene facts
def collect_scene():
    groups = {}
    for c in bpy.data.collections:
        groups[c.name] = sorted(o.name for o in c.objects if o.type == "MESH")
    return groups


def controller_subtree():
    root = bpy.data.objects.get("CPM-PP-JD18")
    if root is None:
        die("controller root empty CPM-PP-JD18 not found")
    meshes = []

    def walk(o):
        for ch in o.children:
            if ch.type == "MESH":
                meshes.append(ch)
            walk(ch)

    walk(root)
    meshes.sort(key=lambda o: o.name)
    return root, meshes


# ---------------------------------------------------------------- apply mode
def main():
    src = os.path.abspath(bpy.data.filepath)
    REPORT["meta"] = {"mode": MODE, "source_blend": src, "blender": bpy.app.version_string,
                      "threads": THREADS, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    bpy.context.scene.render.threads_mode = "FIXED"
    bpy.context.scene.render.threads = THREADS

    all_mesh = mesh_objs()
    scene_groups = collect_scene()
    REPORT["census"] = {"total_mesh_objects": len(all_mesh),
                        "total_polygons": int(sum(len(o.data.polygons) for o in all_mesh)),
                        "by_collection": {k: len(v) for k, v in sorted(scene_groups.items())}}
    print("census: " + str(len(all_mesh)) + " mesh objects in " + str(len(scene_groups)) + " collections")

    quar = [c.name for c in bpy.data.collections if "QUAR" in c.name.upper()]
    quar_objs = [o.name for c in bpy.data.collections if c.name in quar for o in c.objects]
    REPORT["quarantine"] = {"present": bool(quar), "collections": quar,
                            "objects": len(quar_objs), "removed": False}
    print("quarantine collections: " + (str(quar) if quar else "NONE"))

    root, ctrl = controller_subtree()
    ctrl_names = [o.name for o in ctrl]
    coll_ctrl = scene_groups.get("CAD_controller", [])
    check("controller_subtree_found", len(ctrl) > 0, "root=CPM-PP-JD18 mesh children=" + str(ctrl_names))
    check("controller_subtree_matches_collection", sorted(ctrl_names) == sorted(coll_ctrl),
          "subtree=" + str(ctrl_names) + " vs collection CAD_controller=" + str(coll_ctrl))
    REPORT["census"]["controller_subtree"] = ctrl_names

    up = bpy.data.objects.get("LBU-PP.001")
    check("minus_x_upright_exists", up is not None and up.type == "MESH", "object LBU-PP.001")
    uplo, uphi = wbox([up])
    check("upright_is_minus_x", uphi.x < 0.0,
          "LBU-PP.001 X range [" + str(round(uplo.x * MM, 1)) + ", " + str(round(uphi.x * MM, 1)) + "] mm")
    check("upright_in_bale_collection", "LBU-PP.001" in scene_groups.get("CAD_bale", []),
          "CAD_bale = " + str(scene_groups.get("CAD_bale")))

    skid_objs = [bpy.data.objects[n] for n in scene_groups.get("CAD_skid", [])]
    check("skid_collection_nonempty", len(skid_objs) > 0, "CAD_skid n=" + str(len(skid_objs)))
    skid_bottom = min((o.matrix_world @ Vector(c)).z for o in skid_objs for c in o.bound_box)
    scene_bottom = min((o.matrix_world @ Vector(c)).z for o in all_mesh for c in o.bound_box)
    check("skid_bottom_is_scene_bottom", abs(skid_bottom - scene_bottom) < 1e-6,
          "CAD_skid min Z " + str(round(skid_bottom * MM, 2)) + " mm == scene min Z "
          + str(round(scene_bottom * MM, 2)) + " mm")
    target_bottom = skid_bottom + 48.0 * INCH
    REPORT["measured_datums"] = {"skid_bottom_z_mm": round(skid_bottom * MM, 3),
                                 "scene_min_z_mm": round(scene_bottom * MM, 3),
                                 "bracket_height_target_in": 48.0,
                                 "bracket_bottom_target_z_mm": round(target_bottom * MM, 3)}

    eng_objs = [bpy.data.objects[n] for n in scene_groups.get("CAD_engine", [])]
    elo, ehi = wbox(eng_objs)
    eng_c = (elo + ehi) / 2.0
    up_c = (uplo + uphi) / 2.0
    toward_engine = (eng_c - up_c).normalized()
    REPORT["measured_datums"]["engine_bbox_mm"] = box_mm(eng_objs)
    REPORT["measured_datums"]["upright_bbox_mm"] = box_mm([up])

    cand_neg = tilted_faces(up, -1.0, 0.02)
    cand_pos = tilted_faces(up, +1.0, 0.02)
    check("upright_taper_faces_found", len(cand_neg) > 0 and len(cand_pos) > 0,
          "-Y faces=" + str(len(cand_neg)) + " +Y faces=" + str(len(cand_pos)))
    cands = []
    for s, lst in ((-1.0, cand_neg), (+1.0, cand_pos)):
        if lst:
            e = lst[0]
            cands.append({"sign_y": s, "area_mm2": round(e["area"] * MM * MM, 1),
                          "normal": [round(v, 5) for v in e["normal"]],
                          "centroid_mm": [round(v * MM, 3) for v in e["centroid"]],
                          "faces": e["count"],
                          "dot_toward_engine": round(e["normal"].dot(toward_engine), 4)})
    REPORT["measured_datums"]["upright_taper_candidates"] = cands
    chosen = max(cands, key=lambda c: c["dot_toward_engine"])
    check("engine_side_face_selected_by_geometry", chosen["dot_toward_engine"] > 0.5,
          "picked outward normal " + str(chosen["normal"]) + " dot toward engine centroid "
          + str(chosen["dot_toward_engine"]))
    Nu = Vector(chosen["normal"]).normalized()
    Pu_c = None
    for s, lst in ((-1.0, cand_neg), (+1.0, cand_pos)):
        if lst and abs(s - chosen["sign_y"]) < 1e-9:
            Pu_c = lst[0]["centroid"]
    zaxis_deg = math.degrees(math.acos(max(-1.0, min(1.0, abs(Nu.z)))))
    off_vert = 90.0 - zaxis_deg          # angle of the tapered face away from vertical
    check("upright_taper_tilt_plausible", 1.5 < off_vert < 4.5,
          "engine-side face normal " + str(round(zaxis_deg, 3)) + " deg from the Z axis = "
          + str(round(off_vert, 3)) + " deg off vertical (handoff: 87.13 deg from Z / 2.87 off vertical)")
    env = taper_from_envelope(up)
    check("taper_agrees_with_vertex_envelope", abs(env["deg"] - off_vert) < 0.5,
          "face-normal taper " + str(round(off_vert, 2)) + " deg vs vertex-envelope taper "
          + str(round(env["deg"], 2)) + " deg (" + str(env) + ")")
    REPORT["measured_datums"]["target_face"] = {
        "object": "LBU-PP.001", "outward_normal": [round(v, 6) for v in Nu],
        "centroid_mm": [round(v * MM, 3) for v in Pu_c],
        "normal_angle_from_z_deg": round(zaxis_deg, 3),
        "face_off_vertical_deg": round(off_vert, 3),
        "area_mm2": chosen["area_mm2"], "faces": chosen["faces"], "envelope_crosscheck": env}

    cands_m = []
    for o in ctrl:
        for e in face_groups(o).values():
            if e["area"] < 0.0005:
                continue
            d = Nu.dot(e["normal"])
            if d < -0.99:
                cands_m.append({"part": o.name, "area_mm2": round(e["area"] * MM * MM, 1),
                                "normal": [round(v, 6) for v in e["normal"]], "dot_with_upright_normal": round(d, 6),
                                "centroid_mm": [round(v * MM, 3) for v in e["centroid"]],
                                "_e": e, "_o": o})
    cands_m.sort(key=lambda c: c["dot_with_upright_normal"])
    REPORT["measured_datums"]["mating_candidates"] = [
        {k: v for k, v in c.items() if not k.startswith("_")} for c in cands_m]
    for c in cands_m:
        print("  candidate mating face: " + c["part"] + " area=" + str(c["area_mm2"]) + " mm2 normal="
              + str(c["normal"]) + " dot=" + str(c["dot_with_upright_normal"]))
    tight = [c for c in cands_m if c["dot_with_upright_normal"] < -0.9995]
    check("bracket_mating_face_found", len(tight) > 0,
          "controller parts with a face genuinely antiparallel (dot < -0.9995, <1.8 deg) to the "
          + "upright taper: " + str(sorted(set(c["part"] for c in tight))))
    tight.sort(key=lambda c: -c["area_mm2"])
    brk, be = tight[0]["_o"], tight[0]["_e"]
    Nb = be["normal"].normalized()
    Pb_c = be["centroid"]
    ang = math.degrees(math.acos(max(-1.0, min(1.0, -Nu.dot(Nb)))))
    check("taper_mating_already_antiparallel", ang < 0.5,
          brk.name + " mating normal " + str([round(v, 5) for v in Nb]) + " vs upright "
          + str([round(v, 5) for v in Nu]) + ": " + str(round(ang, 3))
          + " deg off antiparallel (no rotation, nothing to cut)")
    REPORT["measured_datums"]["bracket_mating_face"] = {
        "bracket_object": brk.name, "mating_normal": [round(v, 6) for v in Nb],
        "mating_centroid_mm": [round(v * MM, 3) for v in Pb_c],
        "area_mm2": round(be["area"] * MM * MM, 1),
        "deviation_from_antiparallel_deg": round(ang, 4),
        "tight_candidate_parts": sorted(set(c["part"] for c in tight)),
        "near_miss_parts": sorted(set(c["part"] for c in cands_m if c["dot_with_upright_normal"] >= -0.9995))}
    check("bracket_is_PP-CPM-1005", brk.name == "PP-CPM-1005",
          "mating part derived from geometry = " + brk.name)
    check("controller_subtree_size", len(ctrl) == 3, str(ctrl_names))

    brk_bottom = min((brk.matrix_world @ Vector(c)).z for c in brk.bound_box)
    sub_bottom = min((o.matrix_world @ Vector(c)).z for o in ctrl for c in o.bound_box)
    REPORT["measured_datums"]["bracket_bottom_before_mm"] = round(brk_bottom * MM, 3)
    REPORT["measured_datums"]["controller_subtree_bottom_before_mm"] = round(sub_bottom * MM, 3)
    print("bracket(" + brk.name + ") bottom before = " + str(round(brk_bottom * MM, 2)) + " mm ("
          + str(round((brk_bottom - skid_bottom) / INCH, 2)) + " in above skid bottom); target "
          + str(round((target_bottom - skid_bottom) / INCH, 2)) + " in")

    gap = Nu.dot(Pu_c - Pb_c)
    d1 = gap * Nu
    S = (Vector((0, 0, 1)) - Vector((0, 0, 1)).dot(Nu) * Nu).normalized()
    check("inplane_axis_valid", abs(S.z) > 0.9 and abs(S.dot(Nu)) < 1e-9,
          "in-plane slide axis " + str([round(v, 6) for v in S]) + " (S.N=" + str(S.dot(Nu)) + ")")
    t = (target_bottom - (brk_bottom + d1.z)) / S.z
    d2 = t * S
    d3 = Vector((Pu_c.x - Pb_c.x, 0.0, 0.0))
    DT = d1 + d2 + d3
    REPORT["transform"] = {"delta_mm": [round(DT.x * MM, 3), round(DT.y * MM, 3), round(DT.z * MM, 3)],
                           "perpendicular_gap_before_mm": round(gap * MM, 3),
                           "inplane_slide_t_mm": round(t * MM, 3),
                           "x_align_mm": round(d3.x * MM, 3),
                           "rotation_deg": 0.0,
                           "note": "pure translation; mating faces already antiparallel"}
    print("total translation dX=" + str(round(DT.x * MM, 2)) + " dY=" + str(round(DT.y * MM, 2))
          + " dZ=" + str(round(DT.z * MM, 2)) + " mm")

    before_all = snapshot(all_mesh)
    before_ctrl = {o.name: {"matrix_world": before_all[o.name]["matrix"],
                            "bbox_mm": box_mm([o])} for o in ctrl}

    if MODE == "measure":
        REPORT["moved_objects"] = ctrl_names
        REPORT["before"] = before_ctrl
        write_report(argv[1] if len(argv) > 1 else None)
        print("measure mode: no modification, no save.")
        sys.stdout.flush()
        os._exit(0)

    if MODE != "apply":
        die("unknown mode " + MODE)

    out_blend = os.path.abspath(argv[1])
    out_json = os.path.abspath(argv[2])
    src_sha = argv[3]
    check("source_hash_matches_expected", sha256(src) == src_sha, src + " sha256 " + src_sha[:16] + "...")
    check("output_is_new_file", out_blend != src, "out=" + out_blend)
    check("output_not_a_v9_file", "-v9" not in os.path.basename(out_blend), os.path.basename(out_blend))

    T = Matrix.Translation(DT)
    root.matrix_world = T @ root.matrix_world
    bpy.context.view_layer.update()

    after_all = snapshot(all_mesh)
    REPORT["moved_objects"] = ctrl_names
    REPORT["before"] = before_ctrl
    REPORT["after"] = {o.name: {"matrix_world": after_all[o.name]["matrix"],
                                "bbox_mm": box_mm([o])} for o in ctrl}

    for o in ctrl:
        exp = mat_mul_before(before_all[o.name]["matrix"], T)
        got = after_all[o.name]["matrix"]
        dev = max(abs(a - b) for a, b in zip(exp, got))
        check("moved_rigidly[" + o.name + "]", mat_eq(exp, got, 1e-6),
              "world matrix == T @ before, max dev " + str(dev))
        check("geometry_unchanged[" + o.name + "]",
              before_all[o.name]["digest"] == after_all[o.name]["digest"],
              "mesh hash identical (no cutting, no vertex edit)")

    be2 = None
    for e in face_groups(brk).values():
        if Nu.dot(e["normal"]) < -0.99 and e["area"] >= be["area"] * 0.5:
            if be2 is None or e["area"] > be2["area"]:
                be2 = e
    check("mating_face_still_present_after", be2 is not None, brk.name + " mating face re-found")
    Pb2 = be2["centroid"]
    gap_after = Nu.dot(Pu_c - Pb2)
    dot_after = -Nu.dot(be2["normal"].normalized())
    check("mating_gap_zero", abs(gap_after) <= 0.5 * 0.001,
          "perpendicular face-to-face gap after = " + str(round(gap_after * MM, 4)) + " mm")
    check("mating_normals_antiparallel", dot_after > 0.99996,
          "-Nu.Nb = " + str(round(dot_after, 8)) + " ("
          + str(round(math.degrees(math.acos(min(1.0, dot_after))), 4)) + " deg off)")
    brk_bottom2 = min((brk.matrix_world @ Vector(c)).z for c in brk.bound_box)
    check("bracket_height_48in", abs(brk_bottom2 - target_bottom) <= 0.5 * 0.001,
          "bracket bottom Z = " + str(round(brk_bottom2 * MM, 3)) + " mm vs target "
          + str(round(target_bottom * MM, 3)) + " mm => "
          + str(round((brk_bottom2 - skid_bottom) / INCH, 4)) + " in above skid bottom")
    xres = (Pu_c.x - Pb2.x) * MM
    check("x_centred_on_upright_face", abs(xres) <= 0.5,
          "X residual between upright-face and bracket-face centroids = " + str(round(xres, 4)) + " mm")
    check("no_penetration_through_upright", gap_after >= -0.5 * 0.001,
          "gap " + str(round(gap_after * MM, 4)) + " mm >= 0: bracket sits on the upright face")

    REPORT["verification"] = {
        "mating_gap_after_mm": round(gap_after * MM, 4),
        "mating_normal_alignment_negNu_dot_Nb": round(dot_after, 8),
        "mating_angle_error_deg": round(math.degrees(math.acos(min(1.0, dot_after))), 5),
        "bracket_bottom_after_mm": round(brk_bottom2 * MM, 3),
        "bracket_bottom_after_in_above_skid": round((brk_bottom2 - skid_bottom) / INCH, 4),
        "x_align_residual_mm": round(xres, 4),
        "controller_subtree_bbox_after_mm": box_mm(ctrl)}

    ctrl_set = set(ctrl_names)
    inv = {}
    groups = {"pump": scene_groups.get("CAD_pump", []) + scene_groups.get("CAD_pump_new", []),
              "engine": scene_groups.get("CAD_engine", []),
              "skid": scene_groups.get("CAD_skid", []),
              "bale": scene_groups.get("CAD_bale", []),
              "all_non_target": [o.name for o in all_mesh if o.name not in ctrl_set]}
    for gname, names in groups.items():
        m_ok = all(mat_eq(before_all[n]["matrix"], after_all[n]["matrix"], 0.0) for n in names)
        d_ok = all(before_all[n]["digest"] == after_all[n]["digest"] for n in names)
        inv[gname] = {"objects": len(names), "matrices_unchanged": bool(m_ok),
                      "mesh_geometry_unchanged": bool(d_ok)}
        check("invariant[" + gname + "]_matrices", m_ok,
              str(len(names)) + " objects, world matrices bit-identical")
        check("invariant[" + gname + "]_geometry", d_ok,
              str(len(names)) + " objects, mesh hashes identical")
    REPORT["non_target_invariants"] = inv
    check("engine_pump_overlap_untouched",
          all(mat_eq(before_all[n]["matrix"], after_all[n]["matrix"], 0.0)
              for n in groups["pump"] + groups["engine"]),
          "intentional engine/pump Y overlap left exactly as in v9")

    if quar:
        for c in list(bpy.data.collections):
            if "QUAR" in c.name.upper():
                for o in list(c.objects):
                    bpy.data.objects.remove(o, do_unlink=True)
                bpy.data.collections.remove(c)
        REPORT["quarantine"]["removed"] = True
        check("quarantine_removed",
              not [c for c in bpy.data.collections if "QUAR" in c.name.upper()],
              "quarantine collection deleted from the output")
    else:
        check("quarantine_absent_reported", True,
              "no quarantine collection existed in the source; nothing to remove")

    REPORT["invariant_summary"] = {"moved": ctrl_names,
                                   "untouched_mesh_objects": len(all_mesh) - len(ctrl)}

    bpy.ops.wm.save_as_mainfile(filepath=out_blend)
    check("output_saved", os.path.exists(out_blend), out_blend)
    REPORT["meta"]["output_blend"] = out_blend
    REPORT["meta"]["output_bytes"] = os.path.getsize(out_blend)
    REPORT["meta"]["source_sha256_before"] = src_sha
    REPORT["meta"]["source_sha256_after"] = sha256(src)
    REPORT["meta"]["output_sha256"] = sha256(out_blend)
    check("source_untouched",
          REPORT["meta"]["source_sha256_before"] == REPORT["meta"]["source_sha256_after"],
          "v9 blend sha256 identical before and after the run")

    print("saved " + out_blend + " (" + str(REPORT["meta"]["output_bytes"]) + " bytes) sha256 "
          + REPORT["meta"]["output_sha256"][:16] + "...")
    write_report(out_json)


# ---------------------------------------------------------------- verify mode
def verify_main():
    src = os.path.abspath(bpy.data.filepath)
    baseline = json.load(open(argv[1], encoding="utf-8"))
    out_json = os.path.abspath(argv[2])
    REPORT["meta"] = {"mode": "verify", "file": src, "baseline": os.path.abspath(argv[1]),
                      "blender": bpy.app.version_string,
                      "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    base = {r["name"]: r for r in baseline}
    all_mesh = mesh_objs()
    groups = collect_scene()
    REPORT["census"] = {"total_mesh_objects": len(all_mesh),
                        "total_polygons": int(sum(len(o.data.polygons) for o in all_mesh)),
                        "by_collection": {k: len(v) for k, v in sorted(groups.items())}}
    check("census_matches_baseline", len(all_mesh) == len(baseline),
          str(len(all_mesh)) + " mesh objects (baseline " + str(len(baseline)) + ")")
    _, ctrl = controller_subtree()
    ctrl_names = sorted(o.name for o in ctrl)
    check("controller_subtree_still_3", len(ctrl) == 3, str(ctrl_names))

    bad = []
    TOL_MM = 0.02   # the baseline census rounds world coords to a 0.01 mm grid
    for o in all_mesh:
        if o.name in ctrl_names:
            continue
        r = base.get(o.name)
        if r is None:
            bad.append(o.name + ":missing")
            continue
        lo, hi = wbox([o])
        if (max(abs(lo[i] * MM - r["min"][i] * MM) for i in range(3)) > TOL_MM or
                max(abs(hi[i] * MM - r["max"][i] * MM) for i in range(3)) > TOL_MM):
            bad.append(o.name + ":bbox")
    check("non_targets_match_baseline", not bad,
          str(len(all_mesh) - 3) + " non-controller objects match the v9 census within "
          + str(TOL_MM) + " mm (baseline grid)" if not bad else str(bad[:8]))

    moved = 0
    for o in ctrl:
        r = base[o.name]
        lo, hi = wbox([o])
        d = max(abs(lo[i] * MM - r["min"][i] * MM) for i in range(3))
        if d > 1.0:
            moved += 1
        REPORT.setdefault("controller_delta_mm", {})[o.name] = {
            "bbox_min_before_mm": r["min"], "bbox_min_after_mm": [round(v * MM, 3) for v in lo],
            "max_abs_shift_mm": round(d, 3)}
    check("controller_group_moved", moved == 3,
          str(moved) + "/3 controller parts shifted > 1 mm vs v9")

    brk = bpy.data.objects["PP-CPM-1005"]
    skid = [bpy.data.objects[n] for n in groups.get("CAD_skid", [])]
    sb = min((x.matrix_world @ Vector(c)).z for x in skid for c in x.bound_box)
    bb = min((brk.matrix_world @ Vector(c)).z for c in brk.bound_box)
    h_in = (bb - sb) / INCH
    check("bracket_height_48in_in_file", abs(h_in - 48.0) <= 0.02,
          "bracket bottom " + str(round((bb - sb) * MM, 3)) + " mm above skid bottom = "
          + str(round(h_in, 4)) + " in")
    check("no_quarantine_in_output",
          not [c for c in bpy.data.collections if "QUAR" in c.name.upper()],
          "collections: " + str(sorted(c.name for c in bpy.data.collections)))
    REPORT["verification"] = {"bracket_bottom_above_skid_mm": round((bb - sb) * MM, 3),
                              "bracket_height_in": round(h_in, 4),
                              "controller_parts_moved": moved}
    write_report(out_json)


try:
    if MODE == "verify":
        verify_main()
    else:
        main()
except SystemExit:
    raise
except BaseException as e:
    print("EXCEPTION: " + repr(e))
    CHECKS.append({"assertion": "uncaught_exception", "ok": False, "detail": repr(e)})
    try:
        p = None
        if MODE == "apply" and len(argv) > 2:
            p = argv[2]
        elif MODE == "verify" and len(argv) > 2:
            p = argv[2]
        elif len(argv) > 1:
            p = argv[1]
        write_report(p)
    except Exception as e2:
        print("report write failed: " + repr(e2))
    sys.stdout.flush()
    os._exit(1)
sys.stdout.flush()
os._exit(0)
