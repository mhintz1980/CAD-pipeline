"""Astra first-look preview renderer - WIDE scene variant (v10 input, or the
planned out/engine-and-pump-v11-wide.blend once the geometry worker delivers
it; this script does not require or assume v11 exists).

Prepared 2026-09-18 per ASTRA-WIDENING-PLAN-2026-09-18.md revision: NOT yet
rendered. Structural palette split per revised owner direction:
  blender --background --python tools/astra_render_preview.py -- `
      --input <abs .blend> --output-dir <abs dir> [--width 1200] `
      [--samples 32] [--threads 4] [--with-controller-detail] `
      [--blue-hex #003DA5] [--save-blend <abs .blend>]

Livery per ASTRA-WIDENING-PLAN-2026-09-18.md + ASTRA-LIVERY-DIRECTION-2026-09-18.md (supersedes MSP yellow):
  - Skid (CAD_skid) and all structural tray/end-rail/support pieces under
    CAD_pump (PP-FTT/PP-FTS/PP128-FTA/PP-FBS): RAL 6002 Leaf Green
    (approx working sRGB #276235) - the skid is now green WITH the pump per
    the widening revision. This differs from the original renderer, which
    painted structure PMS 293 blue.
  - Lifting bale (CAD_bale): PMS 293 blue (approx working sRGB #003DA5,
    override with --blue-hex; Pantone Process Blue swap pending owner
    clarification) - bale REMAINS blue while skid goes green.
  - Vendor engine painted castings: John Deere green #367C2B (explicit owner
    option; the incomplete five-digit grey string is deliberately NOT guessed).
  - Separable functional finishes are preserved: bright/bare metal -> zinc
    hardware, near-black -> rubber, dark oxidised metal -> exhaust, control
    faces stay dark. No logos, no invented branding.

Engine/pump vendor slots are classified individually (by the slot material's
linear base colour) rather than blanket-overwritten, so the per-face material
slot table survives look-dev. All numeric swatches are digital working
approximations, labelled as such in reports/astra-preview-materials.json.

The placeholder blue used in an earlier draft (#0057B8) is NOT used. If a
Process Blue test is ever requested, the documented Pantone Process Blue
digital approximation is #0085CA (see PROCESS_BLUE_APPROX); PMS 293 remains
the first-preview choice.

Grounded studio look: neutral lit world plus a REAL opaque rough diffuse floor
at the measured skid bottom (2 mm clearance) - this is an opaque local beauty
preview, not a transparent-film composite, so no shadow catcher is used and the
floor shows a genuine contact-shadow footprint under the skid supports. The
floor is a render helper: it is excluded from camera-fitting bounds and from
the geometry invariance digest. Cameras are framed by fitting the measured
bounding box along a chosen view direction with a safety margin, so the whole
machine stays in frame (v9 datum: X[-1.021,1.044] Y[-2.372,2.372]
Z[-0.972,1.956] m). The primary hero looks from -X/+Y/above so the pump body is
on the near side; a secondary -X/-Y view keeps the engine side and the minus-X
controller in evidence.

Source safety: geometry, mesh data and world matrices are never modified.
The script hashes the source .blend before/after and compares an in-memory
geometry digest (vertex coords, loop indices, world matrices) taken before
look-dev and again after rendering. Render helpers (ground catcher, lights,
cameras) are excluded from framing and from both digests.
"""
import argparse
import hashlib
import json
import math
import os
import sys
import time

import bpy
from mathutils import Vector

LIVERY = {  # digital working swatches - approximations, pending calibrated palette
    "pump_hex": "#276235",       # RAL 6002 Leaf Green
    "blue_hex": "#003DA5",       # PMS 293 C (default; --blue-hex overrides)
    "jd_green_hex": "#367C2B",   # John Deere green (explicit option, used)
    "pump_rough": 0.40, "blue_rough": 0.50, "jd_rough": 0.45,
}
FUNCTIONAL = {  # values reused from msp_render_cli/materials.py SUB_ASSEMBLY_MATERIALS
    "hardware":  ("#D8D8D8", 0.25, 0.95),   # zinc_plated_hardware
    "rubber":    ("#171717", 0.88, 0.00),   # rubber_fenders_tires
    "exhaust":   ("#4A4A4A", 0.55, 0.85),   # exhaust_muffler
    "control":   ("#1F1F1F", 0.30, 0.10),   # control_panel_face
}

COLL_SKID = {"CAD_skid"}      # structural skid -> RAL 6002 green (wide revision)
COLL_BALE = {"CAD_bale"}      # lifting bale stays PMS 293 blue
# CAD_pump holds the frame-tray parts (PP-FTT top tray, PP-FTS side/cross
# members, PP128-FTA end rails, PP-FBS bottom supports). Revised owner
# direction: those painted structure pieces now go RAL 6002 green WITH the
# skid and pump (wide-revision livery; the original renderer painted them
# blue) - except genuinely pump-specific mounting brackets, which also stay
# RAL 6002.
COLL_TRAY = {"CAD_pump"}
COLL_PUMP = {"CAD_pump", "CAD_pump_new"}
# ...except genuinely pump-specific mounting brackets, which stay RAL 6002.
PUMP_MOUNT_PAT = ("mfb", "mount")
COLL_ENGINE = {"CAD_engine"}
COLL_CONTROL = {"CAD_controller"}
HARDWARE_PAT = ("bolt", "screw", "nut", "washer", "fastener", "plug")
RUBBER_PAT = ("rubber", "grommet", "seal", "hose")
EXHAUST_PAT = ("exhaust", "muffler")

# Documented Pantone Process Blue digital approximation. NOT applied here -
# PMS 293 remains the first-preview choice per owner direction. Recorded so a
# later Process Blue test does not repeat the earlier bogus #0057B8 example.
PROCESS_BLUE_APPROX = "#0085CA"

# Vendor-slot classification thresholds, expressed in linear-light units.
# Documented so the engine/pump look-dev decisions are reviewable rather than
# a blanket overwrite.
DARK_L = 0.045         # below: matte near-black -> rubber
DARK_METAL_L = 0.13    # below, with low channel spread: oxidised metal -> exhaust
BRIGHT_L = 0.55        # at/above, with low channel spread: bare metal -> hardware
NEUTRAL_SPREAD = 0.10  # max-minus-min channel spread treated as neutral

HELPERS = {"GroundShadowCatcher", "GroundFloor", "Key", "Fill", "Rim",
           "Cam_PumpHero", "Cam_EngineHero", "Cam_Hero", "Cam_Controller"}


def hex_lin(h):
    h = h.lstrip("#")
    lin = lambda c: (c / 255.0) / 12.92 if c / 255.0 <= 0.04045 else (((c / 255.0) + 0.055) / 1.055) ** 2.4
    return (lin(int(h[0:2], 16)), lin(int(h[2:4], 16)), lin(int(h[4:6], 16)), 1.0)


def make_mat(name, hexcode, rough, metal, coat=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = hex_lin(hexcode)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if "Coat Weight" in b.inputs:
        b.inputs["Coat Weight"].default_value = coat
    return m


def base_lin(mat):
    """Linear-light Base Color of a vendor material.

    glTF baseColorFactor is already linear, and the importer stores it
    unchanged on the Principled Base Color, so no conversion is applied here.
    Falls back to the viewport colour if there is no Principled node.
    """
    if mat is None:
        return None
    try:
        if mat.use_nodes:
            for n in mat.node_tree.nodes:
                if n.type == "BSDF_PRINCIPLED":
                    return tuple(n.inputs["Base Color"].default_value[:3])
    except Exception:
        pass
    return tuple(mat.diffuse_color[:3])


def _lum(rgb):
    return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]


def slot_role(rgb, context):
    """Map one vendor material slot to a look-dev role.

    ``context`` is "engine" or "pump". Uncharacterised / neutral slots are the
    painted castings and take the body paint. Bright neutral slots stay bare
    metal, near-black slots stay rubber, dark neutral slots stay oxidised
    metal - i.e. functional finishes are preserved wherever they are separable
    by colour.
    """
    if rgb is None:
        return "jd_green" if context == "engine" else "pump_green"
    lum = _lum(rgb)
    spread = max(rgb) - min(rgb)
    if lum < DARK_L:
        return "rubber"
    if lum < DARK_METAL_L and spread < NEUTRAL_SPREAD:
        return "exhaust"
    if lum >= BRIGHT_L and spread < NEUTRAL_SPREAD:
        return "hardware"
    return "jd_green" if context == "engine" else "pump_green"


def forced_role(o):
    """Whole-object role from name pattern or collection, or None."""
    n = o.name.lower()
    colls = {c.name for c in o.users_collection}
    if any(p in n for p in EXHAUST_PAT):
        return "exhaust"
    if any(p in n for p in RUBBER_PAT):
        return "rubber"
    if colls & COLL_CONTROL:
        return "control"
    if colls & COLL_SKID:
        return "green_structure"   # skid goes Leaf Green in the wide revision
    if colls & COLL_BALE:
        return "blue"              # lifting bale remains PMS 293 blue
    # Frame-tray parts under CAD_pump are painted structure; in the wide
    # revision they take RAL 6002 like the skid/pump. Pump-specific mounting
    # brackets are exempt and fall through to the pump paint context.
    if colls & COLL_TRAY and not any(p in n for p in PUMP_MOUNT_PAT):
        return "green_structure"
    if any(p in n for p in HARDWARE_PAT):
        return "hardware"
    return None


def paint_context(o):
    colls = {c.name for c in o.users_collection}
    if colls & COLL_ENGINE:
        return "engine"
    if colls & COLL_PUMP:          # CAD_pump + CAD_pump_new
        return "pump"
    return None


def slot_face_counts(mesh):
    """Faces per material slot - evidence for which vendor slots matter."""
    n = len(mesh.polygons)
    try:
        import numpy as np
        idx = np.empty(n, dtype=np.int32)
        mesh.polygons.foreach_get("material_index", idx)
        return np.bincount(idx, minlength=1)
    except Exception:
        counts = {}
        for p in mesh.polygons:
            counts[p.material_index] = counts.get(p.material_index, 0) + 1
        arr = [0] * (max(counts) + 1 if counts else 0)
        for k, v in counts.items():
            arr[k] = v
        return arr


def apply_livery(blue_hex):
    mats = {
        "pump_green": make_mat("ASTRA_Pump_RAL6002", LIVERY["pump_hex"], LIVERY["pump_rough"], 0.0, 0.2),
        "green_structure": make_mat("ASTRA_Structure_RAL6002", LIVERY["pump_hex"], LIVERY["pump_rough"], 0.0, 0.1),
        "blue": make_mat("ASTRA_Bale_PMS293", blue_hex, LIVERY["blue_rough"], 0.0),
        "jd_green": make_mat("ASTRA_Engine_JDGreen", LIVERY["jd_green_hex"], LIVERY["jd_rough"], 0.0, 0.15),
        "control": make_mat("ASTRA_Control_Face", *FUNCTIONAL["control"]),
        "exhaust": make_mat("ASTRA_Exhaust", *FUNCTIONAL["exhaust"]),
        "rubber": make_mat("ASTRA_Rubber", *FUNCTIONAL["rubber"]),
        "hardware": make_mat("ASTRA_Hardware", *FUNCTIONAL["hardware"]),
    }
    counts = {}
    inventory = []

    def _bump(role):
        counts[role] = counts.get(role, 0) + 1

    def _add(o, slot, vendor, rgb, role):
        inventory.append({
            "object": o.name, "slot": slot, "vendor": vendor,
            "vendor_lin": [round(c, 4) for c in rgb] if rgb else None,
            "role": role,
        })
        _bump(role)

    for o in bpy.context.scene.objects:
        if o.type != "MESH" or o.name in HELPERS:
            continue
        ctx = paint_context(o)
        forced = forced_role(o)
        slots = list(o.data.materials)

        if not slots:  # no slot table to preserve - append a single material
            role = forced or ("jd_green" if ctx == "engine" else
                              "pump_green" if ctx == "pump" else "green_structure")
            o.data.materials.append(mats[role])
            _add(o, 0, None, None, role)
            continue

        if forced or ctx is None:
            # Whole-object role (structure paint, control face, name-matched
            # functional part, or unclassified fallback). Keep the slot list so
            # material_index stays valid; every slot gets the same material.
            role = forced or "green_structure"
            for i in range(len(slots)):
                o.data.materials[i] = mats[role]
            _add(o, "*", None, None, role)
            continue

        # Engine/pump: classify each vendor slot on its own base colour so the
        # vendor per-face finish table is preserved, not blanket-overwritten.
        faces = slot_face_counts(o.data)
        for i, m in enumerate(slots):
            rgb = base_lin(m)
            role = slot_role(rgb, ctx)
            o.data.materials[i] = mats[role]
            _add(o, i, m.name if m else None, rgb, role)
            if i < len(faces):
                inventory[-1]["faces"] = int(faces[i])

    print("[astra] material role counts (objects/slots):", counts)
    return counts, inventory


def scene_bounds():
    lo = Vector((1e9,) * 3)
    hi = Vector((-1e9,) * 3)
    for o in bpy.context.scene.objects:
        if o.type != "MESH" or o.name in HELPERS:
            continue
        for c in o.bound_box:
            p = o.matrix_world @ Vector(c)
            for i in range(3):
                lo[i] = min(lo[i], p[i])
                hi[i] = max(hi[i], p[i])
    return lo, hi, (lo + hi) / 2, max((hi - lo).length / 2, 0.1)


def bbox_of(objs):
    lo = Vector((1e9,) * 3)
    hi = Vector((-1e9,) * 3)
    for o in objs:
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            for i in range(3):
                lo[i] = min(lo[i], w[i])
                hi[i] = max(hi[i], w[i])
    return lo, hi


def ensure_render_visibility():
    """Snapshot the source's render-suppression flags, then clear them in this
    in-memory preview only.

    The v10 source ships ``CAD_pump_new`` (the Vogelsang pump, 415 meshes) with
    COLLECTION-level ``hide_render = True``. Every object-level flag is clean
    (hide_render False, visible_camera True, in the view layer, non-empty
    evaluated mesh), so the pump silently never reaches a camera ray: the deck
    renders empty and the engine's flywheel is the nearest thing seen looking
    from +Y. A per-object census and a material inventory cannot detect this.

    Nothing geometric happens here - no reimport, no transform, no source write.
    The change is recorded and saved only in the new look-dev .blend.
    """
    changes = []
    for coll in bpy.data.collections:
        if coll.hide_render or coll.hide_viewport:
            before = [bool(coll.hide_render), bool(coll.hide_viewport)]
            coll.hide_render = False
            coll.hide_viewport = False
            changes.append({"scope": "collection:%s" % coll.name,
                            "before[hide_render,hide_viewport]": before,
                            "after[hide_render,hide_viewport]": [False, False]})

    def walk(lc):
        for ch in lc.children:
            before = [bool(ch.exclude), bool(ch.hide_viewport),
                      bool(getattr(ch, "hide_render", False))]
            ch.exclude = False
            ch.hide_viewport = False
            try:
                ch.hide_render = False
            except Exception:
                pass
            after = [bool(ch.exclude), bool(ch.hide_viewport),
                     bool(getattr(ch, "hide_render", False))]
            if before != after:
                changes.append({"scope": "layer_collection:%s" % ch.name,
                                "before[exclude,hide_viewport,hide_render]": before,
                                "after[exclude,hide_viewport,hide_render]": after})
            walk(ch)
    walk(bpy.context.view_layer.layer_collection)

    n_obj = 0
    for o in bpy.context.scene.objects:
        if o.type != "MESH":
            continue
        if bool(o.hide_render) or not o.visible_camera:
            o.hide_render = False
            o.visible_camera = True
            n_obj += 1
    if n_obj:
        changes.append({"scope": "objects", "count": n_obj,
                        "before": "hide_render/visible_camera suppressed",
                        "after": "renderable, camera-visible"})

    bpy.context.view_layer.update()
    for c in changes:
        print("[astra] visibility fix:", c)
    print("[astra] visibility fix: %d change(s)" % len(changes))
    return changes


def verify_render_participation(sc, cam):
    """Prove the pump really contributes to camera rays - not merely that the
    objects exist. Checks the evaluated active view layer, then ray-casts from
    the actual hero camera at a sample of pump meshes and reports what is hit."""
    dg = bpy.context.evaluated_depsgraph_get()
    vl = bpy.context.view_layer
    pump = [o for o in sc.objects if o.type == "MESH"
            and any(c.name == "CAD_pump_new" for c in o.users_collection)]
    not_renderable = [o.name for o in pump if o.hide_render or not o.visible_camera]
    not_in_vl = [o.name for o in pump if o.name not in vl.objects]
    empty = []
    for o in pump:
        oe = o.evaluated_get(dg)
        me = oe.to_mesh() if oe else None
        if me is None or len(me.polygons) == 0:
            empty.append(o.name)
        if me is not None:
            oe.to_mesh_clear()

    # Camera-ray test: aim at the centre of the largest pump meshes.
    origin = cam.matrix_world.translation
    sample = sorted(pump, key=lambda o: -len(o.data.polygons))[:24]
    hits = {}
    for o in sample:
        ctr = sum((o.matrix_world @ Vector(c) for c in o.bound_box),
                  Vector()) / 8.0
        d = ctr - origin
        if d.length < 1e-6:
            continue
        d.normalize()
        hit, _loc, _n, _i, hobj, _mw = sc.ray_cast(dg, origin, d)
        key = hobj.name if (hit and hobj) else "MISS"
        hits[key] = hits.get(key, 0) + 1
    pump_names = {o.name for o in pump}
    pump_hits = sum(n for k, n in hits.items() if k in pump_names)
    visible = (not not_renderable and not not_in_vl and not empty and pump_hits > 0)
    print("[astra] pump render check: %d/%d meshes renderable, all_in_view_layer=%s, "
          "all_non_empty_eval=%s" % (len(pump) - len(not_renderable), len(pump),
                                     not not_in_vl, not empty))
    print("[astra] pump camera-ray hits from %s: %d/%d sample rays hit CAD_pump_new"
          % (cam.name, pump_hits, len(sample)))
    info = {"collection": "CAD_pump_new",
            "pump_mesh_count": len(pump),
            "renderable": len(pump) - len(not_renderable),
            "not_renderable": not_renderable[:10],
            "not_in_view_layer": not_in_vl[:10],
            "empty_evaluated_mesh": empty[:10],
            "camera_ray_probe_camera": cam.name,
            "camera_ray_sample": len(sample),
            "camera_ray_pump_hits": pump_hits,
            "camera_ray_hits_detail": dict(sorted(hits.items(), key=lambda kv: -kv[1])),
            "pump_participates_in_camera_rays": bool(visible)}
    if not visible:
        raise SystemExit("[astra] FAIL: pump does not participate in camera rays: %s"
                         % (info,))
    return info


def setup_studio(radius, ground_z):
    # Opaque, rough, neutral studio floor. This is an opaque local beauty
    # preview, not a transparent-film composite, so a shadow catcher is NOT
    # used: a real diffuse floor at the measured skid bottom (tiny 2 mm
    # clearance) receives the key/fill lights and shows a genuine grounded
    # contact-shadow footprint under the skid supports. Deliberately large so
    # its far edge falls outside the fitted frame (no visible horizon line).
    #
    # Built from a mesh datablock and linked into the scene collection
    # explicitly (rather than primitive_plane_add) so the plane cannot land in
    # an unexpected collection.
    size = radius * 60.0
    half = size / 2.0
    z = ground_z - 0.002
    me = bpy.data.meshes.new("GroundFloorMesh")
    me.from_pydata([(-half, -half, z), (half, -half, z),
                    (half, half, z), (-half, half, z)], [], [(0, 1, 2, 3)])
    me.update()
    floor = bpy.data.objects.new("GroundFloor", me)
    bpy.context.scene.collection.objects.link(floor)
    floor.data.materials.append(
        make_mat("ASTRA_Studio_Floor", "#63666A", 0.92, 0.0))  # rough, modest albedo

    world = bpy.data.worlds.new("ASTRA_World")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = hex_lin("#B8BFC6")
    # Ambient pulled down from the catcher-era 0.55 so key/fill dominate and the
    # contact shadow under the skid reads clearly.
    bg.inputs["Strength"].default_value = 0.38

    print("[astra] floor %s size %.1f m at z=%.4f, in scene=%s, hide_render=%s"
          % (floor.name, size, z, floor.name in bpy.context.scene.objects,
             floor.hide_render))
    return floor


def probe_floor(sc, center, ground_z):
    """Ray-cast straight down from above the machine centre and report what the
    camera would actually hit on the floor - proves the floor really renders."""
    dg = bpy.context.evaluated_depsgraph_get()
    origin = Vector((center.x + 2.0, center.y, ground_z + 6.0))
    hit, loc, _n, _i, obj, _mw = sc.ray_cast(dg, origin, Vector((0.0, 0.0, -1.0)))
    name = obj.name if hit and obj else None
    print("[astra] floor probe: hit=%s object=%s z=%s"
          % (hit, name, round(loc.z, 4) if hit else None))
    return name


def add_lights(center, radius):
    # Key is a SUN, not a huge distant area light. The original 5.3 m softbox at
    # ~12 m produced a penumbra wider than the whole machine, so nothing cast a
    # readable shadow and the machine appeared to float. A small-angular-size
    # sun gives a defined contact shadow on the studio floor, and it is placed
    # on the +X side so the shadow falls towards the -X hero cameras.
    d = bpy.data.lights.new("Key", type="SUN")
    d.energy = 2.0
    d.angle = math.radians(5.0)
    d.color = (1.0, 0.98, 0.95)
    key = bpy.data.objects.new("Key", d)
    bpy.context.scene.collection.objects.link(key)
    key.location = (center.x + radius * 2.0, center.y + radius * 0.4, radius * 3.0)
    direction = Vector((center.x, center.y, center.z)) - key.location
    key.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()

    # Fill and rim stay soft area lights for shading and highlights; energies
    # are dropped so they do not wash the contact shadow back out.
    rigs = [
        ("Fill", -radius * 2.6, -radius * 1.6, radius * 1.6, 200, (0.95, 0.97, 1.0)),
        ("Rim", radius * 0.5, radius * 2.6, radius * 3.0, 450, (1.0, 1.0, 1.0)),
    ]
    for name, x, y, z, base, color in rigs:
        d = bpy.data.lights.new(name, type="AREA")
        d.energy = base * radius ** 1.5
        d.size = radius * 1.8
        d.color = color
        ob = bpy.data.objects.new(name, d)
        bpy.context.scene.collection.objects.link(ob)
        ob.location = (center.x + x, center.y + y, z)
        direction = Vector((center.x, center.y, center.z)) - ob.location
        ob.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def add_camera(name, location, target, lens=60):
    d = bpy.data.cameras.new(name)
    d.lens = lens
    d.clip_start = 0.05
    d.clip_end = 500.0
    ob = bpy.data.objects.new(name, d)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = location
    ob.rotation_euler = (Vector(target) - Vector(location)).to_track_quat("-Z", "Y").to_euler()
    return ob


def bbox_corners(lo, hi):
    return [Vector((x, y, z))
            for x in (lo.x, hi.x) for y in (lo.y, hi.y) for z in (lo.z, hi.z)]


def fit_camera(name, lo, hi, direction, res_x, res_y, lens=60.0,
               margin=0.90, sensor=36.0):
    """Place a camera along ``direction`` far enough that every bounding-box
    corner stays inside frame with ``margin`` headroom, then aim it at the box
    centre. This guarantees the whole subject is visible instead of relying on
    a hand-guessed radius multiple."""
    center = (lo + hi) / 2
    dirv = Vector(direction).normalized()
    fwd = -dirv
    right = fwd.cross(Vector((0.0, 0.0, 1.0)))
    if right.length < 1e-6:
        right = Vector((1.0, 0.0, 0.0))
    right.normalize()
    up = right.cross(fwd).normalized()
    half = (sensor / 2.0) / lens          # AUTO sensor fit: larger axis = width
    if res_x >= res_y:
        tan_h, tan_v = half, half * (res_y / res_x)
    else:
        tan_v, tan_h = half, half * (res_x / res_y)
    dist = 0.3
    for c in bbox_corners(lo, hi):
        w = c - center
        a, b, cc = w.dot(right), w.dot(up), w.dot(fwd)
        dist = max(dist,
                   abs(a) / (tan_h * margin) - cc,
                   abs(b) / (tan_v * margin) - cc)
    loc = center + dirv * dist
    cam = add_camera(name, loc, tuple(center), lens=lens)
    cam.data.clip_end = max(100.0, dist * 8.0)
    print("[astra] camera %s: dist %.2f m, lens %.0f mm" % (name, dist, lens))
    return cam, dist


def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def geo_digest(objects):
    """Hash vertex coords, loop indices and world matrices of the given mesh
    objects. Used to prove look-dev never touched CAD geometry or transforms."""
    h = hashlib.sha256()
    try:
        import numpy as np
    except Exception:
        np = None
    for o in sorted(objects, key=lambda x: x.name):
        me = o.data
        h.update(o.name.encode("utf-8"))
        for row in o.matrix_world:
            h.update((" ".join("%.7f" % v for v in row) + "|").encode("ascii"))
        h.update(str(len(me.vertices)).encode())
        if np is not None:
            co = np.empty(len(me.vertices) * 3, dtype=np.float32)
            me.vertices.foreach_get("co", co)
            h.update(co.tobytes())
            li = np.empty(len(me.loops), dtype=np.int32)
            me.loops.foreach_get("vertex_index", li)
            h.update(li.tobytes())
        else:
            for v in me.vertices:
                h.update(("%.6f %.6f %.6f " % (v.co.x, v.co.y, v.co.z)).encode())
            for lp in me.loops:
                h.update(str(lp.vertex_index).encode())
    return h.hexdigest()


def image_stats(path):
    """Load a rendered PNG back and measure pixel variation."""
    img = bpy.data.images.load(path, check_existing=False)
    try:
        n = len(img.pixels)
        try:
            import numpy as np
            px = np.empty(n, dtype=np.float32)
            img.pixels.foreach_get(px)
            rgb = px.reshape(-1, 4)[:, :3]
            return {
                "pixels": int(rgb.shape[0]),
                "min": float(rgb.min()),
                "max": float(rgb.max()),
                "mean": float(rgb.mean()),
                "std": float(rgb.std()),
                "unique_rounded": int(np.unique(np.round(rgb, 3)).size),
            }
        except Exception:
            vals = [img.pixels[i] for i in range(0, n, 997)]
            return {"pixels": n // 4, "sampled_min": min(vals),
                    "sampled_max": max(vals)}
    finally:
        bpy.data.images.remove(img)


def main():
    if "--" not in sys.argv:
        raise SystemExit("usage: blender -b --python astra_render_wide_preview.py -- "
                         "--input <blend> --output-dir <dir>")
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--width", type=int, default=1200)
    p.add_argument("--samples", type=int, default=32)
    p.add_argument("--threads", type=int, default=4)
    p.add_argument("--blue-hex", default=LIVERY["blue_hex"])
    p.add_argument("--with-controller-detail", action="store_true")
    p.add_argument("--save-blend", default=None)
    a = p.parse_args(sys.argv[sys.argv.index("--") + 1:])

    src = os.path.abspath(a.input)
    out_dir = os.path.abspath(a.output_dir)
    save_blend = (os.path.abspath(a.save_blend) if a.save_blend
                  else os.path.join(out_dir, "astra-wide-preview-lookdev.blend"))
    if os.path.abspath(save_blend) == src:
        raise SystemExit("[astra] refusing to save over the source .blend: " + save_blend)
    os.makedirs(out_dir, exist_ok=True)

    result = {"input": src, "output_dir": out_dir, "save_blend": save_blend}
    t0 = time.time()
    src_hash_before = sha256_file(src)
    print("[astra] source sha256 (before):", src_hash_before)

    bpy.ops.wm.open_mainfile(filepath=src)
    load_s = time.time() - t0
    # The source suppresses the pump at collection level; clear that in memory
    # before anything is measured, coloured or rendered.
    vis_changes = ensure_render_visibility()
    lo, hi, center, radius = scene_bounds()
    print("[astra] bounds m:", tuple(round(v, 3) for v in lo),
          tuple(round(v, 3) for v in hi), "radius", round(radius, 3))

    cad_objs = [o for o in bpy.context.scene.objects
                if o.type == "MESH" and o.name not in HELPERS]
    digest_before = geo_digest(cad_objs)
    print("[astra] geometry digest before look-dev:", digest_before)

    counts, inventory = apply_livery(a.blue_hex)
    floor = setup_studio(radius, lo.z)
    add_lights(center, radius)

    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = a.samples
    sc.cycles.use_denoising = True
    try:
        sc.cycles.denoiser = "OPENIMAGEDENOISE"
    except Exception:
        pass
    sc.cycles.max_bounces = 8
    sc.cycles.diffuse_bounces = 3
    sc.cycles.glossy_bounces = 6
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.adaptive_threshold = 0.02
    sc.cycles.seed = 0
    sc.render.threads_mode = "FIXED"
    sc.render.threads = a.threads
    sc.render.resolution_x = a.width
    sc.render.resolution_y = int(a.width * 0.7)
    sc.render.image_settings.file_format = "PNG"
    sc.view_settings.view_transform = "AgX"          # matches pipeline jobs/*.json
    for look in ("AgX - Medium High Contrast", "Medium High Contrast", "None"):
        try:
            sc.view_settings.look = look
            break
        except Exception:
            continue
    sc.view_settings.exposure = -0.2
    sc.render.use_persistent_data = True

    # Prove the floor is really in the render view layer (a silent miss here is
    # exactly what makes a machine look like it is floating).
    bpy.context.view_layer.update()
    probe_hit = probe_floor(sc, center, lo.z)
    floor_ok = (probe_hit == "GroundFloor")
    if not floor_ok:
        raise SystemExit("[astra] FAIL: floor probe hit %r, expected GroundFloor"
                         % (probe_hit,))

    # PRIMARY hero: pump-side three-quarter from -X / +Y / above. The pump body
    # (CAD_pump_new, Y>0) is on the near side, so it stays legible instead of
    # being hidden behind the engine (CAD_engine spans Y<0). Whole machine is
    # kept in frame by the bounding-box fit.
    # PRIMARY hero: pump-side three-quarter from minus-X / plus-Y / above, so
    # the pump (CAD_pump_new, +Y end) is the nearest and largest subject and the
    # engine stays legible beyond it along the skid's Y axis. The bounding-box
    # fit keeps the complete machine in frame with margin.
    shots = [("astra-wide-preview-threequarter",
              fit_camera("Cam_PumpHero", lo, hi, (-0.40, 0.84, 0.45),
                         sc.render.resolution_x, sc.render.resolution_y,
                         lens=50.0, margin=0.92)[0])]
    # Secondary engine-side view from minus-X / minus-Y / above. Kept as an
    # additional view; it also exposes the minus-X controller face.
    shots.append(("astra-wide-preview-engine-side",
                  fit_camera("Cam_EngineHero", lo, hi, (-0.72, -0.52, 0.46),
                             sc.render.resolution_x, sc.render.resolution_y,
                             lens=50.0, margin=0.92)[0]))
    detail_info = None
    if a.with_controller_detail:
        ctl = [o for o in cad_objs
               if any(c.name == "CAD_controller" for c in o.users_collection)]
        if ctl:
            clo, chi = bbox_of(ctl)
            cam, dist = fit_camera("Cam_Controller", clo, chi, (-0.55, -0.78, 0.30),
                                   sc.render.resolution_x, sc.render.resolution_y,
                                   lens=85.0, margin=0.88)
            shots.append(("astra-wide-preview-controller-detail", cam))
            detail_info = {"bbox_min": [round(v, 4) for v in clo],
                           "bbox_max": [round(v, 4) for v in chi],
                           "camera_dist_m": round(dist, 3)}
        else:
            print("[astra] WARNING: no CAD_controller objects found for detail shot")

    # Prove the pump really reaches camera rays from the primary hero before
    # anything is rendered or called complete.
    pump_check = verify_render_participation(sc, shots[0][1])

    # Save the materialised look-dev scene before rendering so a later Cycles
    # failure cannot lose it. The primary pump-side hero is left as the active
    # camera for owner inspection.
    sc.camera = shots[0][1]
    bpy.ops.wm.save_as_mainfile(filepath=save_blend, compress=True,
                                check_existing=False)
    print("[astra] saved look-dev blend (active camera %s): %s"
          % (shots[0][1].name, save_blend))

    images = {}
    for name, cam in shots:
        sc.camera = cam
        path = os.path.join(out_dir, name + ".png")
        sc.render.filepath = path
        ts = time.time()
        bpy.ops.render.render(write_still=True)
        dt = time.time() - ts
        st = image_stats(path)
        images[name] = {"path": path, "render_s": round(dt, 1), **st}
        print("[astra] wrote %s in %.1fs stats=%s" % (path, dt, st))

    digest_after = geo_digest(cad_objs)
    src_hash_after = sha256_file(src)
    geom_ok = (digest_before == digest_after)
    src_ok = (src_hash_before == src_hash_after)
    print("[astra] geometry digest after :", digest_after)
    print("[astra] geometry unchanged:", geom_ok)
    print("[astra] source unchanged  :", src_ok)
    if not (geom_ok and src_ok):
        raise SystemExit("[astra] FAIL: geometry or source changed during look-dev")

    result.update({
        "script": os.path.abspath(__file__),
        "timing_s": {"open_blend": round(load_s, 1), "total": round(time.time() - t0, 1)},
        "bounds_m": {"min": [round(v, 4) for v in lo], "max": [round(v, 4) for v in hi],
                     "radius": round(radius, 4)},
        "settings": {"width": a.width, "height": int(a.width * 0.7),
                     "samples": a.samples, "threads": a.threads,
                     "engine": "CYCLES/CPU", "view_transform": "AgX - Medium High Contrast",
                     "blue_hex": a.blue_hex, "render_helpers": sorted(HELPERS)},
        "source_sha256_before": src_hash_before,
        "source_sha256_after": src_hash_after,
        "source_unchanged": src_ok,
        "geometry_digest_before": digest_before,
        "geometry_digest_after": digest_after,
        "geometry_unchanged": geom_ok,
        "material_role_counts": counts,
        "material_slot_inventory": inventory,
        "controller_detail": detail_info,
        "source_visibility_fix": {
            "reason": ("v10 ships CAD_pump_new with collection hide_render=True; "
                       "every object-level flag was clean, so the pump could never "
                       "reach a camera ray and the deck rendered empty"),
            "applied_to": "in-memory preview only, saved in the look-dev .blend",
            "source_file_untouched": True,
            "changes": vis_changes,
        },
        "pump_render_participation": pump_check,
        "grounding": {
            "floor_object": floor.name,
            "floor_is_opaque_diffuse": True,
            "floor_material": "ASTRA_Studio_Floor #63666A roughness 0.92",
            "floor_top_z_m": round(lo.z - 0.002, 4),
            "skid_bottom_z_m": round(lo.z, 4),
            "floor_probe_hit": probe_hit,
            "floor_probe_ok": floor_ok,
            "floor_excluded_from": ["camera fit bounds", "geometry digest"],
            "world_strength": 0.38,
            "key_light": "SUN 2.0 / angle 5deg (defined contact shadow)",
        },
        "images": images,
    })
    with open(os.path.join(out_dir, "astra-render-execution.json"), "w") as fh:
        json.dump(result, fh, indent=1)
    with open(os.path.join(out_dir, "astra-wide-preview-slot-inventory.json"), "w") as fh:
        json.dump({"material_role_counts": counts, "slots": inventory}, fh, indent=1)
    print("[astra] DONE in %.1fs" % (time.time() - t0))


if __name__ == "__main__":
    main()
