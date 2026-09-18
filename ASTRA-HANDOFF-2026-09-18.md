# Handoff to Astra — pump skid, scene build → rendering

**Written 2026-09-18 by Claude (Opus 5).** Supersedes `ASTRA-HANDOFF-2026-09-17.md`
for anything about the *current scene*; the 09-17 document is still the reference
for the conversion pipeline, the source-file forensics and the engine-husk
analysis. Read §0 and §1 here first, then dip into 09-17 as needed.

Work area: `C:\Projects\CAD\astra-engine-pump\`. Source CAD was copied, never
modified.

Every claim is labelled **PROVEN** (measured, reproducible), **TESTED**
(observed but not exhaustively), **HYPOTHESIS**, or **OPEN**.

---

## 0. Read this first — six things that will cost you a day

1. **The scene is built by scripts, in a lineage. Do not edit a `.blend` by hand
   and expect it to survive.** v3 → v8 are sequential; each script reads the
   previous file and writes the next. Paths in §2.
2. **Blender's glTF exporter writes collections that are excluded from the view
   layer.** A quarantined duplicate engine leaked into an export and inflated the
   GLB from 23.2 MB to 38.7 MB. `tools/blender_export_clean.py` *deletes* the
   quarantine first — use it, don't just hide the collection. **PROVEN.**
3. **A glTF import parents everything under a root empty.** Setting
   `matrix_world` on every imported object double-applies the transform and
   silently scatters the model. Move only the roots. This cost an hour. **PROVEN.**
4. **Blender resolves relative output paths against its own cwd, not yours.**
   Always pass absolute paths to `--python` scripts. **PROVEN.**
5. **Importing a large single-product mesh is superlinear and slow.** See §7 —
   budget minutes, not seconds, and do not kill the job.
6. **The engine husk's mesh is rotated +90° about X, but its object matrix is
   NOT.** The earlier `--in-axis Y` prep baked that rotation into the *mesh data*
   and left the matrix as pure translation, so you cannot recover the frame by
   composing matrices. Composing it onto a freshly-imported standalone engine
   drops the rotation and lands the engine ~1.3 m out with its Y and Z spans
   swapped. **Verified map: scene Y = −native Z, scene Z = +native Y.** See §1.4.
   The failure is silent — the engine still *looks* like an engine on a skid.

---

## 1. What changed today (2026-09-18)

### 1.1 Pump added — `PP108C24-EO1_THD_TMVP` **PROVEN**

Source: `source/PP108C24-EO1_THD_TMVP.step`, exported from **Onshape** as
**STEP AP242 Edition 2**, 53.1 MB. Exported with **Preprocessing: None** — the
other options ("remove small entities", "convert all surfaces to B-surfaces")
delete or spline-ise exactly the geometry this pipeline exists to preserve.

| | |
|---|---|
| parts | 415 (262 solids, 270 closed shells, 165 open shells) |
| faces | 14,314 |
| triangles | **807,046** @ lin 0.5 mm / ang 20° |
| GLB | `out/pump-pp108c24.glb`, 27.7 MB |
| convert | 17.3 s read · 2.8 s tessellate · 862 MB peak |
| colour | **yes** — 845 styled items, 40 `COLOUR_RGB` survived into the GLB |

It is a complete **Vogelsang rotary lobe pump** — lobe chamber, timing-gear
cover, bearing housing, both ports, mounting feet, fasteners. Nothing like the
engine husk.

**The drive shaft is part `1207517913`** — Ø94.9 mm × 749.2 mm, running along Y.
**PROVEN** by measurement, and its axis is the datum everything else references.

> **⚠ Verify the model number before rendering.** Mark first named
> `PP128S22-EO1_THD_TMVP`, but the file delivered is **`PP108C24`**. The two
> coexist in his world: the skid drawing is *"JD18 & PP108C24"* and the skid
> part is `PP128-PP108-SKID`, but every existing pump-side part in the assembly
> is `PP128*` (`PP128-FTA`, `PP128S22-MFB`). **OPEN** — confirm this is the
> intended pump for this skid.

### 1.2 Lifting bale re-centred — **PROVEN, approved by Mark**

The bale was symmetric about X = 0 while the skid's side structure is symmetric
about **X = +59 mm**. The whole `CAD_bale` collection was shifted **+59 mm** in X.
Result: both bolt plates (`PP-LBB` / `.001`) now engage the skid side-wall inner
faces by **+4 mm** on both sides, and the upright centres centre on X = +59.

### 1.3 Pump placed and centred — **PROVEN**

The pump's bores run along X in its own frame, so it was rotated **+90° about Z**
to put the shaft along Y (coaxial with the engine crank), then **180° about its
own shaft axis**, then translated.

> **The trap that cost two passes:** the pump's **bounding-box centre is 273 mm
> from its rotor axis**. Centring on the bbox centre leaves the *shaft* half a
> metre out while the pump still *looks* roughly central. Centre on the **shaft**,
> not the bbox. The shaft is the line through the pump's own local origin
> (local y=0, z=0), readable from the glTF root's transform.

Mark caught this by annotating a render: his red line measured **X = −497.7 mm**;
the measured rotor axis was **−497.8 mm**. Agreement to 0.1 mm.

Final: shaft at **X = +1.0 mm**, the engine's bbox centreline.
Pump bbox `X[−488, 919] Y[509, 1606] Z[−274, 932] mm`.

### 1.4 Engine swapped to the full vendor model — **PROVEN**

The assembly ships with an **interfaces-only husk**, not a real engine. §2 of the
09-17 handoff proves this: the husk's 4,023 faces are **2,700 cylinders + 1,323
planes and zero B-splines** — the signature of the earlier `export_interfaces`
mate-reference filter. A real casting has thousands of splines and fillets
(compare the controller: 651 B-spline, 368 conical, 180 toroidal).

The full model is **on disk** — see §3. `tools/blender_swap_engine.py` replaces
the husk with it.

**First attempt failed and is worth reading.** Composing the husk's object matrix
onto the imported engine produced a scene where X was right (±16 mm) but Y was
out by 1.3 m and the Y/Z spans were swapped. Cause: the `--in-axis Y` prep baked
+90° about X into the husk's **mesh data**, leaving its object matrix as pure
translation — so the rotation was invisible to matrix composition and got
silently dropped. Fixed by deriving the frame numerically from the two bounding
boxes rather than composing transforms:
`scene Y = −native Z`, `scene Z = +native Y` → rotate +90° about X, then align
bbox centres. Final deltas **X ±16, Y ±13, Z ±1 mm** — the husk's lost curved
surfaces, not error.

### 1.5 Pump placement is FINAL — confirmed by Mark — **PROVEN**

**Mark moved the pump himself and saved `out/engine-and-pump-v9.blend` at 04:17
on 2026-09-18. Do not move it.** Measured back out of the saved file:

| | mm |
|---|---|
| pump bbox | `X[−489, 918] Y[266, 1363] Z[−364, 842]` |
| shaft `1207517913` axis | **X = 0.0, Z = 124.5**, Y centre 640.4 |
| engine bbox | `X[−836, 838] Y[−1762, 522] Z[−483, 1716]` |
| whole scene | `X[−1021, 1044] Y[−2372, 2372] Z[−972, 1956]` |

**The pump's drive end deliberately overlaps the engine envelope in Y** — the
pump starts at Y = 266 mm while the engine runs to Y = 522 mm. The drive shaft
enters the flywheel housing; this interpenetration is intentional. Do not
"fix" it.

Scene totals for render planning: **3,387,117 triangles across 468 meshes.**

### 1.6 Controller relocation — **scripted, not yet run**

Target: the **engine-side** face of the **−X** bale upright (`LBU-PP.001`), which
is the "left" upright in Mark's naming (pump-top.png convention: image-right = +X).

**Taper measured: 2.87° off vertical** — four faces on the upright carry normal
`(0, ±1, ±0.05)`, 87.13° from the Z axis. Cross-checked against the vertex
envelope (584 mm at the base → 334 mm at the top over 2439 mm ≈ 2.93°).

**`PP-CPM-1005` already has a mating face at `(0, +1, −0.05)`** — exactly
antiparallel to the upright's `(0, −1, +0.05)`. Same angle, same handedness.
**So this is a placement, not a modification — no cutting needed.** It looks like
the bracket was designed for this and is currently parked in the wrong place.

Height: 48" above the skid bottom. Skid bottom is Z = −972.3 mm, so
**bracket bottom → Z = +246.9 mm**. It is currently at +264 mm — only 17 mm off.

---

## 2. Scene lineage — exact paths

All under `C:\Projects\CAD\astra-engine-pump\`.

| file | what it is | state |
|---|---|---|
| `out/engine-and-pump-v3.glb` | conversion of the source, upright, outliers dropped | baseline |
| `out/engine-and-pump-v4.blend` / `.glb` | **+ bale shifted +59 mm** | good |
| `out/engine-and-pump-v5.blend` / `.glb` | + pump placed (shaft along Y) | superseded |
| `out/engine-and-pump-v6.blend` / `.glb` | pump 180° — **rotated about the WRONG axis** | superseded |
| `out/engine-and-pump-v7.blend` / `.glb` | pump shaft centred on the engine centreline | superseded |
| `out/engine-and-pump-v8.blend` / `.glb` | + full vendor engine swapped in | good |
| `out/engine-and-pump-v9.blend` / `.glb` | **+ pump at its final position** | **CURRENT — Mark-confirmed** |

**v9 is the current scene and its pump placement is confirmed correct by Mark.**
Everything downstream builds on v9.
`out/engine-and-pump.blend` is the original 09-17 scene — leave it alone.

> **⚠ The `.glb` beside v9 is stale.** `out/engine-and-pump-v9.glb` was written
> at 04:05, *before* Mark's 04:17 manual save — only `out/engine-and-pump-v9.blend`
> carries the final pump position. Never rebuild the scene from any GLB or from
> v8; that silently discards the correction. If Mark asks for further nudges,
> `tools/blender_nudge_pump.py` edits `v9.blend` directly — that pattern is safe.

Scripts, in lineage order:

| script | does |
|---|---|
| `tools/step_to_glb.py` | STEP → XCAF → tessellate → GLB. The converter. |
| `tools/blender_place_pump.py` | import pump, rotate 90° about Z, translate |
| `tools/blender_fix_pump.py` | 180° about Y (**used a wrong axis — see §1.3**) |
| `tools/blender_centre_pump.py` | **centre the shaft** on the engine centreline |
| `tools/blender_swap_engine.py` | replace husk with the vendor engine |
| `tools/blender_move_controller.py` | controller + bracket onto the bale face |
| `tools/blender_export_clean.py` | GLB export that deletes the quarantine first |
| `tools/blender_inspect_parts.py` | dump every mesh's world bbox to JSON |
| `tools/blender_measure_*.py` | taper / face-normal / part measurement |
| `tools/render_v5.py` → `render_v7.py` | the standard 5-view render set |

Analysis tools (OCCT, `.venv/Scripts/python.exe`):

| script | does |
|---|---|
| `tools/step_assembly_map.py` | stdlib-only assembly + geometry mapper, no CAD kernel |
| `tools/find_axis.py` | dominant cylinder axes in a STEP |
| `tools/find_crank.py` | cylinders with axis ∥ Y (crank candidates) |
| `tools/find_disc.py` | large planar faces with normal ∥ Y (flange candidates) |

---

## 3. The good engine model — where it is

The scene had the **husk**. The real engine is here, and Mark could not find it:

| path | what |
|---|---|
| `C:\Projects\Misc\3336180ci510.stp` | **451.8 MB, AP214** — vendor source |
| `C:\Projects\Misc\3336180ci510.prt` | 291.6 MB, Creo part |
| `out/engine-original.glb` | 144.1 MB, **4,537,176 tris** — fine conversion |
| `out/engine-original-coarse.glb` | 94.2 MB, **2,275,074 tris** — coarse |
| Drive `My Drive\3336180ci510.stp` | 473.8 MB |

The full engine is **20× richer** than the husk and brings **507 `COLOUR_RGB` with
74,092 styled items** — it ships with per-face colour that OCCT imports as glTF
materials. Unlike the AP203 assembly, which has **zero colour** — all materials
in the assembly must come from names/roles, which is what
`tools/blender_validate.py`'s role classifier does.

---

## 4. Measured geometry — the datums

Everything in **millimetres**, scene world coordinates, Z up. Machine is
**4.74 m (Y) × 2.07 m (X) × 2.93 m (Z)**.

| datum | value | how |
|---|---|---|
| skid bottom | Z = **−972.3** | scene min Z |
| skid side-wall centreline | X = **+59.0** | side rails mirror-symmetric about it |
| engine centreline | X = **+1.0** | engine bbox centre |
| bale uprights | X −815…−663 and +781…+933 | Y −292…+292, Z −483…+1956 |
| bale taper | **2.87°** off vertical | face normals `(0,±1,±0.05)` |
| pump shaft axis | X = **+1.0**, Z = **+214.5** | part `1207517913` — **v7-era; final placement in §1.5** |
| pump bbox | X[−488,919] Y[509,1606] Z[−274,932] | **v7-era; final placement in §1.5** |
| bracket bottom target | Z = **+246.9** | 48" above skid bottom |

> **The two centre lines disagree by 58 mm and that is real.** The skid's side
> walls centre on **+59**; the engine and the skid's end rails centre on ≈ **0**.
> Mark's annotation confirmed the engine is the datum for the pump. Do not
> "fix" this by averaging them.

---

## 5. Collections in the scene

`CAD_skid`, `CAD_engine`, `CAD_pump` (skid-side hardware), `CAD_pump_new` (the
Vogelsang pump), `CAD_bale`, `CAD_controller`, `CAD_QUARANTINE_outliers`.

**`CAD_QUARANTINE_outliers` holds a duplicate engine** — the outlier copy. Mark
has said to **delete it, he doesn't care**. Do that on your first export.

`tools/render_v5.py` colour-codes by collection (bale red, skid blue, pump cyan,
new pump green, engine grey, controller orange) — useful for framing, **not** for
final renders.

---

## 6. Still open

**Closed since this document was first written:** pump height and SAE flange
mating. Mark set the pump position himself and confirmed it correct — see §1.5.
**Do not reopen those.** He explicitly said of the flanges: *"they are SAE
flanges of the same size… the pump is driven by the engine's flywheel and a
splined adapter that I don't have in the model. For now just keep the flanges
mated together."* No standoff, no spacer, and no adapter part is expected.

What is genuinely still open:

1. **Controller move onto `LBU-PP.001`** — the −X bale upright, engine-side
   face, 2.87° taper, bracket bottom at Z +246.9 mm (48" above the skid bottom).
   `tools/blender_move_controller.py` is written but **has never been run** — it
   was queued against v8 and v9 is now current, so check the target vectors in
   the script against v9 before running it. Expected translation ≈
   `X −105, Y −94, Z −17 mm`.
2. **Confirm the pump model number** (PP108C24 vs PP128S22) — §1.1. Still worth
   a sentence from Mark before any render is published.
3. **Pioneer Pump livery** — not verified; see §8. Confirm with Mark whether the
   render wants MSP yellow/black or a Pioneer-specific livery.
4. **Items carried from the 09-17 handoff** — see that document's §10.

---

## 7. Performance — and why Modal is the right call for the big files

Mark uses Modal for the large files and this laptop is slower. Measured here:

| model | size | tris | convert | peak RSS | **Blender import** |
|---|---|---|---|---|---|
| skid assembly (husk) | 194 MB STEP | 1,077,512 | 2–3 min | 1,667 MB | seconds (53 meshes) |
| pump | 53 MB STEP | 807,046 | 20 s | 862 MB | fast (415 meshes) |
| **engine, fine** | — | 4,537,176 | — | 5,269 MB | **892.7 s** |
| **engine, coarse** | — | 2,275,074 | — | 4,990 MB | **358.8 s** |

**Halving the triangles cuts import time by 60%.** 1.99× the triangles costs
2.49× the time — **≈O(n^1.3)**, superlinear but not quadratic. (The 09-17 handoff
guessed "quadratic-ish"; the measurement corrects that.)

**Mesh count dominates, not triangle count.** The skid GLB carries 1.08 M tris
across 53 meshes and imports in seconds; the engine carries 4.5 M across **2**
meshes and takes a quarter of an hour. If you ever need the fine engine to import
quickly, **split the 4,699 shells into separate XCAF labels before export** —
that is a structural fix, not a quality reduction.

The import cost is **one-time**: import once, save the `.blend`, never pay again.

### Modal recommendation

The 09-17 suggestion of **8 CPU / 64 GB / persistent storage** still stands for
the 450 MB+ vendor models, and is now better supported: the engine conversion
peaked at **5,269 MB** and the assembly at **1,667 MB**, so 64 GB is generous but
safe. Evidence for the region:

- **CPU-bound, not GPU-bound.** Import and tessellation are single-threaded-ish
  Python/C++ work. A CAD GPU has no evidence behind it — **do not add one.**
- **Persistent Modal storage matters more than usual here**, because the engine
  GLB is 144 MB and re-converting it on every run wastes the dominant cost
  (§7). Convert once, keep the artifact.
- **Do the Blender work on Modal too, not just the conversion.** The 15-minute
  import is the single biggest cost in the whole pipeline and it is exactly the
  kind of thing a bigger box eats for pennies. **This is the highest-value
  Modal use in the project** — higher than the STEP conversion.

The existing Modal tooling is at `C:\Projects\msp-render-pipeline\` and
`C:\Users\Markimus\.agents\skills\step-reduction\scripts\modal_step_reduce.py`.

---

## 8. Materials — the company livery already exists, reuse it

**Do not invent a palette.** `C:\Projects\msp-render-pipeline\msp_render_cli\materials.py`
already holds **`LIVERY_PRESETS`**, calibrated against physical studio photography
(DD4S, RL200, RL300). Use it:

| preset key | name | body | frame |
|---|---|---|---|
| **`msp_standard_yellow`** | **MSP Standard Industrial Yellow & Black** | `#F7B500` | `#1B1B1B` |
| `united_rentals_blue` | United Rentals Fleet Blue | `#00529B` | `#141414` |
| `sunbelt_green` | Sunbelt Rentals Fleet Green | `#006B3F` | `#1E201E` |
| `herc_rentals_white` | Herc Rentals Fleet White | `#F2F4F7` | `#202020` |

**"The company colours" = `msp_standard_yellow`** — industrial yellow body,
near-black frame. That is Myers-Seth's own livery and it is the default for a
render of this package.

The same file also carries material presets to reuse rather than re-derive:
`cast_iron_pump`, `zinc_plated_hardware`, `rubber_fenders_tires`,
`exhaust_muffler`, `control_panel_face`.

### Pioneer Pump branding — **NOT VERIFIED**

Mark also offered "or Pioneer Pump". No Pioneer Pump brand assets exist on this
machine (searched Projects and the Drive mount). Pioneer Pump is a Franklin
Electric brand making large centrifugal dewatering pumps. **Do not guess hex
values.** Sources, in order of usefulness:

1. **Mark** — fastest and authoritative.
2. The prior renderings in `My Drive\Renderings\` (`DD6-RENDERING-*.png`,
   `DD6-MSP.png`) — the established look for this product family.
3. `brandfetch.com/pioneerpump.com` — has logos and colours, but is
   bot-verification-blocked to automated fetches; open it in a browser.
4. `pioneerpump.com` / `global.pioneerpump.com` media or press kit.

Note the search also surfaced that Pioneer Pump offers **custom colour** matching
for canopy/equipment branding, so a customer-specific livery may be the actual
requirement rather than a fixed corporate palette. **Confirm with Mark which.**

### Colour mismatch warning

The assembly is AP203 with **zero colour**. The pump (AP242) and the vendor
engine (AP214, 507 `COLOUR_RGB`, 74,092 styled items) **both import with their
own per-face materials**. Expect a visible mismatch between the pump/engine and
everything else unless the livery is applied over the top. Whoever does look-dev
should overrode both, or the render will show vendor colours on two assemblies
and grey everywhere else.

## 9. Rendering — where to start

The render pipeline already exists and is not this document's job to re-derive:

- `C:\Projects\msp-render-pipeline\` — CLI, job manifests, Modal workers,
  scene preparation, parity verification. Read `README.md`, `DEMO.md`,
  `docs/scene-preparation.md` and the `HANDOFF-2026-09-1*.md` series.
- Job manifests live in `jobs/*.json`; the schema is at
  `docs/job_manifest.schema.json`. **`jobs/engpump_01_no-background.json` now
  targets `out/engine-and-pump-v9.blend`** (repointed 2026-09-18 by ZCode; it
  had still pointed at the original 09-17 scene). Its camera values remain
  untuned estimates — expect first-look framing adjustments.
- **`ASTRA-HANDOFF.md`** in that repo covers the matte-pass bug, the ground-shadow
  fix and the parity chain. Read it before touching the renderer.

Two facts worth carrying across:

- **The four shipped job manifests all have `shadow_catcher: false`**, and
  `render_worker` *deletes* any ground shadow catcher in the scene when it is
  off. The machine floats. Only `rl300_02_studio-dark.json` was flipped to
  `true`, and flipping it alone was not enough — a bounce card floods the
  product unless `mute_catcher_bounce()` is applied. See that repo's handoff.
- **This scene has no colour in the assembly** (AP203). Materials must come from
  the role classifier or from your own look-dev. The *pump* and the *vendor
  engine* **do** carry per-face colour and will import with it — expect a
  colour mismatch between the engine/pump and everything else unless you
  override it.

---

## 10. Acceptance evidence from today

- `reports/assembly-map.json` + `.txt` — full product census, tree, per-product
  bbox and verdict. The grounds for the husk finding.
- `reports/pump-convert.json` — pump conversion manifest with per-phase timings.
- `reports/parts-v3.json` / `-v4.json` — per-object world bboxes, before and
  after the bale shift.
- `reports/views/` — every render, including `v7-top/side/iso` and the annotated
  `v6-top-axis.png` that pinned the shaft error.
- `reports/good-engine-discs.txt`, `good-engine-crank.txt` — the vendor engine's
  flange/crank candidates.

---

## 11. Astra's first command

```bash
cd C:\Projects\CAD\astra-engine-pump
"C:/Program Files/Blender Foundation/Blender 5.1/blender.exe" --background out/engine-and-pump-v9.blend --python tools/blender_inspect_parts.py -- reports/parts-v9.json
```

That prints the authoritative object list and world bounds for the current
scene — **v9**, whose pump placement Mark confirmed (§1.5). The earlier
"start from v7, then check v8" instruction is obsolete: v9 supersedes both.
