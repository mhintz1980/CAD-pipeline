"""One-shot Modal worker: widen v10 -> v11 (producer + verifier) then render look-dev.

Usage:
    modal run tools/astra_modal_wide.py
"""
from __future__ import annotations
import os, json, hashlib, time, traceback

import modal

app = modal.App("astra-modal-wide")

vol_in = modal.Volume.from_name("astra-engine-input", create_if_missing=True)
vol_out = modal.Volume.from_name("astra-wide-out", create_if_missing=True)

# EXACT same image as tools/astra_modal_engine.py (cached Blender layers)
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

RUN_ID = time.strftime("wide-%Y%m%dT%H%M%S")
EXPECTED_SHA = "5f8632d8ef9b27da15b221f47feb9fb37dcea7b52493aeba62125523ae5f5e6f"
VOL_PREFIX = RUN_ID
OUT_ROOT = "/out/" + RUN_ID

SCRIPTS = ("astra_widen_v11.py", "astra_verify_wide.py", "astra_render_wide_preview.py")


@app.function(
    image=blender_image,
    gpu=["L4", "A10", "L40S"],
    cpu=(16.0, 16.0),
    memory=(65536, 65536),
    timeout=1800,
    max_containers=1,
    retries=0,
    volumes={"/input": vol_in, "/out": vol_out},
)
def run_wide(run_id: str, out_root: str, expected_sha: str,
             producer_text: str, verifier_text: str, preview_text: str,
             inspection_text: str) -> dict:
    import subprocess, shutil
    logs = []

    def log(msg):
        print(msg)
        logs.append(msg)

    def blender(cmd_args, timeout, tag):
        cmd = ["blender", "-b", "-noaudio", "--threads", "16",
               "--python-exit-code", "1"] + cmd_args
        log("[run] %s: %s ..." % (tag, " ".join(cmd[:8])))
        t0 = time.time()
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            rc, so, se = res.returncode, res.stdout, res.stderr
        except Exception as e:
            rc, so, se = -1, "", "%s: %s\n%s" % (type(e).__name__, e, traceback.format_exc())
        elapsed = time.time() - t0
        for name, text in ((tag + "-stdout.log", so), (tag + "-stderr.log", se)):
            with open(os.path.join(out_root, name), "w", encoding="utf-8") as f:
                f.write(text)
        log("[done] %s: rc=%d elapsed=%.1fs" % (tag, rc, elapsed))
        return rc, elapsed

    def sha256_file(p):
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for b in iter(lambda: f.read(1 << 20), b""):
                h.update(b)
        return h.hexdigest()

    os.makedirs("/work/tools", exist_ok=True)
    os.makedirs("/work/reports", exist_ok=True)
    os.makedirs(out_root, exist_ok=True)
    for name, text in (
        ("astra_widen_v11.py", producer_text),
        ("astra_verify_wide.py", verifier_text),
        ("astra_render_wide_preview.py", preview_text),
    ):
        with open("/work/tools/" + name, "w", encoding="utf-8") as f:
            f.write(text)
    with open("/work/reports/astra-widening-inspection.json", "w", encoding="utf-8") as f:
        f.write(inspection_text)

    src = "/work/out/engine-and-pump-v10.blend"
    os.makedirs("/work/out", exist_ok=True)
    vol_src = "/input/%s/engine-and-pump-v10.blend" % run_id
    if os.path.exists(vol_src):
        shutil.copyfile(vol_src, src)
    else:
        raise SystemExit("input blend not found in volume: %s" % vol_src)
    h = sha256_file(src)
    assert h == expected_sha, "source SHA mismatch: %s" % h
    log("[sha] source OK: %s" % h)

    stage = "producer"
    receipt = {"run_id": run_id, "source_sha256": h, "stages": {}}
    fail = None
    v11 = "/work/out/engine-and-pump-v11-wide.blend"
    try:
        rc, el = blender(
            [src, "--python", "/work/tools/astra_widen_v11.py", "--",
             "/work/reports/astra-widening-v11.json", v11, expected_sha],
            600, "producer")
        receipt["stages"]["producer"] = {"rc": rc, "elapsed": el}
        producer_report = {}
        try:
            producer_report = json.load(open("/work/reports/astra-widening-v11.json"))
        except Exception as e:
            fail = "producer report unreadable: %s" % e
        if rc != 0 and not fail:
            fail = "producer rc=%d" % rc
        if producer_report and producer_report.get("passed") is False and not fail:
            fail = "producer report passed=false"
        if fail:
            raise RuntimeError(fail)

        stage = "verifier"
        rc, el = blender(
            ["--python", "/work/tools/astra_verify_wide.py", "--",
             "--baseline", src, "--candidate", v11,
             "--report", "/work/reports/astra-wide-verifier-result.json"],
            600, "verifier")
        receipt["stages"]["verifier"] = {"rc": rc, "elapsed": el}
        ver = {}
        try:
            ver = json.load(open("/work/reports/astra-wide-verifier-result.json"))
        except Exception as e:
            fail = "verifier report unreadable: %s" % e
        if rc != 0 and not fail:
            fail = "verifier rc=%d" % rc
        if ver and not ver.get("passed", False) and not fail:
            fail = "verifier passed=false"
        if fail:
            raise RuntimeError(fail)

        stage = "render"
        env = dict(os.environ, ASTRA_GPU="1")
        cmd = ["blender", "-b", "-noaudio", "--threads", "16",
               "--python-exit-code", "1", v11,
               "--python", "/work/tools/astra_render_wide_preview.py", "--",
               "--input", v11, "--output-dir", out_root + "/lookdev",
               "--width", "1600", "--samples", "32", "--threads", "16"]
        t0 = time.time()
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=900, env=env)
            rc = res.returncode
            with open(out_root + "/render-stdout.log", "w", encoding="utf-8") as f:
                f.write(res.stdout)
            with open(out_root + "/render-stderr.log", "w", encoding="utf-8") as f:
                f.write(res.stderr)
        except Exception as e:
            rc = -1
            with open(out_root + "/render-stderr.log", "w", encoding="utf-8") as f:
                f.write("%s: %s\n%s" % (type(e).__name__, e, traceback.format_exc()))
        el = time.time() - t0
        log("[done] render: rc=%d elapsed=%.1fs" % (rc, el))
        receipt["stages"]["render"] = {"rc": rc, "elapsed": el}
        if rc != 0:
            raise RuntimeError("render rc=%d" % rc)
    except Exception as e:
        receipt["failure_stage"] = stage
        receipt["error"] = "%s: %s" % (type(e).__name__, e)
        log("[FATAL at %s] %s" % (stage, e))

    try:
        if os.path.exists(v11):
            os.makedirs(out_root + "/blends", exist_ok=True)
            shutil.copyfile(v11, out_root + "/blends/engine-and-pump-v11-wide.blend")
    except Exception as e:
        log("[copy v11 failed] %s" % e)

    outputs = []
    for root, _, files in os.walk(out_root):
        for name in files:
            p = os.path.join(root, name)
            outputs.append({"path": p, "size": os.path.getsize(p)})
    receipt["outputs"] = outputs
    with open(out_root + "/receipt.json", "w", encoding="utf-8") as f:
        json.dump(receipt, f, indent=2)
    with open(out_root + "/worker-log.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(logs))
    vol_out.commit()
    return receipt


def download_outputs(outputs, out_dir: str):
    os.makedirs(out_dir, exist_ok=True)
    for o in outputs:
        # remote paths live under /out/<RUN_ID>/... -> volume-relative strips "/out/"
        remote_rel = o["path"].removeprefix("/out/").lstrip("/")
        rel = os.path.relpath(remote_rel, RUN_ID)
        dst = os.path.join(out_dir, rel)
        os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
        with open(dst, "wb") as f:
            for chunk in vol_out.read_file(remote_rel):
                f.write(chunk)


@app.local_entrypoint()
def main():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    texts = {}
    for n in SCRIPTS:
        p = os.path.join(here, "tools", n)
        with open(p, "r", encoding="utf-8") as f:
            texts[n] = f.read()
        assert len(texts[n]) > 0, "empty script: %s" % n
    with open(os.path.join(here, "reports", "astra-widening-inspection.json"), "r",
              encoding="utf-8") as f:
        inspection_text = f.read()

    src = os.path.join(here, "out", "engine-and-pump-v10.blend")
    h = hashlib.sha256()
    with open(src, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    sha = h.hexdigest()
    assert sha == EXPECTED_SHA, "local source SHA mismatch: %s" % sha
    print("[local] source SHA verified: %s" % sha)

    dest = "%s/engine-and-pump-v10.blend" % VOL_PREFIX
    with vol_in.batch_upload() as up:
        up.put_file(src, dest)
    print("[local] uploaded as %s" % dest)

    t0 = time.time()
    receipt = None
    err = None
    try:
        receipt = run_wide.remote(
            RUN_ID, OUT_ROOT, EXPECTED_SHA,
            texts["astra_widen_v11.py"], texts["astra_verify_wide.py"],
            texts["astra_render_wide_preview.py"], inspection_text)
    except Exception as e:
        err = "%s: %s\n%s" % (type(e).__name__, e, traceback.format_exc())
        print("[FATAL]", err)

    out_dir = os.path.join(here, "reports", "astra-modal-wide", RUN_ID)
    try:
        if receipt:
            download_outputs(receipt.get("outputs", []), out_dir)
            print("[local] downloaded to %s" % out_dir)
    except Exception as e:
        print("[DOWNLOAD ERROR]", e)

    summary = {
        "app_id": app.name,
        "run_id": RUN_ID,
        "source_sha256": sha,
        "wall_sec": time.time() - t0,
        "stages": (receipt or {}).get("stages", {}),
        "failure_stage": (receipt or {}).get("failure_stage"),
        "error": err or (receipt or {}).get("error"),
        "download_dir": out_dir,
    }
    os.makedirs("reports/astra-modal-wide", exist_ok=True)
    with open("reports/astra-modal-wide/summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(json.dumps(summary, indent=2))
    if err or (receipt or {}).get("error"):
        raise SystemExit(1)
