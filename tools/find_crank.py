"""Find cylinders whose axis is parallel to Y near the machine (the crank/flywheel
axis). Reports axis line position in X-Z so the pump can be centred on it.

    python find_crank.py FILE.step --lo Y0 --hi Y1 --min-r R
"""
import argparse, math
from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.TDocStd import TDocStd_Document
from OCP.TCollection import TCollection_ExtendedString
from OCP.XCAFDoc import XCAFDoc_DocumentTool
from OCP.XCAFApp import XCAFApp_Application
from OCP.collections import Sequence_TDF_Label as TDF_LabelSequence
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE
from OCP.TopoDS import TopoDS
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_SurfaceType
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps

ap = argparse.ArgumentParser()
ap.add_argument("file")
ap.add_argument("--lim", type=float, default=3000.0, help="ignore geometry beyond +/-lim")
ap.add_argument("--min-r", type=float, default=60.0)
ap.add_argument("--top", type=int, default=20)
a = ap.parse_args()

app = XCAFApp_Application.GetApplication_s()
doc = TDocStd_Document(TCollection_ExtendedString("XmlXCAF"))
app.NewDocument(TCollection_ExtendedString("XmlXCAF"), doc)
r = STEPCAFControl_Reader(); r.SetNameMode(True); r.ReadFile(a.file); r.Transfer(doc)
st = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
roots = TDF_LabelSequence(); st.GetFreeShapes(roots)

rows = []
for i in range(1, roots.Length() + 1):
    ex = TopExp_Explorer(st.GetShape_s(roots.Value(i)), TopAbs_FACE)
    while ex.More():
        try:
            s = BRepAdaptor_Surface(TopoDS.Face(ex.Current()))
            if s.GetType() == GeomAbs_SurfaceType.GeomAbs_Cylinder:
                c = s.Cylinder(); ax = c.Axis(); d = ax.Direction(); l = ax.Location()
                if abs(d.Y()) > 0.99 and max(abs(l.X()), abs(l.Y()), abs(l.Z())) <= a.lim \
                   and c.Radius() >= a.min_r:
                    p = GProp_GProps(); BRepGProp.SurfaceProperties_s(TopoDS.Face(ex.Current()), p)
                    rows.append((c.Radius(), p.Mass(), l.X(), l.Z(), l.Y(), d.Y()))
        except Exception:
            pass
        ex.Next()

rows.sort(key=lambda t: -t[1])
print(f"{a.file}: {len(rows)} Y-parallel cylinders, r>={a.min_r}, within +/-{a.lim:.0f}")
print(f"{'radius':>9} {'area':>11} {'axis X':>10} {'axis Z':>10} {'at Y':>10}")
for rad, area, lx, lz, ly, dy in rows[:a.top]:
    print(f"{rad:9.1f} {area:11.0f} {lx:10.1f} {lz:10.1f} {ly:10.1f}")
