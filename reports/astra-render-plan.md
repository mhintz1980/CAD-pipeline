# Astra render plan - engine/pump skid first-look preview (2026-09-18)

Status: **RENDERED** - see `reports/astra-render-execution.md` for the executed
run, exit status, timings, hashes and evidence. This plan is retained as the
planning record; the stale statements flagged at the end have been corrected.

## Correction log (DeepSeek Flash, render worker, 2026-09-18)

This file previously claimed: "IMPLEMENTED, NOT RENDERED ... Blender was never
invoked this phase"; that v10 did not exist; that a shadow catcher would ground
the machine; that all engine per-face colours were overridden by design; and it
offered `--blue-hex #0057B8` as a Process Blue test. Those statements are stale or
wrong. Corrections:

1. **Rendered.** Blender 5.1.1 was invoked and produced final artifacts; see
   `reports/astra-render-execution.md` and `reports/astra-preview/`.
2. **v10 exists** - `out/engine-and-pump-v10.blend`, sha256
   `5f8632d8ef9b27da15b221f47feb9fb37dcea7b52493aeba62125523ae5f5e6f`, built by
   the controller worker and independently verified (PASS, zero violations).
3. **Quarantine is absent, not deleted.** The handoff expected a
   `CAD_QUARANTINE_outliers` collection; the independent verifier and this
   worker's collection audit both find no such collection in v9 or v10. No
   deletion step was relied on.
4. **Process Blue example was invalid.** `#0057B8` is not Pantone Process Blue.
   The documented digital approximation is **`#0085CA`**. PMS 293 `#003DA5`
   remains the first-preview choice, so no blue switch is made; `--blue-hex`
   still allows one without code changes.
5. **Engine casting colour is per-slot, not blanket.** The script classifies each
   vendor material slot by linear luminance and channel spread, preserving
   metal/rubber/exhaust where separable, instead of overwriting every slot.
6. **No shadow catcher.** An opaque local beauty preview uses a real opaque,
   rough, neutral diffuse floor (`#63666A`, roughness 0.92) 2 mm below the
   measured skid bottom. The catcher guidance applies to transparent-film
   composites, not this opaque deliverable.
7. **Cameras are reframed.** The planned radius-relative hero was replaced by a
   bounding-box fit: primary pump-side hero from minus-X / plus-Y / above, an
   additional engine-side view, and a controller detail shot.
8. **Blocking source defect found at render time.** v10 ships `CAD_pump_new` with
   **collection-level `hide_render = True`**, so the pump never reached a camera
   ray and the deck rendered empty until the preview cleared the flag in memory.
   Recorded in `astra-render-execution.json` under `source_visibility_fix`.

## What was written
- `tools/astra_render_preview.py` - self-contained Blender 5.1 headless script.
  Opens the input `.blend` in memory, clears the source's render suppression,
  applies livery, builds the grounded studio, renders, proves geometry and source
  invariance, and writes the run record. Does not overwrite the source.
- `reports/astra-preview-materials.json` - palette audit, validated JSON.
- `reports/astra-preview/` - output directory (populated).

## Livery (per ASTRA-LIVERY-DIRECTION-2026-09-18.md; MSP yellow NOT used)
- Pump body (`CAD_pump_new`) and pump-specific mounting brackets: RAL 6002 Leaf
  Green, working hex `#276235` (approximation).
- Skid + bale + the `CAD_pump` frame-tray parts (painted structure under the
  machine, not pump casing): PMS 293 blue, working hex `#003DA5`. Overridable
  with `--blue-hex`.
- Engine painted castings: John Deere green `#367C2B`. The incomplete grey
  `#4C4DF` is deliberately neither used nor corrected.
- Functional finishes preserved per material slot: zinc hardware `#D8D8D8`,
  rubber `#171717`, exhaust `#4A4A4A`, control face `#1F1F1F` - values verified
  against `msp_render_cli/materials.py` SUB_ASSEMBLY_MATERIALS.
- All swatches labelled approximations in the JSON; no logos, no text overlays.

## Scene handling
- Role mapping by existing collections (`CAD_skid`, `CAD_bale`, `CAD_engine`,
  `CAD_pump`, `CAD_pump_new`, `CAD_controller`; 468 meshes, consistent with
  `reports/astra-baseline-v9.json`). Geometry and transforms untouched.
- Render-suppression audit: `CAD_pump_new` was the only suppressed collection.
  The preview clears it in memory and verifies 415/415 pump meshes are renderable,
  in the active view layer, with non-empty evaluated meshes, and that camera rays
  from the hero hit the pump (24/24 sampled rays). Script exits non-zero if not.
- Floor: opaque, rough, neutral diffuse plane at the measured skid bottom with
  2 mm clearance, lit by a 5 degree SUN key plus fill/rim so a contact shadow
  footprint shows under the skid supports. Excluded from camera-fit bounds and
  from the geometry digest.
- Cameras derived from actual bounds (bounding-box fit, 0.92 margin).

## Dispatch command (as executed)
```
cd C:/Projects/CAD/astra-engine-pump
"C:/Program Files/Blender Foundation/Blender 5.1/blender.exe" --background --factory-startup \
  --python tools/astra_render_preview.py -- \
  --input out/engine-and-pump-v10.blend --output-dir reports/astra-preview \
  --width 1200 --samples 48 --threads 4 --with-controller-detail \
  --save-blend reports/astra-preview/astra-preview-v10-lookdev.blend
```
Render: Cycles CPU, 4 threads fixed, 1200x840, 48 samples, OIDN denoise, AgX
Medium High Contrast, persistent data, single process, sequential frames.
`--factory-startup` is used so no user preferences or add-ons affect the result.
Optional Process Blue test: add `--blue-hex #0085CA` (approximation, not tuned).

## Result paths
```
reports/astra-preview/astra-preview-threequarter.png        (primary pump-side hero)
reports/astra-preview/astra-preview-engine-side.png         (additional engine view)
reports/astra-preview/astra-preview-controller-detail.png   (controller close-up)
reports/astra-preview/astra-preview-v10-lookdev.blend       (massed look-dev scene)
reports/astra-preview/astra-render-execution.json           (run record)
reports/astra-preview/astra-preview-render.log              (Blender log, EXIT=0)
```

## Notes / limitations carried forward
- The controller-detail shot assumes the relocation script ran (CAD_controller
  near LBU-PP.001); on un-moved v9 the bbox would frame the parked position.
- Pump fasteners whose mesh names are numeric Onshape IDs stay RAL 6002; only
  text-matched fasteners take zinc. Accepted for first look.
- Not done: mask/matte pass, depth pass, compositing - out of first-look scope.
- Owner visual acceptance is pending and is not claimed by this document.
