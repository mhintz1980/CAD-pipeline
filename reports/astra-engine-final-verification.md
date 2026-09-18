# Astra Engine Export — Independent Final Verification (rev 4, FINAL, 2026-09-18 14:25 EDT)
Supersedes the rev3 (run-20260918T140853) verdict; that run is NOT final and its 10 MB light
STL is NOT packaged. Final run: `reports/astra-modal-engine/run-20260918T141702/`
(script_rev 4, Modal L4, OptiX). Independent verifier: `tools/astra_verify_engine_export.py`
(struct+numpy only, exit 0) → `reports/astra-engine-final-readback.json`.

## ACTUALLY VERIFIED (independent readback)
- engine-detailed-mm.stl: **499,998 tris, 24,999,984 B (25.0 MB)**; count/size exact, 0 non-finite
  verts; bbox [-835.717,-1762.413,-482.756]..[838.154,521.778,1715.771] mm — within ±10 mm of
  expected baseline.
- engine-compact-mm.stl: **350,000 tris, 17,500,084 B (17.5 MB)**; same integrity checks pass;
  bbox max +X 838.062 (full geometry envelope retained, unlike old rev3 light).
- Scope engine-only: 7 bodies from `CAD_engine`; 6 protected (PP12-EM-JD18, EM-SP×4, tiny
  COMPOUND) — producer `mount_preserved_exact: true` for ALL 6 (numpy array_equal vs immutable
  baseline); only COMPOUND.001 (2,274,714 src tris) decimated (497,810 detailed / 347,812 compact).
- Sampled deviations (real BVH [3] distances, bidirectional, 8,000 samples, 0 misses;
  **not certified Hausdorff**):
  - detailed: max **1.55 mm**, mean 0.063 mm → **recommended dimensional reference**.
  - compact: max **10.42 mm**, mean 0.134 mm → exceeds 3 mm reference threshold →
    **labelled VISUAL-ONLY**, not recommended as dimensional reference.
- Preview PNG present and real: 1,020,672 B, 1000×800 Cycles, GPU OptiX, errors=[] in producer JSON.

## TOPOLOGY (reported, NOT claimed watertight — explicitly NOT watertight)
| file | welded verts | boundary edges | non-manifold edges | shells | euler χ |
|---|---|---|---|---|---|
| detailed | 338,540 | 203,241 | 4,147 | 4,275 | −10,538 |
| compact  | 249,113 | 174,095 | 4,112 | 4,342 | −10,422 |
Open bores/ports and unmerged assembly interfaces are intentional; graphics/mesh reference only.

## NOT VERIFIED / LIMITATIONS
- **SolidWorks import UNVERIFIED**: no SolidWorks installed on the verifier machine (read-only
  HKCR/registry + Program Files check found none). Package README carries the official
  SolidWorks path: File > Open → Options → Graphics Body / Mesh BREP, Units: Millimetres,
  no extra scaling. No SW app was launched; no user files touched.
- Non-manifold / open-mesh defects remain in both STLs (see table) — inherent to the export,
  not healed.
- Deviation stats are samples, not guaranteed worst-case bounds.

## DELIVERABLE PACKAGE (byte-verified copies; originals untouched)
`out/engine-solidworks-20260918/`
- engine-detailed-mm.stl (25.0 MB) — recommended reference
- engine-compact-mm.stl (17.5 MB) — visual-only label
- engine-cleaned.blend, engine-preview.png
- README.md (import instructions, quality labels, limitations, provenance)
- MANIFEST.sha256 (SHA256 of all files; copies cmp-verified byte-equal to run source)
Source provenance: out/engine-and-pump-v10.blend SHA256 5f8632d8…5f5e6f; producer
tools/astra_engine_export.py rev4; worker tools/astra_modal_engine.py; run 20260918T141702.

**Verdict: PASS** for structural/units/scope verification of rev4; deliverable package issued.
