"""Reference-photo look development; immutable v10 CAD, Cycles OPTIX only."""
import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector
sys.path.insert(0, str(Path(__file__).parent))
import astra_render_preview as base

PALETTE = {
    'pump_green': '#075D46', 'frame_green': '#104E3E',
    'engine_green': '#285E43', 'skid_grey': '#AEB5B8',
    'engine_iron': '#454B4D', 'rubber': '#171C20',
    'hardware': '#BCC5CA', 'exhaust': '#646969', 'control': '#252D33',
}

def material(name, color, roughness, metallic=0, coat=0, grain=False):
    mat = base.make_mat('REF_' + name, color, roughness, metallic, coat)
    mat.diffuse_color = base.hex_lin(color)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    shader = nodes.get('Principled BSDF')
    if 'Coat Roughness' in shader.inputs:
        shader.inputs['Coat Roughness'].default_value = .22
    # Bump-only casting grain: no displacement and no geometry alteration.
    if grain:
        tex = nodes.new('ShaderNodeTexNoise')
        tex.inputs['Scale'].default_value = 850
        tex.inputs['Detail'].default_value = 2
        coords = nodes.new('ShaderNodeTexCoord')
        links.new(coords.outputs['Object'], tex.inputs['Vector'])
        bump = nodes.new('ShaderNodeBump')
        bump.inputs['Strength'].default_value = .12
        bump.inputs['Distance'].default_value = .00022
        links.new(tex.outputs['Fac'], bump.inputs['Height'])
        links.new(bump.outputs['Normal'], shader.inputs['Normal'])
    return mat

def apply_materials(cad):
    mats = {k: material(k, v,
                       .30 if 'green' in k else .34 if k == 'skid_grey' else
                       .68 if k == 'rubber' else .36,
                       .85 if k == 'hardware' else .65 if k == 'exhaust' else .0,
                       .25 if 'green' in k else .16 if k == 'skid_grey' else .0,
                       k in {'pump_green', 'engine_green', 'engine_iron'})
            for k, v in PALETTE.items()}
    rows = []
    # Snapshot all slot colors before assigning any shared material datablocks.
    original = {o.name: [(m.name if m else None, base.base_lin(m))
                         for m in o.data.materials] for o in cad}
    for o in cad:
        cols = {c.name for c in o.users_collection}
        name = o.name.lower()
        slots = original[o.name] or [(None, None)]
        if not o.data.materials:
            o.data.materials.append(mats['engine_iron'])
        for i, (vendor, rgb) in enumerate(slots):
            if cols & {'CAD_skid', 'CAD_pump'}:
                role = 'skid_grey'
            elif 'CAD_bale' in cols:
                role = 'frame_green'
            elif 'CAD_controller' in cols:
                role = 'control'
            elif any(s in name for s in ('washer', 'bolt', 'screw', 'fastener')):
                role = 'hardware'
            elif any(s in name for s in ('hose', 'rubber', 'grommet', 'seal')):
                role = 'rubber'
            elif any(s in name for s in ('exhaust', 'muffler')):
                role = 'exhaust'
            elif 'CAD_pump_new' in cols:
                r = base.slot_role(rgb, 'pump')
                role = r if r in {'rubber', 'hardware', 'exhaust'} else 'pump_green'
            elif 'CAD_engine' in cols:
                if rgb is None:
                    role = 'engine_green'
                elif base._lum(rgb) < .032:
                    role = 'rubber'
                elif max(rgb) - min(rgb) < .06:
                    role = 'hardware' if base._lum(rgb) > .55 else 'engine_iron'
                elif rgb[1] > rgb[0] * 1.3 and rgb[1] > rgb[2] * 1.3:
                    role = 'engine_green'
                else:
                    role = 'engine_iron'
            else:
                role = 'engine_iron'
            o.data.materials[i] = mats[role]
            rows.append({'object': o.name, 'slot': i, 'vendor': vendor,
                         'original_rgb': rgb, 'role': role})
    return rows

def area(name, pos, target, energy, size, color=(1, 1, 1), size_y=None):
    d = bpy.data.lights.new(name, 'AREA')
    d.energy, d.color = energy * .18, color
    d.shape = 'RECTANGLE'
    d.size, d.size_y = size, size_y or size
    o = bpy.data.objects.new(name, d)
    bpy.context.scene.collection.objects.link(o)
    o.location = pos
    o.rotation_euler = (Vector(target) - o.location).to_track_quat('-Z', 'Y').to_euler()
    return o

def studio(center, ground):
    base.setup_studio(3, ground)
    floor = bpy.data.objects['GroundFloor']
    floor.data.materials.clear()
    floor.data.materials.append(material('Stage', '#303942', .72))
    world = bpy.context.scene.world
    bg = world.node_tree.nodes.get('Background')
    bg.inputs['Color'].default_value = base.hex_lin('#CBD6DF')
    bg.inputs['Strength'].default_value = .22
    c = Vector(center)
    area('REF_KeySoftbox', c + Vector((-3.4, 2.0, 5.5)), c, 2300, 4.0,
         (1.0, .95, .88), 2.7)
    area('REF_FrontStrip', c + Vector((-4.0, 4.5, 1.2)), c, 950, 2.0,
         (.86, .93, 1), 4.0)
    area('REF_RimStrip', c + Vector((3.0, -1.4, 3.5)), c, 2600, 2.3,
         (.85, .94, 1), 4.0)
    area('REF_Overhead', c + Vector((0, -.5, 6)), c, 1700, 3.5, (1, 1, 1), 5)
    area('REF_PumpFill', c + Vector((1.5, 4.5, 2.2)), c, 600, 3)
    return floor

def configure_gpu():
    prefs = bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type = 'OPTIX'
    prefs.get_devices()
    devices = []
    for d in prefs.devices:
        d.use = d.type == 'OPTIX'
        devices.append({'name': d.name, 'type': d.type, 'use': bool(d.use)})
    if not any(d['use'] for d in devices):
        raise RuntimeError('No OPTIX GPU available; refusing CPU fallback')
    bpy.context.scene.cycles.device = 'GPU'
    return devices

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--input', required=True)
    p.add_argument('--output-dir', required=True)
    p.add_argument('--phase', choices=['preview', 'final'], default='preview')
    a = p.parse_args(sys.argv[sys.argv.index('--') + 1:])
    out = Path(a.output_dir); out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    before_hash = base.sha256_file(a.input)
    bpy.ops.wm.open_mainfile(filepath=a.input)
    # Remove only existing photographic helpers, never any CAD mesh.
    for o in list(bpy.context.scene.objects):
        if o.type in {'LIGHT', 'CAMERA'} or o.name in {'GroundFloor', 'GroundShadowCatcher'}:
            bpy.data.objects.remove(o, do_unlink=True)
    visibility = base.ensure_render_visibility()
    cad = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    digest = base.geo_digest(cad)
    lo, hi, center, radius = base.scene_bounds()
    rows = apply_materials(cad)
    floor = studio(center, lo.z)
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    devices = configure_gpu()
    sc.cycles.samples = 40 if a.phase == 'preview' else 256
    sc.cycles.use_denoising = True
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.adaptive_threshold = .025 if a.phase == 'preview' else .008
    sc.cycles.max_bounces = 8
    sc.cycles.diffuse_bounces = 4
    sc.cycles.glossy_bounces = 4
    sc.cycles.seed = 19
    sc.render.resolution_x = 1100 if a.phase == 'preview' else 2800
    sc.render.resolution_y = 800 if a.phase == 'preview' else 2000
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = 'PNG'
    sc.render.image_settings.color_mode = 'RGBA'
    sc.render.image_settings.color_depth = '8'
    sc.render.film_transparent = False
    sc.render.use_persistent_data = True
    sc.render.threads_mode = 'FIXED'; sc.render.threads = 8
    sc.view_settings.view_transform = 'AgX'
    sc.view_settings.look = 'AgX - Medium High Contrast'
    sc.view_settings.exposure = 0
    specs = [('01-pump-hero', (-.92, .74, .43)),
             ('02-side-hero', (-1.0, .32, .34)),
             ('03-drive-side', (.95, .60, .38))]
    shots = [(name, base.fit_camera('REF_' + name, lo, hi, direction,
               sc.render.resolution_x, sc.render.resolution_y, lens=58, margin=.94)[0])
             for name, direction in specs]
    bpy.context.view_layer.update()
    checks = {name: base.verify_render_participation(sc, cam)
              for name, cam in shots}
    if a.phase == 'final':
        pump = [o for o in cad if any(c.name == 'CAD_pump_new' for c in o.users_collection)]
        plo, phi = base.bbox_of(pump)
        detail = base.fit_camera('REF_05-pump-detail', plo, phi, (-.7, 1.0, .36),
                                sc.render.resolution_x, sc.render.resolution_y,
                                lens=75, margin=.76)[0]
        shots.append(('05-pump-detail', detail))
        bpy.context.view_layer.update()
        checks['05-pump-detail'] = base.verify_render_participation(sc, detail)
    sc.camera = shots[0][1]
    saved = out / 'engine-pump-reference-look.blend'
    if a.phase == 'final':
        bpy.ops.wm.save_as_mainfile(filepath=str(saved), compress=True)
    images = []
    for name, cam in shots:
        sc.camera = cam
        sc.render.filepath = str(out / (name + '.png'))
        start = time.time()
        bpy.ops.render.render(write_still=True)
        images.append({'name': name, 'seconds': round(time.time() - start, 2),
                       'stats': base.image_stats(sc.render.filepath)})
        print('BEAUTY_IMAGE', name, flush=True)
    if a.phase == 'final':
        # Matching white studio photograph, with real floor/contact shadows.
        sc.camera = shots[0][1]
        floor.data.materials[0] = material('CatalogueFloor', '#D1D4D5', .78)
        sc.world.node_tree.nodes['Background'].inputs['Strength'].default_value = .32
        sc.render.filepath = str(out / '04-light-studio.png')
        bpy.ops.render.render(write_still=True)
        images.append({'name': '04-light-studio', 'stats': base.image_stats(sc.render.filepath)})
        # Restore hero look in the delivered .blend; all cameras remain available.
        floor.data.materials[0] = bpy.data.materials['REF_Stage']
        sc.world.node_tree.nodes['Background'].inputs['Strength'].default_value = .22
        sc.render.filepath = '//01-pump-hero.png'
        bpy.ops.wm.save_as_mainfile(filepath=str(saved), compress=True)
    after = base.geo_digest(cad)
    source_after = base.sha256_file(a.input)
    assert digest == after, 'CAD geometry or placement changed'
    assert before_hash == source_after, 'Source bytes changed'
    reopened_digest = None
    if a.phase == 'final':
        cad_names = [o.name for o in cad]
        bpy.ops.wm.open_mainfile(filepath=str(saved))
        reopened_digest = base.geo_digest([bpy.data.objects[n] for n in cad_names])
        assert reopened_digest == digest, 'Saved .blend geometry does not match source'
        base.verify_render_participation(bpy.context.scene, bpy.context.scene.camera)
        sc = bpy.context.scene
    report = dict(phase=a.phase, blender=bpy.app.version_string,
                  source_sha256=before_hash, source_unchanged=True,
                  geometry_digest_before=digest, geometry_digest_after=after,
                  reopened_geometry_digest=reopened_digest,
                  geometry_unchanged=True, cad_meshes=len(cad),
                  visibility_changes=visibility, pump_checks=checks, gpu=devices,
                  palette=PALETTE, palette_basis='Approximate appearance from user photographs, not calibrated RAL values',
                  material_slots=rows, images=images, elapsed_seconds=time.time()-t0,
                  resolution=[sc.render.resolution_x, sc.render.resolution_y], samples=sc.cycles.samples)
    (out / 'beauty-report.json').write_text(json.dumps(report, indent=2))
    print('BEAUTY_COMPLETE', json.dumps({'images':len(images), 'seconds':report['elapsed_seconds']}), flush=True)

if __name__ == '__main__':
    main()
