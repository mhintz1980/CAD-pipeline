# Astra preview render - execution and evidence (2026-09-18)

Author: DeepSeek Flash (render worker). Cross-family review and execution of the
GLM-authored preview script.

**Status: rendered final artifacts exist and pass every recorded check.**
**Owner visual acceptance is NOT claimed and remains pending.**

Source of truth for the run: `out/engine-and-pump-v10.blend`
sha256 `5f8632d8ef9b27da15b221f47feb9fb37dcea7b52493aeba62125523ae5f5e6f`
- the exact blend that contains both the pump and the engine, unchanged on disk
before and after this work.

---

## 1. Blocking defect found and fixed: the pump could never render

Astra's review (`ASTRA-PUMP-VISIBILITY-REVIEW-2026-09-18.md`) reported that the
primary image showed an empty deck and the engine flywheel, with the entire
Vogelsang pump absent. That report is correct and this worker's earlier
camera-only hypothesis was **insufficient and wrong**: no camera angle could have
shown the pump, because the pump was never reaching a camera ray.

**Root cause, measured on the source (not inferred from the mesh census):**

| snapshot of `out/engine-and-pump-v10.blend` | value |
|---|---|
| `bpy.data.collections['CAD_pump_new'].hide_render` | **True** |
| `CAD_pump_new.hide_viewport` | False |
| layer-collection `CAD_pump_new` exclude / hide_viewport | False / False |
| `CAD_pump_new` mesh objects | 415 (416 objects) |
| objects with `hide_render` True | **0** |
| objects with `visible_camera` False | **0** |
| objects missing from the active view layer | **0** |
| objects with an empty evaluated mesh | **0** |

Exactly one flag suppresses the pump: the **collection-level `hide_render`**.
Every object-level signal was clean, which is precisely why a 415-mesh inventory,
a material-slot count and a geometry digest all passed while the pump contributed
nothing - those measures prove an object *exists*, not that it *renders*.
`CAD_skid`, `CAD_pump`, `CAD_bale`, `CAD_engine` and `CAD_controller` all have
`hide_render = False`; `CAD_pump_new` is the only suppressed collection.
Material alpha is not a factor: all 41 pump materials are opaque
(`Alpha = 1.0`, `Base Color` alpha `1.0`, `Transmission Weight = 0.0`).

**Correction** (in-memory preview only, `ensure_render_visibility()` in
`tools/astra_render_preview.py`): the source's suppression flags are snapshotted,
then cleared at collection, layer-collection and object level. Recorded change:

```
collection:CAD_pump_new  before[hide_render,hide_viewport]=[True, False]
                         after [hide_render,hide_viewport]=[False, False]
```

Nothing geometric happens: no reimport, no rebuild, no transform, no source
write. The difference is saved only into the new look-dev `.blend`. This is the
only deliberate divergence from the source scene.

**Verification that the pump now genuinely participates in camera rays**
(`verify_render_participation()`, asserted before rendering - the script exits
non-zero if it fails):

- 415/415 pump meshes renderable, all in the active view layer, all with
  non-empty evaluated meshes;
- 24 rays cast from the actual primary hero camera through the centres of the 24
  largest pump meshes: **24/24 hit `CAD_pump_new` objects** (12 distinct meshes);
- visible in the images: the Vogelsang pump body - suction port, discharge elbow
  and flange - sits on the blue tray at the machine's +Y end, foreground of the
  primary hero.

## 2. Second defect: flat background, floating machine

The warm-up showed a flat grey field with no contact shadow. Measured cause: the
background equalled the **world** colour, not the floor - the display ratio
between two world-strength settings (0.55 vs 0.38) matched the AgX-compressed
expectation exactly (1.213), so no floor was in frame at all.

Corrections:

- the plane born from `bpy.ops.mesh.primitive_plane_add` never rendered; it is now
  built from an explicit mesh datablock and linked straight into the scene
  collection (178.3 m plane at z = -0.9743 m, i.e. 2 mm below the measured skid
  bottom -0.9723 m);
- real **opaque, rough, neutral diffuse** floor (`ASTRA_Studio_Floor` `#63666A`,
  roughness 0.92) - deliberately **not** a shadow catcher, per the review;
- the large area key light (soft, penumbra-washed) was replaced by a 5 degree
  **SUN** key so a defined contact shadow forms under the skid supports; fill
  300 to 200, rim 500 to 450; world strength 0.55 to 0.38;
- the floor is excluded from the camera-fit bounds and from the geometry digest;
- a downward ray probe from above the machine verifies the floor is really in the
  render view layer (`floor_probe_hit = GroundFloor`, asserted before rendering).

## 3. Third defect: skid deck misclassified as pump green

The warm-up painted the whole tray deck RAL 6002. Structural roles were derived
from `reports/astra-baseline-v9.json`: `CAD_pump` holds the frame-tray parts
(PP-FTT top tray 1.83 x 4.27 m plates, PP-FTS side/cross members, PP128-FTA end
rails, PP-FBS bottom supports) - these are painted **structure under the
machine**, not pump casing, so they take PMS 293 like the skid. Genuinely
pump-specific mounting brackets (`PP128S22-MFB`, matched by `mfb`/`mount`) stay
RAL 6002. Blue assignments rose 23 to 39 objects, pump green 405 to 389.

## 4. Cameras

- **Primary pump-side hero** - `Cam_PumpHero`, direction `(-0.40, 0.84, 0.45)`
  (minus-X, plus-Y, above), 50 mm, bounding-box fit at 0.92 margin, distance
  12.23 m. The pump is the nearest, largest subject; the John Deere engine stays
  legible beyond it along the skid's Y axis. Complete machine bounds in frame.
- **Secondary engine-side view** - `Cam_EngineHero`, direction `(-0.72, -0.52,
  0.46)`, 11.33 m: shows the engine with its radiator and the blue skid/bale.
  Kept as an additional view.
- **Controller detail** - `Cam_Controller`, 85 mm, 1.80 m, frames `CAD_controller`
  (X -0.937..-0.712, Y -0.636..-0.245, Z 0.198..0.501 m); display and keypad
  legible.

Shot-list changes were made only after the visibility root cause was fixed; no
further camera exploration is pending.

## 5. Exact command, exit status and timings

```
cd C:/Projects/CAD/astra-engine-pump
"C:/Program Files/Blender Foundation/Blender 5.1/blender.exe" --background --factory-startup \
  --python tools/astra_render_preview.py -- \
  --input out/engine-and-pump-v10.blend --output-dir reports/astra-preview \
  --width 1200 --samples 48 --threads 4 --with-controller-detail \
  --save-blend reports/astra-preview/astra-preview-v10-lookdev.blend
```

Blender 5.1.1 (hash b70da489d7f4). **EXIT = 0**, clean quit, no crash.
Single process, sequential frames, one geometry import.

| stage | seconds |
|---|---|
| open v10 | 1.4 |
| three-quarter hero (1200x840, 48 spp) | 51.7 |
| engine-side view | 63.9 |
| controller detail | 98.8 |
| **total** | **221.2** |

Log: `reports/astra-preview/astra-preview-render.log` (Blender + script output,
`EXIT=0`).

## 6. Achieved checks

| check | result |
|---|---|
| source v10 sha256 before == after | `5f8632d8...e5f5e6f` - unchanged |
| source v9 sha256 (untouched) | `09326d83...4e5245a6` - unchanged |
| geometry digest before == after | `235b40f2...2bfafc54` - unchanged |
| pump meshes renderable | 415 / 415 |
| camera-ray hits on pump from hero | 24 / 24 sampled rays |
| floor in render view layer | `GroundFloor` at z -0.9743 m, asserted |
| images load, nontrivial variation | 1200x840 RGBA, 248-256 distinct levels, sigma 0.127-0.158 |
| look-dev `.blend` written | 102,652,025 B, active camera `Cam_PumpHero` |
| helper objects excluded from fit/digest | floor, lights, cameras |

Artifacts (all under `C:/Projects/CAD/astra-engine-pump/`):

| artifact | sha256 | bytes |
|---|---|---|
| `reports/astra-preview/astra-preview-threequarter.png` | `1af217b4cb6739b47de5473e3e21dbaa88c3677223e9abd5dcb77a0c01a4ac6d` | 1,188,604 |
| `reports/astra-preview/astra-preview-engine-side.png` | `be47d244132ae77e09694e6473f97d4ab2c503e765a2438dea33e301973743b5` | 1,237,456 |
| `reports/astra-preview/astra-preview-controller-detail.png` | `76140328d3ab5322396e4b682c4f1c5d8404d3e678f0659162cd64b639bb73df` | 1,295,473 |
| `reports/astra-preview/astra-preview-v10-lookdev.blend` | `339f200da7bc91fb7626967e501734ad2df77547ca62887dc9d11e8ebd31bc6e` | 102,652,025 |
| `tools/astra_render_preview.py` | `1c574bf538192471aee1a7cb71ab58feed0f0fb8774eb1b1ec8a0d94b99fb889` | - |
| `reports/astra-preview/astra-render-execution.json` | machine-readable run record | 122,641 |
| `reports/astra-preview/astra-preview-slot-inventory.json` | per-slot vendor colour to assigned role, with face counts | 118,376 |

## 7. Script changes made by this worker

1. `ensure_render_visibility()` - snapshot and clear the pump's collection-level
   render suppression; report the change (new).
2. `verify_render_participation()` - assert 415/415 renderable, all in the active
   view layer, non-empty evaluated meshes, and camera rays hitting the pump
   (new; hard failure otherwise).
3. `probe_floor()` - ray-probe proving the floor is in the render view layer
   (new; hard failure otherwise).
4. Floor rebuilt as an explicit mesh linked to the scene collection (replacing
   `primitive_plane_add`, which did not render); opaque diffuse `#63666A` at 0.92
   roughness, 2 mm clearance below the skid bottom.
5. Lighting: 5 degree SUN key (energy 2.0) instead of a large soft area key;
   fill/rim reduced; world strength 0.55 to 0.38.
6. Tray/structure role split: `CAD_pump` frame-tray parts to PMS 293, pump mount
   brackets (`mfb`/`mount`) to RAL 6002.
7. Cameras reframed (pump-side primary hero; engine-side secondary; controller
   detail) and fit margin 0.90 to 0.92.
8. `grounding`, `source_visibility_fix` and `pump_render_participation` blocks
   added to `astra-render-execution.json`.
9. Earlier fixes retained: undefined `COLL_PUMP_NEW` crash, per-slot engine/pump
   classification instead of blanket overwrite, bounding-box camera fitting,
   source-hash and geometry-invariance proofs.

## 8. Unresolved limitations (honest)

1. **The source scene ships a suppressed pump.** `CAD_pump_new.hide_render = True`
   is a property of `out/engine-and-pump-v10.blend` itself. The preview corrects
   it in memory; if anyone renders v10 from the UI or via another tool without
   this step, the pump will be absent again. This needs a source-side decision by
   the scene owner - the preview must not rewrite the source, so it is reported,
   not fixed.
2. **This worker's earlier camera-only diagnosis was wrong.** It delayed the
   correct fix. The lesson is recorded here: inventory counts and digests do not
   establish render participation, and the audit that did (collection flags) was
   only run after the visual report.
3. **Same-family limitation.** The script was authored by GLM; the review and
   execution above are DeepSeek Flash. That is a cross-family review of the
   *script*, but the worker's own report is not independently reviewed.
4. **Colour swatches are digital approximations**, not certified physical paint
   matches. PMS 293 vs Pantone Process Blue is still unresolved with the owner;
   PMS 293 `#003DA5` is used for this preview. Process Blue's documented
   approximation is `#0085CA` (the earlier `#0057B8` example was invalid).
5. **Pump fasteners remain RAL 6002** where the mesh name is a numeric Onshape ID
   and cannot be text-matched to a hardware pattern.
6. **No mask/depth passes, no compositing, no text overlays or branding** - out
   of scope by instruction.
7. **No mechanical interference assessment**; this is a visual preview only.
8. **Contact shadow is a studio setup**, not a measured photometric match; the
   floor albedo/roughness are aesthetic choices.
9. **Owner visual acceptance is pending.** The pump is now visible and
   identifiable; whether the livery and framing are accepted is Mark's call.

## 9. Warm-up diagnostics

`reports/astra-preview/_warmup/` is retained as evidence, not as a deliverable:
`warmup*.log` (1-13), the diagnostic scripts (`audit_vis.py`, `probe_proj.py`,
`ortho_views.py`, `layout.py`), the orthographic layout views, hero-angle
candidate montages, and the post-fix warm-up (`warmup12.log`/`warmup13.log`) that
first showed the real pump before the final full-resolution render was allowed to
proceed. The full-resolution images in `reports/astra-preview/` supersede all
warm-up images.

## 10. Cross-family review verdict

The GLM-authored script was reviewed and repaired by DeepSeek Flash (different
family), and every defect listed above was found by measurement, not assumption.
The visibility defect was found by the owner's visual inspection, not by this
worker - that is a failure of this worker's verification order and is reported as
such in section 8.2. With the pump verified present in camera rays and visible in
the primary image, the render leg is **executed and evidence-backed**; visual
acceptance remains with the owner.
