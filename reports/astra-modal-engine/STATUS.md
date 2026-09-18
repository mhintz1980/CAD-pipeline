# STATUS - JOB COMPLETED 14:11 EDT (deadline 14:44)
## Results: run-20260918T140853
- App ap-6ViotFIVYEcYiZVTRHDiDX, fn run_export, L4/OPTIX, 16/16 CPU, 64GiB, 81s remote
- Source SHA verified locally AND in cloud: 5f8632d8...5f5e6f (unchanged)
- engine-detailed.stl 499,996 tris (25MB) / engine-light.stl 199,998 tris (10MB) - targets hit
- engine-cleaned.blend 17.1MB, units mm-baked scale_length=0.001
- bbox asserted close to expected [-835.7..838.2] X mm; independent STL readback OK (reports/astra-engine-review-stl-readback.json)
- PROTECTED (full-res): EM-SP* + PP12-EM-JD18; DECIMATED: COMPOUND + COMPOUND.001 - correct orientation
- Receipt: reports/astra-modal-engine/receipt.json; all artifacts downloaded to reports/astra-modal-engine/run-20260918T140853/
## Limitation
- engine-preview.png FAILED ("Cannot render, no camera") - export-script staging bug (producer seat), not wrapper. All other deliverables complete. GPU evidence: nvidia-smi.txt + render_gpu OPTIX/NVIDIA L4 in JSON.

## REV4 RUN COMPLETE 14:19 EDT - run-20260918T141702
- App ap-5nQEdu1JOSOSNKFohnvtvf, 83s remote, L4 OPTIX
- engine-preview.png: REAL PNG 1000x800 RGBA 1,020,672 B rendered on OPTIX/NVIDIA L4
- detailed 499,998 tris 25.0MB; light 350,000 tris 17.5MB
- COMPOUND (360 tri) protected exact; only COMPOUND.001 decimated
- rev3 run-20260918T140853 preserved immutable
