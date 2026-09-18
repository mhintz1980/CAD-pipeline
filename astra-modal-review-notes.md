# Architect review of initial cloud wrapper, 13:56 EDT
Please fix before execution/download:
- batch_upload supports uploads, NOT down.get_file. Use Volume.read_file yielding bytes (stream write) or CLI volume get, verified current API. Download even when remote fails to retain logs.
- Output must use unique /output/{run_id} directory; pass that to exportscript. Do not share /output root or return stale prioroutputs.
- Explicit cpu=(16,16), memory=(65536,65536) if supported to bound billedresourceceiling; current scalarsoftCPUlimit canburst. Verify SDKsignature.
- Use --python-exit-code 1 in Blender invocation so script exceptions aren't exit0.
- Capture true starttime before job, persist resource/jobids in receipt; currentstarted equalsfinished.
- Stage logs and outputcommit in finally for error recovery; subprocess timeout <function2400 (e.g2250).
- Userdeadline14:44EDT, cloudstartasap. No extraapproval.
