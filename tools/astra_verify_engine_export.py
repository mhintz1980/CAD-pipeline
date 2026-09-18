"""Independent binary STL verifier for the Astra engine-export deliverable.

Reads STL file(s) with struct+numpy only (no trimesh, no Blender, no bpy).
Reports, per file: header/declared-vs-actual triangle count, file-size integrity,
bbox in file units, non-finite vertex count, degenerate triangles, zero-length
edges, welded-vertex count, boundary (open) edges, non-manifold edges and
connected shells.

Deliberately independent of the export worker's own validation so that "actual
readback" claims can be cross-checked. It does NOT promise that a watertight
result is desirable: an assembly mesh legitimately contains open surfaces
(bores, ports, mating faces), so boundary edges are "evidence", not auto-fail.

Usage:
  python tools/astra_verify_engine_export.py --stl A.stl --stl B.stl --report R.json
  python tools/astra_verify_engine_export.py --dir <folder> --glob "*.stl" --report R.json

Exit code: 0 if all structural integrity checks pass, nonzero otherwise.
Topology openness alone does NOT fail.
"""
import argparse
import json
import struct
import sys
from pathlib import Path

import numpy as np

REC = np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
REC_SIZE = 50


def _union_find(n, edges):
    """Connected components from an (M,2) int array. Returns (labels, n_shells)."""
    parent = np.arange(n, dtype=np.int64)

    def find(x):
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    for a, b in edges:
        ra, rb = find(int(a)), find(int(b))
        if ra != rb:
            parent[ra] = rb
    roots = {}
    labels = np.empty(n, dtype=np.int64)
    for i in range(n):
        r = find(i)
        if r not in roots:
            roots[r] = len(roots)
        labels[i] = roots[r]
    return labels, len(roots)


def analyse(path, weld_eps):
    p = Path(path)
    out = {"path": str(p), "ok": False, "errors": []}
    raw = p.read_bytes()
    out["bytes"] = len(raw)
    if len(raw) < 84:
        out["errors"].append("file smaller than 84-byte STL header")
        return out

    header = raw[:80]
    out["header_ascii"] = header.split(b"\x00")[0].decode("ascii", "replace").strip()
    declared = struct.unpack("<I", raw[80:84])[0]
    out["declared_triangles"] = int(declared)

    expected = 84 + declared * REC_SIZE
    out["expected_bytes"] = expected
    out["size_consistent"] = (expected == len(raw))
    is_ascii = raw[:5].lower() == b"solid" and not out["size_consistent"]
    out["looks_ascii"] = bool(is_ascii)
    if is_ascii:
        out["errors"].append(
            "does not parse as binary STL (starts solid and size mismatch); "
            "likely ASCII STL or corrupt")
        return out
    if not out["size_consistent"]:
        out["errors"].append(
            "size mismatch: expected %d for %d tris, got %d" % (expected, declared, len(raw)))

    n = min(declared, (len(raw) - 84) // REC_SIZE)
    arr = np.frombuffer(raw, dtype=REC, count=n, offset=84)
    tris = arr["v"].astype(np.float64)
    out["triangles"] = int(n)

    pts = tris.reshape(-1, 3)
    finite = np.isfinite(pts).all(axis=1)
    out["vertices_total"] = int(pts.shape[0])
    out["nonfinite_vertices"] = int((~finite).sum())
    if out["nonfinite_vertices"]:
        out["errors"].append("%d non-finite vertex coords" % out["nonfinite_vertices"])

    good = pts[finite]
    if good.size == 0:
        out["errors"].append("no finite vertices")
        return out

    bmin = good.min(axis=0)
    bmax = good.max(axis=0)
    dim = bmax - bmin
    out["bbox_min"] = [round(float(x), 4) for x in bmin]
    out["bbox_max"] = [round(float(x), 4) for x in bmax]
    out["bbox_size"] = [round(float(x), 4) for x in dim]
    out["bbox_center"] = [round(float(x), 4) for x in (bmin + bmax) / 2.0]
    out["units_hint"] = ("coordinates look like millimetres" if dim.max() > 50
                         else "coordinates look small; verify units")

    tv = tris
    e0 = tv[:, 1] - tv[:, 0]
    e1 = tv[:, 2] - tv[:, 0]
    cross = np.cross(e0, e1)
    area2 = np.linalg.norm(cross, axis=1)
    diag = float(np.linalg.norm(dim)) or 1.0
    area_tol = 1e-9 * diag * diag
    out["degenerate_triangles"] = int((area2 <= area_tol).sum())
    edge_lengths = np.concatenate([
        np.linalg.norm(tv[:, 1] - tv[:, 0], axis=1),
        np.linalg.norm(tv[:, 2] - tv[:, 1], axis=1),
        np.linalg.norm(tv[:, 0] - tv[:, 2], axis=1),
    ])
    out["zero_length_edges"] = int((edge_lengths <= area_tol ** 0.5).sum())

    allpts = tris.reshape(-1, 3)
    key = np.round(allpts / weld_eps).astype(np.int64)
    _, inv = np.unique(key, axis=0, return_inverse=True)
    inv = inv.reshape(-1)
    out["weld_eps"] = weld_eps
    out["welded_vertices"] = int(inv.max() + 1) if inv.size else 0

    f = inv.reshape(-1, 3)
    fgood = f[(f[:, 0] != f[:, 1]) & (f[:, 1] != f[:, 2]) & (f[:, 0] != f[:, 2])]
    out["welded_faces_for_topology"] = int(fgood.shape[0])
    edges = np.concatenate([fgood[:, [0, 1]], fgood[:, [1, 2]], fgood[:, [2, 0]]])
    edges = np.sort(edges, axis=1)
    nv = out["welded_vertices"]
    ekey = edges[:, 0].astype(np.int64) * (nv + 1) + edges[:, 1]
    uniq, counts = np.unique(ekey, return_counts=True)
    out["unique_edges"] = int(uniq.size)
    out["boundary_edges"] = int((counts == 1).sum())
    out["nonmanifold_edges"] = int((counts > 2).sum())
    out["manifold_edges"] = int((counts == 2).sum())
    V, E, F = nv, int(uniq.size), int(fgood.shape[0])
    out["euler_characteristic"] = V - E + F

    max_shells = 2_000_000
    if nv and nv <= max_shells:
        _, shells = _union_find(nv, edges)
        out["shells"] = int(shells)
    else:
        out["shells"] = None

    out["watertight"] = (out["boundary_edges"] == 0 and
                         out["nonmanifold_edges"] == 0 and
                         out["degenerate_triangles"] == 0)

    ok = (out["size_consistent"] and out["nonfinite_vertices"] == 0 and n > 0)
    out["ok"] = bool(ok)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stl", action="append", default=[])
    ap.add_argument("--dir")
    ap.add_argument("--glob", default="*.stl")
    ap.add_argument("--report")
    ap.add_argument("--weld-eps", type=float, default=1e-3,
                    help="weld tolerance in file units (default 0.001 mm)")
    a = ap.parse_args()

    files = list(a.stl)
    if a.dir:
        files += sorted(str(p) for p in Path(a.dir).glob(a.glob))
    if not files:
        print("FATAL: no STL inputs (use --stl or --dir)")
        sys.exit(2)

    results = [analyse(f, a.weld_eps) for f in files]
    report = {"tool": "astra_verify_engine_export.py", "weld_eps_mm": a.weld_eps,
              "files": results, "all_ok": all(r["ok"] for r in results)}

    for r in results:
        print("\n== %s" % r["path"])
        print("   ok=%s bytes=%s tris=%s declared=%s size_consistent=%s" % (
            r["ok"], r.get("bytes"), r.get("triangles"),
            r.get("declared_triangles"), r.get("size_consistent")))
        if r.get("bbox_size"):
            print("   bbox_min=%s bbox_max=%s size=%s" % (
                r["bbox_min"], r["bbox_max"], r["bbox_size"]))
            print("   units_hint: %s" % r["units_hint"])
        print("   nonfinite=%s degenerate=%s zero_len_edges=%s" % (
            r.get("nonfinite_vertices"), r.get("degenerate_triangles"),
            r.get("zero_length_edges")))
        print("   welded_verts=%s boundary_edges=%s nonmanifold_edges=%s shells=%s euler=%s watertight=%s" % (
            r.get("welded_vertices"), r.get("boundary_edges"), r.get("nonmanifold_edges"),
            r.get("shells"), r.get("euler_characteristic"), r.get("watertight")))
        for e in r.get("errors", []):
            print("   ERROR: %s" % e)

    if a.report:
        Path(a.report).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("\nwrote %s" % a.report)
    sys.exit(0 if report["all_ok"] else 1)


if __name__ == "__main__":
    main()
