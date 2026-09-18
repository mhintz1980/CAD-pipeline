# Independent wide-scene verifier plan (GLM Flash) - 2026-09-18

## Scope
Independent verification of confirmed widening: +76.2 mm each side (152.4 mm total),
fixed engine/pump, controller follows left (minus-X) bale upright.
Baseline (authoritative source): `out/engine-and-pump-v10.blend` (on-disk SHA-256 recorded in report).
Candidate: `out/engine-and-pump-v11-wide.blend`.
Tool: `tools/astra_verify_wide.py` (only file owned by this worker, besides this plan).

## Invocation (run only after implementation worker finishes; no Blender launch now)
```
blender -b -P tools/astra_verify_wide.py -- `
  --baseline C:/Projects/CAD/astra-engine-pump/out/engine-and-pump-v10.blend `
  --candidate C:/Projects/CAD/astra-engine-pump/out/engine-and-pump-v11-wide.blend `
  --report C:/Projects/CAD/astra-engine-pump/reports/astra-wide-verifier-report.json
```
Exit code 0 = all checks pass; nonzero on any failure or stale/identical candidate file.
No blend is saved; user-owned Blender GUI untouched.

## Checks implemented
1. Object sets identical; candidate file hash differs from baseline (no false PASS on stale copy); mesh count 468.
2. Classification into side (20: six MC channel longitudinal skid members, PP-FTS-1005 pair,
   four PP-FBS outer braces, eight bale meshes excluding LBA-CB), controller (3), lengthened (15:
   PP-FTT pair, six PP-FTS-1008, Copy of Copy of Part11^PP128-FTA pair, Part1^PP128-PP108-SKID pair,
   tube rectangular_ai_TR12x6x0.25x80 pair, LBA-CB), fixed (430) - class counts enforced.
3. Side meshes: uniform +/-76.2 mm X translation, dY=dZ=0 (0.1 mm tol).
4. Controller meshes: -76.2 mm X, dY=dZ=0; internal rigid-group relative transforms unchanged.
5. Fixed meshes (incl. 415 CAD_pump_new, 7 CAD_engine, DOUBLER pair, MNT-PEB-CTF-PP12-WIDE,
   PLT-MNT-6SL-PE-PP12, four PP128S22-MFB): world coords bit-comparable unchanged.
6. Engine/pump local vertex data AND world matrices identical.
7. Topology unchanged everywhere: loop vertex-index arrays, triangle counts, per-mesh hash.
8. Lengthened meshes: every vertex X delta in {-76.2, 0, +76.2} mm (0.1 mm tol), dY=dZ=0,
   extreme-X endpoints move outward, central mount region stays fixed.
9. Cut planes at nominal X=-680 / +798 mm: every triangle crossing a plane in either file must
   have world-space face normal X ~= 0 (straight X-extrusion / planar profile), so curved
   transverse features are not split or distorted. Curved longitudinal extrusion edges are
   accepted when topology is unchanged (check 7).
10. Scene bbox: overall X width +152.4 mm, centre X unchanged, Y/Z bbox unchanged,
    top height (48in bale) preserved.
11. Uprights (PP128-FTA pair): spacing +152.4 mm, each exactly outward 76.2 mm.
12. Materials, collection membership, parents, visibility metadata (hidden/hide_viewport) unchanged.
13. No scale or rotation introduced vs baseline (rigid-matrix determinants/column norms).

## Limitations
- Connection/stress integrity, weld and bolt adequacy are NOT certified; geometric/transform
  checks only. Remaining connection tests are reported as UNVERIFIED.
- Clearance/interference between moved parts is not re-simulated.
- Cut-plane test is a heuristic (normal X tolerance 0.05), applied to both files for fairness.
- Baseline defects are intentionally not rejected; before/after stats compared only.
- If the implementation worker used different cut planes, this verifier still checks the
  nominal -680/+798 mm planes independently; a fail there flags rather than auto-rejects, and
  any override would require independent safe-feature evidence.
- Blender must have numpy available (bundled).
