# Controller relocation v9 → v10 — scene worker (DeepSeek Flash)

**Verdict: PASS** — 45/45 numeric assertions, `reports/astra-controller-v10.json`.
Exit status preserved. **Owner visual acceptance is NOT declared.**

## Commands actually run (all `--background -t 4`, exit status captured)

| # | command | exit |
|---|---|---|
| 1 | `blender --background -t 4 out/engine-and-pump-v9.blend --python tools/blender_inspect_parts.py -- reports/astra-baseline-v9.json` | 0 |
| 2 | `... --python tools/astra_controller_v10.py -- measure reports/astra-controller-measure.json` | 0 |
| 3 | `... --python tools/astra_controller_v10.py -- apply out/engine-and-pump-v10.blend reports/astra-controller-v10.json <v9 sha256>` | 0 |
| 4 | `blender --background -t 4 out/engine-and-pump-v10.blend --python tools/astra_controller_v10.py -- verify reports/astra-baseline-v9.json reports/astra-controller-verify-v10.json` | 0 |

Negative controls (assertions do fail the command): wrong source hash → **exit 1, no file written**;
unmodified v9 verified → **exit 1** (`controller_group_moved 0/3`).

## Hashes / sizes

* v9 in: `09326d83af1a4bfafbe46572194c965b73de937e8e73814fd974c9824e5245a6`, 102,845,766 B, mtime 2026-09-18 04:17:56 — **byte-identical after the run**
* v10 out: `5f8632d8ef9b27da15b221f47feb9fb37dcea7b52493aeba62125523ae5f5e6f`, 102,843,862 B
* `source/PP108C24-EO1_THD_TMVP.step` `b41a55cf…` — never opened

## Datums measured from v9 (nothing assumed)

* skid bottom **Z = −972.342 mm** = scene min Z (handoff −972.3) ✔
* engine-side face of `LBU-PP.001`: normal **(0, −0.998647, +0.052010)**, centroid **(−729.757, −233.749, 637.240) mm**, area 272,255 mm², 30 faces; **87.019° from Z = 2.981° off vertical**; vertex-envelope cross-check 2.934° (292.1 mm → 167.1 mm over Z −483.4…1955.7)
* side chosen by geometry: `dot(normal, upright→engine-centroid)` = **+0.630 for −Y** vs negative for +Y
* mating part **derived from geometry** (face antiparallel to the upright taper) = **`PP-CPM-1005`**, normal (0, +0.998630, −0.052336) — **0.0177° off antiparallel ⇒ already mated; no rotation, nothing cut**. Near-misses `MSP-CP-CP750E`, `PP-CPM-1001` were normal `(0,1,0)` flats, correctly rejected.
* bracket bottom before = **+263.977 mm = 48.67 in** above skid bottom

## Moved (rigid pure translation)

Subtree of empty `CPM-PP-JD18`, which equals collection `CAD_controller`:
`MSP-CP-CP750E`, `PP-CPM-1001`, `PP-CPM-1005`.

**Δ = (−105.208, −94.638, −17.119) mm** (handoff predicted ≈ −105 / −94 / −17 ✔).

| object | bbox before (mm) | bbox after (mm) |
|---|---|---|
| MSP-CP-CP750E | X[−831.8,−606.5] Y[−541.0,−264.8] Z[214.6,518.3] | X[−937.0,−711.7] Y[−635.7,−359.5] Z[197.5,501.2] |
| PP-CPM-1001 | X[−724.2,−614.1] Y[−482.7,−222.4] Z[222.2,441.9] | X[−829.4,−719.3] Y[−577.3,−317.0] Z[205.1,424.8] |
| PP-CPM-1005 | X[−633.6,−607.7] Y[−273.2,−150.1] Z[264.0,442.5] | X[−738.8,−712.9] Y[−367.8,−244.7] Z[246.9,425.4] |

World matrices (row 3 = translation, before → after): MSP-CP-CP750E
(−0.646043, −0.398869, 0.381132) → (−0.751251, −0.493506, 0.364013); PP-CPM-1001
(−0.620400, −0.374754, 0.228575) → (−0.725608, −0.469392, 0.211456); PP-CPM-1005
(−0.614050, −1.277133, −0.673747) → (−0.719258, −1.371771, −0.690866). Rotation blocks identical.

## Post-conditions

* mating face gap after **0.0001 mm**; −Nu·Nb = **0.99999995** (0.0177°)
* bracket bottom **246.858 mm = 48.0000 in** above measured skid bottom
* X align residual **0.0001 mm**; no penetration (gap ≥ 0)
* moved rigidly (max matrix deviation 3e-8); **mesh hashes identical** ⇒ geometry not cut
* invariants: **465 non-target objects** bit-identical world matrices **and** identical mesh hashes (pump 435, engine 7, skid 14, bale 9); intentional engine/pump Y overlap untouched
* **quarantine: ABSENT in v9** — no duplicate engine, nothing removed

## Discrepancies vs handoff

1. **`CAD_QUARANTINE_outliers` does not exist in v9** (handoff §5 expects a duplicate engine). Reported, no action needed.
2. Taper 2.981° vs handoff 2.87° (87.13° from Z) — 0.11°; envelope 2.934°. Both measured, consistent.
3. Everything else matches handoff: 468 mesh objects, **3,387,117 polygons**, scene bounds, pump bbox X[−489,918] Y[266,1363] Z[−364,842], engine bbox, v9 mtime 04:17.

## Observations (bbox level, for owner review — not acceptance)

* Post-move controller bbox X[−937.0,−711.7] Y[−635.7,−244.7] Z[197.5,501.2] mm. Panel centre X −824.3 sits 85 mm outboard of the upright centre (−739.0) because the bracket↔panel offset is fixed; the **bracket** itself lands well inside the 272,255 mm² target face.
* Controller bbox overlaps the engine bbox; the engine bbox already contains the bale uprights, so this is a bbox observation, not a collision finding.
* Pump model number (PP108C24 vs PP128S22, handoff §1.1) and livery remain open — untouched.

## Artifacts

`tools/astra_controller_v10.py` 27,294 B · `out/engine-and-pump-v10.blend` 102,843,862 B ·
`reports/astra-controller-v10.json` 16,649 B · `reports/astra-baseline-v9.json` 169,988 B ·
logs `reports/astra-controller-{baseline,measure,apply,verify-v9,verify-v10,neg1}.log` ·
negative-control report `reports/astra-controller-negtest.json`.
No v9 file, existing report, existing script, or original blend was written.

