"""CPU Cycles studio inputs. Run with blender --background --python this_file."""

import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector


ROOT = Path("outputs/studio-demo")
ROOT.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = 24
scene.cycles.use_denoising = True
scene.render.threads_mode = "FIXED"
scene.render.threads = 4
scene.render.resolution_x = 512
scene.render.resolution_y = 320
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.fps = 24
scene.world = bpy.data.worlds.new("Studio")
scene.world.use_nodes = True
scene.world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.16, 0.18, 0.22, 1)
scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.35


def material(name, color, metallic=0, roughness=0.4):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    node = mat.node_tree.nodes.get("Principled BSDF")
    node.inputs["Base Color"].default_value = (*color, 1)
    node.inputs["Metallic"].default_value = metallic
    node.inputs["Roughness"].default_value = roughness
    return mat


def aim(obj, point):
    obj.rotation_euler = (Vector(point) - obj.location).to_track_quat("-Z", "Y").to_euler()


def light(name, position, energy, size, color):
    data = bpy.data.lights.new(name, "AREA")
    data.energy, data.shape, data.size, data.color = energy, "DISK", size, color
    obj = bpy.data.objects.new(name, data)
    scene.collection.objects.link(obj)
    obj.location = position
    aim(obj, (0, 0, 1))


copper = material("Brushed copper", (0.63, 0.21, 0.07), 0.8, 0.24)
gray = material("Neutral guide", (0.3, 0.36, 0.42), 0.15, 0.32)
floor = material("Studio floor", (0.12, 0.145, 0.18), 0.15, 0.32)
bpy.ops.mesh.primitive_plane_add(size=200)
bpy.context.object.data.materials.append(floor)
light("Key softbox", (-3, -4, 6), 950, 4, (1.0, 0.85, 0.7))
light("Fill softbox", (4, -1, 4), 700, 3, (0.65, 0.8, 1))
light("Rim softbox", (1, 4, 5), 1200, 3, (1, 0.93, 0.85))
bpy.ops.object.camera_add(location=(4.2, -7.5, 4.0))
camera = bpy.context.object
camera.data.type = "ORTHO"
camera.data.ortho_scale = 5.6
aim(camera, (0, 0, 1.05))
scene.camera = camera


def cube(name, dimensions, mat):
    bpy.ops.mesh.primitive_cube_add(size=2, location=(0, 0, dimensions[2] / 2 + 0.05))
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(mat)
    bevel = obj.modifiers.new("Rounded machined edges", "BEVEL")
    bevel.width, bevel.segments = 0.1, 5
    obj.modifiers.new("Face normals", "WEIGHTED_NORMAL")
    return obj


def render(obj, angle, filename):
    obj.rotation_euler.z = math.radians(angle)
    scene.render.filepath = str(ROOT / filename)
    bpy.ops.render.render(write_still=True)


obj = cube("Copper cube", (1.65, 1.65, 1.65), copper)
render(obj, 15, "first.png")
render(obj, 75, "last.png")
if "--review-only" in sys.argv:
    (ROOT / "rigid-frames").mkdir(exist_ok=True)
    for index in (0, 14, 28, 42, 55):
        render(obj, 15 + 60 * index / 55, "rigid-frames/%04d.png" % index)
else:
    bpy.data.objects.remove(obj, do_unlink=True)

    # A different appearance/shape for image + video motion-reference testing.
    bpy.ops.mesh.primitive_torus_add(major_radius=0.82, minor_radius=0.26,
                                    major_segments=64, minor_segments=24, location=(0, 0, 1.14))
    obj = bpy.context.object
    obj.rotation_euler.x = math.pi / 2
    obj.data.materials.append(copper)
    for face in obj.data.polygons:
        face.use_smooth = True
    render(obj, 15, "target.png")
    bpy.data.objects.remove(obj, do_unlink=True)

    guide = cube("Different guide cuboid", (1.35, 1.1, 2.1), gray)
    (ROOT / "guide-frames").mkdir(exist_ok=True)
    for index in range(56):
        render(guide, 15 + 60 * index / 55, "guide-frames/%04d.png" % index)
