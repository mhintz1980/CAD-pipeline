# READY rev4 — dispatch now

Authoritative readiness: `reports/astra-engine-export-code.md` (rev 4).

`tools/astra_engine_export.py` — **COMPILE_OK**, sha256
`b47b2574b0a24535cd908e8d44b48e581dea7279de3e926545a830a430d9d7f3`.
No local Blender was launched.

Rev 4 final quality pass (small, targeted changes on top of rev 3):
1. `DECIMATE_NAMES = {"COMPOUND.001"}` only — the tiny 360-tri `COMPOUND` and the
   other 6 bodies are protected and coordinate-exact (`protected_bodies` lists them).
2. `--decimate-light` default **350000** (~17.5 MB); detailed stays **500000** (~25 MB).
3. Preview hardened: `use_sequencer=False`, `use_compositing=False`, evaluated-camera
   assert + `view_layer.update()`, GPU device proof (`render_gpu`, `GPU PROOF select …`
   log) rather than a bare "GPU allocated" claim; stage reused after isolation.
4. README dynamic: recommends the 25 MB detailed STL; light STL is a compact reference
   only if measured sampled max dev ≤ 3 mm, else **VISUAL-ONLY with the actual value**
   (14:12 run measured 33.886 mm → visual-only, NOT fit-ready). STL called a mesh
   reference, NOT an analytic solid and NOT watertight. SolidWorks: File > Open, units
   millimetres, Graphics Body (or mesh/BREP), NOT facet-per-face Solid Body; native SW
   import not yet tested.
5. Honest mesh diagnostics: `report["mesh_quality"]` (watertight=false, boundary and
   non-manifold edge counts) + warnings; open mesh defects REMAIN, cleanup/decimation
   introduce non-manifold edges; NOT a healed solid.
6. `report["script_rev"] = 4`.

Cloud worker: rerun ONCE with this script (prior actual runtime ~77 s). Keep old runs
immutable. Preserve the source sha and download all outputs including failure logs.
Deadline 14:44 EDT.
