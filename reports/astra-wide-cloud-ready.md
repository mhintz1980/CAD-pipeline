# Astra wide-scene cloud readiness — code review & preparation (final)

Date: 2026-09-18. Seat: code review/preparation only. **No local Blender run, no cloud job
launched from this seat, no v10 edits, no git writes.** Source `out/engine-and-pump-v10.blend`
is immutable (sha256 `5f8632d8ef9b27da15b221f47feb9fb37dcea7b52493aeba62125523ae5f5e6f`).

## Governing decision (applied)
`ASTRA-WIDENING-DOUBLER-DECISION.md` **supersedes** `astra-wide-verifier-spec.md` (older policy):
- DOUBLER and DOUBLER.001 are **lengthened** at their outboard ends, cut planes **X=-665/+665 mm**.
- DOUBLER central engine-support footprint |X| <= 635.5 mm must remain **bit-unchanged**.
- End extension is +/-76.2 mm world-X per side — **not** a global scale.
- Updated counts: **23 rigid / 17 lengthened (incl. DOUBLER pair) / 428 fixed = 468**.
- Nominal cuts for the other 15 members remain X=-680/+798 mm.
- Baseline v10 clearances: left 13.559 mm, right 22.959 mm (inspection JSON, matches).

## Files reviewed / owned
- `tools/astra_widen_v11.py` (producer) — reviewed, **already conforms** to the DOUBLER
  decision: `CUT_DOUB=(-665,665)`, `CENTRAL_KEEP=635.5`, 17/23/428 counts, per-plane
  `plane_safety()` proofs (vertex-free runs, |n_x|<=1e-3 on crossing faces, >=5 mm margins,
  no vertex inside the keep band moved), actual post-edit BVH clearance measurement
  (not baseline+76.2), rigid/lengthened/fixed hash and topology guards, reload recheck.
  No changes required.
- `tools/astra_verify_wide.py` (verifier) — **updated** to the current policy:
  - class counts now 20/17/3/428; DOUBLER classified lengthened.
  - New dedicated check: DOUBLER central |X|<=635.5 mm vertices unchanged; outboard
    deltas in {0, +/-76.2}; dYZ=0.
  - New check: DOUBLER X span +152.4 mm, bbox centre unchanged.
  - Cut-plane heuristic now uses per-class planes (members -680/+798; DOUBLER -665/+665).
  - Lengthened check message corrected to 17.
  - Limitations note the superseding decision explicitly.
- Both scripts `python -m py_compile` **PASS**. Producer and verifier reports use
  **disjoint paths** (below).

## Portability (Linux cloud vs Windows local)
Both scripts are already portable CLIs with **all-path arguments**; no Windows defaults are
hardcoded for source/output/report paths:
- Producer: `OUT_JSON`, `SAVE_BLEND` (rel. paths resolve against repo root of the script
  location, which works identically on Linux); source is asserted to be `<repo>/out/engine-and-pump-v10.blend`.
- Verifier: `--baseline/--candidate/--report` are mandatory; no default paths.
No Windows-specific code in either script. `os.path` used throughout (POSIX-safe).

## Exact cloud commands (Linux)
Run from the repository root (same tree pushed to the cloud machine); Blender >= 3.6 with numpy.

1. Producer (background, 4 threads, saves v11 only after all guards pass):
```bash
blender -b -noaudio --threads 4 out/engine-and-pump-v10.blend \
  --python-exit-code 1 --python tools/astra_widen_v11.py -- \
  reports/astra-widening-v11.json out/engine-and-pump-v11-wide.blend \
  5f8632d8ef9b27da15b221f47feb9fb37dcea7b52493aeba62125523ae5f5e6f
```
2. Independent verifier (never saves blends; exit 0 only on all-pass):
```bash
blender -b -noaudio --threads 4 --python-exit-code 1 --python tools/astra_verify_wide.py -- \
  --baseline out/engine-and-pump-v10.blend \
  --candidate out/engine-and-pump-v11-wide.blend \
  --report reports/astra-wide-verifier-result.json
```
(Prefer absolute paths if CWD is not the repo root; both scripts accept them.)

## Disjoint report paths
- Producer: `reports/astra-widening-v11.json` (+ sibling log owned by producer seat).
- Verifier: `reports/astra-wide-verifier-result.json` — new, does not collide with
  producer or inspection outputs.

## Review assertions (static, no execution here)
- Names used are taken directly from the producer's asserted part lists and collection
  counts (validated against 468-mesh source at runtime, not guessed): 17 LEN, 23 RIGID,
  FIXED_GUARD mounts, `CPM-PP-JD18` EMPTY with exactly 3 mesh children.
- Verifier fails closed: any check failure -> non-zero exit and `passed:false` in JSON;
  stale candidate (identical sha256 to baseline) is rejected.
- The DOUBLER guard is a direct vertex-level check (no inference from bbox), so a
  re-centred or globally scaled doubler cannot pass.

## Remaining limitations
- Static compile + code review only; scripts are unexecuted in this seat (no Blender here).
- Verifier does not re-measure engine/upright clearance (producer does, with real BVH
  queries; inspection baseline 13.559/22.959 mm recorded for comparison).
- Connection/weld/bolt integrity not certified; geometry checks only.
