# Blocking visual defect — pump absent

Mark reiterated that rendering must start with C:/Projects/CAD/astra-engine-pump/out/engine-and-pump-v10.blend, which contains BOTH pump and engine. This is the exact source already used and must stay so.

Astra inspected revised _warmup/astra-preview-threequarter.png: from the +Y side the engine flywheel and empty front skid are visible, but the entire Vogelsang pump is absent. This is NOT explained by camera occlusion. Source inventory contains CAD_pump_new 415 meshes and pump bbox at Y 0.266..1.363 m. Treat preview as FIX_FIRST until pump body is visible.

Investigate source and prepared in-memory visibility: per-object hide_render, camera-ray visibility, collection hide_render, recursive view-layer exclude/hide_viewport flags, source material alpha/transmission, and source mesh evaluation/dependency graph inclusion. Snapshot actual settings from v10 before changes; do not infer from census alone. Also check whether renderer is accidentally purging pump via helper removal or name-based filtering, and whether prepared digest counts hidden objects without proving render contribution.

Correct only preview visibility/material handling as needed to show existing source pump. No reimport, no rebuilding CAD, no geometry relocation, no source file overwrite. Keep v10 hash unchanged. If source v10 visibility suppresses pump, explicitly enable CAD_pump_new and required ancestors in the in-memory preview, save that difference only in new lookdev .blend, and report it. Confirm all expected pump objects participate in evaluated active view-layer and camera rays before final render.

After fixing, a small warmup with visible pump is REQUIRED before any more full-res render. Show both engine and pump in primary hero, keep Pioneer colour mapping and floor grounding. Keep report honest about the earlier camera-only hypothesis being insufficient. Stop camera beauty iteration until visibility root cause is resolved.
