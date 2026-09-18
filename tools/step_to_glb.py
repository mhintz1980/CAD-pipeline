#!/usr/bin/env python3
"""
step_to_glb.py - STEP -> OpenCascade XCAF -> tessellation -> GLB/glTF.

Uses the XCAF (extended CAF) document model, so the assembly tree, component
NAMES and per-occurrence TRANSFORMS survive into the glTF node hierarchy.
RWGltf_CafWriter consumes the XCAF document directly - no intermediate STL,
no flattening.

Presentation rule enforced here: we tessellate every FACE the kernel gives
us - solids, closed shells, open shells and free surfaces alike. Nothing is
dropped for failing a solid-validity test. Open shells are real visible
geometry in vendor CAD, not junk.

Instrumented: wall time per phase, peak working set, triangle counts.

    python step_to_glb.py --probe                      # 5s API smoke test
    python step_to_glb.py IN.step OUT.glb [options]

Options:
    --lin MM       linear deflection, model units (default 0.5)
    --ang DEG      angular deflection degrees (default 25)
    --parallel     multi-threaded meshing (default on)
    --inspect-only dump the XCAF tree + per-shape census, write no GLB
    --json PATH    write a machine-readable manifest
"""

from __future__ import annotations

import argparse
import ctypes
import json
import math
import os
import sys
import time

# ---------------------------------------------------------------- telemetry


class _MEMCOUNTERS(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_ulong),
        ("PageFaultCount", ctypes.c_ulong),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def mem_mb():
    """(current, peak) working set in MB. Windows; 0,0 elsewhere."""
    try:
        c = _MEMCOUNTERS()
        c.cb = ctypes.sizeof(c)
        k32 = ctypes.WinDLL("kernel32")
        fn = getattr(k32, "K32GetProcessMemoryInfo", None)
        if fn is None:
            fn = ctypes.WinDLL("psapi").GetProcessMemoryInfo
        fn.argtypes = [ctypes.c_void_p, ctypes.POINTER(_MEMCOUNTERS),
                       ctypes.c_ulong]
        fn.restype = ctypes.c_int
        if not fn(k32.GetCurrentProcess(), ctypes.byref(c), c.cb):
            return 0.0, 0.0
        return c.WorkingSetSize / 1e6, c.PeakWorkingSetSize / 1e6
    except Exception:
        return 0.0, 0.0


class Phase:
    log = []

    def __init__(self, name):
        self.name = name

    def __enter__(self):
        self.t = time.time()
        print(f"[ ] {self.name} ...", file=sys.stderr, flush=True)
        return self

    def __exit__(self, *a):
        dt = time.time() - self.t
        cur, peak = mem_mb()
        Phase.log.append(
            {"phase": self.name, "sec": round(dt, 2),
             "rss_mb": round(cur), "peak_mb": round(peak)}
        )
        print(
            f"[x] {self.name}: {dt:.1f}s  rss={cur:.0f}MB peak={peak:.0f}MB",
            file=sys.stderr, flush=True,
        )


# ---------------------------------------------------------------- OCCT glue

def _imports():
    from OCP.STEPCAFControl import STEPCAFControl_Reader
    from OCP.TDocStd import TDocStd_Document
    from OCP.TCollection import (
        TCollection_ExtendedString, TCollection_AsciiString,
    )
    from OCP.XCAFDoc import XCAFDoc_DocumentTool
    from OCP.XCAFApp import XCAFApp_Application
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.RWGltf import RWGltf_CafWriter
    from OCP.Message import Message_ProgressRange
    from OCP.RWMesh import RWMesh_CoordinateSystem, RWMesh_NameFormat
    from OCP.TDF import TDF_Label
    from OCP.collections import (
        Sequence_TDF_Label as TDF_LabelSequence,
        IndexedDataMap_TCollection_AsciiString_TCollection_AsciiString
        as TColStd_IndexedDataMapOfStringString,
    )
    from OCP.TDataStd import TDataStd_Name
    from OCP.TopoDS import TopoDS
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import (
        TopAbs_ShapeEnum, TopAbs_FACE, TopAbs_SOLID, TopAbs_SHELL,
        TopAbs_EDGE, TopAbs_VERTEX,
    )
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from OCP.Interface import Interface_Static
    from OCP.IFSelect import IFSelect_ReturnStatus
    from OCP.TopLoc import TopLoc_Location
    from OCP.BRep import BRep_Tool
    from OCP.TopoDS import TopoDS_Shape
    return locals()


G = None


def open_doc(path, verbose=True):
    """Read STEP into an XCAF document. Returns (doc, reader)."""
    g = G
    # Keep names + colours + layers. Colours are absent from AP203 but the
    # flags cost nothing and matter for AP214/242 sources.
    app = g["XCAFApp_Application"].GetApplication_s()
    doc = g["TDocStd_Document"](g["TCollection_ExtendedString"]("XmlXCAF"))
    app.NewDocument(g["TCollection_ExtendedString"]("XmlXCAF"), doc)

    rdr = g["STEPCAFControl_Reader"]()
    rdr.SetNameMode(True)
    rdr.SetColorMode(True)
    rdr.SetLayerMode(True)
    rdr.SetMatMode(True)
    rdr.SetPropsMode(True)

    st = rdr.ReadFile(path)
    if st != g["IFSelect_ReturnStatus"].IFSelect_RetDone:
        raise SystemExit(f"STEP read failed: status={st}")
    if not rdr.Transfer(doc):
        raise SystemExit("STEP transfer into XCAF failed")
    return doc, rdr


def census(shape):
    """Count topology in a shape without assuming validity."""
    g = G
    out = {}
    for key, enum in (
        ("solids", g["TopAbs_ShapeEnum"].TopAbs_SOLID),
        ("shells", g["TopAbs_ShapeEnum"].TopAbs_SHELL),
        ("faces", g["TopAbs_ShapeEnum"].TopAbs_FACE),
        ("edges", g["TopAbs_ShapeEnum"].TopAbs_EDGE),
    ):
        exp = g["TopExp_Explorer"](shape, enum)
        n = 0
        while exp.More():
            n += 1
            exp.Next()
        out[key] = n
    # open vs closed shells
    exp = g["TopExp_Explorer"](shape, g["TopAbs_ShapeEnum"].TopAbs_SHELL)
    op = cl = 0
    while exp.More():
        if exp.Current().Closed():
            cl += 1
        else:
            op += 1
        exp.Next()
    out["shells_closed"] = cl
    out["shells_open"] = op
    return out


def bbox(shape):
    g = G
    b = g["Bnd_Box"]()
    try:
        g["BRepBndLib"].Add_s(shape, b, True)
        if b.IsVoid():
            return None
        lo, hi = b.CornerMin(), b.CornerMax()
        xm, ym, zm = lo.X(), lo.Y(), lo.Z()
        xx, yx, zx = hi.X(), hi.Y(), hi.Z()
        return dict(
            min=[round(xm, 3), round(ym, 3), round(zm, 3)],
            max=[round(xx, 3), round(yx, 3), round(zx, 3)],
            size=[round(xx - xm, 3), round(yx - ym, 3), round(zx - zm, 3)],
            diag=round(math.dist((xm, ym, zm), (xx, yx, zx)), 3),
        )
    except Exception as e:
        return {"error": str(e)}


def walk_tree(doc, max_depth=8):
    """Free shapes + their component structure, with names and locations."""
    g = G
    st = g["XCAFDoc_DocumentTool"].ShapeTool_s(doc.Main())
    roots = g["TDF_LabelSequence"]()
    st.GetFreeShapes(roots)

    def label_name(lab):
        from OCP.TDataStd import TDataStd_Name
        nm = TDataStd_Name()
        if lab.FindAttribute(TDataStd_Name.GetID_s(), nm):
            return nm.Get().ToExtString()
        return "<unnamed>"

    out = []

    def rec(lab, depth, parent):
        nm = label_name(lab)
        ref = g["TDF_Label"]()
        is_ref = st.GetReferredShape_s(lab, ref)
        target = ref if is_ref else lab
        tname = label_name(target) if is_ref else nm
        node = {
            "depth": depth,
            "name": nm,
            "referred": tname if is_ref else None,
            "is_assembly": bool(st.IsAssembly_s(target)),
            "parent": parent,
        }
        try:
            loc = st.GetLocation_s(lab)
            tr = loc.Transformation()
            node["origin"] = [
                round(tr.TranslationPart().X(), 4),
                round(tr.TranslationPart().Y(), 4),
                round(tr.TranslationPart().Z(), 4),
            ]
        except Exception:
            node["origin"] = None
        if not node["is_assembly"]:
            try:
                sh = st.GetShape_s(target)
                node["census"] = census(sh)
                node["bbox_local"] = bbox(sh)
            except Exception as e:
                node["error"] = str(e)
        out.append(node)
        if depth < max_depth and st.IsAssembly_s(target):
            comps = g["TDF_LabelSequence"]()
            st.GetComponents_s(target, comps)
            for i in range(1, comps.Length() + 1):
                rec(comps.Value(i), depth + 1, tname)

    for i in range(1, roots.Length() + 1):
        rec(roots.Value(i), 0, None)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", nargs="?")
    ap.add_argument("output", nargs="?")
    ap.add_argument("--lin", type=float, default=0.5)
    ap.add_argument("--ang", type=float, default=25.0)
    ap.add_argument("--inspect-only", action="store_true")
    ap.add_argument("--json")
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--out-unit-m", type=float, default=1.0,
                    help="length of one output unit in metres "
                         "(1.0 = glTF metres convention)")
    ap.add_argument("--in-unit-m", type=float, default=0.001,
                    help="length of one OCCT internal unit in metres. "
                         "OCCT converts STEP to MM on read regardless of "
                         "the file unit, so 0.001 is correct even for an "
                         "inch STEP.")
    ap.add_argument("--in-axis", default="Z", choices=["Z", "Y"],
                    help="up-axis of the SOURCE model as it sits in the "
                         "STEP. Most CAD is Z-up, but an assembly whose "
                         "top-level occurrence rotates the whole machine "
                         "can land Y-up; if the result arrives in Blender "
                         "lying on its side, flip this.")
    ap.add_argument("--up", default="Y", choices=["Y", "Z"],
                    help="output up-axis. glTF convention is Y-up; "
                         "Blender's glTF importer converts it to Z-up.")
    a = ap.parse_args()

    global G
    with Phase("import OCP"):
        G = _imports()

    if a.probe:
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
        g = G
        app = g["XCAFApp_Application"].GetApplication_s()
        doc = g["TDocStd_Document"](g["TCollection_ExtendedString"]("XmlXCAF"))
        app.NewDocument(g["TCollection_ExtendedString"]("XmlXCAF"), doc)
        st = g["XCAFDoc_DocumentTool"].ShapeTool_s(doc.Main())
        box = BRepPrimAPI_MakeBox(10.0, 20.0, 30.0).Shape()
        lab = st.AddShape(box)
        from OCP.TDataStd import TDataStd_Name
        TDataStd_Name.Set_s(lab, g["TCollection_ExtendedString"]("ProbeBox"))
        g["BRepMesh_IncrementalMesh"](box, 0.5, False, 25.0 * math.pi / 180, True)
        out = os.path.join(os.path.dirname(__file__), "_probe.glb")
        w = g["RWGltf_CafWriter"](g["TCollection_AsciiString"](out), True)
        meta = g["TColStd_IndexedDataMapOfStringString"]()
        ok = w.Perform(doc, meta, g["Message_ProgressRange"]())
        print(f"PROBE ok={ok} bytes={os.path.getsize(out) if os.path.exists(out) else 0}")
        print("census(box):", census(box), "bbox:", bbox(box))
        return

    if not a.input:
        ap.error("input required")

    src_bytes = os.path.getsize(a.input)
    with Phase("STEP -> XCAF read+transfer"):
        doc, rdr = open_doc(a.input)

    with Phase("walk XCAF tree"):
        tree = walk_tree(doc)

    leaves = [n for n in tree if not n["is_assembly"]]
    tot = {}
    for n in leaves:
        for k, v in (n.get("census") or {}).items():
            tot[k] = tot.get(k, 0) + v
    print("\n== XCAF LEAF TOTALS ==", file=sys.stderr)
    print(json.dumps(tot, indent=1), file=sys.stderr)

    manifest = {
        "input": a.input,
        "input_bytes": src_bytes,
        "lin_deflection": a.lin,
        "ang_deflection_deg": a.ang,
        "leaf_totals": tot,
        "nodes": tree,
    }

    tri = 0
    if not a.inspect_only:
        g = G
        st = g["XCAFDoc_DocumentTool"].ShapeTool_s(doc.Main())
        roots = g["TDF_LabelSequence"]()
        st.GetFreeShapes(roots)
        with Phase(f"tessellate lin={a.lin} ang={a.ang}"):
            for i in range(1, roots.Length() + 1):
                sh = st.GetShape_s(roots.Value(i))
                g["BRepMesh_IncrementalMesh"](
                    sh, a.lin, False, a.ang * math.pi / 180.0, True
                )
        with Phase("count triangles"):
            for i in range(1, roots.Length() + 1):
                sh = st.GetShape_s(roots.Value(i))
                exp = g["TopExp_Explorer"](
                    sh, g["TopAbs_ShapeEnum"].TopAbs_FACE
                )
                while exp.More():
                    f = g["TopoDS"].Face(exp.Current())
                    loc = g["TopLoc_Location"]()
                    t = g["BRep_Tool"].Triangulation_s(f, loc)
                    if t is not None:
                        tri += t.NbTriangles()
                    exp.Next()
            print(f"    triangles={tri:,}", file=sys.stderr)

        with Phase(f"write GLB {a.output}"):
            w = g["RWGltf_CafWriter"](
                g["TCollection_AsciiString"](a.output), True
            )
            # OCCT works in mm and Z-up; glTF is metres and Y-up. Set this
            # explicitly - a silent 1000x or 25.4x scale error is the single
            # easiest way to lose a day downstream.
            cs = g["RWMesh_CoordinateSystem"]
            conv = w.ChangeCoordinateSystemConverter()
            conv.SetInputLengthUnit(a.in_unit_m)
            conv.SetOutputLengthUnit(a.out_unit_m)
            conv.SetInputCoordinateSystem(
                cs.RWMesh_CoordinateSystem_Zup if a.in_axis == "Z"
                else cs.RWMesh_CoordinateSystem_Yup
            )
            conv.SetOutputCoordinateSystem(
                cs.RWMesh_CoordinateSystem_Yup if a.up == "Y"
                else cs.RWMesh_CoordinateSystem_Zup
            )
            w.SetParallel(True)
            # XCAF occurrence labels are "NAUO18"-style; the human name lives
            # on the referred PRODUCT. Ask for the product name first so the
            # glTF nodes arrive in Blender as PP-LBB / MSP-CP-CP750E rather
            # than NAUO18, which is what makes downstream grouping possible.
            nf = g["RWMesh_NameFormat"]
            w.SetNodeNameFormat(nf.RWMesh_NameFormat_ProductOrInstance)
            w.SetMeshNameFormat(nf.RWMesh_NameFormat_ProductOrInstance)
            # Node names come from the XCAF labels, i.e. the STEP product
            # names - this is what keeps component identity into Blender.
            meta = g["TColStd_IndexedDataMapOfStringString"]()
            ok = w.Perform(doc, meta, g["Message_ProgressRange"]())
            if not ok:
                raise SystemExit("GLB write failed")
        manifest["output"] = a.output
        manifest["output_bytes"] = os.path.getsize(a.output)
        manifest["triangles"] = tri

    manifest["phases"] = Phase.log
    cur, peak = mem_mb()
    manifest["peak_rss_mb"] = round(peak)
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, indent=1)
        print(f"manifest -> {a.json}", file=sys.stderr)
    print(
        f"\nDONE  in={src_bytes/1e6:.1f}MB "
        + (f"out={manifest.get('output_bytes',0)/1e6:.1f}MB tri={tri:,} " if not a.inspect_only else "")
        + f"peak_rss={peak:.0f}MB",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
