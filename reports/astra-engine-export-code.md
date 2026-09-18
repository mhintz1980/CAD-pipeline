# tools/astra_engine_export.py — implementation report

Date: 2026-09-18 · Owner: Markimus (+ independent reviewer, DeepSeek seat) ·
Status: **READY (rev 4)**

**Rev 4 supersedes rev 3.** `python -m py_compile tools/astra_engine_export.py`
→ **COMPILE_OK**. No local Blender was launched. Script sha256:
`b47b2574b0a24535cd908e8d44b48e581dea7279de3e926545a830a430d9d7f3`.
Signal: `astra-engine-export-ready-rev4.md`.

## Rev 4 fixes (final quality pass)

1. **Selection preserved (blocker from the 14:12 run).** `DECIMATE_NAMES =
   {"COMPOUND.001"}` **only**. The tiny `COMPOUND` (360 tris) and the other bodies
   are now protected and coordinate-exact — 6 protected bodies:
   `report["protected_bodies"]` lists them; per-body
   `mount_preserved_exact=true`, `mount_dev_mm=0.0` (array_equal vs the immutable
   mm baseline). Decimating the tiny casting was a real defect in rev 3.
2. **Targets:** `--decimate-light` default **350000** (~17.5 MB); detailed stays
   **500000** (~25 MB). Extra ~3 KB of detail is negligible.
3. **Preview robustness / GPU proof.** `render_preview` sets
   `scene.render.use_sequencer = False` and `use_compositing = False` (a source
   sequencer/compositor can pull in another Scene with no camera and abort the
   render), asserts an evaluated `scene.camera` and calls `view_layer.update()`
   before rendering. `setup_gpu_cycles` records `render_gpu`
   (`backend`, `device_used`, `scene_cycles_device`, per-device `{name,type,use}`)
   and logs a `GPU PROOF select backend=… device=…` line with Cycles
   `log_level=1` — i.e. device-selection + Cycles device-init evidence, not a bare
   "GPU allocated" claim. Honest `CPU_FALLBACK` if no OPTIX/CUDA device exists.
   The preview reuses the already-staged isolated scene.
4. **README rewritten (dynamic).** Recommends the **25 MB detailed STL** for
   reference/measurement. The light STL is called a compact reference **only if**
   its measured sampled `light_max_dev_mm <= 3 mm`; otherwise it is labelled
   **VISUAL-ONLY** and the **actual** deviation is printed (the 14:12 run measured
   **33.886 mm** → visual-only; never called fit-ready). STL files are stated to
   be **mesh/graphics references, NOT analytic solids and NOT watertight**.
   SolidWorks guidance: **File > Open**, Options units **millimetres**, import as
   **Graphics Body** (or mesh/BREP if available), do **not** accept the default
   conventional facet-per-face Solid Body conversion; native SW import
   **not yet tested**.
5. **Honest mesh diagnostics.** New `report["mesh_quality"]` block
   (`watertight: false`, summed `detailed_boundary_edges`,
   `detailed_nonmanifold_edges`) plus rewritten `warnings`: the source is an OPEN
   vendor mesh, open boundaries and defects **REMAIN**, cleanup/decimation
   **introduce** non-manifold edges (source ~0 → ~4075 cleaned / ~4076 detailed),
   and this is **not a healed solid**. No claim that open edges are intentional or
   that new non-manifold edges are benign.
6. **Rev-4 marker**: `report["script_rev"] = 4`; README title "mesh reference, rev 4".

### Runtime result of the first real cloud run (L4) — export SUCCEEDED
App `ap-6ViotFIVYEcYiZVTRHDiDX`, run `run-20260918T140853`, 77.0 s:
* `scene_units` METRIC / `scale_length=1.0` / `mm_factor=1000` → bbox assert
  **passed** (`src_bbox_mm` = expected −835.717…837.721 mm). Units fix proven.
* 7 engine bodies; rev-3 decimated = `COMPOUND`,`COMPOUND.001` (rev 4 decimates
  only `COMPOUND.001`); protected mounts had `mount_preserved_exact=true`,
  `mount_dev_mm=0.0`.
* `engine-detailed.stl` 499,996 tris / 24,999,884 B (detailed sampled max
  1.548 mm, mean 0.0625 mm); `engine-light.stl` 199,998 tris / 9,999,984 B
  (sampled max **33.886 mm** → **NOT acceptable for fit/clearance**);
  `nonfinite_triangle_coords=0`; STL validation all true.
* Independent readback (my verifier) agrees — see `reports/astra-engine-review.md` §I.
* **Only failure: the preview** (`Error: Cannot render, no camera`) → fixed in rev 3
  (`scene.camera = cam`) and hardened in rev 4 (sequencer/compositing disabled,
  evaluated-camera assert, GPU proof, stage reuse). STL/blend/JSON/README were
  already written before the render, so nothing else was lost.

Writer/reader unit test (this seat, offline): the binary-STL writer emits a
284-byte watertight mm tetrahedron that my independent verifier
(`tools/astra_verify_engine_export.py`) reads back as 4 tris, bbox 1000 mm,
boundary=0, nonmanifold=0, euler=2, watertight=True.

## Rev 3 fixes (astra-engine-rev3-fix.md) — retained

1. **Units factor was a no-op (rev 2 blocker).** Rev 2 wrote
   `Matrix.Scale(mm / 1000.0, 4) @ world` with `mm = scale_length*1000`, i.e. it
   scaled by `scale_length` — for a metres scene that is `1.0`, so the geometry
   stayed in metres and the bbox assert would abort. **Rev 3 uses
   `copy.data.transform(Matrix.Scale(mm, 4) @ world)`** (line 105). This is
   convention-robust: metres scene (`scale_length=1`) → ×1000; mm scene
   (`scale_length=0.001`, coords already mm) → ×1. The hard bbox assert
   (`-835.717…837.721` mm, tol 10) proves it at runtime.
2. **Non-destructive ordering.** STL exports, `engine-cleaned.blend` string,
   JSON report and `README.md` are written **before** the (failure-prone) render,
   and destructive isolation/save happen **last**: order is
   detailed STL → light STL → guards/metrics/mount-proof →
   `write_outputs()` → isolate + save blend → preview → `write_outputs()` again.
   Source/protected identities are **frozen as strings** (`src_names`,
   `protected_names`) so nothing touches a freed Blender ID. Generated light
   copies are dropped at isolation (only detailed bodies persist in the blend).
3. **Stage/unhide before render.** `stage_scene` now force-shows the view layer,
   all layer collections and every working object/collection
   (`exclude=False`, `hide_viewport=False`, `hide_render=False`, `hide_set(False)`)
   before linking into `ENGINE_EXPORT`, so inherited layer visibility cannot hide
   the clones. The preview is asserted to exist and exceed 1 KB (`written` flag);
   a render failure is recorded, not fatal (artifacts already on disk).
4. **mm-accurate blend.** Before saving, `unit_settings.scale_length = 0.001`
   (+ `length_unit = 'MILLIMETERS'`) so the mm-baked world coords are represented
   correctly; the STL is valid mm with the 1e3 scaling already applied.
5. **Mount proof by geometry, not counts.** For every protected body,
   `mount_preserved_exact` = `np.array_equal(base_tris[n], tri_coords(working[n]))`
   (shape + finite + exact), with `mount_dev_mm = 0.0`. Post-decimation topology
   (`detailed_stats`, `light_stats`) and per-variant deviations (`deviation_detailed`
   in mm via `find_nearest(...)[3]`, `deviation_light`) are recorded for BOTH
   variants.
6. **Rev marker** (rev 3 set `report["script_rev"] = 3`; **rev 4 sets `= 4`**); READY
   only after inspection.

## Rev 2 fixes retained (from astra-engine-export-fix.md)

- `DECIMATE_NAMES` (rev 2 = `{"COMPOUND","COMPOUND.001"}`; **rev 4 = `{"COMPOUND.001"}`**);
  all other bodies protected full-res; recorded in `protected_bodies`/`decimated_bodies`.
- `find_nearest(...)[3]` distance (never `[2]` index); misses = NaN + counted.
- Immutable mm baseline triangle arrays used for every deviation; BVH built in
  mm world space (`bm.transform(matrix_world)`).
- Copies unparented (`parent=None`, `matrix_parent_inverse=Identity`) before baking.
- Cycles preview: OPTIX→CUDA→CPU fallback with honest evidence.
- Guard asserts: STL size/count/nonempty, non-finite coords, bbox.
- Conservative cleanup only (duplicates/degenerate ≤0.001 mm, normal recalc); no
  hole filling of bores/ports, no clearance voxel fill.

## Interface (rev 4)

```
blender -b /input/engine-and-pump-v10.blend --python /scripts/astra_engine_export.py -- \
    --output-dir /output [--decimate-detailed 500000] [--decimate-light 350000] [--save-source-blend]
```

## Dependencies

Blender 5.x/4.x (bpy, bmesh, mathutils) + bundled numpy. CPU except the Cycles
preview (GPU OPTIX/CUDA preferred, honest CPU fallback). No pip, no internet.

## Pipeline order (rev 4)

1. Collect `CAD_engine` meshes recursively (7 bodies, ~2.277M tris). No pump/skid/bale.
2. mm-baseline copies (immutable) → **hard bbox assert** vs expected mm bounds.
3. Working copies; `COMPOUND.001` cleaned conservatively; the other 6 bodies bypass cleanup.
4. Detailed proportional decimation of `COMPOUND.001` only → ~500k incl. full-res
   protected bodies; per-body bidirectional BVH deviation (seed 42) vs mm baseline.
5. JD-green materials on castings (only if unmaterialled).
6. **`engine-detailed.stl`** and **`engine-light.stl`** exported and guarded.
7. Metrics: cleaned bbox, mount array-equality proof, per-variant topology/deviations,
   `mesh_quality` (boundary/non-manifold counts, `watertight=false`).
8. `astra-engine-export.json` + `README.md` written (recoverable before render).
9. **Isolation last** (pointer set), `scale_length=0.001`, save `engine-cleaned.blend`.
10. **Preview last** (best effort): `engine-preview.png` 1000×800/32spp, sequencer/
    compositing disabled, evaluated camera, GPU device proof; report/README rewritten
    with the preview outcome.

## Outputs (in `--output-dir`)

| File | Required | Notes |
|---|---|---|
| `engine-cleaned.blend` | yes | engine-only, mm coords, unit scale 0.001, individual bodies |
| `engine-detailed.stl` | yes | binary, ~500k tris (~25 MB), validated; recommended for reference |
| `engine-light.stl` | yes | binary, ~350k tris (~17.5 MB), validated; visual-only unless sampled max dev ≤3 mm |
| `engine-preview.png` | yes | 1000×800 Cycles 32spp, JD green castings, GPU evidence in JSON |
| `astra-engine-export.json` | yes | measured stats, assertions, deviations, GPU backend |
| `README.md` | yes | import instructions & limitations |
| `engine-source-extracted.blend` | optional | `--save-source-blend` |

## Notes for worker

- Upstream original files are never modified (copies only; `save_as_mainfile(copy=True)`).
- If castings already carry materials, JD green is not forced over them.
- Detailed/light counts are actual measured values, compensated for full-res mounts.
- If the bbox assert fires, units/world transforms are wrong — do **not** ship;
  capture the JSON `src_bbox_mm` and `scene_units` for diagnosis.
