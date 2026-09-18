#!/usr/bin/env python3
"""
step_assembly_map.py - stdlib-only ISO 10303-21 assembly + geometry mapper.

Answers, without a CAD kernel:
  * what products exist, and how the NAUO tree nests them
  * the placement transform of every assembly occurrence
  * per-product geometry census (solids / closed shells / open shells /
    surface models / faces / curve-only) and a local bounding box
  * units, schema, exporting system
  * which products are visually complete vs. interface-face-only husks

Written for the Astra CAD-to-Blender prep, 2026-09-17. Read-only: never
writes to, moves, or reinterprets the source file.

Usage:
    python step_assembly_map.py FILE.step --json out.json
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
from collections import defaultdict

# Entities that terminate a geometry walk cheaply (leaf numeric data).
_POINT = "CARTESIAN_POINT"
_DIR = "DIRECTION"

_REF_RE = re.compile(rb"#(\d+)")
_NUM_RE = re.compile(rb"-?\d+\.?\d*(?:[EeDd][-+]?\d+)?")

# Geometry buckets we census per product.
BUCKETS = (
    "MANIFOLD_SOLID_BREP",
    "BREP_WITH_VOIDS",
    "CLOSED_SHELL",
    "OPEN_SHELL",
    "SHELL_BASED_SURFACE_MODEL",
    "GEOMETRIC_CURVE_SET",
    "ADVANCED_FACE",
    "FACE_SURFACE",
    "B_SPLINE_SURFACE_WITH_KNOTS",
    "PLANE",
    "CYLINDRICAL_SURFACE",
    "CONICAL_SURFACE",
    "TOROIDAL_SURFACE",
    "SPHERICAL_SURFACE",
)


def _split_top_level(body: bytes):
    """Split a STEP argument list on top-level commas."""
    out, depth, cur, instr = [], 0, bytearray(), False
    i = 0
    while i < len(body):
        c = body[i : i + 1]
        if instr:
            cur += c
            if c == b"'":
                # '' is an escaped quote inside a STEP string
                if body[i + 1 : i + 2] == b"'":
                    cur += b"'"
                    i += 2
                    continue
                instr = False
        elif c == b"'":
            instr = True
            cur += c
        elif c == b"(":
            depth += 1
            cur += c
        elif c == b")":
            depth -= 1
            cur += c
        elif c == b"," and depth == 0:
            out.append(bytes(cur))
            cur = bytearray()
        else:
            cur += c
        i += 1
    out.append(bytes(cur))
    return out


def _unquote(tok: bytes) -> str:
    tok = tok.strip()
    if tok.startswith(b"'") and tok.endswith(b"'"):
        tok = tok[1:-1]
    return tok.decode("latin-1").replace("''", "'")


def parse(path: str, verbose=True):
    """One streaming pass. Returns (ents, points, header_lines)."""
    ents = {}  # id -> (type:str, body:bytes)
    points = {}  # id -> (x, y, z)
    dirs = {}  # id -> (x, y, z)
    header = []

    t0 = time.time()
    buf = bytearray()
    in_data = False
    nbytes = 0

    with open(path, "rb") as fh:
        for raw in fh:
            nbytes += len(raw)
            s = raw.strip()
            if not in_data:
                header.append(s.decode("latin-1", "replace"))
                if s.startswith(b"DATA"):
                    in_data = True
                continue
            buf += s
            # A record ends at ';'
            while True:
                semi = buf.find(b";")
                if semi < 0:
                    break
                rec = bytes(buf[:semi])
                del buf[: semi + 1]
                if not rec.startswith(b"#"):
                    continue
                eq = rec.find(b"=")
                if eq < 0:
                    continue
                try:
                    eid = int(rec[1:eq])
                except ValueError:
                    continue
                rhs = rec[eq + 1 :].lstrip()
                if rhs.startswith(b"("):
                    # complex entity: ( A(..) B(..) ) -> keep all type names
                    names = re.findall(rb"([A-Z_0-9]+)\s*\(", rhs)
                    ents[eid] = ("|".join(n.decode() for n in names), rhs)
                    continue
                paren = rhs.find(b"(")
                if paren < 0:
                    continue
                etype = rhs[:paren].strip().decode("latin-1")
                body = rhs[paren + 1 : rhs.rfind(b")")]
                if etype == _POINT:
                    nums = _NUM_RE.findall(body)
                    if len(nums) >= 3:
                        try:
                            points[eid] = tuple(
                                float(n.replace(b"D", b"E")) for n in nums[-3:]
                            )
                        except ValueError:
                            pass
                    continue
                if etype == _DIR:
                    nums = _NUM_RE.findall(body)
                    if len(nums) >= 3:
                        try:
                            dirs[eid] = tuple(
                                float(n.replace(b"D", b"E")) for n in nums[-3:]
                            )
                        except ValueError:
                            pass
                    continue
                ents[eid] = (etype, body)

    if verbose:
        print(
            f"  parsed {nbytes/1e6:.1f} MB  {len(ents):,} entities  "
            f"{len(points):,} points  in {time.time()-t0:.1f}s",
            file=sys.stderr,
        )
    return ents, points, dirs, header


def refs(body: bytes):
    return [int(m) for m in _REF_RE.findall(body)]


def build(path: str):
    ents, points, dirs, header = parse(path)
    by_type = defaultdict(list)
    for eid, (t, _) in ents.items():
        by_type[t].append(eid)

    # ---- products -------------------------------------------------------
    prod_name = {}
    for eid in by_type.get("PRODUCT", []):
        args = _split_top_level(ents[eid][1])
        prod_name[eid] = _unquote(args[1]) if len(args) > 1 else _unquote(args[0])

    # PRODUCT_DEFINITION_FORMATION* -> product
    pdf_to_prod = {}
    for t in list(by_type):
        if t.startswith("PRODUCT_DEFINITION_FORMATION"):
            for eid in by_type[t]:
                r = [x for x in refs(ents[eid][1]) if x in prod_name]
                if r:
                    pdf_to_prod[eid] = r[0]

    # PRODUCT_DEFINITION -> product
    pd_to_prod = {}
    for eid in by_type.get("PRODUCT_DEFINITION", []):
        for r in refs(ents[eid][1]):
            if r in pdf_to_prod:
                pd_to_prod[eid] = pdf_to_prod[r]
                break

    # PRODUCT_DEFINITION_SHAPE -> product_definition
    pds_to_pd = {}
    for eid in by_type.get("PRODUCT_DEFINITION_SHAPE", []):
        for r in refs(ents[eid][1]):
            if r in pd_to_prod:
                pds_to_pd[eid] = r
                break

    # A *plain* SHAPE_REPRESENTATION_RELATIONSHIP links a product's base
    # SHAPE_REPRESENTATION to the rep that actually holds its geometry
    # (ADVANCED_BREP_SHAPE_REPRESENTATION / MANIFOLD_SURFACE_SHAPE_REPRESENTATION).
    # The *complex* form (...WITH_TRANSFORMATION...) is an assembly occurrence
    # link and must NOT be followed, or children leak into the parent census.
    geom_rep_types = (
        "ADVANCED_BREP_SHAPE_REPRESENTATION",
        "MANIFOLD_SURFACE_SHAPE_REPRESENTATION",
        "GEOMETRICALLY_BOUNDED_SURFACE_SHAPE_REPRESENTATION",
        "GEOMETRICALLY_BOUNDED_WIREFRAME_SHAPE_REPRESENTATION",
    )
    srr_link = defaultdict(list)
    for eid in by_type.get("SHAPE_REPRESENTATION_RELATIONSHIP", []):
        r = refs(ents[eid][1])
        base = [x for x in r if x in ents and ents[x][0] == "SHAPE_REPRESENTATION"]
        geom = [x for x in r if x in ents and ents[x][0] in geom_rep_types]
        for b in base:
            for g in geom:
                srr_link[b].append(g)

    # SHAPE_DEFINITION_REPRESENTATION(#pds, #rep) -> product -> rep(s)
    prod_rep = {}
    for eid in by_type.get("SHAPE_DEFINITION_REPRESENTATION", []):
        r = refs(ents[eid][1])
        pds = next((x for x in r if x in pds_to_pd), None)
        rep = next(
            (x for x in r if x in ents and "REPRESENTATION" in ents[x][0]), None
        )
        if pds is not None and rep is not None:
            prod = pd_to_prod[pds_to_pd[pds]]
            prod_rep.setdefault(prod, []).append(rep)
            prod_rep[prod].extend(srr_link.get(rep, []))

    # ---- assembly tree (NAUO) -------------------------------------------
    nauo = {}
    edges = []
    for eid in by_type.get("NEXT_ASSEMBLY_USAGE_OCCURRENCE", []):
        args = _split_top_level(ents[eid][1])
        r = [x for x in refs(ents[eid][1]) if x in pd_to_prod]
        if len(r) >= 2:
            parent, child = pd_to_prod[r[0]], pd_to_prod[r[1]]
            tag = _unquote(args[1]) if len(args) > 1 else ""
            nauo[eid] = (parent, child, tag)
            edges.append((parent, child, tag, eid))

    # ---- occurrence transforms ------------------------------------------
    # CONTEXT_DEPENDENT_SHAPE_REPRESENTATION(#rep_rel, #pds) where the pds
    # belongs to the NAUO; the rep_rel carries ITEM_DEFINED_TRANSFORMATION.
    def axis_placement(eid):
        """AXIS2_PLACEMENT_3D -> (origin, z_axis, x_axis)"""
        if eid not in ents:
            return None
        r = refs(ents[eid][1])
        o = next((x for x in r if x in points), None)
        ax = [x for x in r if x in dirs]
        return (
            points.get(o, (0.0, 0.0, 0.0)),
            dirs.get(ax[0], (0.0, 0.0, 1.0)) if len(ax) > 0 else (0.0, 0.0, 1.0),
            dirs.get(ax[1], (1.0, 0.0, 0.0)) if len(ax) > 1 else (1.0, 0.0, 0.0),
        )

    idt = {}
    for eid in by_type.get("ITEM_DEFINED_TRANSFORMATION", []):
        r = refs(ents[eid][1])
        if len(r) >= 2:
            idt[eid] = (axis_placement(r[0]), axis_placement(r[1]))

    # nauo entity id -> transform, via CDSR -> PDS(of nauo)
    pds_of_nauo = {}
    for eid in by_type.get("PRODUCT_DEFINITION_SHAPE", []):
        for r in refs(ents[eid][1]):
            if r in nauo:
                pds_of_nauo[eid] = r

    nauo_xform = {}
    for eid in by_type.get("CONTEXT_DEPENDENT_SHAPE_REPRESENTATION", []):
        r = refs(ents[eid][1])
        nid = next((pds_of_nauo[x] for x in r if x in pds_of_nauo), None)
        if nid is None:
            continue
        for x in r:
            if x in ents:
                sub = refs(ents[x][1])
                hit = next((y for y in sub if y in idt), None)
                if hit:
                    nauo_xform[nid] = idt[hit]
                    break

    # ---- per-product geometry census + local bbox ------------------------
    owner = {}  # entity id -> product id  (first claim wins)
    census = {p: defaultdict(int) for p in prod_name}
    bbox = {p: None for p in prod_name}
    shared = defaultdict(int)

    for prod, reps in prod_rep.items():
        stack = list(reps)
        lo = [math.inf] * 3
        hi = [-math.inf] * 3
        cols = ([], [], [])
        seen_local = set()
        while stack:
            eid = stack.pop()
            if eid in seen_local:
                continue
            seen_local.add(eid)
            if eid in points:
                p = points[eid]
                for i in range(3):
                    v = p[i]
                    if v < lo[i]:
                        lo[i] = v
                    if v > hi[i]:
                        hi[i] = v
                    cols[i].append(v)
                continue
            if eid in dirs:
                continue
            e = ents.get(eid)
            if e is None:
                continue
            etype, body = e
            if eid in owner and owner[eid] != prod:
                shared[prod] += 1
            else:
                owner[eid] = prod
                for part in etype.split("|"):
                    if part in BUCKETS:
                        census[prod][part] += 1
            # Do not descend through assembly-occurrence links, or a parent
            # would absorb every child's geometry. Substring test because the
            # occurrence link is a complex entity ("A|B|C").
            if (
                "REPRESENTATION_RELATIONSHIP" in etype
                or "CONTEXT_DEPENDENT_SHAPE_REPRESENTATION" in etype
                or "NEXT_ASSEMBLY_USAGE_OCCURRENCE" in etype
            ):
                continue
            stack.extend(refs(body))
        if lo[0] != math.inf:
            # Raw min/max is easily poisoned by a handful of stray construction
            # points (B-spline control hulls, dangling placements). The p1/p99
            # box is what actually corresponds to visible material, so report
            # both and let the reader see the spread.
            rlo, rhi = [0.0] * 3, [0.0] * 3
            for i in range(3):
                col = sorted(cols[i])
                n = len(col)
                rlo[i] = col[max(0, int(n * 0.01))]
                rhi[i] = col[min(n - 1, int(n * 0.99))]
            bbox[prod] = {
                "min": [round(v, 4) for v in lo],
                "max": [round(v, 4) for v in hi],
                "size": [round(hi[i] - lo[i], 4) for i in range(3)],
                "diag": round(
                    math.sqrt(sum((hi[i] - lo[i]) ** 2 for i in range(3))), 3
                ),
                "robust_min": [round(v, 4) for v in rlo],
                "robust_max": [round(v, 4) for v in rhi],
                "robust_diag": round(
                    math.sqrt(sum((rhi[i] - rlo[i]) ** 2 for i in range(3))), 3
                ),
                "n_points": len(cols[0]),
            }

    # ---- units ----------------------------------------------------------
    units = []
    for t in list(by_type):
        if "UNIT" in t and ("LENGTH_UNIT" in t or "SI_UNIT" in t):
            for eid in by_type[t][:40]:
                units.append(ents[eid][1].decode("latin-1", "replace")[:120])
    # A CONVERSION_BASED_UNIT names the unit and points at a
    # LENGTH_MEASURE_WITH_UNIT holding the factor to SI (25.4 for inch).
    conv_names, conv_factor = set(), None
    for t in list(by_type):
        if "CONVERSION_BASED_UNIT" in t:
            for eid in by_type[t]:
                args = _split_top_level(ents[eid][1])
                for tok in args:
                    if b"'" in tok:
                        conv_names.add(_unquote(tok).upper())
                        break
                for r in refs(ents[eid][1]):
                    e = ents.get(r)
                    if e and e[0] == "LENGTH_MEASURE_WITH_UNIT":
                        n = _NUM_RE.findall(e[1])
                        if n:
                            try:
                                conv_factor = float(n[0].replace(b"D", b"E"))
                            except ValueError:
                                pass
    unit_blob = " ".join(units).upper()
    if conv_names:
        unit_guess = (
            f"{'/'.join(sorted(conv_names))} "
            f"(conversion factor to mm = {conv_factor})"
        )
    elif ".MILLI." in unit_blob and "METRE" in unit_blob:
        unit_guess = "MILLIMETRE"
    elif "METRE" in unit_blob:
        unit_guess = "METRE"
    else:
        unit_guess = "UNKNOWN"

    return dict(
        header=header,
        prod_name=prod_name,
        prod_rep=prod_rep,
        edges=edges,
        nauo=nauo,
        nauo_xform=nauo_xform,
        census=census,
        bbox=bbox,
        shared=shared,
        unit_guess=unit_guess,
        by_type={k: len(v) for k, v in by_type.items()},
        ents_total=len(ents),
        points_total=len(points),
    )


def classify(name: str, c: dict) -> str:
    """Heuristic verdict on whether a product is renderable as-is."""
    solids = c.get("MANIFOLD_SOLID_BREP", 0) + c.get("BREP_WITH_VOIDS", 0)
    closed = c.get("CLOSED_SHELL", 0)
    openish = c.get("OPEN_SHELL", 0)
    faces = c.get("ADVANCED_FACE", 0) + c.get("FACE_SURFACE", 0)
    if solids or closed:
        if openish > max(20, faces * 0.5):
            return "SOLID+LOOSE_SURFACES"
        return "SOLID (renderable)"
    if openish and faces:
        # loose faces, no solid: interface husk or true surface body
        if openish > 50 and faces / max(openish, 1) < 1.6:
            return "INTERFACE_HUSK (loose faces - NOT visually complete)"
        return "SURFACE_BODY (tessellate as sheet)"
    if faces:
        return "FACES_ONLY"
    return "NO_GEOMETRY (assembly node or empty)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--json")
    a = ap.parse_args()

    print(f"Mapping {a.file} ...", file=sys.stderr)
    m = build(a.file)

    name = m["prod_name"]
    inv = {v: k for k, v in name.items()}
    child_count = defaultdict(int)
    for p, c, tag, _ in m["edges"]:
        child_count[p] += 1
    roots = [p for p in name if child_count[p] and not any(
        c == p for _, c, _, _ in m["edges"])]

    print()
    print(f"UNITS: {m['unit_guess']}")
    print(f"entities={m['ents_total']:,} points={m['points_total']:,}")
    print(f"products={len(name)} nauo_edges={len(m['edges'])} "
          f"transforms_resolved={len(m['nauo_xform'])}")
    print(f"roots: {[name[r] for r in roots]}")

    print("\n== PRODUCT CENSUS ==")
    hdr = f"{'product':44} {'solid':>5} {'clsd':>5} {'open':>5} {'face':>6} {'diag_mm':>9}  verdict"
    print(hdr)
    print("-" * len(hdr))
    rows = []
    for pid, nm in sorted(name.items(), key=lambda kv: kv[1].lower()):
        c = m["census"][pid]
        bb = m["bbox"][pid]
        verdict = classify(nm, c)
        rows.append((nm, dict(c), bb, verdict))
        print(
            f"{nm[:44]:44} "
            f"{c.get('MANIFOLD_SOLID_BREP',0):>5} "
            f"{c.get('CLOSED_SHELL',0):>5} "
            f"{c.get('OPEN_SHELL',0):>5} "
            f"{c.get('ADVANCED_FACE',0)+c.get('FACE_SURFACE',0):>6} "
            f"{(bb['diag'] if bb else 0):>9.1f}  {verdict}"
        )

    print("\n== ASSEMBLY TREE (NAUO) ==")
    kids = defaultdict(list)
    for p, c, tag, eid in m["edges"]:
        kids[p].append((c, tag, eid))

    def walk(p, depth, seen):
        if depth > 6 or p in seen:
            return
        for c, tag, eid in sorted(kids.get(p, []), key=lambda t: t[1]):
            xf = m["nauo_xform"].get(eid)
            org = xf[0][0] if xf and xf[0] else None
            loc = (
                f"  @({org[0]:.1f},{org[1]:.1f},{org[2]:.1f})" if org else "  @?"
            )
            print("  " * depth + f"- {name.get(c,'?')}  [{tag}]{loc}")
            walk(c, depth + 1, seen | {p})

    for r in roots:
        print(f"* {name[r]}")
        walk(r, 1, set())

    if a.json:
        out = {
            "file": a.file,
            "units": m["unit_guess"],
            "entities": m["ents_total"],
            "points": m["points_total"],
            "products": [
                {
                    "name": nm,
                    "census": c,
                    "bbox_local": bb,
                    "verdict": v,
                }
                for nm, c, bb, v in rows
            ],
            "tree": [
                {
                    "parent": name.get(p),
                    "child": name.get(c),
                    "tag": tag,
                    "origin": (
                        m["nauo_xform"][eid][0][0]
                        if eid in m["nauo_xform"] and m["nauo_xform"][eid][0]
                        else None
                    ),
                    "z_axis": (
                        m["nauo_xform"][eid][0][1]
                        if eid in m["nauo_xform"] and m["nauo_xform"][eid][0]
                        else None
                    ),
                    "x_axis": (
                        m["nauo_xform"][eid][0][2]
                        if eid in m["nauo_xform"] and m["nauo_xform"][eid][0]
                        else None
                    ),
                }
                for p, c, tag, eid in m["edges"]
            ],
            "entity_counts": m["by_type"],
            "header": m["header"][:25],
        }
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=1)
        print(f"\njson -> {a.json}")


if __name__ == "__main__":
    main()
