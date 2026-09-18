# Wide-scene render preparation — GLM Flash

Objective: Prepare renderer for user's new 6-inch-wider skid/bale revision and green skid, in parallel with geometry inspection. DO NOT run Blender or alter geometry.

Work C:/Projects/CAD/astra-engine-pump. Read ASTRA-WIDENING-PLAN-2026-09-18.md, ASTRA-LIVERY-DIRECTION-2026-09-18.md, tools/astra_render_preview.py, reports/astra-preview/astra-render-execution.json narrowly. Other workers active; preserve their work. Own only tools/astra_render_wide_preview.py and reports/astra-wide-render-plan.md. Clone current renderer to new script using native Write/Edit, preserve original script.

Changes: split structural palette so skid (CAD_skid and structural tray/end-rail/support pieces under CAD_pump) is RAL6002 Leaf Green like pump, while lifting bale remains PMS293 blue. Engine remains John Deere green with functional per-slot finishes preserved. Carry forward in-memory CAD_pump_new visibility fix, evaluated/camera-ray pump participation assertions, opaque neutral floor, primary pump-side camera, engine-side camera, controller closeup, source/geometry invariance, saved separate lookdev blend. All geometry bounds from input, no fixed v10 dimensions. Accept arbitrary input path including planned out/engine-and-pump-v11-wide.blend, output reports/astra-wide-preview. Do not create or read nonexistent v11 as if ready.

Constraints: no Blender launch, cloud, dependency installs, source model edits, original renderer overwrite, global config or commits. Only minimal necessary modifications, no redesign. Preserve valid existing options including --blue-hex. Mark this prepared but not rendered. The grey #4C4DF remains incomplete, do not invent it. Native Write/Edit only for files.

Verification: Python compile; source review proves green skid mapping separate from blue bale and visibility fix still present. Write concise plan with exact invocation after geometry worker and independent verifier finish. Final under250words. REASONING low. Implement immediately, prior pipeline exploration sufficient; avoid long re-planning.
