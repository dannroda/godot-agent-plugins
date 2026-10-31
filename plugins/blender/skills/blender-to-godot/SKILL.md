---
name: "blender-to-godot"
description: "Use when moving assets from Blender to Godot 4: glTF/GLB export settings, model facing direction, scale, import name suffixes (-col, -convcol, -colonly, -rigid, -navmesh, -noimp, -loop), culling, transparency, vertex colors, rigs, control bones, actions, shape keys, custom properties, .blend import failures, and checking the imported scene headlessly."
---

# Blender to Godot

Every table row was observed by exporting from Blender 5.2.3 and importing into Godot 4.7.2 and 4.8 beta 2 headless, then reading the node tree. On other versions, rerun the check at the end.

## Export

```python
bpy.ops.export_scene.gltf(
    filepath=out,
    export_format='GLB',
    export_apply=True,      # apply modifiers (default False)
    export_extras=True,     # custom properties (default False)
    export_def_bones=True,  # deform bones only (default False)
)
```

Export `.glb` files into the Godot project and keep the `.blend` outside it (see the `.blend` trap below). `use_selection=True` limits the export to selected objects.

## Geometry and transforms

| In Blender | In Godot |
|---|---|
| Point at `(0, -3, 0)` | `(0, 0, 3)`. Blender −Y becomes Godot +Z. |
| Model faces −Y (Blender's Front view) | It faces +Z. Godot's `Node3D.look_at()` aims −Z unless `use_model_front` is true, so the model can look backward. |
| Object scale `(2, 1, 1)` | The node keeps scale `(2, 1, 1)`. Apply scale first so collision shapes don't inherit a non-uniform scale. |
| Mesh with no UVs | Import logs `UVs are required to generate tangents`. |

## Object name suffixes

The suffix is removed from the name, except on the Empty row.

| Name | Result |
|---|---|
| `Crate-col` | Mesh + `StaticBody3D` with a `ConcavePolygonShape3D` |
| `Barrel-convcol` | Mesh + `StaticBody3D` with a `ConvexPolygonShape3D` |
| `Wall-colonly` | `StaticBody3D` with a `ConcavePolygonShape3D`, no visible mesh |
| `Ball-rigid` | `RigidBody3D` with mesh and `ConvexPolygonShape3D` |
| `Floor-navmesh` | `NavigationRegion3D` |
| `Skip-noimp` | Not imported |
| Empty named `Trigger-colonly` | A plain `Node3D` that keeps the suffix and has **no shape**. Use a simple mesh for the collider. |

Concave shapes are for static geometry. For anything that moves, use a convex collider or a simple low-poly mesh.

## Materials

| In Blender | In Godot |
|---|---|
| New material, untouched | `cull_mode = DISABLED`, because `use_backface_culling` defaults to False. Set it True on closed meshes. |
| `use_backface_culling = True` | `cull_mode = BACK` |
| Principled `Alpha` 0.5 | `TRANSPARENCY_ALPHA_DEPTH_PRE_PASS` |
| `Emission Strength` 5 | Emission enabled, `emission_energy_multiplier` 5 |
| Color attribute, material doesn't use it | The mesh has `ARRAY_COLOR`, but `vertex_color_use_as_albedo` is false: colors arrive and don't show. Enable it on the Godot material. |

## Rigs and animations

| In Blender | In Godot |
|---|---|
| Armature + skinned mesh | `Skeleton3D` with the mesh as child, plus an `AnimationPlayer` |
| `use_deform = False` on a control bone, with `export_def_bones=True` | The bone isn't exported |
| Action `Walk-loop` | Animation `Walk` with linear loop mode |
| Action `Jump` | No loop |
| Action not used anywhere, with or without fake user | **Still exported** (default `export_animation_mode='ACTIONS'`). Delete test actions first. |
| Shape keys, no modifiers, `export_apply=True` | Blend shapes kept |
| Shape keys **and** a modifier, `export_apply=True` | **Blend shapes lost** with no error. Apply the modifier by hand before adding the keys, or export without `export_apply`. |

## Custom properties

With `export_extras=True`, `obj['spawn_weight'] = 3` arrives as `node.get_meta("extras")["spawn_weight"]` with value `3.0`: integers become floats. Cast before comparing.

## The `.blend` trap

A `.blend` inside the project, with no Blender path in the editor settings, fails headless import: `Blender path is invalid or not set`. In the test, a `.glb` in the same project also failed to load until the `.blend` was removed. This breaks CI. Unless every machine has Blender configured, commit only `.glb` files to the project.

## Check the result

Don't assume the export worked; read what Godot built. Save this as `dump_scene.gd` in the project and pass the scene path after `--`:

```gdscript
extends SceneTree

func walk(node: Node, depth: int) -> void:
	var line := "%s%s <%s>" % ["  ".repeat(depth), node.name, node.get_class()]
	if node is CollisionShape3D and node.shape:
		line += " " + node.shape.get_class()
	if node is AnimationPlayer:
		line += " %s" % [node.get_animation_list()]
	print(line)
	for child in node.get_children():
		walk(child, depth + 1)

func _init() -> void:
	var path := OS.get_cmdline_user_args()[0]
	var scene: PackedScene = load(path)
	assert(scene != null, "could not load " + path)
	var root := scene.instantiate()
	walk(root, 0)
	root.free()
	quit()
```

```bash
godot --headless --import --path game
godot --headless --path game --script res://dump_scene.gd -- res://models/crate.glb
```

Compare the tree with what the asset should contain: expected bodies, shapes and animations. Then open it in a running scene to judge the look, since the node tree says nothing about appearance.

For hand changes in Godot, keep the `.glb` as the source and make an inherited scene or set import options; a reimport replaces the generated scene.
