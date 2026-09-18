# Handoff to Astra — engine and pump skid, CAD → Blender

**Written 2026-09-17 by Claude (Opus 5), advance engineering pass.**
Target: customer-ready renders of the industrial pump skid, tomorrow.
You own final execution. Nothing here locks you in — every finding is
labelled, and the tooling is small enough to throw away if you disagree.

Work area: `C:\Projects\CAD\astra-engine-pump\`
Source CAD was copied, never modified. Original stays on Drive.

---

## 0. The two things that will bite you

1. **The engine in this assembly is a reduced stand-in, not the real model.**
   The product is literally named `3336180ci510-interfaces-v5-64MB` — it is
   the *interfaces-only* output of the earlier `step-reduction` run. It still
   renders as a recognisable engine + radiator, but every non-planar,
   non-cylindrical face is gone. Detail below (§2).
2. **With default flags the model arrives in Blender lying on its side, with
   a duplicate engine 121 m away.** Both are already handled in the shipped
   assets (`--in-axis Y`, `--drop-outliers`) — but if you re-convert from
   scratch and forget them, you get a tipped machine framed against a 121 m
   empty scene.

**Already done and verified, so you do not have to redo it:** the STEP is
converted, upright, complete and named (`out/engine-and-pump-v3.glb`); the
render-ready scene is built (`out/engine-and-pump.blend`); a job manifest
points at it (`jobs/engpump_01_no-background.json`); and test renders are in
`reports/validate-final/`. Start at §9.

---

## 1. What I found

### The source file — PROVEN

`engine and pump.STEP`, Google Drive root → copied to
`source/engine-and-pump.STEP`

| Fact | Value |
|---|---|
| bytes | 194,506,148 |
| sha256 | `72c89067c059ba37a4d9d209acbbbb8abc1d948add6615500d69a631135f3d56` |
| schema | AP203 `CONFIG_CONTROL_DESIGN` |
| exporter | `SwSTEP 2.0` / **SolidWorks 2026**, stamped 2026-09-17T21:23:27 |
| **units** | **INCH** (31 `CONVERSION_BASED_UNIT`, factor 0.0254 to metre) |
| products | 31 — of which **25 carry geometry**, 6 are pure assembly nodes |
| occurrences | 58 `NEXT_ASSEMBLY_USAGE_OCCURRENCE`, **56 non-identity transforms** |
| **colour / style** | **NONE.** `style: {}` — zero styled items, zero `COLOUR_RGB` |

**AP203 carries no colour.** Your materials must come from names/roles, not
from the file. The role classifier in `tools/blender_validate.py` does this
and got 100% coverage on this assembly (§6).

Geometry reps: 23 `ADVANCED_BREP_SHAPE_REPRESENTATION` (solids) +
2 `MANIFOLD_SURFACE_SHAPE_REPRESENTATION` (surface-only) = 25.

### The open shells are real — PROVEN

4,021 `OPEN_SHELL` in the file. They are **not junk**, and they are not
spread across the assembly: **4,012 of them belong to one product**, the
engine. OCCT reads all of them (8,033 counting both instances) and
tessellates them normally. No sewing, healing or validity filtering was
needed or used.

### Component map — PROVEN

| Role | Products |
|---|---|
| engine | `3336180ci510-interfaces-v5-64MB`, `JD18-EMA`, `PP12-EM-JD18`, `EM-SP`×4 |
| pump | `PP128-FTA`, `PP-FTT`×2, `PP-FTS-1005`×2, `PP-FTS-1008`×6, `PP-FBS`, `PP128S22-MFB`, `Copy of Copy of Part11^PP128-FTA`×2 |
| controller | `MSP-CP-CP750E`, `CPM-PP-JD18`, `PP-CPM-1001`, `PP-CPM-1005` |
| lifting bale | `LBA-CB`, `LBS-LG`×2, `LBS-SH`×2, `LBU-PP`×2, `PP-LBB`×2 |
| skid | `PP128-PP108-SKID`, `Part1^…SKID`×2, `MC6X18-SKE*`, `mc channel`, `tube rectangular`, `PLT-MNT-*`, `MNT-PE*`, `DOUBLER`×2 |

All five expected components are present. `roles_missing: none`.

Machine size, measured after conversion: **4.74 × 2.07 × 2.93 m** —
correct for a pump skid, so the unit chain is sound end to end.

---

## 2. The engine — TESTED, and I was wrong once

**My first call was too strong and I am correcting it.** I claimed the engine
was "loose faces, not visually complete". The render disproved that.

What is **PROVEN**:

* The engine product is the interfaces reduction, by name and by signature.
* Its 4,023 faces are **2,700 `CYLINDRICAL_SURFACE` + 1,323 `PLANE` = 4,023
  exactly**. Zero B-spline, zero toroidal, zero conical, zero spherical.
  A real casting cannot have that distribution — for contrast the
  controller `MSP-CP-CP750E` has 651 B-spline, 368 conical, 180 toroidal,
  34 spherical faces.
* The real engine model exists and is **20× richer**:
  `C:\Projects\Misc\3336180ci510.stp`, 451.8 MB, AP214, **82,139 faces**,
  3,363 B-spline + 6,775 toroidal + 6,197 conical surfaces, and — unlike the
  assembly — **507 `COLOUR_RGB` with 74,092 styled items**, i.e. it ships
  with per-face colour that OCCT will import as glTF materials.

What is **TESTED** (see `reports/validate-v2/isolate_engine.png`):

* The husk **does** render as a coherent engine + radiator package: radiator
  core with grille, frame, block, exhaust elbows, filters, housings. At
  mid-distance it reads as an engine.
* What is missing is every filleted, blended and organic surface. Expect
  holes and hard unfinished edges in close-ups, and a visibly "faceted"
  look where castings should be rounded.

**Judgement, not proof:** for a wide three-quarter hero shot the husk is
probably acceptable. For any close-up of the engine it is not.

### The swap is cheap — CONFIRMED

I converted the real engine and compared frames. **The husk sits in the same
coordinate system as the original**, so substituting it is a transform copy,
not a re-fit:

| local bbox (mm) | min | max |
|---|---|---|
| original `3336180ci510.stp` | [−837.6, −479.1, −365.0] | [841.4, 1595.1, 1910.8] |
| husk (in this assembly) | [−819.8, −473.7, −349.8] | [821.8, 1587.8, 1893.2] |

Every delta is **5–20 mm** — precisely the curved outer faces the reduction
dropped. Insert `out/engine-original.glb` at the husk's occurrence transform
and it lands within 2 cm.

Cost of the swap, measured:

| | husk (in assembly) | real engine |
|---|---|---|
| faces | 4,023 | **82,272** |
| triangles @ 0.5 mm | 386,072 | **4,537,176** |
| GLB | (part of 23.5 MB) | **144.1 MB** |
| colour | none | **507 RGB, 74,092 styled items** |

So the full-fidelity engine is **11.8× the triangles** and brings its own
materials. A whole-scene budget with the real engine is ~4.8 M triangles —
fine for Cycles, and `blender_prepare_assembly.py --tri-budget` will hold a
ceiling if you want one.

---

## 3. What I tested

### PROVEN — the conversion path that works

```
STEP → OCCT 8.0 STEPCAFControl_Reader (XCAF)
     → BRepMesh_IncrementalMesh
     → RWGltf_CafWriter → GLB
     → bpy.ops.import_scene.gltf
```

XCAF is the point: names, per-occurrence transforms and the assembly tree
survive into the glTF node graph. No STL, no flattening, no rebuilding
hierarchy by hand.

Kernel: `cadquery-ocp==8.0.1.0.0` in an **isolated uv venv**
(`.venv`, CPython 3.12.12) inside the work dir. Nothing installed
system-wide, nothing touched in the user's global Python.

### Measured — full assembly, this machine (Windows 11, local)

| Phase | Wall time | Peak RSS |
|---|---|---|
| import OCP | 0.7–1.6 s | 214 MB |
| **STEP → XCAF read + transfer** | **113 s** (168 s when contended) | **1,075 MB** |
| walk XCAF tree | 0.9 s | — |
| tessellate (lin 0.5 mm, ang 20°) | **5.4 s** | 1,667 MB |
| count triangles | 0.1 s | — |
| write GLB | 0.9 s | — |
| **total** | **≈ 2–3 min** | **1,667 MB** |

Output: **23.5 MB GLB, 1,077,512 triangles, 53 objects.**
Triangle count is preserved exactly through Blender import — OCCT and
Blender agree to the triangle.

**The read dominates completely.** Tessellation of this assembly is 5 s.
Any optimisation effort belongs on the parse, not the mesher.

### PROVEN — Blender side

* `blender --background` + **Cycles CPU** renders reliably headless.
* **Workbench and EEVEE silently write nothing** in headless Windows —
  no error, exit code 0, no file. I hit this and added a hard check for it
  in the validator. Do not trust a zero exit code from a Blender render.
* The existing `msp-render-pipeline` `render_worker.import_cad_model()`
  **already accepts `format: "glb"`** (`bpy.ops.import_scene.gltf`). The
  converted asset drops into the existing job-manifest pipeline with no new
  render infrastructure.

### Scene prep, run end to end

`tools/blender_prepare_assembly.py` on the converted GLB:

```
[import]                 objects=53  triangles=1,077,512
[collections]            bale=9 controller=3 engine=7 pump=20 skid=14
[quarantine_outliers]    count=1  hidden=True  worst_m=121.4
[normals_weld_cleanup]   verts_welded=136,324  faces_removed=1,063
                         sharp_edges=483,344  smooth_polys=690,377
[after_cleanup]          triangles=690,377
[decimate]               skipped (under 4M budget)
[materials]              assigned=52  palette=6
[saved]                  out/engine-and-pump.blend  29.5 MB
```

Dropping the duplicate engine occurrence alone removes **36%** of the
scene's triangles.

---

## 4. Known failure modes — each one cost me time, each one is now caught

| # | Failure | Symptom | Fix |
|---|---|---|---|
| 1 | **Duplicate engine occurrence at −121.4 m** | Camera frames a 125 m scene; product is a speck. Real defect in the source assembly, confirmed independently by a text parse *and* by OCCT. | `--drop-outliers` quarantines it (does not delete). |
| 2 | **Model arrives Y-up in Blender** | Machine lies on its side. Source is Z-up but the top-level occurrence rotates the whole assembly; OCCT's Z→Y conversion then Blender's Y→Z leaves net +Y up. | `--in-axis Y` on `step_to_glb.py`. Verify: bale crossbar at max Z, base rails at min Z. |
| 3 | **Workbench/EEVEE render nothing headless** | Exit 0, no PNG, no error. | Use `--engine CYCLES`. Validator now raises instead of passing silently. |
| 4 | **glTF nodes named `NAUO18`** | Role classification finds nothing; every object "unclassified". XCAF occurrence labels are NAUO ids; the product name is on the *referred* shape. | `SetNodeNameFormat(RWMesh_NameFormat_ProductOrInstance)` — already set in the tool. |
| 5 | **Blender relative render paths** | Silent no-write. | Validator forces absolute paths. |
| 6 | **Text-level bboxes poisoned by stray points** | `MSP-CP-CP750E` reads 57,504 in (1.46 km) from raw min/max. | `step_assembly_map.py` reports a p1–p99 `robust_diag` next to the raw one. Robust value: 16.3 in. Correct. |
| 7 | **Losing visible geometry to validity filtering** | Not hit, and deliberately so — nothing in this path drops geometry for failing a solid test. Open shells tessellate like anything else. | Keep it that way. |
| 8 | **Importing the 144 MB / 4.5 M-tri engine GLB takes ~15 minutes** | Blender logs two `create Mesh node COMPOUND` lines and then appears hung for a quarter of an hour. It is not hung. **Measured: `IMPORT OK objects=3 tris=4,537,188 in 892.7s`.** The engine is one merged product, so it arrives as 2 huge glTF meshes and the importer's per-mesh cost is superlinear (~O(n^1.3)). See §11. | Use the coarse build — **358.8 s for 2.28 M tris**, 60% faster. Either way, budget the time and do not kill the job at 10 minutes, as I wrongly did twice. |
| 9 | **Silently-swallowed `bpy.ops` failures** | `bpy.ops.object.shade_auto_smooth()` inside a bare `except` failed with no message, leaving **every** polygon smooth-shaded and putting visible facet banding across flat plates. I shipped this, saw it in a render, and fixed it. | `blender_prepare_assembly.py` now marks sharp edges directly in bmesh (no operator) and **raises** if zero sharp edges result. Same lesson as the `mask.png` bug in your last handoff: a step with no gate is a step that will fail quietly. |

---

## 5. Modal recommendation — evidence, not the prior estimate

**The standing suggestion of 8 CPU / 64 GB is roughly 40× over-provisioned
for this file.** Measured peak for the whole 194 MB conversion was
**1.67 GB**.

| Job | Recommend | Why |
|---|---|---|
| Convert `engine and pump.STEP` | **2 CPU, 4 GB, 900 s, no GPU** | Measured 1.67 GB peak / ~3 min. 4 GB is already 2.4× headroom. |
| Convert the 451 MB vendor engine | **4 CPU, 16 GB, 1800 s, no GPU** | **Measured:** read 338.7 s / 3,092 MB, tessellate 29.8 s / **5,269 MB peak**, GLB write 18.9 s. ~6.5 min total. 16 GB gives 3× headroom. |
| Render | **reuse the existing `gpu="L4", cpu=4, memory=16384`** | Already proven in `msp-rp-t04/scripts/cloud_parity.py`. Don't re-derive it. |

**No GPU for the CAD conversion.** OCCT's reader and mesher are CPU-only;
a GPU is pure cost there.

Honestly: **this conversion does not need Modal at all.** It ran locally in
under three minutes inside 1.7 GB. Modal earns its place for *rendering*
(the L4 path that already exists), not for this parse. Use the cloud if you
want reproducibility or parallel variants — not because the file is too big.

`--freecad conda` / FreeCAD 1.0 remains the fallback if OCCT ever chokes,
but it was not needed: this is a SolidWorks AP203 export, not the Creo
export that segfaulted FreeCAD 0.20.2 in the earlier pipeline. **No FreeCAD
is installed locally** — that path is Modal-only.

---

## 6. Visual validation — cheap, and it already caught things

`tools/blender_validate.py` runs in ~1–2 min on CPU Cycles and answers the
acceptance questions directly:

On the shipped `out/engine-and-pump-v3.glb`:

```
objects=53 triangles=1,077,512
core size (m) = [2.065, 4.744, 2.928]       <- height in Z. correct.
all  size (m) = [2.065, 124.932, 2.928]     <- the 121 m outlier, visible
missing roles: none
  bale        objects= 9  tris=11,152
  controller  objects= 3  tris=259,148
  engine      objects= 7  tris=773,972
  pump        objects=20  tris=29,200
  skid        objects=14  tris=4,040
OUTLIERS (1):
  121.4 m  engine  3336180ci510-interfaces-v5-64MB
```

It writes `report.json` plus turntable views, a framing shot that *includes*
outliers, and `--isolate` renders one view per role — which is how you see
at a glance that a component arrived as loose faces rather than a solid.

Note the engine husk is **72% of the scene's triangles** while contributing
the least finished surface. If you swap in the real engine, budget for that.

**One caveat on running the validator against a `.blend` rather than a
GLB.** Quarantined outliers live in a collection excluded from the view
layer, and Blender stops evaluating excluded objects — so their
`matrix_world` reads as identity and the validator reports them at the
origin with no outlier flagged. The *outcome* is right (they are excluded
and `hide_render`, so they do not render), but do not read
"`all size` == `core size`" on a prepped `.blend` as proof the outlier was
handled. Check the GLB, or check `CAD_QUARANTINE_outliers` directly.

---

## 7. Existing assets to reuse — exact paths

| Path | What |
|---|---|
| `C:\Users\Markimus\.agents\skills\step-reduction\SKILL.md` | The reduction playbook. Its hard-won rules (Python version matching, UTF-8 stdout, image layer order, env-vars-not-argv) still apply to any Modal work. |
| `…\step-reduction\scripts\step_text_scan.py` | Stdlib streaming STEP scanner. Run it first on any new file — settles assembly-vs-single-product in seconds. I used it and it was right. |
| `…\step-reduction\scripts\modal_step_reduce.py` | Modal driver, FreeCAD apt/conda. Untouched. |
| `…\step-reduction\references\plan-3336180ci510.md`, `troubleshooting.md` | Prior engine-specific plan + import playbook. |
| `C:\Projects\msp-render-pipeline\` | The render pipeline. `render_worker.import_cad_model()` accepts `glb`. |
| `C:\Projects\msp-render-pipeline\jobs\rl300_02_studio-dark.json` | Job manifest template — copy it, set `cad_source.format: "glb"`. |
| `C:\Projects\msp-rp-t04\scripts\cloud_parity.py` | Proven Modal render resources (`gpu="L4", cpu=4, memory=16384`). |
| `C:\Projects\msp-render-pipeline\ASTRA-HANDOFF.md` | Your prior handoff. The shadow-catcher bounce-muting finding still matters for any render you ship. |
| `C:\Projects\Misc\3336180ci510.stp` | **The real engine, 451.8 MB, with colour.** |
| Drive `3336180ci510-reduced/3336180ci510-reduced-brep-347MB.stp` | Shell-dropped engine that keeps real surfaces — middle option between husk and full. |

**Capabilities checked:** official Modal skill present
(`~/.agents/skills/modal`, v1.5.5). Blender MCP present but needs a live GUI
session — headless `blender --background` is the reliable automation surface
and is what the tools here use. **No FreeCAD installed locally.** No
CadQuery/OCP/build123d was present before this session; I added OCP only
inside the project venv.

---

## 8. Open questions — yours, not mine

1. **Does the engine need to be the real model?** Depends on the shot. Wide
   three-quarter: husk is probably fine. Engine close-up: it is not. The
   swap is confirmed cheap (§2), so this is a taste call, not a cost call.
2. **Is the 121 m duplicate engine meant to be there?** It is quarantined,
   not deleted, so this is reversible either way. My read: it is a
   duplicate-instance defect in the SolidWorks assembly, worth telling Mark
   about regardless of the render.
3. **Does Mark want the engine's own colours?** The real engine carries 507
   RGB colours; the assembly carries none. Mixing them gives a coloured
   engine on a grey skid. Either extend the role palette to match, or
   suppress the engine's colours with `SetColorMode(False)`.

---

## 9. Astra first command

**The conversion is already done and verified — `out/engine-and-pump-v3.glb`
is correct, upright, complete, and named.** Verified output:

```
objects=53 triangles=1,077,512
core size (m) = [2.065, 4.744, 2.928]     <- height in Z. correct.
missing roles: none
OUTLIERS (1):  121.4 m  engine  3336180ci510-interfaces-v5-64MB
```

**The render-ready `.blend` is also already built** —
`out/engine-and-pump.blend`, 29.3 MB, 690,377 triangles, sorted into
`CAD_engine` / `CAD_pump` / `CAD_skid` / `CAD_bale` / `CAD_controller`
collections, outlier quarantined, role materials assigned.

**And a job manifest is written and pointed at it:**
`jobs/engpump_01_no-background.json` (cloned from
`rl300_01_no-background.json`, camera retargeted for a 4.74 m body,
`hide_misplaced_isolators` turned **off** because that hack is RL300-specific).
It **validates clean against `msp-render-pipeline/docs/job_manifest.schema.json`**.

So your actual first command is the render itself:

```bash
cd C:/Projects/msp-render-pipeline && python -m msp_render_cli run C:/Projects/CAD/astra-engine-pump/jobs/engpump_01_no-background.json
```

I have **not** run this — it is a billable/production path and the camera
numbers are my estimate, not a tuned framing. Expect to adjust
`distance_multiplier` (5.2) and `target_offset` (z 1.40) on the first look.

Regenerate the prep with different choices any time:

```bash
cd C:/Projects/CAD/astra-engine-pump && "C:/Program Files/Blender Foundation/Blender 5.1/blender.exe" --background --python tools/blender_prepare_assembly.py -- --input out/engine-and-pump-v3.glb --output out/engine-and-pump.blend --drop-outliers --materials --json reports/prep.json
```

If you want to reproduce the conversion from scratch:

```bash
cd C:/Projects/CAD/astra-engine-pump && .venv/Scripts/python.exe tools/step_to_glb.py source/engine-and-pump.STEP out/engine-and-pump-v3.glb --lin 0.5 --ang 20 --in-axis Y --json reports/convert-glb-v3.json
```

Accept when `core size (m)` reads roughly `[2.07, 4.74, 2.93]` — height in
**Z** — and `missing roles: none`. Then prep and hand to the existing
pipeline:

```bash
cd C:/Projects/CAD/astra-engine-pump && "C:/Program Files/Blender Foundation/Blender 5.1/blender.exe" --background --python tools/blender_prepare_assembly.py -- --input out/engine-and-pump-v3.glb --output out/engine-and-pump.blend --drop-outliers --materials --json reports/prep.json
```

---

## 10. Files I created

All under `C:\Projects\CAD\astra-engine-pump\`. Nothing outside this
directory was modified; no source CAD was changed.

| Path | Purpose |
|---|---|
| `tools/step_assembly_map.py` | Stdlib STEP assembly/geometry mapper. Products, NAUO tree, occurrence transforms, per-product surface-type census, raw + robust bboxes, units. No CAD kernel; 10 s on 194 MB. This is what proved the engine-husk finding. |
| `tools/step_to_glb.py` | The converter. STEP → XCAF → tessellation → GLB, with unit/axis/name-format control and per-phase time + peak-RAM telemetry. `--probe` is a 5 s API smoke test. |
| `tools/blender_validate.py` | Headless validation: role coverage, outlier detection, scale check, turntable + isolation renders, `report.json`. |
| `tools/blender_prepare_assembly.py` | GLB → render-ready `.blend`: collections by role, outlier quarantine, normals, weld, degenerate-face removal, budgeted decimation, role materials. |
| `source/engine-and-pump.STEP` | Copy of the Drive original. Read-only in this work. |
| `reports/*.json`, `reports/*.log` | Machine-readable manifests and run logs for every claim above. |
| `reports/validate-v2/*.png` | Acceptance renders, including `isolate_engine.png`. |
| `out/engine-and-pump-v3.glb` | **The good one.** Correct units, upright (Z-up), product-named nodes. 23.5 MB, 1,077,512 tris. Start here. |
| `out/engine-and-pump.glb`, `-v2.glb` | Earlier iterations — v1 unnamed nodes, v2 named but Y-up. Kept for diffing; do not ship. |
| `out/engine-original.glb` | The **real** 451 MB engine, converted. 144.1 MB, 4,537,176 tris, with its native colours. Use for the swap in §2. Imports in ~15 min (§11). |
| `out/engine-original-coarse.glb` | Same engine at lin 2.0 mm / ang 35°. 98.8 MB, 2,275,074 tris, imports in 358.8 s. **Try this one first.** |
| `out/engine-and-pump.blend` | **Render-ready scene**, built from v3. 29.3 MB, 690,377 tris, role collections, outlier quarantined, materials assigned. |
| `out/test-prep.blend` | Earlier proof that the prep script runs end to end (built from v2, so it is tipped). Disposable. |
| `jobs/engpump_01_no-background.json` | Job manifest for the existing `msp_render_cli`, pointed at the `.blend`. Camera is an estimate, not a tuned framing. |
| `.venv/` | Isolated CPython 3.12 + `cadquery-ocp` 8.0.1. Disposable. |

`tools/step_assembly_map.py` is worth promoting into
`~/.agents/skills/step-reduction/scripts/` if you find it useful — it is
general, stdlib-only, and complements `step_text_scan.py`. I left it here
rather than mutating a shared skill mid-mission.

`tools/_import_probe.py` is a throwaway diagnostic (§11); delete it freely.

---

## 11. The real engine — slow, not broken

**I got this wrong once and corrected it, so read the conclusion, not the
first paragraph of the story.**

Two attempts to render `out/engine-original.glb` produced no output and I
concluded Blender was dying silently on it. **That was wrong — I was
checking before it finished.** A clean isolated import probe settles it:

```
IMPORTING out/engine-original.glb 151.09 MB
IMPORT OK objects=3 tris=4,537,188 in 892.7s
```

**The import works. It takes just under 15 minutes.** The engine is one
merged vendor product, so OCCT emits it as 2 enormous `COMPOUND` meshes, and
Blender's glTF importer is a Python add-on whose cost per mesh scales
badly. For contrast, the 53-object skid GLB (1.08 M tris spread over 53
meshes) imports in seconds. **Mesh count, not triangle count, is what the
importer cares about.**

Two builds of the real engine are on disk, both measured end to end:

| file | deflection | triangles | GLB | convert peak RSS | **Blender import** |
|---|---|---|---|---|---|
| `out/engine-original.glb` | lin 0.5 mm / ang 20° | 4,537,176 | 144.1 MB | 5,269 MB | **892.7 s** |
| `out/engine-original-coarse.glb` | lin 2.0 mm / ang 35° | 2,275,074 | 98.8 MB | 4,990 MB | **358.8 s** |

Halving the triangles cuts import time by **60%** (1.99× the triangles costs
2.49× the time — roughly O(n^1.3), so it is superlinear but not quadratic).
**Start with the coarse build** unless a close-up needs the fine one; at
2.0 mm deflection on a 3.5 m engine the difference is not visible in a
wide shot.

Either way it is a **one-time** cost: import once, save the `.blend`, and
you never pay it again.

**If the 15-minute import is unacceptable**, the structural fix is to stop
handing Blender two giant meshes: the engine is 4,699 open shells, and
emitting one glTF mesh per shell (or per N shells) turns one pathological
mesh into thousands of small ones — the shape the importer is fast at. That
is a change to `step_to_glb.py`: add the shells to XCAF as separate labels
before writing. I did not do it; the 15-minute path works and it is a
one-time cost, since after import you save a `.blend` and never pay it again.

**What is unaffected:** the skid assembly
(`out/engine-and-pump-v3.glb`, `out/engine-and-pump.blend`) imports in
seconds and is ready to render. Nothing here blocks tomorrow's image.
