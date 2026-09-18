"""Locate the engine's rear (SAE) flange face in the scene: the big Y-normal
planar disc at the +Y end of the engine. Uses numpy on the raw mesh for speed."""
import bpy, sys
import numpy as np
from mathutils import Vector

lo_y = -5.0   # search below this world Y (set from engine max Y)
for o in bpy.data.objects:
    if o.type != "MESH" or "CAD_engine" not in [c.name for c in o.users_collection]:
        continue
    me = o.data
    n = len(me.polygons)
    if n == 0:
        continue
    nrm = np.empty(n * 3, dtype=np.float32)
    cen = np.empty(n * 3, dtype=np.float32)
    me.polygons.foreach_get("normal", nrm)
    me.polygons.foreach_get("center", cen)
    nrm = nrm.reshape(n, 3); cen = cen.reshape(n, 3)
    mw = np.array(o.matrix_world)
    R = mw[:3, :3]; T = mw[:3, 3]
    wn = nrm @ R.T
    wc = cen @ R.T + T
    # world Y facing, at the +Y end of the engine
    m = (wn[:, 1] > 0.985) & (wc[:, 1] > 0.35)
    print(f"\n=== {o.name}: {n:,} polys, {m.sum():,} facing +Y beyond Y=0.35 m")
    if m.sum() == 0:
        continue
    sel = wc[m]
    print(f"  Y range of selected: {sel[:,1].min():.3f} .. {sel[:,1].max():.3f} m")
    # cluster by Y for the largest plane
    for ylo, yhi in [(0.45, 0.55), (0.50, 0.60), (0.35, 0.45), (0.55, 0.70)]:
        mm = m & (wc[:, 1] >= ylo) & (wc[:, 1] < yhi)
        if mm.sum() < 50:
            continue
        c = wc[mm]
        print(f"  band Y[{ylo:.2f},{yhi:.2f}): {mm.sum():,} faces  "
              f"centroid X={c[:,0].mean()*1000:+8.1f} Z={c[:,2].mean()*1000:+8.1f} mm  "
              f"Xspan={(c[:,0].max()-c[:,0].min())*1000:7.1f} Zspan={(c[:,2].max()-c[:,2].min())*1000:7.1f} mm")
