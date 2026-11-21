"""Render the 2020 source OBJ as a scale profile and two views beneath the ends.

Run with Blender 4.x in background mode, passing the OBJ and PNG after --.
The only transformation places the native X-starboard, Y-up, Z-bow coordinates
in Blender's X-starboard, Y-bow, Z-up frame.
"""
import math
import sys
import tempfile
from pathlib import Path

import bpy
from mathutils import Vector
from PIL import Image, ImageDraw, ImageFont

source, destination = [Path(a).resolve() for a in sys.argv[sys.argv.index('--') + 1:]]
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.samples = 12
scene.cycles.use_denoising = False
scene.render.film_transparent = True
scene.render.image_settings.color_mode = 'RGBA'
scene.view_settings.view_transform = 'AgX'
scene.world = bpy.data.worlds.new('Polar daylight')
scene.world.use_nodes = True
background = scene.world.node_tree.nodes.get('Background')
background.inputs['Color'].default_value = (.83, .91, 1.0, 1.0)
background.inputs['Strength'].default_value = .8

colors = {}
for line in source.with_suffix('.mtl').read_text().splitlines():
    columns = line.split()
    if not columns:
        continue
    if columns[0] == 'newmtl':
        name = columns[1]
    if columns[0] == 'Kd':
        colors[name] = tuple(map(float, columns[1:4]))

vertices, triangles, surface = [], [], []
materials = list(colors)
for line in source.read_text().splitlines():
    if line.startswith('v '):
        x, z, y = map(float, line.split()[1:])
        vertices.append((x, y, z))
    elif line.startswith('usemtl '):
        index = materials.index(line.split()[1])
    elif line.startswith('f '):
        indices = [int(v.split('/')[0]) - 1 for v in line.split()[1:]]
        if len(indices) != 3:
            raise ValueError('Triangulated model expected')
        triangles.append(tuple(reversed(indices)))
        surface.append(index)

mesh = bpy.data.meshes.new('Ship')
mesh.from_pydata(vertices, [], triangles)
ship = bpy.data.objects.new('Rimehaven', mesh)
scene.collection.objects.link(ship)
for name in materials:
    material = bpy.data.materials.new(name)
    material.diffuse_color = (*colors[name],1)
    material.use_nodes = True
    shader = material.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Base Color'].default_value = material.diffuse_color
    shader.inputs['Roughness'].default_value = .57
    mesh.materials.append(material)
mesh.polygons.foreach_set('material_index', surface)
mesh.update()

def sun(location, strength):
    data = bpy.data.lights.new('Daylight', 'SUN')
    data.energy = strength
    data.angle = math.radians(14)
    light = bpy.data.objects.new('Daylight', data)
    scene.collection.objects.link(light)
    light.rotation_euler = (-Vector(location)).to_track_quat('-Z','Y').to_euler()

sun((.6, .85, 1.45), 2.2)
sun((-.9, -.3, .4), .65)
cam = bpy.data.objects.new('Inspection', bpy.data.cameras.new('Inspection'))
scene.collection.objects.link(cam)
scene.camera = cam
cam.data.type = 'ORTHO'
cam.data.clip_end = 600

def render(path, eye, target, span, size):
    cam.location = Vector(target) + Vector(eye).normalized() * 240
    cam.rotation_euler = (Vector(target) - cam.location).to_track_quat('-Z','Y').to_euler()
    cam.data.ortho_scale = span
    scene.render.resolution_x, scene.render.resolution_y = size
    scene.render.resolution_percentage = 100
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    return Image.open(path).convert('RGBA')

def font(name, size):
    # Pillow also resolves local fonts by filename on common OSes.
    for family in [name, 'DejaVuSans.ttf', 'arial.ttf']:
        try:
            return ImageFont.truetype(family, size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)

ink = '#152d3a'
muted = '#436370'
accent = '#197c7f'
paper = '#e8eff0'
white = '#f6f9f8'
board = Image.new('RGB', (1600, 1090), white)
draw = ImageDraw.Draw(board)
def label(x, y, s, points=21, bold=False, color=ink, anchor=None):
    family = 'DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf'
    draw.text((x, y), s, font=font(family, points), fill=color, anchor=anchor)
def paste(image, x, y):
    board.paste(image, (x,y), image)

with tempfile.TemporaryDirectory() as workspace:
    tmp = Path(workspace)
    profile = render(tmp / 'side.png', (1,0,0), (0,0,10), 177, (1520,430))
    forward = render(tmp / 'bow.png', (.8, 1.05,-.24), (0,58.5,1.7), 51.5, (730,298))
    stern = render(tmp / 'stern.png', (.70,-1.37,-.48), (0,-72.5,-1.4), 49.5, (730,298))

    draw.rectangle((0,0,1600,132), fill='#132e3c')
    label(55,17,'WHITE MERIDIAN CLASS',20,True,'#92d7ce')
    label(52,42,'HMAS Rimehaven',57,True,'#f2f7f6')
    label(1544,40,'Antarctic patrol icebreaker',30,False,'#f2f7f6','ra')
    label(1544,87,'Sea Power  /  2020 fit  /  v0.2.0',19,False,'#bad2d7','ra')

    draw.rectangle((0,133,1600,635), fill=paper)
    label(54,151,'Starboard profile',30,True)
    # Orthographic ship centre at y=10 m; mark the actual z=0 datum.
    top = 199
    pixels_per_metre = 1520 / 177
    waterline = round(top + 430 / 2 + 10 * pixels_per_metre)
    draw.line((48,waterline,1552,waterline), fill='#699295', width=2)
    paste(profile,40,top)
    label(55,600,'Length 160 m     /     Beam 29 m',19,False,muted)
    label(1544,600,'Teal line · design waterline',19,False,muted,'ra')
    draw.line((48,635,1552,635), fill='#aabfc2',width=2)

    for x, image, title, caption in [
        (47,forward,'Icebreaking bow','Raked forefoot and forward skeg.'),
        (823,stern,'Stern gear','Three shrouded screws beneath the rounded stern.'),
    ]:
        label(x+4,659,title,29,True)
        draw.rectangle((x,713,x+730,1011),fill=paper)
        paste(image,x,713)
        label(x+4,1032,caption,20,False,muted)

destination.parent.mkdir(parents=True, exist_ok=True)
board.save(destination, optimize=True)
print('Wrote', destination, 'from', source)
