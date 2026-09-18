# Astra wide-scene render plan — PREPARED, NOT RENDERED (2026-09-18)

Owner: GLM Flash (wide render prep worker). Script: `tools/astra_render_wide_preview.py` (clone of `tools/astra_render_preview.py`, original untouched).

## Livery deltas vs. original renderer
- `CAD_skid` + all structural tray/end-rail/support pieces under `CAD_pump` (PP-FTT/FTS, PP128-FTA, PP-FBS): **RAL 6002 Leaf Green** #276235 (new `green_structure` role, material `ASTRA_Structure_RAL6002`) — skid goes green WITH pump per widening revision.
- `CAD_bale` lifting bale: **PMS 293 blue** #003DA5 (unchanged; `--blue-hex` preserved).
- Engine: John Deere green #367C2B with per-slot functional finishes preserved. Grey #4C4DF deliberately not guessed.

## Carried forward (unchanged)
In-memory `CAD_pump_new` collection `hide_render` fix; evaluated + camera-ray pump participation assertions; opaque neutral floor at measured skid bottom; pump-side hero, engine-side hero, optional controller closeup; source sha256 + geometry digest invariance; separate look-dev blend save; all bounds measured from input (no fixed v10 dimensions).

## Invocation — run ONLY after geometry worker delivers `out/engine-and-pump-v11-wide.blend` AND independent verifier passes
```
blender --background --python tools/astra_render_wide_preview.py -- `
  --input C:/Projects/CAD/astra-engine-pump/out/engine-and-pump-v11-wide.blend `
  --output-dir C:/Projects/CAD/astra-engine-pump/reports/astra-wide-preview `
  --width 1200 --samples 32 --threads 4 --with-controller-detail
```
If v11 is not ready, the script accepts `out/engine-and-pump-v10.blend` unchanged (livery still applies; geometry is whatever the input holds). Do not treat v11 as existing until the worker writes it. Outputs: `reports/astra-wide-preview/astra-wide-preview-*.png`, `astra-wide-preview-lookdev.blend`, `astra-render-execution.json`, `astra-wide-preview-slot-inventory.json`.

## Status
`python -m py_compile` passes. Source review confirms skid/tray green mapping is separate from blue bale role and the visibility fix + ray assertions are intact. No Blender run, no geometry edits, no commits.
