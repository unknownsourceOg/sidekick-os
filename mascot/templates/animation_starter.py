"""A bundled Blender scene; the app passes a new project folder, never model code."""
import argparse
import math
from pathlib import Path
import sys
import bpy

parser = argparse.ArgumentParser()
parser.add_argument('--output', required=True)
args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
out = Path(args.output).resolve(); out.mkdir(parents=True, exist_ok=True)
target = out / 'sidekick-starter.blend'
if target.exists():
    raise RuntimeError('The animation project already exists; choose a new project.')
bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
scene = bpy.context.scene
scene.render.engine = 'BLENDER_EEVEE_NEXT'
scene.render.resolution_x = 1280; scene.render.resolution_y = 720
scene.render.resolution_percentage = 100
scene.render.fps = 24; scene.frame_end = 96
scene.world.color = (0.008, 0.016, 0.025)
material = bpy.data.materials.new('Sidekick teal'); material.diffuse_color = (0.06, 0.8, 0.56, 1)
material.use_nodes = True
bsdf = material.node_tree.nodes.get('Principled BSDF')
bsdf.inputs['Base Color'].default_value = (0.025, 0.55, 0.34, 1)
bsdf.inputs['Metallic'].default_value = 0.65; bsdf.inputs['Roughness'].default_value = 0.25
bpy.ops.mesh.primitive_cube_add(size=2, location=(0, 0, 1))
obj = bpy.context.object; obj.name = 'Your animated object'; obj.data.materials.append(material)
bevel = obj.modifiers.new('Soft corners', 'BEVEL'); bevel.width = 0.16; bevel.segments = 5
obj.rotation_euler = (0, 0, 0); obj.keyframe_insert('rotation_euler', frame=1)
obj.rotation_euler = (0.2, 0, 2 * math.pi); obj.keyframe_insert('rotation_euler', frame=96)
bpy.ops.mesh.primitive_plane_add(size=200)
bpy.ops.object.light_add(type='AREA', location=(2, -4, 7)); bpy.context.object.data.energy = 1600
bpy.context.object.data.shape = 'DISK'; bpy.context.object.data.size = 5
bpy.ops.object.camera_add(location=(5, -7, 4))
camera = bpy.context.object
from mathutils import Vector
camera.rotation_euler = (Vector((0, 0, 1)) - camera.location).to_track_quat('-Z', 'Y').to_euler()
scene.camera = camera; scene.frame_set(1)
scene.render.image_settings.file_format = 'PNG'; scene.render.filepath = str(out / 'frames/frame-')
bpy.ops.wm.save_as_mainfile(filepath=str(target))
(out / 'START-HERE.txt').write_text('Press Space in Blender to play the 4-second animation.\n'
    'Use Render > Render Animation to export PNG frames.\n'
    'Ask Sidekick in Animation mode to plan changes or write Blender Python.\n')
print('SIDEKICK_ANIMATION_READY=' + str(target))
