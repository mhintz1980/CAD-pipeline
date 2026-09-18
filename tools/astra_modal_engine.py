"""One-shot Modal worker: run astra_engine_export.py in Blender 5.1 on L4 GPU.

Usage:
    modal run tools/astra_modal_engine.py --script tools/astra_engine_export.py
"""
from __future__ import annotations
import os
import json
import hashlib
import time
import traceback

import modal

app = modal.App("astra-engine-export")

vol_in = modal.Volume.from_name("astra-engine-input", create_if_missing=True)
vol_out = modal.Volume.from_name("astra-engine-out", create_if_missing=True)

blender_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install(
        "wget", "xz-utils", "libglu1-mesa", "libxi6",
        "libxrender1", "libxfixes3", "libxcursor1", "libxinerama1",
        "libxkbcommon0", "libsm6", "libxxf86vm1", "libgl1"
    )
    .run_commands(
        "wget -q https://download.blender.org/release/Blender5.1/blender-5.1.2-linux-x64.tar.xz -O /tmp/blender.tar.xz || wget -q https://download.blender.org/release/Blender5.1/blender-5.1.0-linux-x64.tar.xz -O /tmp/blender.tar.xz",
        "tar -xf /tmp/blender.tar.xz -C /opt",
        "ln -s /opt/blender-5*/blender /usr/local/bin/blender",
        "rm /tmp/blender.tar.xz",
    )
)

RUN_ID = time.strftime("run-%Y%m%dT%H%M%S")
EXPECTED_SHA = "5f8632d8ef9b27da15b221f47feb9fb37dcea7b52493aeba62125523ae5f5e6f"


def rel_to_volume(p: str) -> str:
    return p.removeprefix("/output/").lstrip("/")
OUT_ROOT = f"/output/{RUN_ID}"


@app.function(
    image=blender_image,
    gpu="L4",
    cpu=(16.0, 16.0),
    memory=(65536, 65536),
    timeout=2400,
    max_containers=1,
    retries=0,
    volumes={"/input": vol_in, "/output": vol_out},
)
def run_export(script_text: str, blend_vol_path: str, run_id: str, out_root: str,
               expected_sha: str) -> dict:
    import subprocess
    os.makedirs("/scripts", exist_ok=True)
    with open("/scripts/astra_engine_export.py", "w") as f:
        f.write(script_text)

    blend = blend_vol_path
    h = hashlib.sha256()
    with open(blend, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    cloud_sha = h.hexdigest()
    assert cloud_sha == expected_sha, f"cloud SHA mismatch: {cloud_sha}"

    os.makedirs(out_root, exist_ok=True)
    cmd = ["blender", "-b", blend, "--python", "/scripts/astra_engine_export.py",
           "--python-exit-code", "1", "--", "--output-dir", out_root]
    t0 = time.time()
    err = None
    res = None
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=2250)
        elapsed = time.time() - t0
        print("[BLENDER STDOUT]\n" + res.stdout)
        if res.stderr:
            print("[BLENDER STDERR]\n" + res.stderr)
        with open(f"{out_root}/blender-stdout.log", "w", encoding="utf-8") as f:
            f.write(res.stdout)
        with open(f"{out_root}/blender-stderr.log", "w", encoding="utf-8") as f:
            f.write(res.stderr)
        rc = res.returncode
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        elapsed = time.time() - t0
        rc = -1
        print("[JOB ERROR]", err)
        with open(f"{out_root}/job-error.txt", "w", encoding="utf-8") as f:
            f.write(err + "\n\n" + traceback.format_exc())

    # GPU / memory evidence (best-effort)
    try:
        smi = subprocess.run(["nvidia-smi"], capture_output=True, text=True)
        with open(f"{out_root}/nvidia-smi.txt", "w", encoding="utf-8") as f:
            f.write(smi.stdout + smi.stderr)
    except Exception as e:
        print("nvidia-smi failed:", e)
    try:
        with open("/proc/meminfo") as f:
            meminfo = f.read()
        with open(f"{out_root}/meminfo.txt", "w", encoding="utf-8") as f:
            f.write(meminfo)
    except Exception as e:
        print("meminfo failed:", e)

    vol_out.commit()

    outputs = []
    for root, _, files in os.walk(out_root):
        for name in files:
            p = os.path.join(root, name)
            outputs.append({"path": p, "size": os.path.getsize(p)})
    return {
        "run_id": run_id,
        "returncode": rc,
        "error": err,
        "elapsed_sec": elapsed,
        "blend_sha256": cloud_sha,
        "outputs": outputs,
    }


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download_outputs(outputs, out_dir: str):
    os.makedirs(out_dir, exist_ok=True)
    for o in outputs:
        rel = rel_to_volume(o["path"])
        dst = os.path.join(out_dir, rel)
        os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
        # read_file returns an ITERATOR of chunks (not a context manager / bytes)
        with open(dst, "wb") as f:
            for chunk in vol_out.read_file(rel):
                f.write(chunk)


def save_receipt(receipt: dict):
    os.makedirs("reports/astra-modal-engine", exist_ok=True)
    with open("reports/astra-modal-engine/receipt.json", "w") as f:
        json.dump(receipt, f, indent=2)


@app.local_entrypoint()
def main(script: str = "tools/astra_engine_export.py"):
    size = os.path.getsize(script)
    assert size > 0, f"Export script is empty/incomplete: {script}"
    with open(script, "r", encoding="utf-8") as f:
        script_text = f.read()

    blend = "out/engine-and-pump-v10.blend"
    sha = sha256_file(blend)
    assert sha == EXPECTED_SHA, f"Source SHA mismatch: {sha}"
    print(f"[local] source SHA verified: {sha}")

    dest = f"{RUN_ID}/engine-and-pump-v10.blend"
    with vol_in.batch_upload() as up:
        up.put_file(blend, dest)
    print(f"[local] uploaded blend to volume as {dest}")

    started_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    t0 = time.time()
    receipt = {
        "run_id": RUN_ID,
        "source_sha256": sha,
        "source_bytes": os.path.getsize(blend),
        "script": script,
        "app_name": app.name,
        "function_name": "run_export",
        "resources": {"cpu": "16/16", "memory_mib": "65536/65536", "gpu": "L4", "timeout_s": 2400},
        "started_utc": started_utc,
    }

    result = None
    err_local = None
    try:
        result = run_export.remote(script_text, f"/input/{dest}", RUN_ID, OUT_ROOT,
                                   EXPECTED_SHA)
        receipt["remote"] = result
    except Exception as e:
        err_local = f"{type(e).__name__}: {e}"
        receipt["local_error"] = err_local + "\n" + traceback.format_exc()
        print("[FATAL]", err_local)

    receipt["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    receipt["wall_sec"] = time.time() - t0

    out_dir = f"reports/astra-modal-engine/{RUN_ID}"
    try:
        outputs = (result or {}).get("outputs", [])
        if not outputs:
            # remote failed before listing; attempt whole run-dir download via CLI listing not available;
            # fall back to known log names
            outputs = [{"path": f"{OUT_ROOT}/{n}", "size": 0}
                       for n in ("blender-stdout.log", "blender-stderr.log", "job-error.txt")]
        download_outputs(outputs, out_dir)
        receipt["download_dir"] = out_dir
    except Exception as e:
        receipt["download_error"] = f"{type(e).__name__}: {e}"
        print("[DOWNLOAD ERROR]", e)

    save_receipt(receipt)
    print(f"[local] receipt saved; outputs in {out_dir if os.path.isdir(out_dir) else 'N/A'}")
    if result and result.get("returncode") != 0:
        raise SystemExit(f"remote job failed rc={result.get('returncode')}: {result.get('error')}")
    if err_local:
        raise SystemExit(1)
