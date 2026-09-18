# Astra Engine Export (mesh reference, rev 4)

Units: **millimetres** (source world metres converted via scale_length*1000; assembly
origin & orientation preserved; bbox asserted against expected engine bounds).
Source: `engine-and-pump-v10.blend`, collection `CAD_engine` (7 meshes). Pump/skid/bale excluded.

## Recommended file for reference
- `engine-detailed.stl` - binary STL, 499998 tris (~25 MB), sampled max deviation 1.548 mm. Recommended for reference/measurement; still a mesh, NOT an analytic solid.

## Files
- `engine-cleaned.blend` - engine bodies only, mm world coords (unit scale 0.001);
  all non-decimated bodies (PP12-EM-JD18, EM-SP, EM-SP.001, EM-SP.002, EM-SP.003, COMPOUND) preserved coordinate-exact.
- `engine-detailed.stl` - binary STL, 499998 tris (target 500000), ~25 MB.
- `engine-light.stl` - binary STL, 350000 tris (~17.5 MB). **VISUAL-ONLY**: measured sampled max deviation 10.421 mm (> 3 mm) - NOT for fit/clearance.
- `engine-preview.png` - 1000x800 Cycles preview (GPU/CPU evidence in JSON).
- `astra-engine-export.json` - topology before/after, deviations, STL validation, GPU evidence.

## SolidWorks import (native import NOT yet tested by this pipeline)
- Use File > Open, select the STL, then set Options units = millimetres.
- Import as **Graphics Body**, or as a mesh/BREP if your SolidWorks version offers it.
- Do NOT accept the default conventional facet-per-face Solid Body conversion; it is
  unsuitable for this large open assembly mesh.
- The .blend can be appended for individual bodies (unit scale 0.001 = mm).

## Limitations
These STL files are mesh/graphics references: NOT analytic solids and NOT watertight.
The source is an OPEN vendor mesh; bores/ports are NOT filled and no voxel clearance
fill was performed. Cleanup/decimation leave open boundaries and introduce non-manifold
edges (see astra-engine-export.json mesh_quality). Defects REMAIN - this is not a
healed solid. Deviations are deterministic BVH-sample estimates, not certified Hausdorff.
