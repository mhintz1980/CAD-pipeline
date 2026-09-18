# Astra decision on inspection H2 — preserve the plate/upright interface

Supersedes the earlier instruction to keep DOUBLER and DOUBLER.001 entirely fixed. The inspection reports a real 0mm plate/upright interface that would open by27.85mm if the plates stayed unchanged.

Extend BOTH doubler plates at their outboard ends by76.2mm each, while leaving the entire central engine-support footprint fixed. Engine mount PP12-EM-JD18 occupies X[-635.001,+635.001]mm; EM-SP supports are within +/-448.2mm. Doubler curved end features begin around |X|=698mm. Candidate cut planes X=-665,+665mm are outside the fixed engine footprint and inside the straight plate span before its end fillets. Verify those two cuts directly from actual source faces and curved transverse features; the inspection's listed bands omit some short gaps. If either cut crosses a feature, choose another verified plane between |X|640 and690mm, preserving ALL geometry within |X|635.5mm.

Use the same world-X end-extension method as other members, with Y/Z and topology preserved. Original doubler bbox centre stays where it is (near0mm); do not recenter it to the +59mm sidewall datum. Do not move or stretch the engine mount plates or any engine part.

Updated expected counts:23 rigid translated meshes,17 lengthened meshes,428 entirely fixed meshes; total468. Other15 lengthened members keep nominal cutplanes -680,+798mm. DOUBLER pair use their own explicit safe cuts. Independently check the moved left-upright contact against extended DOUBLER.001 and unchanged central mount footprint. Do not accept a new gap or silently move mounting holes.
