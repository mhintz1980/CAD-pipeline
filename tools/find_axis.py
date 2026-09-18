"""Report the dominant cylindrical axes of a STEP, via OCCT.

Finds the largest-radius / largest-area cylindrical faces and prints their axis
direction and a point on the axis. Used to identify a shaft or bore axis
without trusting a render.

    python find_axis.py FILE.step [--top N] [--min-r MM]
"""
import argparse, math, sys
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
ap.add_argument("file"); ap.add_argument("--top", type=int, default=14)
ap.add_argument("--min-r", type=float, default=10.0)
a = ap.parse_args()

app = XCAFApp_Application.GetApplication_s()
doc = TDocStd_Document(TCollection_ExtendedString("XmlXCAF"))
app.NewDocument(TCollection_ExtendedString("XmlXCAF"), doc)
r = STEPCAFControl_Reader(); r.SetNameMode(True); r.SetColorMode(True)
r.ReadFile(a.file); r.Transfer(doc)
st = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
roots = TDF_LabelSequence(); st.GetFreeShapes(roots)

rows = []
for i in range(1, roots.Length() + 1):
    sh = st.GetShape_s(roots.Value(i))
    ex = TopExp_Explorer(sh, TopAbs_FACE)
    while ex.More():
        f = TopoDS.Face(ex.Current())
        try:
            s = BRepAdaptor_Surface(f)
            t = s.GetType()
            if t == GeomAbs_SurfaceType.GeomAbs_Cylinder:
                cyl = s.Cylinder()
                ax = cyl.Axis()
                d = ax.Direction(); loc = ax.Location()
                props = GProp_GProps(); BRepGProp.SurfaceProperties_s(f, props)
                rows.append((cyl.Radius(), props.Mass(),
                             (d.X(), d.Y(), d.Z()), (loc.X(), loc.Y(), loc.Z())))
        except Exception:
            pass
        ex.Next()

rows = [x for x in rows if x[0] >= a.min_r]
rows.sort(key=lambda x: -x[1])            # by area
print(f"===== {a.file}  ({len(rows)} cylindrical faces >= {a.min_r} r) =====")
print(f"{'radius':>9} {'area_mm2':>12}  {'axis dir':>22}  point on axis")
seen = set()
for rad, area, d, loc in rows[:a.top]:
    key = tuple(round(v, 2) for v in d)
    print(f"{rad:9.2f} {area:12.1f}  ({d[0]:6.3f},{d[1]:6.3f},{d[2]:6.3f})  "
          f"({loc[0]:9.2f},{loc[1]:9.2f},{loc[2]:9.2f})")
    seen.add(key)
print("distinct axis directions among those:", len(seen))
