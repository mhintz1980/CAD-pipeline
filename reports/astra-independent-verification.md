# Independent verification - v9 to v10 controller relocation

**Date:** 2026-09-18 - **Verifier:** tools/astra_verify_v10.py (fresh-context, independent of producer code paths)
**Process:** Blender 5.1.1, --background --threads 4, both blends loaded sequentially in one process
**Exit code: 0 - VERDICT: PASS** (14/14 checks). Log: reports/astra-independent-verification.log
Full JSON: reports/astra-independent-verification.json

## Invocation (exact)
```
"C:/Program Files/Blender Foundation/Blender 5.1/blender.exe" --background --threads 4 --python tools/astra_verify_v10.py -- --baseline "C:/Projects/CAD/astra-engine-pump/out/engine-and-pump-v9.blend" --candidate "C:/Projects/CAD/astra-engine-pump/out/engine-and-pump-v10.blend" --report "C:/Projects/CAD/astra-engine-pump/reports/astra-independent-verification.json"
```

## Results
- Census: 468 meshes both files, 6 collections each, no unexpected additions.
- Controller: all 3 parts (MSP-CP-CP750E, PP-CPM-1001, PP-CPM-1005) moved by one shared pure translation **X -105.208, Y -94.638, Z -17.119 mm**; zero rotation (max inter-part delta 1.98e-07 m); mesh geometry bit-identical by SHA-256.
- Non-controller: all 465 other objects have unchanged matrices, bboxes, parents, collection membership, and material slots.
- Bracket height: PP-CPM-1005 bottom Z +246.86 mm, skid bottom -972.34 mm = **48.0000 in** (tolerance 0.02 in).
- Mating planes: upright LBU-PP.001 engine-side face n=(0, -0.9986, +0.052) vs bracket face n=(0, +0.9986, -0.0523): antiparallel to **0.0054 deg**, plane separation **0.052 mm**.
- Pump shaft 1207517913: digest, matrix, and bbox identical to v9.
- Quarantine: CAD_QUARANTINE_outliers absent from both v9 and v10 (already removed upstream; the allowed-removal condition was not exercised).

## Notes
- Two early FAILs were verifier-side face-selection bugs (the upright carries symmetric +/-Y, +/-z-tapered faces); fixed by explicitly targeting the handoff-documented normals (0, -1, +0.05) / (0, +1, -0.05). The final run is authoritative.
- Material data-block *contents* (shader nodes, colours) were not deep-compared - only per-object slot names were hashed, matching the parent's scope that all materials should be unchanged as scene metadata.
- No blend was saved; both files were opened read-only.
