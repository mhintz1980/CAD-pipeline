"""Isolated bounded cloud lookdev; leaves the SolidWorks export job alone."""
from pathlib import Path
import hashlib
import json
import os
import time
import modal

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA = '5f8632d8ef9b27da15b221f47feb9fb37dcea7b52493aeba62125523ae5f5e6f'
app = modal.App('engine-pump-reference-beauty')
volume = modal.Volume.from_name('engine-pump-reference-beauty', create_if_missing=True)
image = (modal.Image.debian_slim(python_version='3.11')
    .apt_install('wget', 'xz-utils', 'libglu1-mesa', 'libxi6', 'libxrender1',
                 'libxfixes3', 'libxcursor1', 'libxinerama1', 'libxkbcommon0',
                 'libsm6', 'libxxf86vm1', 'libgl1')
    .run_commands(
        'wget -q https://download.blender.org/release/Blender5.1/blender-5.1.2-linux-x64.tar.xz -O /tmp/blender.tar.xz || wget -q https://download.blender.org/release/Blender5.1/blender-5.1.0-linux-x64.tar.xz -O /tmp/blender.tar.xz',
        'tar -xf /tmp/blender.tar.xz -C /opt',
        'ln -s /opt/blender-5*/blender /usr/local/bin/blender',
        'rm /tmp/blender.tar.xz'))

@app.function(image=image, gpu=['L40S', 'A10', 'L4'], cpu=8, memory=32768,
              timeout=1800, max_containers=1, retries=0,
              scaledown_window=2,
              volumes={'/data':volume})
def render(scripts: dict, run_id: str, phase: str):
    import subprocess
    from pathlib import Path
    out = Path('/data') / run_id
    out.mkdir(exist_ok=False)
    scripts_dir = Path('/scripts'); scripts_dir.mkdir(exist_ok=True)
    for name, value in scripts.items():
        (scripts_dir / name).write_text(value)
    source = Path('/data/input/engine-and-pump-v10.blend')
    if hashlib.sha256(source.read_bytes()).hexdigest() != SOURCE_SHA:
        raise RuntimeError('Source SHA mismatch in cloud')
    smi = subprocess.run(['nvidia-smi'], capture_output=True, text=True)
    (out/'nvidia-smi.txt').write_text(smi.stdout+smi.stderr)
    cmd = ['blender','-b','--python-exit-code','1','--python',
           '/scripts/beauty_reference_20260918.py','--','--input',str(source),
           '--output-dir',str(out),'--phase',phase]
    started=time.time()
    with (out/'blender.log').open('w') as log:
        try:
            proc=subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, timeout=1650)
            returncode=proc.returncode
        except subprocess.TimeoutExpired:
            log.write('\nBEAUTY_TIMEOUT after 1650 seconds\n')
            returncode=124
    volume.commit()
    files=[{'name':p.name,'bytes':p.stat().st_size,
            'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
           for p in out.iterdir() if p.is_file() and p.suffix != '.blend1']
    return {'run_id':run_id,'returncode':returncode,
            'seconds':time.time()-started,'files':files,
            'function_call_id':modal.current_function_call_id()}

@app.local_entrypoint()
def main(phase: str='preview', run_id: str=''):
    if phase not in {'preview','final'}:
        raise ValueError('phase must be preview or final')
    run_id = run_id or (phase+'-'+time.strftime('%Y%m%dT%H%M%S'))
    if not all(c.isalnum() or c in '-_' for c in run_id):
        raise ValueError('unsafe run id')
    source=ROOT/'out/engine-and-pump-v10.blend'
    if hashlib.sha256(source.read_bytes()).hexdigest()!=SOURCE_SHA:
        raise RuntimeError('Local source SHA mismatch')
    scripts={name:(ROOT/'tools'/name).read_text(encoding='utf8') for name in
             ['astra_render_preview.py','beauty_reference_20260918.py']}
    local=ROOT/'reports/reference-beauty-20260918'/run_id
    local.mkdir(parents=True,exist_ok=False)
    for name, value in scripts.items():
        (local/name).write_text(value,encoding='utf8')
    with volume.batch_upload(force=True) as upload:
        upload.put_file(source,'/input/engine-and-pump-v10.blend')
    print('BEAUTY_SUBMIT',run_id,flush=True)
    result=render.remote(scripts,run_id,phase)
    for f in result['files']:
        target=local/f['name']
        with target.open('wb') as dest:
            for chunk in volume.read_file('/'+run_id+'/'+f['name']):
                dest.write(chunk)
        if hashlib.sha256(target.read_bytes()).hexdigest()!=f['sha256']:
            raise RuntimeError('Download hash mismatch: '+f['name'])
    result['source_unchanged']=hashlib.sha256(source.read_bytes()).hexdigest()==SOURCE_SHA
    result['app_id']=app.app_id
    result['local_directory']=str(local)
    (local/'modal-receipt.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    print('BEAUTY_DOWNLOADED',json.dumps(result),flush=True)
    if result['returncode'] != 0:
        raise RuntimeError('Blender failed; see downloaded blender.log')
