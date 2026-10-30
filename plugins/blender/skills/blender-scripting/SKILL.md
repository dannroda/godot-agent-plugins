---
name: "blender-scripting"
description: "Use when building, editing, checking or previewing 3D game assets with Blender Python (bpy, bmesh) in headless mode: props and blockouts, modifiers, UVs, materials, keyframes, render previews, poly and scale audits. Covers Blender 5 API changes (action.fcurves, use_auto_smooth, use_nodes). To export to a game engine, see blender-to-godot."
---

# Blender scripting (5.x)

Everything here was run on Blender 5.2.3 in background mode. For another version, check names with `bpy.app.version` and `dir()` before trusting them.

## Run it so failures are visible

```bash
blender -b --factory-startup --python-exit-code 1 --python build.py -- out/crate.glb
```

- `--python-exit-code` must come **before** `--python`. Without it, or placed after, a script that raises still exits 0.
- `--factory-startup` keeps the user's add-ons and preferences out of the result.
- Script arguments go after `--`: `sys.argv[sys.argv.index('--') + 1:]`.

## Rules

- Start with `bpy.ops.wm.read_factory_settings(use_empty=True)`. The default cube, camera and light are gone, and the glTF exporter stays available.
- Create data with `bpy.data` and `bmesh`. They need no selection or active object. Use `bpy.ops` only where no data API exists (UV unwrap, smooth operators), and set the active object first.
- `obj.matrix_world` is stale after you set a transform until `bpy.context.view_layer.update()` runs.
- Keep bevels, mirrors and arrays as modifiers. The exporter can apply them, and the source stays editable.
- Write every size in meters. 1 Blender unit becomes 1 Godot unit.

## Blender 5 changes that break older snippets

| Old code | Now |
|---|---|
| `action.fcurves` | Raises `AttributeError`. Use `action.layers[0].strips[0].channelbag(slot).fcurves`, or `bpy_extras.anim_utils.action_ensure_channelbag_for_slot(action, slot)` to create it. `obj.keyframe_insert()` still works. |
| `mesh.use_auto_smooth = True` | Raises `AttributeError`. Use `bpy.ops.object.shade_auto_smooth()`, which adds a "Smooth by Angle" modifier. |
| `material.use_nodes = True` | Not needed: a new material already has `Principled BSDF` and `Material Output`. Setting it warns that it goes away in Blender 6. |
| `'BLENDER_EEVEE_NEXT'` | The engine is `'BLENDER_EEVEE'`. |

An action slot comes from `obj.animation_data.action_slot`. Principled input names include `Base Color`, `Metallic`, `Roughness`, `Alpha`, `Emission Color` and `Emission Strength`.

## Template: build, audit, preview

```python
import bmesh, bpy, math, sys
from mathutils import Vector

out = sys.argv[sys.argv.index('--') + 1]
MAX_TRIS = 500
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

mesh = bpy.data.meshes.new('Crate')
bm = bmesh.new()
bmesh.ops.create_cube(bm, size=1.0)
bm.to_mesh(mesh)
bm.free()
crate = bpy.data.objects.new('Crate', mesh)
scene.collection.objects.link(crate)
crate.location.z = 0.5
crate.modifiers.new('Bevel', 'BEVEL').width = 0.03

wood = bpy.data.materials.new('Wood')
wood.use_backface_culling = True
wood.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (0.45, 0.28, 0.12, 1)
mesh.materials.append(wood)

bpy.context.view_layer.objects.active = crate
crate.select_set(True)
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.02)
bpy.ops.object.mode_set(mode='OBJECT')
bpy.context.view_layer.update()

# Measure the evaluated mesh: it is what gets exported, modifiers included.
problems = []
depsgraph = bpy.context.evaluated_depsgraph_get()
for obj in [o for o in scene.objects if o.type == 'MESH']:
    evaluated = obj.evaluated_get(depsgraph).to_mesh()
    bm = bmesh.new()
    bm.from_mesh(evaluated)
    tris = sum(len(face.verts) - 2 for face in bm.faces)
    open_edges = sum(not edge.is_manifold for edge in bm.edges)
    bm.free()
    size = [round(v, 3) for v in obj.dimensions]
    print(f'AUDIT {obj.name}: {tris} tris, size {size} m, {open_edges} non-manifold edges')
    if tris > MAX_TRIS:
        problems.append(f'{obj.name}: over {MAX_TRIS} tris')
    if not obj.data.uv_layers:
        problems.append(f'{obj.name}: no UVs')
    if any(abs(s - 1) > 1e-4 for s in obj.scale):
        problems.append(f'{obj.name}: unapplied scale {tuple(obj.scale)}')
    obj.evaluated_get(depsgraph).to_mesh_clear()
if problems:
    sys.exit('AUDIT FAILED: ' + '; '.join(problems))

# Frame the model and render a preview to look at. Workbench is the fast check.
corners = [crate.matrix_world @ Vector(c) for c in crate.bound_box]
center = sum(corners, Vector()) / 8
radius = max((c - center).length for c in corners)
camera = bpy.data.objects.new('PreviewCamera', bpy.data.cameras.new('PreviewCamera'))
scene.collection.objects.link(camera)
scene.camera = camera
camera.location = center + Vector((1, -1, 0.7)).normalized() * radius * 4
camera.rotation_euler = (center - camera.location).to_track_quat('-Z', 'Y').to_euler()
scene.render.engine = 'BLENDER_WORKBENCH'
scene.render.resolution_x, scene.render.resolution_y = 640, 480
scene.render.filepath = out + '.preview.png'
bpy.ops.render.render(write_still=True)

bpy.ops.wm.save_as_mainfile(filepath=out + '.blend')
bpy.data.objects.remove(camera)
bpy.ops.export_scene.gltf(filepath=out, export_format='GLB', export_apply=True)
```

The numbers don't tell you if it looks right. Open the preview and compare it with the brief. Workbench shows the shape in flat gray, not the `Base Color`, so judge materials with Eevee or Cycles. If you can't view images, say so and ask the user to check it.

`sys.exit('...')` with a message returns exit code 1 here, so a failed audit stops the build. Non-manifold edges are printed but don't fail it: planes and cards have them on purpose.

All three engines rendered with no display on the test machine. Cycles is the choice for a final image or for baking; Eevee depends on the machine's GPU support.
