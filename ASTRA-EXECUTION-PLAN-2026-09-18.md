# Engine/pump scene continuation

User request: read the September 18 handoff and begin; delegate execution to DeepSeek v4.1-Flash and GLM-5.3-Flash using parallel workers. Astra owns planning and high-level review.

## Deliverable

A verified controller relocation saved as a new v10 scene, followed by a grounded Pioneer green/blue studio preview and controller detail. Engine painted castings use John Deere green. See ASTRA-LIVERY-DIRECTION-2026-09-18.md for the owner's updated palette. Preserve the manually accepted v9 pump placement. This is a reviewable local result; visual acceptance remains with Mark.

## Ownership and sequence

1. DeepSeek `deepseek/deepseek-flash`: inspect v9, record baseline and source hash, implement and run controller placement, prove non-target invariance, save new v10 and evidence.
2. GLM `zai/glm-5.3-flash`, parallel: read rendering handoffs/materials, implement local preview script and material mapping. Wait before loading Blender.
3. Fresh-context cross-family review: inspect the other worker's implementation and evidence; require concrete fixes for failures.
4. Render execution after scene validation: one Blender process, bounded CPU/memory use, sequential views. Astra inspects outputs and decides whether corrections are required.

## Constraints

- Immutable v9 and source CAD; no changes to pipeline repositories or the current scene-prep worktree.
- No pump repositioning, flange corrections, generated adapter, or reopening v9 acceptance.
- Controller/bracket placement derives from measured v9 datums: negative-X upright, engine-side face, 48 inches above measured skid bottom.
- Pioneer RAL 6002 and PMS 293 / Process Blue replace the initial MSP assumption per Mark's live direction. Use PMS 293 pending clarification between the two distinct blues. PP108C24 identity remains a user decision before publication.
- No cloud dispatch, publishing, commits, global routing changes, or owner-acceptance flag changes.
- Verify requested/resolved provider models using proxy request records; CLI-requested model strings alone are insufficient proof.

## Acceptance checks

Source hash unchanged; only intended controller assembly moved; bracket target height and mating face measured; all pump/engine/skid/bale transforms and mesh data invariant; output scene reloads; rendered artifact exists, camera shows full machine, controller detail is legible, contact shadow visible; report numerical verification separately from visual judgment.
