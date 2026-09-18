# Astra Engine Export (cleaned mesh reference, rev 3)

Units: **millimetres** (source world metres converted via scale_length*1000; assembly
origin & orientation preserved; bbox asserted against expected engine bounds).
Source: `engine-and-pump-v10.blend`, collection `CAD_engine` (7 meshes). Pump/skid/bale excluded.

## Files
- `engine-cleaned.blend` - engine bodies only, mm world coords (unit scale 0.001);
  mount/interface bodies (PP12-EM-JD18, EM-SP, EM-SP.001, EM-SP.002, EM-SP.003) at FULL resolution, untouched.
- `engine-detailed.stl` - binary STL, 499996 tris (target 500000).
- `engine-light.stl` - binary STL, 199998 tris (target 200000).
- `engine-preview.png` - 1000x800 Cycles preview (OPTIX/CUDA evidence in JSON, honest CPU fallback).
- `astra-engine-export.json` - topology before/after both variants, deviations, STL validation, GPU evidence.

## Import notes
- STL: File > Import > STL (binary). Values are millimetres; apply no extra scaling.
- .blend: unit scale is 0.001 (mm); Append > Collection `ENGINE_EXPORT` for individual bodies.

## Limitations
Graphics/mesh reference only - NOT an analytic solid, NOT watertight. Intentional bores
and open ports remain open. Deviations are deterministic BVH-sample estimates.
