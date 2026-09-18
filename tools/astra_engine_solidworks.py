"""astra_engine_solidworks.py -- export the engine in the formats SolidWorks can
actually show, including colour.

Companion to tools/astra_engine_export.py (rev 4), which produced the 25 MB
engine-detailed-mm.stl.  That file is a correct STL; the problem is what
SolidWorks does with it.  See docs/solidworks-import.md for the full diagnosis.
The short version:

  * STL carries no colour, so SolidWorks always shows it grey.  OBJ imported as
    a GRAPHICS BODY does carry per-facet colour -- that is the only route that
    reproduces the Blender look.
  * SolidWorks' default mesh import builds one BREP face per facet, capped at
    500,000.  The rev4 STL has 499,998 -- under the cap, so SolidWorks accepts it
    and then tries to knit half a million faces.  Default --facet-budget here is
    450,000, deliberately clear of that cliff.
  * An STL has no concept of a body, so all 7 engine bodies collapse into one
    shell.  bodies/ gets one STL each, so SolidWorks shows 7 selectable bodies.

Outputs (into --out-dir):
    engine-colour-mm.obj + .mtl    coloured; import as Graphics Body
    engine-graphics-mm.stl         single STL, <= --facet-budget facets
    bodies/<name>-mm.stl           one STL per engine body
    README.md, MANIFEST.sha256

Run:
  blender -b -noaudio --threads 4 out/engine-and-pump-v11-wide.blend \
     --python-exit-code 1 --python tools/astra_engine_solidworks.py -- \
     --out-dir out/engine-solidworks-rev5 \
     --out-json reports/astra-engine-solidworks.json

NEVER mutates the source: every operation runs on unparented "__mm" copies with
the world matrix and the metres->mm scale baked into the mesh data, and the
.blend is never saved.
"""
import bpy, sys, os, json, time, struct, hashlib, argparse
import numpy as np
from mathutils import Matrix

T0 = time.time()


def log(*a):
    print("[sw %6.1fs]" % (time.time() - T0), *a, flush=True)


def fail(msg):
    raise RuntimeError(msg)


ENGINE_COLL = "CAD_engine"
# Only the big casting is ever decimated.  The other six bodies -- PP12-EM-JD18,
# EM-SP x4 and the 360-triangle COMPOUND -- stay coordinate-exact, exactly as in
# astra_engine_export.py rev 4, so the mounting interfaces remain trustworthy.
DECIMATE_NAMES = {"COMPOUND.001"}
FACET_BUDGET_DEFAULT = 450000          # SolidWorks BREP cliff is 500,000
GRAPHICS_WARN = 5000000                # SolidWorks warns above this


# --------------------------------------------------------------- scene access
def engine_mesh_objects():
    coll = bpy.data.collections.get(ENGINE_COLL)
    if coll is None:
        fail("collection %r not found" % ENGINE_COLL)
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


def mm_scale_factor():
    """Metres -> millimetres, honouring the scene's unit scale."""
    return bpy.context.scene.unit_settings.scale_length * 1000.0


def make_mm_copy(obj, mm):
    """Independent copy: unparented, world matrix and mm scale baked into the
    mesh, object matrix identity.  Source is never touched."""
    world = obj.matrix_world.copy()
    c = obj.copy()
    c.data = obj.data.copy()
    c.parent = None
    c.matrix_parent_inverse = Matrix.Identity(4)
    c.matrix_world = Matrix.Identity(4)
    c.data.transform(Matrix.Scale(mm, 4) @ world)
    bpy.context.scene.collection.objects.link(c)
    c.name = obj.name + "__mm"
    c.hide_viewport = False
    c.hide_render = False
    try:
        c.hide_set(False)
    except Exception:
        pass
    return c


def count_tris(o):
    me = o.data
    me.calc_loop_triangles()
    return len(me.loop_triangles)


def tri_coords(o):
    """N x 3 x 3 float64 world triangle coordinates (mm, matrix already baked)."""
    me = o.data
    me.calc_loop_triangles()
    n = len(me.loop_triangles)
    if n == 0:
        return np.zeros((0, 3, 3))
    lti = np.empty(n * 3, dtype=np.int32)
    me.loop_triangles.foreach_get("vertices", lti)
    co = np.empty(len(me.vertices) * 3, dtype=np.float64)
    me.vertices.foreach_get("co", co)
    tris = co.reshape(-1, 3)[lti.reshape(n, 3)]
    m = np.array(o.matrix_world)
    if not np.allclose(m, np.eye(4)):
        tris = tris @ m[:3, :3].T + m[:3, 3]
    return tris


def decimate_body(o, target):
    cur = count_tris(o)
    if target is None or cur <= target or cur == 0:
        return 1.0
    mod = o.modifiers.new("Decimate", "DECIMATE")
    mod.ratio = target / cur
    mod.use_collapse_triangulate = True
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.modifier_apply(modifier=mod.name)
    return mod.ratio


# ---------------------------------------------------------------- axis option
def to_up_axis(tris, up):
    """Z-up (assembly frame) -> Y-up (SolidWorks' view convention).

    -90 deg about X: (x, y, z) -> (x, z, -y).  Applied to STL coordinates only;
    the OBJ exporter does its own conversion via forward_axis/up_axis.
    """
    if up == "Z" or not len(tris):
        return tris
    out = np.empty_like(tris)
    out[..., 0] = tris[..., 0]
    out[..., 1] = tris[..., 2]
    out[..., 2] = -tris[..., 1]
    return out


# ------------------------------------------------------------------ STL write
def export_binary_stl(tris, path, label):
    n = len(tris)
    with open(path, "wb") as f:
        f.write(label.encode("ascii", "replace")[:80].ljust(80, b" "))
        f.write(struct.pack("<I", n))
        if n:
            v0, v1, v2 = tris[:, 0], tris[:, 1], tris[:, 2]
            nrm = np.cross(v1 - v0, v2 - v0)
            ln = np.linalg.norm(nrm, axis=1, keepdims=True)
            ln[ln == 0] = 1.0
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
    ok = (n == exp_n) and (size == 84 + 50 * n) and n > 0
    return {"facets": n, "bytes": size, "mb": round(size / 1e6, 2),
            "count_matches": n == exp_n, "size_consistent": size == 84 + 50 * n,
            "ok": bool(ok)}


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


# ------------------------------------------------------------------ OBJ write
def export_obj(copies, path, up):
    """Coloured OBJ + MTL.  SolidWorks imports per-facet colour ONLY when the
    mesh is brought in as a Graphics Body (see docs/solidworks-import.md)."""
    bpy.ops.object.select_all(action="DESELECT")
    for c in copies:
        c.select_set(True)
    bpy.context.view_layer.objects.active = copies[0]
    # forward/up 'Y'/'Z' is the identity transform: coordinates are written
    # exactly as they sit in the (mm-baked) mesh.  'NEGATIVE_Z'/'Y' is the
    # ordinary OBJ Y-up convention.
    fa, ua = ("Y", "Z") if up == "Z" else ("NEGATIVE_Z", "Y")
    bpy.ops.wm.obj_export(
        filepath=path,
        export_selected_objects=True,
        export_materials=True,
        export_triangulated_mesh=True,
        export_normals=True,
        export_uv=False,
        export_colors=True,
        apply_modifiers=True,
        global_scale=1.0,
        forward_axis=fa,
        up_axis=ua,
        path_mode="AUTO",
    )
    mtl = os.path.splitext(path)[0] + ".mtl"
    return {"obj_bytes": os.path.getsize(path) if os.path.exists(path) else 0,
            "mtl_present": os.path.exists(mtl),
            "mtl_bytes": os.path.getsize(mtl) if os.path.exists(mtl) else 0,
            "forward_axis": fa, "up_axis": ua}


# ---------------------------------------------------------------------- README
README = """# Engine for SolidWorks -- rev 5

Source scene: `{src}`
Generated {when} by `tools/astra_engine_solidworks.py`. Units: **millimetres**.
Up axis as written: **{up}**.

## Which file to open

| file | import as | you get |
|---|---|---|
| `engine-colour-mm.obj` | **Graphics Body** | colour, matching the Blender render. **Start here.** |
| `engine-graphics-mm.stl` | Graphics Body, or Solid Body **with "Mesh body" ticked** | grey, faceted, one body |
| `bodies/*.stl` | Graphics Body | grey, but **{nbody} separately selectable bodies** |

**File > Open** (not File > Import). File type **Mesh Files (\\*.stl; \\*.obj; ...)**.
Click **Options...**, set **Unit: Millimeters**, choose the import type from the
table, then Open. Apply no extra scaling -- these files are already millimetres.
Keep `engine-colour-mm.mtl` beside the `.obj`; SolidWorks reads colour from it.

**Do not** import as Solid/Surface Body with "Mesh body" unticked. That path
builds one BREP face per facet and is what makes the engine unusable.

## Honest limits

- These are **mesh references, not analytic solids, and not watertight.** The
  source vendor mesh has open bores and ports by design; nothing here heals them.
  No watertight, solid or engineering-tolerance claim is made.
- The large casting is decimated ({dec}); the other bodies are coordinate-exact.
- If you need to measure, mate or design against the engine, import the original
  STEP (`3336180ci510.stp`) instead -- it is the only CAD-grade route.
- No SolidWorks round-trip has been run by us; these instructions come from
  SolidWorks' documentation. Please report what actually happens.

See `docs/solidworks-import.md` in the CAD-pipeline repo for the full reasoning.
"""


# ------------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default="out/engine-solidworks-rev5")
    ap.add_argument("--out-json", default="reports/astra-engine-solidworks.json")
    ap.add_argument("--facet-budget", type=int, default=FACET_BUDGET_DEFAULT)
    ap.add_argument("--no-decimate", action="store_true",
                    help="keep full resolution; removes faceting, rules out the BREP path")
    ap.add_argument("--up", choices=("Z", "Y"), default="Z",
                    help="Z keeps the assembly frame (default); Y matches SolidWorks' views")
    ap.add_argument("--no-obj", action="store_true")
    ap.add_argument("--no-per-body", action="store_true")
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    args = ap.parse_args(argv)

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    absify = lambda p: p if os.path.isabs(p) else os.path.join(root, p)
    out, out_json = absify(args.out_dir), absify(args.out_json)
    os.makedirs(out, exist_ok=True)
    os.makedirs(os.path.join(out, "bodies"), exist_ok=True)
    os.makedirs(os.path.dirname(out_json), exist_ok=True)

    mm = mm_scale_factor()
    rep = {"script": "astra_engine_solidworks.py", "script_rev": 1,
           "source_blend": bpy.data.filepath, "blender": bpy.app.version_string,
           "mm_scale_factor": mm, "up_axis": args.up,
           "facet_budget": args.facet_budget, "no_decimate": bool(args.no_decimate),
           "solidworks_brep_facet_limit": 500000,
           "solidworks_graphics_warn_facets": GRAPHICS_WARN,
           "started": time.strftime("%Y-%m-%dT%H:%M:%S"), "bodies": []}
    if abs(mm - 1000.0) > 1e-6:
        rep["unit_warning"] = ("scene unit scale is not 1.0; mm factor is %r" % mm)

    src = engine_mesh_objects()
    src_names = sorted(o.name for o in src)
    rep["source_bodies"] = src_names
    log("engine bodies: %d -- %s" % (len(src), ", ".join(src_names)))

    copies = [make_mm_copy(o, mm) for o in src]
    bpy.context.view_layer.update()

    # --- decimate only the big casting, proportional to the facet budget ------
    raw = {c.name: count_tris(c) for c in copies}
    total_raw = sum(raw.values())
    protected = sum(v for k, v in raw.items()
                    if k.replace("__mm", "") not in DECIMATE_NAMES)
    rep["triangles_source_total"] = total_raw
    rep["triangles_protected"] = protected

    if args.no_decimate:
        rep["decimation"] = "none (--no-decimate)"
    else:
        room = max(args.facet_budget - protected, 1000)
        for c in copies:
            base = c.name.replace("__mm", "")
            if base in DECIMATE_NAMES:
                r = decimate_body(c, room)
                log("decimated %s: %d -> %d (ratio %.4f)"
                    % (base, raw[c.name], count_tris(c), r))
        rep["decimation"] = ("only %s, to fit budget %d with %d protected"
                             % (sorted(DECIMATE_NAMES), args.facet_budget, protected))

    # --- per-body triangle arrays --------------------------------------------
    tri_by_body = {}
    for c in copies:
        base = c.name.replace("__mm", "")
        t = to_up_axis(tri_coords(c), args.up)
        tri_by_body[base] = t
        rep["bodies"].append({
            "name": base, "triangles_source": raw[c.name], "triangles_out": int(len(t)),
            "decimated": base in DECIMATE_NAMES and not args.no_decimate,
            "bbox_min_mm": [round(float(v), 3) for v in t.reshape(-1, 3).min(axis=0)] if len(t) else None,
            "bbox_max_mm": [round(float(v), 3) for v in t.reshape(-1, 3).max(axis=0)] if len(t) else None,
        })

    allt = np.concatenate([t for t in tri_by_body.values() if len(t)]) \
        if any(len(t) for t in tri_by_body.values()) else np.zeros((0, 3, 3))
    if not len(allt):
        fail("no triangles to export")
    if not np.isfinite(allt).all():
        fail("non-finite coordinates in the export")
    rep["triangles_exported_total"] = int(len(allt))
    rep["bbox_mm"] = {"min": [round(float(v), 3) for v in allt.reshape(-1, 3).min(axis=0)],
                      "max": [round(float(v), 3) for v in allt.reshape(-1, 3).max(axis=0)]}
    if len(allt) > GRAPHICS_WARN:
        rep["facet_warning"] = ("%d facets exceeds SolidWorks' %d graphics-body warning"
                                % (len(allt), GRAPHICS_WARN))
    rep["fits_solidworks_brep_path"] = bool(len(allt) < 500000)

    # --- single STL -----------------------------------------------------------
    stl_path = os.path.join(out, "engine-graphics-mm.stl")
    n, size = export_binary_stl(allt, stl_path,
                                "engine mm %s-up graphics mesh (NOT watertight)" % args.up)
    rep["stl_single"] = validate_stl(stl_path, n)
    if not rep["stl_single"]["ok"]:
        fail("single STL failed validation: %s" % rep["stl_single"])
    log("engine-graphics-mm.stl: %d facets, %.1f MB" % (n, size / 1e6))

    # --- per-body STLs --------------------------------------------------------
    if not args.no_per_body:
        rep["stl_bodies"] = {}
        for base, t in sorted(tri_by_body.items()):
            if not len(t):
                continue
            safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in base)
            p = os.path.join(out, "bodies", "%s-mm.stl" % safe)
            bn, _ = export_binary_stl(t, p, "engine body %s mm (NOT watertight)" % safe)
            v = validate_stl(p, bn)
            rep["stl_bodies"][base] = v
            if not v["ok"]:
                fail("per-body STL failed validation: %s" % base)
        log("per-body STLs: %d files" % len(rep["stl_bodies"]))

    # --- coloured OBJ ---------------------------------------------------------
    if not args.no_obj:
        obj_path = os.path.join(out, "engine-colour-mm.obj")
        try:
            rep["obj"] = export_obj(copies, obj_path, args.up)
            if not rep["obj"]["mtl_present"]:
                rep["obj"]["warning"] = ("no .mtl written -- the engine bodies carry no "
                                         "materials in this scene, so SolidWorks will "
                                         "show the OBJ grey exactly like the STL")
            log("engine-colour-mm.obj: %.1f MB, mtl=%s"
                % (rep["obj"]["obj_bytes"] / 1e6, rep["obj"]["mtl_present"]))
        except Exception as e:                       # exporter absent or renamed
            rep["obj"] = {"error": "%s: %s" % (type(e).__name__, e)}
            log("OBJ export FAILED: %s" % e)

    # --- README + manifest ----------------------------------------------------
    with open(os.path.join(out, "README.md"), "w") as f:
        f.write(README.format(
            src=bpy.data.filepath, when=time.strftime("%Y-%m-%d %H:%M"),
            up=args.up, nbody=len(tri_by_body), dec=rep["decimation"]))

    lines = []
    for dirpath, _, names in os.walk(out):
        for nm in sorted(names):
            if nm == "MANIFEST.sha256":
                continue
            p = os.path.join(dirpath, nm)
            lines.append("%s  %s" % (sha256_file(p), os.path.relpath(p, out).replace("\\", "/")))
    with open(os.path.join(out, "MANIFEST.sha256"), "w") as f:
        f.write("\n".join(sorted(lines)) + "\n")
    rep["manifest_entries"] = len(lines)
    rep["out_dir"] = out
    rep["verdict"] = "PASS"

    with open(out_json, "w") as f:
        json.dump(rep, f, indent=1)
    log("report -> %s" % out_json)
    log("DONE: %d facets total, BREP path %s"
        % (len(allt), "available" if rep["fits_solidworks_brep_path"] else "NOT available"))


if __name__ == "__main__":
    main()
