"""Summarise cylinder axis directions in a STEP, grouped, ignoring far geometry."""
import sys, math
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

f = sys.argv[1]
lim = float(sys.argv[2]) if len(sys.argv) > 2 else 3000.0   # ignore geometry beyond +/-lim
app = XCAFApp_Application.GetApplication_s()
doc = TDocStd_Document(TCollection_ExtendedString("XmlXCAF"))
app.NewDocument(TCollection_ExtendedString("XmlXCAF"), doc)
rd = STEPCAFControl_Reader(); rd.SetNameMode(True); rd.ReadFile(f); rd.Transfer(doc)
st = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
roots = TDF_LabelSequence(); st.GetFreeShapes(roots)

groups = {}
near = 0; far = 0
for i in range(1, roots.Length() + 1):
    sh = st.GetShape_s(roots.Value(i))
    ex = TopExp_Explorer(sh, TopAbs_FACE)
    while ex.More():
        try:
            s = BRepAdaptor_Surface(TopoDS.Face(ex.Current()))
            if s.GetType() == GeomAbs_SurfaceType.GeomAbs_Cylinder:
                ax = s.Cylinder().Axis(); d = ax.Direction(); l = ax.Location()
                if max(abs(l.X()), abs(l.Y()), abs(l.Z())) > lim:
                    far += 1
                else:
                    near += 1
                    p = GProp_GProps(); BRepGProp.SurfaceProperties_s(TopoDS.Face(ex.Current()), p)
                    key = (round(abs(d.X()), 2), round(abs(d.Y()), 2), round(abs(d.Z()), 2))
                    g = groups.setdefault(key, {"n": 0, "rmin": 1e9, "rmax": 0, "area": 0.0})
                    g["n"] += 1
                    r = s.Cylinder().Radius()
                    g["rmin"] = min(g["rmin"], r); g["rmax"] = max(g["rmax"], r)
                    g["area"] += p.Mass()
        except Exception:
            pass
        ex.Next()

print(f"{f}")
print(f"  cylinders near origin (<= {lim:.0f}): {near}   far/outlier: {far}")
print(f"  {'|axis| dir':>22} {'count':>7} {'r_min':>9} {'r_max':>9} {'area':>12}")
for k, g in sorted(groups.items(), key=lambda kv: -kv[1]["area"]):
    print(f"  ({k[0]:5.2f},{k[1]:5.2f},{k[2]:5.2f}) {g['n']:7d} {g['rmin']:9.1f} {g['rmax']:9.1f} {g['area']:12.0f}")
