---
name: "godot-code-review"
description: "Use when reviewing or refactoring Godot 4 GDScript, scenes or shaders for architecture smells, coupling, lifecycle and await bugs, Resource sharing, unsafe loading and saves, spawning and pooling mistakes, performance pitfalls, shader errors and over-engineering, including jam-scope sanity checks."
---

# Godot 4 Code Review Checklist

Report findings ranked by impact. For each one, give the file and line, the smell, a concrete failure scenario and the smallest fix. Point to the skill that holds the fix pattern: `godot-architecture`, `godot-patterns`, `godot-communication`, `godot-data-driven` or `godot-shader-techniques`. Don't suggest a pattern the project's scope doesn't justify.

## Coupling
- [ ] `get_parent()`, `owner.` or `get_node("../..")` used to call behavior, or a child assuming its parent has a method (`get_parent().die()`) → emit a signal; the parent connects.
- [ ] Long hardcoded paths (`$"../../UI/HUD/Label"`) → `@export` reference, `%UniqueName` inside the same scene, or a signal.
- [ ] Branching on `node.name` (`body.name == "Player"`) → type check, component, group constant or id.
- [ ] `is_in_group("x") and has_method("y")` used for hits → typed cast (`area as HurtboxComponent`) plus collision layers.
- [ ] Unrelated branches reference each other → EventBus, or a coordinator that relays.
- [ ] Leaf object (coin, pickup, component) calls an autoload directly → emit a signal; the level or a coordinator relays it.

## Responsibility
- [ ] A script over ~300 lines, or one handling input, movement, combat, UI and audio together → split into components or rules + view + context.
- [ ] A `match`/if chain over an enum or flags longer than ~50 lines → State or Strategy.
- [ ] Boolean trap: `is_dashing`, `is_stunned` and `is_attacking` combined in conditionals → State.
- [ ] Gameplay values stored in, or read from, UI or Timer nodes → a rules object owns the value; the view only displays it.
- [ ] Nodes used only to hold data → Resource or RefCounted.
- [ ] A subclass that overrides nothing → component or `.tres`.
- [ ] Inherited scenes more than one level deep, or script inheritance more than two → flatten into components.
- [ ] Editable Children used on several instances of one scene → `@export` on the inner root, or a variant scene.

## Lifecycle and scene tree
- [ ] An override of `_ready`/`_process`/`_physics_process` in a subclass whose base implements it, with no `super()` → add `super()`, or comment that replacing it is intended.
- [ ] A Node with a required-argument `_init()`, or a Resource whose `_init` has required parameters → defaults, `setup()`, a static factory, or RefCounted.
- [ ] `remove_child()` with no `queue_free()` and no re-add → free it (orphan leak).
- [ ] Two RefCounted objects referencing each other → `weakref()` for the back-link.
- [ ] `find_child` used to find runtime-spawned nodes → keep the reference, or pass `owned = false`.
- [ ] A `@tool` script creating nodes without setting `owner` → `owner = get_tree().edited_scene_root` after `add_child`.
- [ ] Gameplay spawns added to `get_tree().root` or under the shooter → inject a level-owned world container.
- [ ] Spawn transform set with `global_*` before `add_child` (silently wrong in 2D, an error in 3D), or after it (`_ready` runs at the origin) → set the local transform before adding (`parent.to_local(world_pos)`).
- [ ] An `add_child` of a physics node, or toggling `disabled`/`monitoring`, inside `body_entered`/`area_entered` → `call_deferred` / `set_deferred`.
- [ ] `await` inside `_ready` → an explicit async `start()`.

## Signals, await and autoloads
- [ ] `await` on a signal of an object that may be freed (tween, enemy, UI), or a queue awaiting a tween → race it against a timeout, and re-validate with `is_instance_valid()` after the await.
- [ ] `create_timer(t)` for gameplay waits → `create_timer(t, false)` (the default keeps running while paused).
- [ ] `call_group` for logic that must not fail → typed signal (members without the method are skipped silently).
- [ ] A signal emitted in `_ready` that a sibling must catch (startup race) → push/pull: the listener reads current state, then subscribes.
- [ ] A HUD connected to signals but never sent the initial values → push the current state once after connecting.
- [ ] An autoload holding gameplay state (`player_hp`, `score`, `inventory`) or rules → observable Resource or level-owned object; the autoload stays a service.
- [ ] A `var current_x` on the EventBus, or a bus callback that emits another bus event, or listeners whose order matters → state in a Resource; a coordinator with direct calls.
- [ ] A Resource setter that reaches an autoload → emit the Resource's own signal.
- [ ] An autoload's `_ready` uses a later autoload or the main scene → reorder the list, or have the scene register itself.
- [ ] `class_name` equal to an autoload name → rename one (it's a parse error).
- [ ] Save-on-quit without `get_tree().auto_accept_quit = false` → handle `NOTIFICATION_WM_CLOSE_REQUEST`, and `APPLICATION_PAUSED` on mobile.

## Resources and data
- [ ] A `.tres` from `load()` mutated at runtime, or a runtime field (`current_hp`, cooldown left) on a `.tres`-backed Resource → keep templates read-only; copy into a state object, or duplicate.
- [ ] `duplicate(true)` relied on for a private copy whose sub-resources are external `.tres` → `duplicate_deep(Resource.DEEP_DUPLICATE_ALL)` (4.5+), or copy only the fields that change.
- [ ] A strategy or config Resource storing per-entity state → make it stateless, or duplicate it per user.
- [ ] Exported properties or arrays mutated on an observed Resource with no `emit_changed()` → emit in the setter or mutator.
- [ ] An `@export var` renamed with no migration (old `.tres` values drop silently) → a `_set()` shim, then re-save the `.tres` files.
- [ ] Raw JSON Dictionaries used in gameplay, or `d["key"]` without type checks → a validating reader into typed objects. JSON numbers are floats.
- [ ] `var t: Array[int] = json_array` → `t.assign(json_array)` and check the size.
- [ ] Enums saved as ints → save the name.
- [ ] `FileAccess.file_exists("res://…tres")` or `DirAccess` scans of `res://` with no `.remap` handling → `ResourceLoader.exists()` / `ResourceLoader.list_directory()`; `Image.load("res://…png")` → `load()` the imported texture.

## Saves and external files (security)
- [ ] `load()` of `.tres`/`.res`, `ConfigFile`, `str_to_var` or `get_var(true)` on `user://` or downloaded files → JSON plus validation (all of these can run embedded scripts).
- [ ] A save written in place, with no version → write to a temp file, rotate to `.bak`, add `"version"` and migrate on load.
- [ ] Mod or asset paths used without a sandbox check (`..`, absolute) → resolve inside the allowed root.
- [ ] Saving node paths or `.tres` references → save domain data.

## Patterns
- [ ] An FSM entering its initial state in `_ready` before the actor is ready, or state scripts defining `_process`/`_physics_process` → start on `actor.ready`; states only implement `update`/`physics_update`.
- [ ] `HealthComponent` emitting `died` again on hits after death → guard on `is_dead()`.
- [ ] A pooled node with signals connected on acquire, `queue_free()` called on it, or no reset on reuse → connect once, release through the pool, reset in `on_acquired`.
- [ ] A command history with no cap, or an undo cache in a different space than the one it restores (global vs local) → `MAX_HISTORY`; match the spaces.
- [ ] A Command pattern added only for key remapping → `InputMap` rebinding.
- [ ] Unbounded arrays (histories, logs, pools) → cap them.

## Safety and typing
- [ ] Magic strings for groups, signals, input actions or animation names → constants (`const GROUP_ENEMY := &"enemy"`).
- [ ] Missing static types on vars, params and returns; `Variant` where the type is known.
- [ ] External data used without type and range validation.

## Performance
- [ ] `load()` or `instantiate()` of heavy scenes in hot paths → `preload` or threaded load.
- [ ] Per-frame `get_node()` or `find_child()` → cache in `@onready`.
- [ ] `_process` running on idle objects → `set_process(false)`, timers or signals.
- [ ] Heavy per-instance nodes (FSM, many components) on mass objects (bullets, debris) → plain logic or a pool.
- [ ] Deep scene trees for simple entities.
- [ ] Audio players inside entities that get freed (the sound cuts off) → pooled AudioService.
- [ ] `set_shader_parameter` every frame with an unchanged value → set it on change, or use a global shader uniform.

## Shaders (`godot-shader-techniques`)
- [ ] `light()` writing `DIFFUSE_LIGHT =` instead of `+=`, multiplying `ALBEDO` into it, or adding ambient/constant terms → `+=`; the engine applies albedo; ambient goes to `EMISSION`.
- [ ] Custom Lambert without `LIGHT_COLOR` or `/ PI` → `LIGHT_COLOR * ATTENUATION * ndl / PI`.
- [ ] Manual sRGB conversion of lighting or `ALBEDO` → remove it, or make it a named art uniform.
- [ ] An albedo/color sampler or uniform without `source_color`, or a data texture (mask, noise, roughness, flow, density) with it → fix the hint.
- [ ] A normal map without `hint_normal`, reading `.b` from it, or setting both `NORMAL` and `NORMAL_MAP` → add the hint, rebuild Z, keep one.
- [ ] View-space `NORMAL.y` used as "up" → `mat3(INV_VIEW_MATRIX) * NORMAL`.
- [ ] `mat3(row0, row1, row2)` copied from textbook notation → pass columns, or `transpose()` once.
- [ ] Vertex displacement or rotation without updating `NORMAL`/`TANGENT`/`BINORMAL`, or without `extra_cull_margin`/`custom_aabb` → fix both.
- [ ] `skip_vertex_transform` without transforming the normals too, or a non-rigid matrix without the inverse-transpose for normals.
- [ ] Camera-facing vertex code using `INV_VIEW_MATRIX` → `MAIN_CAM_INV_VIEW_MATRIX`, or check `IN_SHADOW_PASS`.
- [ ] `COLOR = texture(TEXTURE, UV)` in canvas_item → modify `COLOR` (keeps modulate). Modulate used as a per-instance ID → `instance uniform`.
- [ ] Hard `step`/`<` masks on moving or 3D surfaces → SDF plus `fwidth` smoothstep.
- [ ] A full-screen `ColorRect` with the default `mouse_filter` → `MOUSE_FILTER_IGNORE`.
- [ ] Depth reconstruction using `depth * 2.0 - 1.0` on Forward+/Mobile → the reverse-Z formula, with a `CURRENT_RENDERER` branch.
- [ ] Alpha-blended foliage or fences → `ALPHA_SCISSOR_THRESHOLD`.
- [ ] A stencil-reading material in the opaque pass → move it to the transparent pass.
- [ ] Ray-march loops with `texture()`, no early out and no box or depth bound → `textureLod`, an early exit, a slab test, the scene-depth limit.
- [ ] Specular denominators without `max(..., 1e-4)`; `RIM`/`ANISOTROPY`/`CLEARCOAT` set while a custom `light()` exists (they do nothing); `#define` macros for helpers → guards; implement them yourself; typed functions.

## Agents editing the project
- [ ] With editor tools available (`godot.*` MCP tools), `.tscn`/`.uid`/`.import` written by hand, or project files written from the shell → use the scene tools for scenes and the file tools for scripts.
- [ ] Files moved outside the editor without their `.uid`, or with stale `path=` references → move them together and fix the references, or move them in the FileSystem dock.

## Over-engineering (flag these too)
- [ ] A pattern with a single implementation and no planned second one.
- [ ] A state machine for something with two states.
- [ ] Generic components used by one entity.
- [ ] Dozens of tiny files with no folder structure.
- [ ] A factory or builder wrapping a one-off object.

## Jam mode (game jam / prototype)
When the project is a jam or prototype, review against shipping, not purity:
- Allowed: direct references inside a scene, booleans, one larger player script, and hardcoded values that are clearly marked.
- Still required: Resources for values you'll tune, an EventBus rather than tangled references across scenes, `preload` for spawned scenes, and no crashes on freed objects.
- Suggest refactors only when they unblock the next feature or fix a bug.
