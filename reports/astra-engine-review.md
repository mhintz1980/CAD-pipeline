# Independent review — Astra engine export (Modal -> SolidWorks)

Reviewer seat: independent (read-only source; owns this file,
`reports/astra-repo-status.md`, `tools/astra_verify_engine_export.py`).
Scan time: 2026-09-18 ~14:00 EDT. Deadline 14:44 EDT.

Verdict: **1 CRITICAL geometry bug + 2 deviation bugs in the export script; Modal
wrapper now largely wired but has a likely download-path defect. Artifacts not
yet downloaded — runtime verification pending.**

Files reviewed (hashes at time of review):
* `tools/astra_engine_export.py` sha256 `5b62e70747c730437dd5241d907a82c05a43afdefed2dd85dd924bf5c48e86f9` (15,047 B)
* `tools/astra_modal_engine.py`  sha256 `24da51bc0521dd972cbef4841f42aab7fc34d75b41ba918dba55a00fd64b597b` (5,404 B)

---

## A. Export script `tools/astra_engine_export.py` — code issues (code first)

### A1 — CRITICAL: protected/decimated sets are INVERTED; both triangle targets are unreachable
Line 23: `PROTECTED_NAMES = {"COMPOUND", "COMPOUND.001"}`.

The spec: *"Decimate each body proportional to triangle count, protect small
mounting interfaces (**objects other than COMPOUND / COMPOUND.001**) at full
resolution."* So the protected (full-res) set is the **small** interfaces, and
`COMPOUND` / `COMPOUND.001` are the bodies to **decimate**.

Evidence — actual engine composition (from `reports/astra-baseline-v9.json`,
`collection == "CAD_engine"`; `ASTRA-HANDOFF-2026-09-17.md:440` calls them
"2 enormous COMPOUND meshes"):

| object | polys | role |
|---|---|---|
| COMPOUND.001 | **2,274,714** | the enormous merged body (99.99% of tris) |
| COMPOUND | 360 | tiny |
| EM-SP, EM-SP.001, EM-SP.002, EM-SP.003 | 156 each | small mounting interfaces |
| PP12-EM-JD18 | 1,204 | small mounting interface |
| **total** | **~2,276,902** | |

The script therefore keeps the 2,274,714-tri body at FULL resolution and
decimates only the ~1,828 tris of the small mounts. Consequence:
* `protected_tris ≈ 2,275,074 > decimate_detailed (500,000)` so `need =
  max(500000-2275074, 1) = 1` and `factor_d = max(1/1828, 0.01) = 0.01`
  (line 273-274): the **detailed STL lands at ~2.27 M tris, not ~500 k**.
* Same for light: **~2.27 M tris, not ~200 k**.
* Simultaneously the small mounting interfaces (the ones that must stay intact)
  are collapsed to ~1% — the exact bodies the spec protects are destroyed.

**Fix:** protect the small interfaces, decimate the compounds, e.g.
```python
PROTECTED_NAMES = {o.name for o in src_objs if o.name not in {"COMPOUND", "COMPOUND.001"}}
```
or hard-code `{"EM-SP", "EM-SP.001", "EM-SP.002", "EM-SP.003", "PP12-EM-JD18"}`.
Then `factor_d = (500000-1828)/(2276902-1828) ≈ 0.219` and
`fl = (200000-1828)/(~500000-1828) ≈ 0.398`, i.e. the targets become reachable.

### A2 — BUG: deviation sampling reads the BVH **triangle index**, not the distance
Lines 171 and 175:
```python
d1 = np.array([src_tree.find_nearest(p)[2] or 0.0 for p in pts])
d2 = np.array([dec_tree.find_nearest(p)[2] or 0.0 for p in pts2])
```
`BVHTree.find_nearest()` returns `(location, normal, index, distance)`. `[2]`
is the **index**; the distance is `[3]`. So `max_dev_mm` / `mean_dev_mm` are
triangle indices, not millimetres. (The `or 0.0` also turns a real index `0`
into `0.0`.) **Fix:** use `[3]` (and guard against `None` when the tree is empty).

### A3 — BUG: source sample points are in LOCAL space while the dec tree is in WORLD space
`sample_deviation` samples with `sample_pts(src_obj, samples)` (line 174), and
`sample_pts` -> `tri_coords` returns `me.vertices.co` **local** coordinates.
But `dec_tree` (`bvh_from(dec_obj)`) is baked to world (the dec copy had its
world transform applied; `bvh_from` then transforms by the identity). So `d2`
compares local-space points against a world-space tree and is meaningless
whenever the original engine object has a non-identity `matrix_world` (they do —
the engine was centred/placed). `d1` is fine because `dec_obj` is already world.
**Fix:** transform `src` sample points to world, or build `src_tree` and sample
`src` in the same space (e.g. sample from the world-baked clean copy and query
the world `src_tree`). Combine with A2 before trusting any deviation number.

### A4 — MEDIUM: units are self-contradictory in the report (verification risk)
Line 232-236 expects `scale_length == 1.0` labelled *"expected meters"*, but
line 251-253 compares raw world coordinates against **millimetre** bounds
(X -835.7…837.7). Both cannot be true: if the scene is metre-scaled, raw coords
would be ~0.84, not 835. Whichever it is:
* the STL is exported as **raw coordinates** (no ×1000), so the numeric range is
  whatever the blend stores; it must be **millimetres** for SolidWorks to read
  it as mm on import;
* `DEGENERATE_EPS = 0.001` (line 24) and the `remove_doubles`/`dissolve_degenerate`
  distances are in **scene units** — if 1 unit = 1 m this welds at 1 mm (1000×
  the spec's 0.001 mm) and will over-merge real geometry.
**Action:** read `scene_units.scale_length` from the downloaded
`astra-engine-export.json` and reconcile the "expected meters" text and the
weld tolerance against the actual value before trusting the export.

### A5 — MINOR: `nonmanifold_edges` double-counts boundaries
Line 69: `nonman_e = sum(1 for e in bm.edges if not e.is_manifold)`. In bmesh an
edge with a single face is **both** boundary and not manifold, so the reported
"nonmanifold" count includes all boundary edges. True non-manifold (>2 faces)
= `nonman_e - bound_e`. Report them separately to avoid a false alarm that the
surfaces are "broken".

### A6 — MINOR / spec gap: no `engine-preview.png`
The export spec requires a 1000×800 `engine-preview.png` (GPU Cycles OPTIX/CUDA,
JDgreen castings, framed to engine bounds). **Neither the export script nor the
Modal wrapper renders anything** — the preview deliverable is missing. If it is
still required, the L4 is only used for a validation render that does not exist.

### A7 — MINOR notes
* `engine-cleaned.blend` is saved *after* detailed decimation (line 295 vs 283),
  so it contains the ~500 k meshes, not the cleaned full-res ones; the README
  wording implies cleanup-only. Acceptable per spec ordering, but state it.
* `validate_stl` (210-216) re-reads only count/size; non-finite is computed from
  the in-memory array, not read back from the file. Use the independent verifier
  (§C) for true readback.
* `collect_stl_tris` merges all 7 bodies into one unindexed STL mesh (318-323);
  body separation survives only in the `.blend`. Fine for a mesh reference.
* `bbox_of` (130-138) transforms the local `bound_box`, a transformed local AABB;
  it can slightly overestimate for rotated bodies.
* Performance: `analyze_mesh` builds a bmesh and Python-iterates ~3.4 M edges
  twice per body for COMPOUND.001, and `sample_deviation` builds a BVH on 2.27 M
  tris up to 4×. Minutes, but within the 2400 s budget — watch the log.

---

## B. Modal wrapper `tools/astra_modal_engine.py`

### B1 — FIXED since first read
* Input path is now parametric: `run_export(script_text, blend_vol_path, run_id)`
  (line 47) and `main` passes `f"/input/{dest}"` (line 128). *(was a blocker)*
* `main` now calls `run_export.remote(...)` (128) and downloads outputs (131-141).
  *(was a blocker)*
* The wasteful `put_directory("out", ...)` upload of the whole ~1.4 GB `out/`
  tree was removed; only the single 98 MB blend is uploaded (123-124).

### B2 — OPEN, likely HIGH: download uses a mounted path, not a volume-relative path
Lines 135-141 walk `/output` and call
`vol_out.read_file(o["path"])` where `o["path"]` is the **mount** path
(`/output/engine-light.stl`). `Volume.read_file()` paths are **relative to the
volume root**, so this looks for `output/engine-light.stl` *inside* the volume
and will likely raise `FileNotFoundError`, losing the results. Use the
volume-relative `rel` already computed (line 136) or `o["path"].removeprefix("/output/")`,
or prefer `vol_out.batch_download()`.

### B3 — OPEN, MEDIUM: remote source hash computed but never checked
`run_export` hashes the blend into `blend_sha256` (54-57, 100) but nothing
asserts it equals `5f8632d8…5f5e6f`. Add an assertion (pass the expected hash in)
so a mis-uploaded/renamed file can never be processed silently.

### B4 — OPEN, LOW: failures are not surfaced
The function commits the volume and returns even when `res.returncode != 0`
(89-102). Treat non-zero as failure in the receipt and skip a bogus "success".

### B5 — OPEN, LOW: outputs go to the volume root, not a unique prefix
The spec asked for a unique output prefix; the function writes `engine-*.stl`
etc. to `/output` root. Fine for a single run (`max_containers=1`) but it will
collide on any rerun. Prefer `/output/{run_id}/...`.

### B6 — OPEN, UNVERIFIED: Blender download URL / image deps
The `download.blender.org/release/Blender5.1/blender-5.1.{2,0}-linux-x64.tar.xz`
names (line 27) are unverified; a wrong name fails the image build and burns the
deadline. Confirm the exact release file, and that the L4/Cycles path needs no
extra libs (e.g. `libegl1`/`libgbm1`).

> Debug hint for the team: independent single-file STL readback/debugging is
> available via `tools/astra_verify_engine_export.py` (§C).

---

## C. Independent verifier (this seat)

`tools/astra_verify_engine_export.py` sha256
`e6316d6eb71a2b4decdc612faa74bcdec5ed1ead3f768ef1271abcc5b629115b`.
Pure `struct`+`numpy` (no Blender, no trimesh). Per file: header, declared vs
actual tri count, file-size consistency, bbox (file units + units hint),
non-finite vertices, degenerate tris, zero-length edges, welded-vertex count,
boundary/open edges, non-manifold edges, connected shells, Euler characteristic,
watertight flag. Exit 0 only on structural integrity (size/finite/non-empty);
openness alone does not fail.

Self-test (this session, synthetic, then removed):
* watertight tetra -> boundary=0, nonmanifold=0, shells=1, euler=2, watertight=True.
* single open triangle -> boundary_edges=3, watertight=False.
* corrupt file (declared 99) -> `size mismatch`, ok=False, exit 1.

Run once artifacts land:
```
python tools/astra_verify_engine_export.py \
  --stl reports/astra-modal-engine/<RUN_ID>/engine-light.stl \
  --stl reports/astra-modal-engine/<RUN_ID>/engine-detailed.stl \
  --report reports/astra-engine-review-stl-readback.json
```

## D. Verification checklist for the downloaded artifacts (pending)

1. `astra-engine-export.json`: `engine_object_count == 7`, names match the 7
   above, `scene_units.scale_length` read and reconciled (A4), `src_bbox_mm`
   matches the spec bounds.
2. `engine-detailed.stl` ≈ 500 k tris, `engine-light.stl` ≈ 200 k tris — **if
   they are ~2.27 M, A1 is confirmed at runtime**.
3. Per-body `detailed_tris` for the small mounts unchanged (protected) and
   COMPOUND.001 decimated ~×0.22.
4. Independent readback (tool §C): bbox in mm, finite, non-empty; boundary-edge
   counts interpreted as evidence of intentional open bores/ports, not failure.
5. Source immutability: `out/engine-and-pump-v10.blend` sha256 still
   `5f8632d8…5f5e6f`.

---

## F. Runtime findings (from the two preflight runs, 13:54 / 13:57 EDT)

Evidence: `reports/astra-modal-engine/preflight.log`, `preflight2.log`,
`run-20260918T135401/`, `run-20260918T135557/` (both run dirs **empty**).

### F1 — BLOCKER (confirmed at runtime): download API misused, nothing persisted
`preflight2.log` traceback:
```
tools/astra_modal_engine.py:139 in main
    with vol_out.read_file(o["path"]) as data:
TypeError: 'generator' object does not support the context manager protocol
```
`Volume.read_file()` returns a **generator of byte chunks**, not a context
manager. The earlier attempt (`preflight.log`) failed differently:
`VolumeUploadContextManager object has no attribute 'get_file'`. Both runs
crashed **after** the remote function succeeded, so the run dirs are empty and
**no artifact was ever downloaded**.

> **STILL PRESENT as of wrapper rev `01fa13d5`** (`download_outputs`, line 140:
> `with vol_out.read_file(o["path"]) as data:`) — the *same* crash, even though
> `STATUS.md` claims it was fixed. It will fail again on the paid run.

**SDK proof (this seat, installed Modal `1.5.5`):**
```
Volume.read_file(self, path: str) -> collections.abc.AsyncGenerator[bytes, None]
# (wrapped by @live_method_gen -> a sync generator of bytes in a sync caller)
# example from the SDK docstring:
#   data = b""
#   for chunk in vol.read_file("1mb.csv"):
#       data += chunk
hasattr(Volume, "batch_download") == False     # does NOT exist in 1.5.5
```
So `read_file` must be **iterated** (not used as a context manager), the path is
**volume-relative** (not the mounted `/output/...`), and there is **no**
`batch_download`. Exact fix for `download_outputs`:
```python
def download_outputs(outputs, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    for o in outputs:
        rel_vol = o["path"].removeprefix("/output/")        # volume-relative path
        dst = os.path.join(out_dir, os.path.relpath(o["path"], OUT_ROOT))
        os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
        with open(dst, "wb") as f:
            for chunk in vol_out.read_file(rel_vol):        # iterate the generator
                f.write(chunk)
```
(My earlier `batch_download` suggestion is **withdrawn** — that API is absent in
1.5.5.) This is the single remaining thing that will lose the deliverables.

### F2 — BLOCKER (confirmed at runtime): the remote "Blender" was a STUB — the export never ran
`preflight2.log` remote stdout:
```
blend | Read blend: "/input/run-20260918T135557/engine-and-pump-v10.blend"
STUB: blender 5.1.2
Blender 5.1.2 (hash ec6e62d40fa9 built 2026-05-19 02:18:37)
Blender quit
```
Return was `returncode: 0`, `elapsed_sec: 3.31`, and the only outputs are
`blender-stdout.log`, `blender-stderr.log` (0 B), `meminfo.txt`,
`nvidia-smi.txt`, and an 8-byte `stub.txt`. **No `[astra-export]` log lines, no
`engine-light.stl`, no `engine-cleaned.blend`.** So whatever binary ran printed
`STUB` and exited immediately — `astra_engine_export.py` was never executed
(a real `-b file --python script` run would print the script's `[astra-export]`
logs and take minutes, not 3 s). The current source installs real Blender via
`wget`, so either an earlier stub image was still cached/used for these
preflights, or the image is producing a stub binary.

**Action before the paid run:** prove real Blender by (a) `blender --version` in
the image build log, and (b) the export run printing `[astra-export] DONE ...`
plus a nonempty `engine-light.stl`/`engine-detailed.stl` and
`astra-engine-export.json` in the outputs list. Until then there is **zero**
evidence the export pipeline works.

### F3 — Confirmed infrastructure (good)
* GPU: **NVIDIA L4**, driver 580.95.05, CUDA 13.0, 23,034 MiB idle — L4 available.
* Host MemTotal ~763 GB visible in `/proc/meminfo` (the `memory=65536` request is
  enforced by cgroup, not visible here — not an error, just note it).
* Input upload works: remote read `/input/run-20260918T135557/engine-and-pump-v10.blend`
  and re-hashed it to `5f8632d8…5f5e6f` (matches source).

---

## G. Independent corroboration of the architect fix note + 3 extra defects

The producer is rewriting the export script per `astra-engine-export-fix.md`
(8 blocking points) and the Modal worker per `astra-modal-review-notes.md`. My
independent findings A1/A2/A3/A4/A6/A7 map 1:1 onto points 1/3/2/6/7. Three
additional defects in the **original** script (fix points 4 and 5) that I can
confirm from its own logic:

### G1 — Invalid Blender (RNA) references used after deletion
The original `main()` removes every non-copy object at lines 291-294
(`bpy.data.objects.remove`), but then the **light** pass calls
`sample_deviation(src, c2)` (line 316) where `src` is one of those **just-deleted
original** objects. Accessing a freed Blender ID (`src.name`, `src.matrix_world`,
`analyze_mesh(src)`) is undefined and can crash or silently return stale/garbage
data. Fix: keep the immutable source objects alive until all metrics and exports
are finished; only isolate/delete afterwards (or work entirely on separate
source-copies + output scene).

### G2 — `id(obj)` used for Blender-ID set membership
Line 291 `keep = set(id(c) for _, c in copies)` compares Python `id()`s of Blender
objects. `id()` is only unique while the object is alive and can be recycled;
after `bpy.data.objects.remove` frees others, membership tests can mis-fire. Use
object **references** (or `obj.as_pointer()`) as the membership key.

### G3 — `obj.copy()` keeps the parent, risking a double transform
`make_clean_copy` (78-98) does `copy = obj.copy()` (which retains `.parent` and
`.parent_inverse`), then sets `copy.matrix_world = Identity` and bakes
`me.transform(obj.matrix_world)`. If any engine body is parented, the retained
parent plus the world bake can double-apply (or the world bake can disagree with
the parent-derived world), so the exported bodies may be displaced. Fix: clear
`copy.parent` / reset `matrix_parent_inverse` **before** baking the captured
world matrix, and verify against the source bbox.

These are consistent with the architect's points 4 and 5 and should be checked
explicitly in the rewritten script. Any claim of "READY" must be demonstrated by
the script's own asserts plus a nonempty, correctly-scaled STL — not by a
compile-only report.

---

## H. Review of rewritten export script rev 2 (sha256 `692f8582…79c65e2`, 14:01)

Rev 2 implements the architect fix list and resolves most of my A/G items. **One
new BLOCKER remains** (H1), plus minor notes.

### H1 — BLOCKER: unit conversion is a no-op; the mm scale is dropped by a stray /1000
Line 109:
```python
copy.data.transform(Matrix.Scale(mm / 1000.0, 4) @ world)   # world(m) -> world(mm)
```
`mm = mm_scale_factor() = scale_length * 1000` (lines 92-95). The script's own
docstring (line 11), the JSON label (line 340/502) and the architect fix note all
say the copy must be scaled by **`scale_length * 1000`**. But `mm / 1000.0` equals
**`scale_length`**, so for the documented scene (`Unit System = Metric`,
`scale_length = 1.0`, raw world coords in **metres**) the scale is **1.0** — i.e.
**no conversion at all**. The mesh stays at ~0.835 and the hard bbox assert
(lines 367-372) compares it to `-835.717…837.72` mm and **aborts with zero
output**.

Independent confirmation that the factor must be ×1000: the only prior, proven
conversions in this repo are `tools/astra_controller_v10.py:26,88` and
`tools/astra_verify_wide.py` — both do `mm = raw * 1000.0` on the same source
blend ("Internal units scene metres").

**Fix (one character of intent):**
```python
copy.data.transform(Matrix.Scale(mm, 4) @ world)            # mm == scale_length*1000
```
If the run's `scene_units.scale_length` were, against expectation, `1000`, the
current line would coincidentally be correct — but that contradicts the
metres convention and the spec. The bbox assert is a good fail-safe: it will
stop a mis-scaled STL from shipping, at the cost of the run.

### H2 — Confirmed correct in rev 2 (fixes my A/G findings)
* **FIX 1** `protected = [o for o in src_objs if o.name not in DECIMATE_NAMES]`
  (line 355) — the two large `COMPOUND*` castings are now the decimated set and
  the small mounts are protected. Matches the baseline counts. ✔
* **FIX 2** bbox asserted against expected mm with a hard `fail()` (367-372);
  `src_bbox_mm` recorded. (Units factor itself is H1.) ✔ (structure)
* **FIX 3** `hit[3]` distance (line 221), misses -> `NaN` and counted (218-219),
  baseline samples taken from immutable mm copies (`base_tris`, 361) — A2/A3 fixed. ✔
* **FIX 4** isolation via `as_pointer()` set (434-437), baselines kept until after
  all object-based metrics; light pass uses `base_tris` arrays not freed objects —
  no dangling RNA (G1/G2 fixed). ✔
* **FIX 5** `copy.parent = None` and `matrix_parent_inverse = Identity` before the
  world bake (106-108) — G3 fixed. ✔
* **FIX 6** `stage_scene` + `setup_gpu_cycles` + `render_preview` now produce
  `engine-preview.png` 1000×800/32-spp with OPTIX→CUDA→CPU evidence — A6 closed. ✔
* **FIX 7** guard asserts on STL size/count/nonempty and finite coords (470-480);
  mounts bypass cleanup and decimation with `mount_preserved_exact` (484-487); the
  detailed/light factors now use `prot_total` so targets ~500 k / ~200 k are
  reachable. ✔

### H3 — Minor notes (non-blocking)
* `nonmanifold_edges` still counts boundary edges (line 118: `not e.is_manifold`
  is true for 1-face edges). Report `bound` and `nonman − bound` separately.
* `BVHTree.find_nearest(p)` is handed a **numpy** row (line 216); mathutils often
  wants a `Vector`/sequence — pass `tuple(p)` to avoid a possible TypeError.
* No assertion enforces the ~10 MB / ~25 MB size targets (only the internal
  size/count/nonempty consistency); fine, but the JSON `approx_mb` should be
  eyeballed at runtime.
* Timing watch: `base_tris` holds float64 for the 2.27 M body (~163 MB) and
  `analyze_mesh` Python-iterates ~3.4 M edges per body several times; the render
  runs before isolation. Comfortable within the 2250 s cap, but confirm in the log.

> Net: rev 2 is close. **Fix H1 (drop the `/1000.0`) and re-verify the bbox
> assert passes before dispatching the paid run** — otherwise the script
> fail-fasts and the deadline is spent on a no-op.

---

## I. Runtime artifact verification (first real L4 run, 14:08, verified 14:1x)

Run `run-20260918T140853` (app `ap-6ViotFIVYEcYiZVTRHDiDX`), 77 s in-Blender /
90.7 s wall, GPU **OPTIX / NVIDIA L4**. Artifacts downloaded to
`reports/astra-modal-engine/run-20260918T140853/`. Remote `returncode=1` was
**solely** the caught preview error (see I5); the STL/blend/JSON/README outputs
were produced and downloaded regardless.

### I1 — Independent binary-STL readback (`tools/astra_verify_engine_export.py`)
Report: `reports/astra-engine-review-stl-readback.json`.

| | engine-detailed.stl | engine-light.stl |
|---|---|---|
| bytes | 24,999,884 | 9,999,984 |
| declared = actual tris | 499,996 = 499,996 | 199,998 = 199,998 |
| size consistent (84+50n) | **true** | **true** |
| non-finite vertices | 0 | 0 |
| bbox min | −835.717, −1762.413, −482.756 | −835.717, −1762.413, −482.756 |
| bbox max | 838.154, 521.778, 1715.771 | 835.754, 521.441, 1715.258 |
| units hint | **millimetres** | **millimetres** |
| degenerate tris / zero-len edges | 169 / 486 | 82 / 205 |
| boundary (open) edges | 203,324 | 105,707 |
| non-manifold edges | 4,088 | 4,076 |
| shells | 4,275 | 4,329 |
| watertight | false (expected) | false (expected) |

The tool's own readback (count/size/bbox/finite/open edges) **agrees with the
script's JSON** (e.g. JSON `detailed_stats` boundary 203,329 + mounts 0 ≈ the
203,324 measured; small delta is only the weld tolerance). Units are genuine mm
(bbox matches the expected −835.7…837.7 engine bounds), so the earlier unit
blocker is closed.

### I2 — Interpretation of open surfaces vs "healing"
Open boundaries are **intrinsic to this vendor assembly**, not damage: the source
`COMPOUND.001` already has **1,517,118** boundary edges. Conservative cleanup
*dropped* that to **422,099**, and decimation to **203,329** (detailed) /
105,707 (light) — i.e. boundaries were **reduced by removing duplicates/degenerate
faces, never by hole-filling**, exactly as required. No voxel/clearance fill was
performed. This is the correct behaviour: the deliverable is explicitly a mesh
reference, **not** watertight, and the JSON says so.

### I3 — Quality note: decimation introduces non-manifold edges
Source `COMPOUND.001` non-manifold = **0**, but after cleanup/decimation it is
**4,075 / 4,076**. Edge-collapse decimation can create non-manifold edges as a
side effect. This is a *known cost* of simplification, not "healing"; it does not
break SolidWorks mesh import but should be stated in the README/limitations
(currently only boundary/open is mentioned). Optional: add a one-line note, or
run a light `remove_doubles`-only pass; not a blocker for a graphics reference.

### I4 — Minor: decimation vertex shift at the X extreme
Detailed STL X-max is 838.154 mm vs the source 837.721 mm (+0.43 mm); light is
835.754 mm (−1.97 mm vs source). This is the expected surface deviation from
collapse (JSON: detailed max dev 1.55 mm, light 33.9 mm on the big casting).
Within BBOX_TOL_MM=10 for the source assert; report properly as mesh deviation.

### I5 — Preview was the only failure; now fixed (this seat owns the script)
`blender-stdout.log`: `Error: Cannot render, no camera` → JSON `preview.error`.
Root cause: `stage_scene` created a camera but never assigned `scene.camera`.
**Fixed** (`scene.camera = cam`, plus a guard). STL/blend/JSON/README were all
written **before** the render, so nothing else was lost — vindicating the
"exports before preview" ordering. A re-dispatch is needed only to obtain the
preview PNG.

### I6 — Mount preservation proven exactly
JSON: all 5 protected mounts `mount_preserved_exact=true`, `mount_dev_mm=0.0`
(via `np.array_equal` against the immutable baseline), and their tri counts are
identical across src/clean/detailed/light. A1 and the fix-5 requirement are
satisfied at runtime.

---

## E. Status (updated 14:1x EDT)

* **Ownership change:** this seat (independent reviewer) now **owns**
  `tools/astra_engine_export.py` + `reports/astra-engine-export-code.md` and has
  produced **rev 3** (sha256 `d5aae7d07f7f22640051eb120fbbcedd1fb955fd55959eba46f267504afa882e`;
  rev-3 shipped, then a preview-camera fix),
  implementing all six `astra-engine-rev3-fix.md` points:
  1. `Matrix.Scale(mm, 4) @ world` — H1 fixed (convention-robust: metres→×1000,
     mm-scene→×1); the bbox assert adjudicates at runtime.
  2. Exports → guards/metrics/mount-proof → README/report → **isolation** →
     **preview**; source/protected names frozen as strings; light copies dropped
     at isolation.
  3. `stage_scene` force-shows view layer/collections/objects; preview asserted
     written (>1 KB), render failure non-fatal.
  4. `engine-cleaned.blend` saved with `scale_length=0.001` (mm representation).
  5. `mount_preserved_exact` via `np.array_equal` vs immutable baseline; post-
     decimation topology + mm deviations for BOTH variants.
  6. Rev-3 marker; READY only after inspection.
  Compile OK; STL writer ↔ verifier unit-tested (watertight mm tetra read back).
* Modal wrapper (`f5f9d631…`): input-path / invoke / over-upload **fixed**;
  **F1 download crash still present** (line 133) — see F1 above.
* Stub runs explained: `tools/_stub_export.py` prints `STUB: blender …`.
* **Runtime: the export EXECUTED successfully on L4** — units verified, 7 bodies,
  mounts preserved exactly, detailed 499,996 tris / light 199,998 tris, STLs
  independently read back (§I). **Only the preview PNG failed** (`no camera`),
  now fixed; a re-dispatch yields the preview. See §I.
* Git: origin CAD-pipeline, branch `main`, in sync (0/0), no CAD binaries
  tracked — see `reports/astra-repo-status.md`.
