"""
KRESLO 3D MODELI - Blender Python (bpy) skripti
--------------------------------------------------
3ddd.ru kabi saytlarga joylashga tayyor, real ko'rinishdagi
(subdivision surface, bevel, PBR materiallar bilan) kreslo modeli yaratadi.

ISHLATISH:
1. Blender'ni oching (yangi, bo'sh sahna)
2. Yuqoridagi "Scripting" bo'limiga o'ting
3. "New" tugmasini bosib yangi skript oching
4. Shu faylning butun mazmunini o'sha yerga joylang (nusxa-joylashtiring)
5. Pastdagi OUTPUT_DIR o'zgaruvchisiga qayerga eksport qilinishini yozing
6. "Run Script" (▶️) tugmasini bosing

Skript ishlab bo'lgach, sahnada tayyor kreslo paydo bo'ladi va
OUTPUT_DIR papkasiga .obj hamda .fbx fayllar eksport qilinadi.

Keyingi qadamlar (tavsiya):
- Cycles renderi bilan render qiling (materiallar Cycles/Eevee ikkalasida ham ishlaydi)
- HDRI muhit yorug'ligini qo'shing (World > Environment Texture)
- Kerak bo'lsa qo'shimcha detal (tikuv chizig'i, tugmalar) qo'shing
"""

import bpy
import bmesh
import math
import os

# ================== SOZLAMALAR ==================
OUTPUT_DIR = r"C:\Users\MAG GADJET\Desktop\kreslo_3d"   # eksport qilinadigan papka - o'zgartiring
FABRIC_COLOR = (0.55, 0.16, 0.09, 1.0)   # to'qima rangi (terrakota)
WOOD_COLOR = (0.25, 0.14, 0.07, 1.0)     # yog'och rangi
CUSHION_COLOR = (0.85, 0.62, 0.30, 1.0)  # yostiqcha rangi
# ==================================================


def clear_scene():
    """Sahnadagi barcha obyektlarni tozalaydi"""
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    for block in list(bpy.data.meshes):
        if block.users == 0:
            bpy.data.meshes.remove(block)


def make_material(name, base_color, roughness=0.7, metallic=0.0):
    """Oddiy PBR (Principled BSDF) material yaratadi"""
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = base_color
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    return mat


def make_fabric_material(name, base_color):
    """Mayin bo'rtma (bump) effekti bilan to'qima materiali yaratadi"""
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = base_color
    bsdf.inputs["Roughness"].default_value = 0.85

    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 120.0
    noise.inputs["Detail"].default_value = 4.0

    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.08

    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def make_wood_material(name, base_color):
    """Yog'och tolasi ko'rinishidagi procedural material yaratadi"""
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    bsdf.inputs["Roughness"].default_value = 0.35

    wave = nodes.new("ShaderNodeTexWave")
    wave.inputs["Scale"].default_value = 8.0
    wave.inputs["Distortion"].default_value = 3.0

    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (base_color[0]*0.6, base_color[1]*0.6, base_color[2]*0.6, 1.0)
    ramp.color_ramp.elements[1].color = base_color

    links.new(wave.outputs["Color"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


def add_soft_box(name, size, location, bevel_width=0.04, subsurf_levels=2):
    """Yumshoq, dumaloqlangan (yostiqsimon) qutini yaratadi -
    o'rindiq, suyanchiq va qo'l suyanchiqlari uchun ishlatiladi"""
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = (size[0] / 2, size[1] / 2, size[2] / 2)
    bpy.ops.object.transform_apply(scale=True)

    bevel = obj.modifiers.new(name="Bevel", type='BEVEL')
    bevel.width = bevel_width
    bevel.segments = 6
    bevel.limit_method = 'ANGLE'

    subsurf = obj.modifiers.new(name="Subsurf", type='SUBSURF')
    subsurf.levels = subsurf_levels
    subsurf.render_levels = subsurf_levels

    bpy.ops.object.shade_smooth()
    return obj


def add_turned_leg(name, location, height=0.5, top_radius=0.045, bottom_radius=0.03):
    """Aylantirilgan (lathe) uslubdagi yog'och oyoq yaratadi -
    Bezier profilini Screw modifikatori bilan aylantirib hosil qiladi"""
    curve_data = bpy.data.curves.new(name + "_profile", type='CURVE')
    curve_data.dimensions = '2D'
    spline = curve_data.splines.new('BEZIER')

    # Oyoq profilini belgilaydigan nazorat nuqtalari (klassik "turned leg" shakli)
    points = [
        (0.0, 0.0, top_radius),
        (height * 0.25, 0.0, top_radius * 1.15),
        (height * 0.45, 0.0, top_radius * 0.65),
        (height * 0.7, 0.0, top_radius * 0.9),
        (height, 0.0, bottom_radius),
    ]
    spline.bezier_points.add(len(points) - 1)
    for i, (z, y, x) in enumerate(points):
        bp = spline.bezier_points[i]
        bp.co = (x, 0, z)
        bp.handle_left_type = 'AUTO'
        bp.handle_right_type = 'AUTO'

    profile_obj = bpy.data.objects.new(name + "_profile", curve_data)
    bpy.context.collection.objects.link(profile_obj)

    screw = profile_obj.modifiers.new(name="Screw", type='SCREW')
    screw.axis = 'Z'
    screw.angle = math.radians(360)
    screw.steps = 24
    screw.render_steps = 24

    bpy.context.view_layer.objects.active = profile_obj
    bpy.ops.object.convert(target='MESH')
    leg = bpy.context.active_object
    leg.name = name
    leg.location = location
    leg.rotation_euler = (math.radians(90), 0, 0)
    bpy.ops.object.shade_smooth()
    return leg


def build_chair():
    fabric_mat = make_fabric_material("Fabric_Terracotta", FABRIC_COLOR)
    wood_mat = make_wood_material("Wood_Walnut", WOOD_COLOR)
    cushion_mat = make_fabric_material("Fabric_Cushion", CUSHION_COLOR)

    # O'rindiq
    seat = add_soft_box("Seat", size=(1.0, 0.9, 0.18), location=(0, 0, 0.5))
    seat.data.materials.append(fabric_mat)

    # Suyanchiq
    backrest = add_soft_box("Backrest", size=(1.0, 0.18, 0.8), location=(0, -0.4, 0.95))
    backrest.rotation_euler = (math.radians(-8), 0, 0)
    backrest.data.materials.append(fabric_mat)

    # Qo'l suyanchiqlari
    for side, x in [("L", -0.48), ("R", 0.48)]:
        arm = add_soft_box(f"Armrest_{side}", size=(0.16, 0.85, 0.45), location=(x, 0, 0.72))
        arm.data.materials.append(fabric_mat)

    # Dekorativ yostiqcha
    cushion = add_soft_box("Cushion", size=(0.5, 0.12, 0.45), location=(0, -0.28, 0.78),
                            bevel_width=0.06, subsurf_levels=2)
    cushion.rotation_euler = (math.radians(20), 0, math.radians(3))
    cushion.data.materials.append(cushion_mat)

    # Oyoqlar
    leg_positions = [
        ("Leg_FL", (-0.42, 0.35, 0.0)),
        ("Leg_FR", (0.42, 0.35, 0.0)),
        ("Leg_BL", (-0.42, -0.35, 0.0)),
        ("Leg_BR", (0.42, -0.35, 0.0)),
    ]
    for name, loc in leg_positions:
        leg = add_turned_leg(name, loc, height=0.42)
        leg.data.materials.append(wood_mat)

    # Barcha qismlarni "Kreslo" nomli guruhga birlashtirish
    parts = [obj for obj in bpy.data.objects if obj.name.startswith(
        ("Seat", "Backrest", "Armrest", "Cushion", "Leg")
    )]
    bpy.ops.object.select_all(action='DESELECT')
    for p in parts:
        p.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join()
    bpy.context.active_object.name = "Kreslo"


def setup_lighting_and_camera():
    """Sodda studio yoritish va kamera (preview render uchun)"""
    bpy.ops.object.light_add(type='AREA', location=(2.5, -2.5, 3))
    key = bpy.context.active_object
    key.data.energy = 400
    key.data.size = 2.5

    bpy.ops.object.light_add(type='AREA', location=(-2.5, 2, 2))
    fill = bpy.context.active_object
    fill.data.energy = 150
    fill.data.size = 3

    bpy.ops.object.camera_add(location=(3.2, -3.2, 1.8),
                               rotation=(math.radians(72), 0, math.radians(45)))
    bpy.context.scene.camera = bpy.context.active_object


def export_model():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    bpy.ops.object.select_all(action='DESELECT')
    chair = bpy.data.objects.get("Kreslo")
    if chair:
        chair.select_set(True)
        bpy.context.view_layer.objects.active = chair

    obj_path = os.path.join(OUTPUT_DIR, "kreslo.obj")
    fbx_path = os.path.join(OUTPUT_DIR, "kreslo.fbx")

    bpy.ops.wm.obj_export(filepath=obj_path, export_selected_objects=True)
    bpy.ops.export_scene.fbx(filepath=fbx_path, use_selection=True)

    print(f"Eksport qilindi: {obj_path}")
    print(f"Eksport qilindi: {fbx_path}")


# ================== ISHGA TUSHIRISH ==================
clear_scene()
build_chair()
setup_lighting_and_camera()
export_model()
print("Kreslo 3D modeli muvaffaqiyatli yaratildi!")
