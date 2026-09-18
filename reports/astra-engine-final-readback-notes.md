# Independent verifier notes — rev3 code review + SolidWorks presence (2026-09-18 14:08 EDT)

Owner: independent final verification agent. Scope: engine-only (7 meshes, `CAD_engine`).

## Fresh review of tools/astra_engine_export.py rev3 (read-only, no producer history)
No blocking bugs found. Prior fix-list items verified present in code:
- Units: `mm_scale_factor() = scale_length*1000`; bake via `Matrix.Scale(mm,4) @ matrix_world`. OK.
- Exports+README+JSON written BEFORE destructive isolation and render. OK (recoverable).
- Mount preservation: `np.array_equal` of baseline vs working tri coords for protected bodies. OK.
- Deviation: BVH `find_nearest` hit[3] = distance, misses → NaN (not zero-filled), bidirectional. OK.
- STL header says "(not watertight)" — honest; report records boundary/nonmanifold counts, no watertight claim.
- GPU evidence honest CPU fallback; PNG existence asserted (relaxed to >1 KB).

Non-blocking observations:
1. `stage_scene` relinks working bodies into new `ENGINE_EXPORT` collection; the saved
   `engine-cleaned.blend` is saved BEFORE staging, so the blend contains working bodies in
   their original collections but the mm copies — acceptable, but note the export coll is
   NOT in the saved blend (README says "Append > Collection ENGINE_EXPORT" — this could
   mislead; flag to architect).
2. Deviation sample loop is per-point Python over BVH (8000 pts/body) — slow but fine on cloud.
3. `write_outputs` called twice (pre- and post-render) — intended, fine.
4. `clean_mesh_mm` may merge near-degenerate geometry in DECIMATE_NAMES only; mounts bypass. OK.
5. STL float32 rounding: baseline compare uses float64 mesh coords, STL stores f4 — mount
   "exact preservation" claim applies to the blend bodies, not to the STL bytes; verifier
   checks STL independently. OK.

## SolidWorks presence check (read-only registry + Program Files)
- No `SOLIDWORKS.Part` ProgID, no `.sldprt`/`.sldasm` handler, no `C:\Program Files\SOLIDWORKS Corp`.
- Only a bare `.stl` key with NO default value (no association at all).
- **Conclusion: SolidWorks is NOT installed on this machine. SW import round-trip is
  UNVERIFIED.** We do NOT and cannot launch any SW app here.

## Official SolidWorks import instructions (from SW documentation knowledge; to follow on a
## machine that HAS SolidWorks — none available here, so marked unverified)
- Binary STL mm: File > Open, set file type to STL (*.stl), click Options…, set
  Import as: Graphics Body (or Mesh Body for the tessellation feature), Units: Millimeters,
  then Open. (NOT "File > Import" — that path does not exist in SolidWorks for STL.)
- Do NOT apply extra scaling; STL is already mm.

## Blocking bugs in cloud preflight (NOT my code, flagged for architect)
- `reports/astra-modal-engine/preflight2.log`: modal `Volume.read_file` used as context
  manager → `TypeError: 'generator' object does not support the context manager protocol`.
  Producer STATUS.md claims this was fixed ("download via Volume.read_file (bytes)"), but
  preflight2 still shows the old pattern at lines ~139-140. Fix must land before dispatch.
