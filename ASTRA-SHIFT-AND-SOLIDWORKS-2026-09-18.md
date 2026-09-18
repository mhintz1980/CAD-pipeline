# Shift the payload 12 in toward the pump end, and fix the SolidWorks import

**Written 2026-09-18.** Two owner requests, one document. Nothing here has been
*run* — there is no Blender and no `.blend` in the session this was written in
(`out/` and `*.blend` are gitignored, and the scenes live only on
`C:\Projects\CAD\astra-engine-pump\`). Both scripts compile; both need a run on
Mark's machine or on Modal. Labels follow the house convention: **PROVEN**
(measured), **DERIVED** (computed from measured values), **OPEN**.

---

## 1. Shift everything on the skid 12 in toward the pump end

> *"shift everything on top of the skid — the engine, the pump, and both tables
> they sit on, the mounts — toward the pump's end of the skid by approximately
> 12 inches."*

`tools/astra_shift_topside_v12.py` — **COMPILE_OK**, never run.

### 1.1 Direction and distance — **DERIVED**

12 in = **304.8 mm**, along world **+Y**.

+Y is the pump end, cross-checked two ways:

- Pump bbox `Y[266, 1363]`, engine bbox `Y[−1762, 522]` (handoff §1.5, **PROVEN**).
- The pump's drive shaft enters the engine's **flywheel** housing, and that
  overlap sits at `Y ≈ 266…522` — the engine's +Y end. The radiator is at −Y.

### 1.2 The partition — **DERIVED from measured bboxes**

468 meshes split 426 / 42.

**Moves (426)** — the payload:

| set | n | what |
|---|---|---|
| `CAD_engine` | 7 | vendor engine, `PP12-EM-JD18` engine mount, `EM-SP` ×4 — **the mounts** |
| `CAD_pump_new` | 415 | the Vogelsang PP108C24 — **the pump** |
| `DOUBLER`, `DOUBLER.001` | 2 | transverse plates under the engine mount — **the engine's table** |
| `PLT-MNT-6SL-PE-PP12`, `MNT-PEB-CTF-PP12-WIDE` | 2 | base plate + pedestal under the pump — **the pump's table** |

**Stays (42)** — the skid and what is welded to it: the other 10 `CAD_skid`
members (base channels, rectangular tubes, both end caps), all 20 `CAD_pump`
deck parts (`PP-FTT` top and bottom plates, `PP-FTS` webs, the `PP-FBS` /
`PP128S22-MFB` / `PP128-FTA` perimeter), all 9 `CAD_bale`, all 3 `CAD_controller`.

> **OPEN — please confirm "both tables".** `DOUBLER` ×2 and the
> `PLT-MNT` / `MNT-PEB` pair are the two *separate* sub-frames, one under each
> machine, so they are what the phrase most naturally means. The alternative
> reading is the shared deck plate `PP-FTT` — but that is one table spanning the
> whole skid, not two, and moving it would move the skid's own top surface.
> **Run `--dry` first**: it prints the exact partition and every measurement
> without touching or saving anything.

### 1.3 Method — why this one is safe

Rigid translation of **object transforms only**. No vertex is touched, so all
468 mesh datablocks keep a **bit-identical geometry hash** — "engine and pump
geometry unchanged" is proven, not asserted. Only the roots of the moved forest
are translated and children inherit, which is the fix for handoff §0.3 (setting
`matrix_world` on every object under a glTF root double-applies the transform).

Hard guards, any of which aborts before saving:

- collection census must be exactly `{pump_new 415, engine 7, pump 20, skid 14, bale 9, controller 3}`
- the partition must be total and disjoint, and every named skid part must exist
- no **fixed** object may be parented under a **moved** one (it would be dragged along)
- every moved bbox must have moved by exactly `(0, +304.8, 0)` mm within 0.01 mm
- every fixed bbox must not have moved at all (1e-4 mm)
- every mesh hash must be unchanged
- it refuses to overwrite an existing scene file

### 1.4 Two consequences you should decide on before this ships

**a. The deck's hole pattern does not move. — DERIVED**

Both tables are fastened to `PP-FTT` at fixed positions. Sliding them 304.8 mm
along Y leaves the deck's existing holes orphaned and the tables landing on blank
plate. The script reports the before/after footprint and whether the new one is
still over the deck; it **cannot re-cut holes**. Someone has to, in CAD.

**b. The lifting bale does not move, so the package will hang further out of
level. — DERIVED, and this is the one worth a hard look**

The bale is the lifting point and its axis is at **Y ≈ 0**. It is explicitly in
the "stays" set, because you did not list it. Moving the heaviest thing on the
skid 304.8 mm toward one end moves the payload's centroid the same 304.8 mm off
the lift axis. The script reports the shift using a *triangle-area-weighted
surface centroid* — a *geometric proxy only*. It is **not** a mass CG: it weights
every square millimetre of surface equally and knows nothing about wall
thickness, density, or the parts the model does not carry (coolant, fuel, the
splined drive adapter, guarding).

**A real lift check needs part masses, which this model does not have.** If the
package is meant to stay level on a single-point lift, the bale probably has to
follow the payload — say the word and it is a two-line change to the partition.

### 1.5 Predicted geometry — **DERIVED, to be confirmed by the run**

Using the v9-era measured bounds (v11 widened X only, so Y is unchanged):

| | before | after +304.8 |
|---|---|---|
| payload Y span | −1762 … 1363 | −1457 … 1668 |
| clearance to the −Y (radiator) end of the skid | 610 mm | **915 mm** |
| clearance to the +Y (pump) end of the skid | 1009 mm | **704 mm** |

So the shift roughly balances the two end margins. Nothing overhangs; both
tables stay well inside the deck's `Y[−2130, 2137]`.

**Bale clearance must be re-measured, not assumed.** The +152.4 mm widening in
v11 was done because the engine crowded the uprights; a Y shift slides a
*different* engine cross-section past them, and that can go either way. The
script measures it before and after via BVH.

### 1.6 Run it

```bat
cd C:\Projects\CAD\astra-engine-pump
set BL="C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"

REM 1. dry run: prints the partition and every measurement, changes nothing
%BL% -b -noaudio --threads 4 ^
  reports\astra-modal-wide\wide-20260918T143014\blends\engine-and-pump-v11-wide.blend ^
  --python-exit-code 1 --python tools\astra_shift_topside_v12.py -- ^
  --out-json reports\astra-shift-v12-dry.json --dry

REM 2. after you have agreed the partition
%BL% -b -noaudio --threads 4 ^
  reports\astra-modal-wide\wide-20260918T143014\blends\engine-and-pump-v11-wide.blend ^
  --python-exit-code 1 --python tools\astra_shift_topside_v12.py -- ^
  --out-json reports\astra-shift-v12.json ^
  --save-blend out\engine-and-pump-v12-shift.blend --dy-mm 304.8
```

`--dy-mm` is the whole knob — "approximately 12 inches" is easy to retune.
v11-wide is never written to.

---

## 2. Make the engine look right in SolidWorks

Full diagnosis and the import steps: **`docs/solidworks-import.md`**.
Exporter: `tools/astra_engine_solidworks.py` — **COMPILE_OK**, never run.

### 2.1 What is wrong — **PROVEN from the rev4 readback**

The rev4 STL is a *correct* STL. The problem is what SolidWorks does with it.

1. **SolidWorks' default mesh import builds one BREP face per facet, capped at
   500,000. Our file has 499,998** — two under. So SolidWorks does not refuse it;
   it accepts it and tries to knit half a million faces.
2. **It is not watertight**: 203,241 boundary edges, 4,147 non-manifold edges,
   4,275 shells. Blender renders open meshes happily; a BREP knit cannot close
   them. A solid was never available from this file.
3. **STL carries no units.** Ours is mm. On the wrong dropdown it arrives 25.4×
   large.
4. **STL carries no colour**, so it is always grey — nothing like the Blender
   images.
5. The big casting was decimated 2,274,714 → 497,810 (sampled max dev 1.55 mm).
   Blender's smooth shading hides that; SolidWorks flat-shades every facet.
6. Z-up vs SolidWorks' Y-up views.

### 2.2 The fix

**Export OBJ and import it as a Graphics Body.** SolidWorks' documentation is
explicit: importing a mesh as a *graphics body* brings in per-vertex colour,
per-facet colour, decals, textures and transparency — as a *Mesh BREP*, only
transparency survives. That is the only route that reproduces the Blender look.

`tools/astra_engine_solidworks.py` emits, from the live scene:

- `engine-colour-mm.obj` + `.mtl` — coloured, for Graphics Body import
- `engine-graphics-mm.stl` — single STL held to `--facet-budget` (default
  **450,000**, deliberately clear of the 500,000 cliff)
- `bodies/*.stl` — one per engine body, so SolidWorks shows **7 selectable
  bodies** instead of one undifferentiated shell
- `README.md`, `MANIFEST.sha256`, JSON report

`--no-decimate` gives the full 2.28 M triangles if the complaint is faceting;
`--up Y` writes Y-up.

If you need to *measure or mate* against the engine rather than look at it,
none of this helps — import the original STEP (`C:\Projects\Misc\3336180ci510.stp`,
451.8 MB AP214, with its 507 `COLOUR_RGB`). It is slow and heavy and it is the
only CAD-grade route. The trade-off table is in `docs/solidworks-import.md` §2.

### 2.3 **OPEN — the reference images did not arrive**

Your message said "here are images of what the STL looks like in Blender", but
no images came through on this end. Everything above is diagnosed from the
measured mesh statistics and SolidWorks' documentation, not from seeing the
symptom. The likeliest single cause is #1 (default Solid Body import). If what
you are actually seeing is *faceting*, the answer is `--no-decimate`; if it is
*grey*, it is the OBJ; if it is *huge*, it is the unit dropdown. Please re-send
the images, or just say which of those it looks like.

**Also still unverified:** no SolidWorks exists on any machine in this project
(registry and Program Files both checked), so no import round-trip has ever been
run. Every instruction is documented behaviour, not observed behaviour.

---

## 3. Files added

| path | what | state |
|---|---|---|
| `tools/astra_shift_topside_v12.py` | the 12 in payload shift, with invariance proofs | COMPILE_OK, never run |
| `tools/astra_engine_solidworks.py` | coloured OBJ + per-body STL export | COMPILE_OK, never run |
| `docs/solidworks-import.md` | why it looks wrong, five options, exact import steps | — |

Nothing under `out/`, no scene, and no source CAD was touched.
