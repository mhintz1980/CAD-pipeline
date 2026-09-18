"""Find large planar faces whose normal is parallel to Y - i.e. discs/bosses facing
along the crank axis (flywheel, bell housing). Reports each face centroid in X-Z."""
import argparse
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
ap.add_argument("file"); ap.add_argument("--lim", type=float, default=3000.0)
ap.add_argument("--min-area", type=float, default=8000.0)
ap.add_argument("--top", type=int, default=16)
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
            if s.GetType() == GeomAbs_SurfaceType.GeomAbs_Plane:
                pl = s.Plane(); n = pl.Axis().Direction()
                if abs(n.Y()) > 0.99:
                    p = GProp_GProps(); BRepGProp.SurfaceProperties_s(TopoDS.Face(ex.Current()), p)
                    if p.Mass() >= a.min_area:
                        c = p.CentreOfMass()
                        if max(abs(c.X()), abs(c.Y()), abs(c.Z())) <= a.lim:
                            rows.append((p.Mass(), c.X(), c.Z(), c.Y(), n.Y()))
        except Exception:
            pass
        ex.Next()

rows.sort(key=lambda t: -t[0])
print(f"{a.file}: {len(rows)} Y-normal planar faces, area>={a.min_area:.0f}")
print(f"{'area':>11} {'X':>10} {'Z':>10} {'at Y':>10} {'n.Y':>6}")
for area, x, z, y, ny in rows[:a.top]:
    print(f"{area:11.0f} {x:10.1f} {z:10.1f} {y:10.1f} {ny:6.2f}")
