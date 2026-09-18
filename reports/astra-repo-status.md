# Independent repository status & safety scout — Astra engine export

Reviewer seat: independent review/scout (read-only source; owns this file and
`reports/astra-engine-review.md` + `tools/astra_verify_engine_export.py` only).
Time of scan: 2026-09-18, deadline 14:44 EDT.

## 1. Remote / branch / divergence

| item | value |
|---|---|
| origin fetch+push | `https://github.com/mhintz1980/CAD-pipeline.git` |
| repo type | **PUBLIC** (per brief) |
| current branch | `main` |
| HEAD | `c81123abad56500e3c1d73d34d1e795ba5d2826f` |
| `origin/main` | `c81123abad56500e3c1d73d34d1e795ba5d2826f` |
| divergence | **0 ahead / 0 behind** (`git rev-list --left-right --count origin/main...main` = `0 0`) |
| `git fetch origin` (read-only) | no new refs; HEAD == origin/main |
| working tree | clean except untracked files (below) |

No merge/reset/pull/push performed. Local checkout is exactly in sync with remote.

## 2. Untracked (not yet committed)

```
?? astra-engine-export-spec.md
?? astra-engine-review-spec.md
?? astra-modal-cloud-spec.md
?? reports/astra-engine-export-worker.json
?? reports/astra-engine-review-worker.json
?? reports/astra-modal-cloud-worker.json
?? reports/astra-modal-engine/          (STATUS.md so far)
?? tools/astra_verify_engine_export.py  (this seat's verifier)
```

## 3. Binary-safety audit (repository is public — never commit CAD)

* Tracked `.blend/.blend1/.glb/.stl/.step/.iges` count: **0**. Good.
* `.gitignore` correctly excludes `source/`, `out/`, `*.blend`, `*.blend1`,
  `reports/views/`, `reports/validate-*/`, `.venv/`, `__pycache__/`.
* `git check-ignore -v` confirms `out/engine-and-pump-v10.blend` and `source`
  are ignored (`.gitignore:10` and `.gitignore:4`).
* Largest **tracked** files are render PNGs (~1.7 MB) — under GitHub 100 MB limit.
* `out/engine-and-pump-v10.blend` (98 MB, proprietary vendor CAD) is untracked
  and ignored — must stay that way.

## 4. Source-input immutability (independent re-hash)

`out/engine-and-pump-v10.blend` sha256 =
`5f8632d8ef9b27da15b221f47feb9fb37dcea7b52493aeba62125523ae5f5e6f`, 102,843,862 B.
Independently reproduced this session; **matches** the Modal spec and the prior
controller-review record. Source must remain unmodified by the Modal leg.

## 5. Safe, scoped commit candidates (architect decides; no commit made here)

Only **text/scripts**, no geometry:

* `astra-engine-export-spec.md`, `astra-engine-review-spec.md`, `astra-modal-cloud-spec.md`
* `reports/astra-engine-export-worker.json`, `reports/astra-engine-review-worker.json`,
  `reports/astra-modal-cloud-worker.json`
* `reports/astra-modal-engine/**` — **caution**: verify each file is text/small
  (STATUS.md, logs, JSON, PNG preview). **Never** stage any `.blend`/`.stl`/`.glb`
  or the 98 MB source that a worker may drop into a reports subfolder.
* `tools/astra_verify_engine_export.py` (this seat), `tools/astra_engine_export.py`,
  `tools/astra_modal_engine.py` (sibling seats) once present and reviewed.

Suggested pre-commit guard before any push:
`git add -A -n` (dry run) then eyeball; reject any path matching
`\.(blend|glb|stl|step|stp)$` or `^source/` or `^out/`.

## 6. Scout notes / limitations

* Sibling `tools/astra_engine_export.py` and `tools/astra_modal_engine.py` were
  **not present** at scan time; `reports/astra-modal-engine/STATUS.md` exists
  (Modal wrapper planning started). Code review is in `reports/astra-engine-review.md`
  and should be re-run once the sibling scripts land.
* No unrelated repository areas were scanned.
