# Fresh-context code review — controller v9 → v10 (DeepSeek Flash)

**Verdict: SHIP** for the controller relocation artifact. No blockers found.
Cross-family rendering review: **UNAVAILABLE** (render leg never ran — see §5).
Reviewer is same family as the controller author (limitation, §4).

## 1. Independently reproduced (read-only, this session)

| item | value | how |
|---|---|---|
| `out/engine-and-pump-v9.blend` | sha256 `09326d83af1a4bfafbe46572194c965b73de937e8e73814fd974c9824e5245a6`, 102,845,766 B, mtime 2026-09-18 04:17:56 | `sha256sum`, `stat` |
| `out/engine-and-pump-v10.blend` | sha256 `5f8632d8ef9b27da15b221f47feb9fb37dcea7b52493aeba62125523ae5f5e6f`, 102,843,862 B | `sha256sum` |
| `reports/astra-controller-v10.json` | verdict PASS, **45 assertions, 0 fails** | parsed |
| `tools/astra_controller_v10.py` | sha256 `fe544d7156cff00c9b240ac0f099cce15cb457252bf148c2090299ca171c4d4d` | `sha256sum` |

Hashes match the worker's claims exactly. Blender 5.1.1. Logs
`reports/astra-controller-{baseline,measure,apply,verify-v9,verify-v10,neg1}.log`
corroborate exit behaviour.

## 2. Invariants verified in code *and* in logs

* **v9 immutability** — pre-hash `astra_controller_v10.py:393`, post-hash `:497`;
  sha256 identical before/after (also asserted `:498`). Sources/configs untouched.
* **New-file-only guard** — `:394` output ≠ source, `:395` rejects any `-v9` basename.
* **Rigid, non-destructive move** — transform applied only to root empty
  `CPM-PP-JD18` `:397-399`; every child re-checked as `T @ before` (`:407-415`) and
  mesh digest identical (`:413-415`) ⇒ no cutting, no vertex edits.
* **Non-target invariance** — `:451-471`, bit-identical world matrices *and* mesh
  hashes for pump 435 / engine 7 / skid 14 / bale 9 / all-non-target 465.
  Intentional engine↔pump Y overlap explicitly re-asserted untouched `:468-471`.
* **Fail-fast** — `check()` raises; wrapper `:580-595` writes the JSON report and
  `os._exit(1)`. Negative controls are genuine: `verify-v9` exited 1 on
  `controller_group_moved 0/3`; `neg1` exited 1 on `source_hash_matches_expected`
  (and wrote no output blend).

## 3. Plane fit / transform mathematics

* `face_groups()` `:93-116` transforms normals with the inverse-transpose (correct
  for non-uniform/affine matrices) and area-weights both centroid and normal.
  Normal keys rounded to 0.01 (≈0.57°) — the 2.98° taper separates cleanly from
  the 0° flats (confirmed by the near-miss list in the measure log).
* Taper **2.981°** from face normals is independently cross-checked against a
  *normal-independent* vertex-envelope estimate **2.934°** (`:297-300`, `:171-183`)
  — a real triangulation, not a single-source claim.
* Engine side is chosen by geometry — `dot(normal, upright→engine-centroid)` =
  **+0.630** for −Y vs negative for +Y (`:265`, `:283-286`).
* Mating partner is derived, not hard-coded: `PP-CPM-1005` face is **0.0177°** off
  antiparallel (`:326-346`); the `MSP-CP-CP750E` (0,1,0) flats at ~2.98° are
  correctly rejected. Nothing was rotated or cut.
* Pure-translation decomposition (`:357-365`): perpendicular closure `d1` along
  `Nu`, in-plane slide `d2 = t·S` with `S` verified orthogonal-to-`Nu` and
  near-vertical (`:360`), then X alignment `d3`. Arithmetic re-derived by hand
  from `gap 93.619`, `brk_bottom 263.977` → `t = −22.018` ✓.
* Post-conditions: mating gap **0.0001 mm**, X residual **0.0001 mm**,
  bracket bottom **48.0000 in** above the measured skid bottom (skid bottom ==
  scene min Z asserted at 1e-6 m, `:252`). Δ = (−105.208, −94.638, −17.119) mm,
  matching the handoff's ≈(−105, −94, −17).

## 4. Caveats (non-blocking) and limitations

1. **Same-family limitation** — the controller author is DeepSeek, as is this
   reviewer; this is a code/evidence audit, *not* an independent implementation
   review. The separate GLM verifier's reload checks cover that gap.
2. **Tolerances expressed as `0.5 * 0.001` m** (`:426`, `:432`, `:437`) = 0.5 mm,
   i.e. 48 in ± 0.5 mm. Correct but loose relative to the 0.0001 mm achieved.
3. **`verify_main` (`:507-570`) never hashes the blend it verifies** — a stale or
   renamed file at the given path could still verify. The independent GLM reload
   check is the mitigation.
4. **Quarantine accounting** — deletion happens at `:473-485` *after* `all_mesh`
   was captured at `:219`, so `invariant_summary.untouched_mesh_objects` (`:488`)
   would overstate the output count if a quarantine existed. Not exercised:
   quarantine is absent in v9 (handoff §5 expects one — worker reported the
   discrepancy correctly).
5. **Placement choice, not error** — X centring uses the area-weighted centroid of
   the whole 30-face upright face; the panel centre lands ~85 mm outboard of the
   upright centre. Bracket↔panel offset is fixed, so this is a design question for
   owner visual acceptance.
6. Controller bbox overlaps the engine bbox; the bale uprights already sit inside
   the engine bbox, so this is expected bbox overlap, not evidence of a clash.
   Mesh-level interference was not assessed here.

## 5. Rendering leg — corrected: worker recovered, preview reviewed and rendered

**Correction, 2026-09-18 (DeepSeek Flash render leg).** The claim that the GLM
render worker "never produced a script or artifact" is **stale and wrong**.
The initial failure was real but was an authentication error, not an abandonment:
`astra-render-worker-output.json` records `terminal_reason: api_error`,
`result: "Not logged in · Please run /login"` for `zai/glm-5.3-flash`, and the
retry recovered — `astra-render-worker-pioneer.json` records
`terminal_reason: completed` for the same model, and the worker then produced
`tools/astra_render_preview.py`, `reports/astra-render-plan.md` and
`reports/astra-preview-materials.json`. What remained true at the time was only
that **Blender was never invoked** during that preparation phase (the Blender
slot was held by the independent verifier), so no image existed and no visual
claim had been made. The one-line cross-family status in this report's header
therefore predates this correction; the historical wording is preserved below.

Cross-family review and execution of the render leg has since been carried out
(GLM-authored script reviewed and repaired by a different model family,
DeepSeek Flash) and is evidenced in `reports/astra-render-execution.md`,
`reports/astra-preview-render.log` and `reports/astra-preview/*.png`. Defects
found and fixed there: an undefined `COLL_PUMP_NEW` crash, blanket overwriting
of all engine/pump vendor material slots, hand-guessed camera framing that did
not guarantee the whole machine was in shot, no saved look-dev `.blend`, and no
source-hash / geometry-invariance proof. Camera bounds, grounding, output paths,
library reuse and recolouring were all reviewed. Residual limitation: the render
reviewer is DeepSeek, the same family as the author of this report, so this is a
cross-family review of the *script* (GLM), not of the reviewer's own report.

Historical limitation wording, as recorded at review time:

> `tools/astra_render_preview.py` **does not exist**; `reports/astra-render-plan.md`
> and `reports/astra-preview/` are absent. `astra-render-worker-output.json` shows
> `terminal_reason: api_error`, `result: "Not logged in · Please run /login"` for
> `zai/glm-5.3-flash` — the GLM render worker never produced a script or artifact.
> Per spec this was not waited on. There is therefore **no cross-family review of
> camera bounds, grounding/contact shadow, output paths, library reuse, or
> recolouring**; no asset was reviewed for unsafe geometry changes because none
> exists. This blocks the preview deliverable, not the v10 scene.
