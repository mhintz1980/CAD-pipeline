# Getting the engine to look right in SolidWorks

**Written 2026-09-18.** Covers `out/engine-solidworks-20260918/engine-detailed-mm.stl`
(499,998 triangles, 25.0 MB, binary, millimetres) and what to do instead.

> **The one-line answer.** An STL cannot carry colour, and SolidWorks' *default*
> STL import path tries to build one BREP face per triangle — 499,998 of them,
> two under its hard limit. Export **OBJ** and import it as a **Graphics Body**,
> and the engine arrives looking like the Blender render, colours included.

---

## 1. Why it looks wrong

Six things differ between Blender and SolidWorks. They are ranked by how much
damage each one does, and every claim is either measured from
`reports/astra-engine-final-readback.json` or cited from SolidWorks' own docs.

### 1.1 SolidWorks' default import path makes one face per triangle — **the big one**

SolidWorks' mesh import Options dialog offers **Solid Body / Surface Body /
Graphics Body**, plus a **Mesh body** checkbox:

| Option | What SolidWorks builds | Documented limit |
|---|---|---|
| Solid/Surface Body, **Mesh body unchecked** | standard BREP — **one face per facet** | **500,000 facets** |
| Solid/Surface Body, **Mesh body checked** | a mesh BREP body | warns above 5,000,000 |
| **Graphics Body** | display-only mesh | warns above 5,000,000; **imports fastest** |

Our detailed STL is **499,998 facets — two under the 500,000 ceiling.** So the
non-mesh path does not refuse the file; it *accepts* it and then tries to knit
half a million individual BREP faces. Expect SolidWorks to grind for a very long
time and hand back something it can barely redraw. That is not a file problem,
it is a path problem.

### 1.2 The mesh is not watertight, so a solid can never be knitted

Measured on the delivered file:

| | detailed | compact |
|---|---|---|
| boundary edges | **203,241** | 174,095 |
| non-manifold edges | 4,147 | 4,112 |
| separate shells | 4,275 | 4,342 |
| Euler χ | −10,538 | −10,422 |

Blender renders open, non-manifold meshes without complaint — that is why it
looks fine there. A BREP knit cannot close 203,241 open edges. Asking for a
Solid Body from this file is asking for something the geometry does not contain.
The open bores, ports and unmerged assembly interfaces are *intentional*; this
was always a graphics reference, never a healed solid.

### 1.3 STL carries no units

The STL format stores no unit. Our file is millimetres. If SolidWorks' import
**Unit** dropdown is on inches, the engine arrives **25.4× too large** — the
1.674 m wide engine becomes 42.5 m. Set the dropdown to **Millimeters**
explicitly; do not rely on whatever it remembered from last time.

### 1.4 STL carries no colour — and this is fixable

The Blender images are John Deere green castings, RAL 6002 and PMS 293. An STL
has no colour field at all, so SolidWorks will always show it grey.

SolidWorks reads the same mesh-import path for `.obj`, and its documentation is
explicit about what survives:

> When importing as a **graphics body**, per-vertex colouring, per-facet
> colouring, decals, textures and transparency are imported. If you import as a
> **Mesh BREP**, only transparency is imported.

**So: OBJ + Graphics Body is the only route that reproduces the Blender look.**
That is what `tools/astra_engine_solidworks.py` now produces.

### 1.5 The casting was decimated 4.6×, and SolidWorks flat-shades it

`COMPOUND.001` went from **2,274,714 → 497,810** triangles to hit the 25 MB
target. Sampled max deviation **1.55 mm**, mean 0.063 mm. Blender's smooth
shading interpolates normals across that and it reads as a smooth casting;
a SolidWorks graphics/mesh body is flat-shaded per facet, so every one of those
facets shows and the castings look chipped and low-poly.

If the complaint is "it looks faceted", the fix is **more triangles**, not
different import options — use `--no-decimate` (2.28 M triangles). That is still
under the 5,000,000 graphics-body warning, but it rules out the BREP path
permanently.

### 1.6 Z-up vs Y-up

The assembly is Z-up (Blender convention). SolidWorks' default view orientation
treats **Y** as up, so a Z-up import appears lying on its back in the standard
isometric. Harmless — rotate the view — but it is the first thing you notice.
Pass `--up Y` if you would rather the file matched SolidWorks' convention, at
the cost of no longer sharing a frame with the assembly and the STLs.

---

## 2. What to do — five options and their trade-offs

| | Route | Matches Blender? | Usable as CAD? | Cost |
|---|---|---|---|---|
| **A** | **Import the original STEP** — `C:\Projects\Misc\3336180ci510.stp` | **Best available.** True analytic surfaces, no faceting at all, and AP214 vendor colour (507 `COLOUR_RGB`, 74,092 styled items) | **Yes** — real BREP solids: measure, section, mate, reference | 451.8 MB AP214. Expect a long import and a heavy part. This is the expensive option, and the only one that yields CAD |
| **B** | **OBJ → Graphics Body** *(recommended for looks)* | **Yes** — colours, per-facet shading, transparency all survive | No. Display only: cannot measure, mate or section | Seconds. ~30 MB |
| **C** | STL → Graphics Body | Shape only, grey, faceted | No | Seconds |
| **D** | STL → Solid/Surface Body **with Mesh body ticked** | Shape only, grey, faceted | Partly — a mesh BREP can be sectioned and some measurements work | Minutes |
| **E** | STL → Solid/Surface Body, **Mesh body unticked** | — | — | **Don't.** This is the default, and it is what produces the result you are seeing (§1.1) |

**Recommendation.** If you want the engine to *look* like the Blender images
inside SolidWorks, take **B**. If you need to actually design against it —
measure a flange, locate a mounting boss, mate the splined adapter — take **A**
and accept the import time; nothing derived from a mesh will give you that.

There is no option that is both cheap and CAD-grade. That trade-off is inherent
to the source: the mesh was produced *from* the STEP for rendering, and the
information a solid needs was discarded at tessellation.

---

## 3. Exact import steps

**OBJ, coloured (option B):**

1. **File → Open** (*not* File → Import — SolidWorks has no such path for meshes).
2. File type: **Mesh Files (\*.stl; \*.obj; \*.off; \*.ply; \*.ply2)**.
3. Select `engine-colour-mm.obj`. Keep `engine-colour-mm.mtl` **in the same
   folder** — SolidWorks reads it from there; it is not embedded.
4. Click **Options…**
   - Import as: **Graphics Body**
   - Unit: **Millimeters**
   - Do **not** apply any extra scale.
5. **Open.**

**STL (options C / D):** identical, but at step 4 choose **Graphics Body** (C) or
**Solid Body** *with the **Mesh body** checkbox ticked* (D).

**STEP (option A):** File → Open, select the `.stp`, Options → import as solid
bodies. Give it time and RAM.

> **Unverified.** No SolidWorks installation exists on any machine in this
> project — the verifier checked the registry and Program Files and found none
> (`reports/astra-engine-final-readback-notes.md`). Every step above comes from
> SolidWorks' published documentation, not from a round-trip we ran. Please
> confirm on your machine and tell us what actually happened.

---

## 4. Producing the files

```bat
cd C:\Projects\CAD\astra-engine-pump

REM coloured OBJ + per-body STLs + a facet-budgeted single STL
"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" -b -noaudio ^
   out\engine-and-pump-v11-wide.blend --python-exit-code 1 ^
   --python tools\astra_engine_solidworks.py -- ^
   --out-dir out\engine-solidworks-rev5 ^
   --out-json reports\astra-engine-solidworks.json
```

Useful flags:

| flag | effect |
|---|---|
| `--no-decimate` | full 2.28 M triangles — removes the faceting of §1.5, rules out the BREP path |
| `--facet-budget N` | single-STL triangle ceiling (default **450,000**, deliberately clear of the 500,000 cliff) |
| `--up Y` | write Y-up instead of Z-up (§1.6) |
| `--no-obj` / `--no-per-body` | skip an output |

Outputs land in `--out-dir`:

```
engine-colour-mm.obj / .mtl    coloured, for Graphics Body import   <- option B
engine-graphics-mm.stl         single STL, <= --facet-budget facets <- option C/D
bodies/<name>-mm.stl           one STL per engine body (7 files)
README.md, MANIFEST.sha256, astra-engine-solidworks.json
```

### Why per-body STLs

An STL has no concept of a body, so the 25 MB file collapses all seven engine
bodies into one undifferentiated shell. Import the `bodies/` set instead and
SolidWorks gives you seven separately selectable bodies — you can hide the
casting to see the mounts, or give each one its own appearance. The six small
bodies (`PP12-EM-JD18`, `EM-SP` ×4, the 360-triangle `COMPOUND`) are
coordinate-exact and never decimated, so they stay dimensionally trustworthy
even when the big casting has been reduced.

---

## 5. What is still not certain

- **No SolidWorks round-trip has been run** (§3). Everything here is documented
  behaviour, not observed behaviour.
- Whether SolidWorks reads our `.mtl` **base colours** specifically is confirmed
  by the docs for graphics bodies in general; we have not seen it happen with
  *this* file.
- The 1.55 mm figure is a **sampled bidirectional deviation** (8,000 BVH samples,
  0 misses), not a certified Hausdorff bound. Do not quote it as a tolerance.
- Nothing in this document makes the mesh watertight, and nothing here is an
  engineering certification.

## Sources

- [Mesh Files (\*.stl, \*.obj) — SOLIDWORKS 2025 Help](https://help.solidworks.com/2025/English/SolidWorks/sldworks/c_stl_files.htm)
- [Mesh Files, VRML, and 3MF Import Options — SOLIDWORKS 2025 Help](https://help.solidworks.com/2025/English/SolidWorks/sldworks/HIDD_OPTIONS_IMPORT_VRML_2.htm)
- [SOLIDWORKS STL Import Settings Overview — GoEngineer](https://www.goengineer.com/blog/solidworks-stl-import-settings-overview)
- [Working with Mesh Files in SOLIDWORKS — Hawk Ridge Systems](https://support.hawkridgesys.com/hc/en-us/articles/203485653-Working-with-Mesh-Files-in-SOLIDWORKS)
- Measured locally: `reports/astra-engine-final-verification.md`,
  `reports/astra-engine-final-readback.json`,
  `reports/astra-engine-final-readback-notes.md`
