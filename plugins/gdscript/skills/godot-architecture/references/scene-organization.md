# Scene organization: reuse, references, owner, spawning

Read this when you are building or restructuring `.tscn` files: choosing between instancing, inherited scenes, script inheritance and components; wiring references inside a scene; editing `.tscn` text directly; or spawning at runtime.

## 1. Four reuse tools, four jobs

| Tool | Relationship | Use for | Don't use for |
|---|---|---|---|
| **Instancing** a scene | has-a / many-of | A part inside a bigger thing (`Engine` in `Ship`), and many copies of one object in a level | Variants that differ only by numbers: use a `.tres` instead |
| **Inherited scene** (New Inherited Scene) | is-a, *visual/structural* variant | Same node layout and script, different sprite, shape, scale or exported values (`grunt.tscn` → `grunt_elite.tscn`), UI skin variants | Adding new behavior, or more than one level deep |
| **Script inheritance** (`extends Base`) | is-a, *logic* variant | The subclass really overrides behavior (`attack()` differs) | Code reuse without overriding: make a component |
| **Composition** (component child nodes or strategy Resources) | has-a capability | Capabilities shared across unrelated things (Player, Crate and Turret all take damage) | One-off behavior used by exactly one scene |

Decision order: is the difference only data → `.tres` in an `@export` slot. Is it a capability → component. Is it a behavior override of a shared identity → script inheritance (the inherited scene swaps in the subclass script). Is it only visuals/layout on the same identity → inherited scene.

Heuristics:
- An `extends` whose subclass overrides nothing is a component or a `.tres` in disguise.
- Keep script inheritance to two levels and inherited scenes to one. Deeper chains make every base edit a project-wide risk.
- The base-scene benefit is real: 50 enemies built from empty scenes + components means 50 edits to change a collision layer. If many things share an identity, give them a base scene, then add components on top.
- Prototype first. Extract the component or base scene when the second or third copy appears, not before.

## 2. Inherited scene mechanics and traps

- The derived `.tscn` stores only **overrides** against the base. Base edits propagate unless the derived scene overrode that property.
- You cannot delete or reparent inherited nodes in the derived scene. Hiding or disabling them is the only option. If variants need different node sets, the base is too big: move the optional parts into instanced components.
- Renaming or moving a node in the base orphans the derived scenes' overrides for it. The editor may warn, or the override may silently stop applying. Rename base nodes rarely, and re-open the derived scenes after doing it.
- Swapping the root script in a derived scene: the new script must `extends` the base script (by `class_name`) or the base contract and its exported values break.
- Signals connected in the base scene are inherited. Don't connect them again in the derived scene or the handler runs twice.
- Inherited nodes show in a different color (orange/yellow tint) in the Scene dock. That is the hint that edits there are overrides.

## 3. Editable Children

Right-click an instanced scene → Editable Children exposes its internals for per-instance overrides.
- Treat it as a level-design escape hatch (nudge one marker, swap one sprite in one placement), never as architecture.
- The overrides are stored in the *outer* scene, keyed by node path inside the inner scene. Restructuring the inner scene silently drops or misapplies them.
- If several instances need the same tweak, expose it instead: `@export` a property on the inner scene's root (with a setter that applies it to the child), or make a variant `.tscn`.
- An agent should not enable Editable Children to "reach in" from code either. Talk to the instanced scene through its root's API.

## 4. Referencing nodes inside a scene

| Need | Use | Why |
|---|---|---|
| Internal child that may move during layout work | `@onready var bar: ProgressBar = %HealthBar` (scene-unique name) | Survives reparenting inside the same scene |
| Node chosen per placement, or something outside this scene's subtree | `@export var target: Node2D` | Inspector injection, no path at all |
| Fixed direct child that never moves | `@onready var timer: Timer = $Cooldown` | Simplest; fine for shallow, stable trees |
| Something in a different scene/branch | Never a path. Signal, injection by the parent/spawner, or a service | Paths across scene boundaries are the main source of breakage |

Scene-unique names (`%Name`, `unique_name_in_owner = true`):
- Scoped to the **owner** scene. From the parent scene you can't reach `%Inner` inside an instanced child. Use `%Child/%Inner` only if you accept the coupling. Better, call a method on the child root.
- Names must be unique per owner. The editor refuses a second node with the same unique name (verify for nodes created by code).
- Don't mark everything unique: only nodes the script actually references.
- Exporting every internal node clutters the Inspector and lets designers break internal wiring. Use `%` for internals and `@export` for the scene's public slots.

Exported node references are stored as paths in the `.tscn` and resolved on instantiate. They are valid by `_ready`. They can only point at nodes inside the same saved scene (including inside instanced children), never into another scene file.

## 5. `owner`: what it means and where it bites

- `owner` = the root of the scene file that saved this node. Nodes created in the editor get it automatically. **Nodes created by code have `owner == null`.**
- `PackedScene.pack(root)` saves only nodes whose owner is `root`. Unowned children are dropped (tested 4.7.2: 0 children saved). When a `@tool` script or editor plugin creates nodes that must persist, set `node.owner = get_tree().edited_scene_root` (or the root you will pack) **after** `add_child`.
- `find_child()`/`find_children()` default to `owned = true` and skip runtime-spawned nodes.
- Don't use `owner` as "my parent" or "my game object" in gameplay code. Inside an instanced sub-scene it is that sub-scene's root, not the outer actor. Pass the reference explicitly.

## 6. Hierarchy rules

1. **One idea per scene.** Someone who opens it should know its purpose from the root name.
2. **Runs with F6.** The scene must not crash standalone. Missing optional dependencies degrade gracefully (null-checked exports, signals nobody listens to).
3. **Shallow gameplay trees.** Extra plain `Node`/`Node2D` "folders" add depth and path fragility. Extract a subtree into its own scene instead. **Exception:** UI, where nested Containers are how layout works.
4. **Communication direction.** Parent → child: direct calls (the parent owns and knows its children). Child → parent: signals. Sibling ↔ sibling: never direct; the parent listens to one and calls the other. Unrelated scenes: injected references, an event bus or a service (godot-communication).
5. **`_ready` order is children first, then the parent.** A parent can use its children in `_ready`. A child cannot assume the parent's `_ready` ran, which is one more reason children don't call up.
6. **Groups are tags, not structure.** Use them to query or broadcast to a category ("destructible", "persist"). Group names are constants. `call_group("g", "method")` skips members that lack the method **silently** (tested 4.7.2), so a typo does nothing. Prefer typed signals or an event bus for broadcasts that matter.
7. **Never branch on `node.name`.** Duplicate names are auto-renamed (`@Enemy@2` style, tested 4.7.2) and names change in refactors. Use types, groups or exported ids.

## 7. Spawning at runtime

```gdscript
const BOLT_SCENE: PackedScene = preload("res://features/weapons/bolt.tscn")

@export var projectile_parent: Node2D  # injected: the level's Projectiles node

func fire(from: Marker2D) -> void:
	var bolt := BOLT_SCENE.instantiate() as Bolt
	bolt.setup(from.global_transform, damage)  # configure before entering the tree
	projectile_parent.add_child(bolt)
```

- Spawn into a container the level owns (injected), not `get_tree().root` (it survives scene changes) and not the shooter (projectiles would inherit its movement).
- Configure with a `setup()` call before `add_child` so `_ready` sees final values. Place it before `add_child` with a local transform relative to the parent (`node.position = parent.to_local(world_pos)`, or `parent.global_transform.affine_inverse() * xform`). `global_*` before adding is wrong: 2D silently treats it as local, so the parent's offset is added; 3D errors with `!is_inside_tree()` (tested 4.7.2). Setting it after adding makes `_ready` run at the origin.
- `preload` (const) for small, always-needed scenes. `load()` for dynamic paths or rarely-used heavy assets. `ResourceLoader.load_threaded_request()` + `load_threaded_get_status()` polling + `load_threaded_get()` for levels behind a loading screen. Don't add threaded loading until a hitch is measurable.
- `@export var scene: PackedScene` beats a hard-coded path string: it survives file moves (UID) and lets designers swap content.
- Two scenes that preload or export each other form a load cycle (cyclic-dependency load error, verify). Break it with a registry/id lookup or a `load()` at use time.
- Instantiation cost scales with node count. Big bursts (wave spawns) → pool or spread over frames, after profiling.

## 8. Editing `.tscn` text directly (agents)

**Check first whether the editor has tools for this.** When `godot.*` MCP tools are available (for example the Godot Agent Harness: `create_scene`, `add_node`, `set_properties`, `attach_script`, `connect_signal`…), build and edit scenes with them and never write `.tscn`, `.uid` or `.import` files by hand. The harness rejects those writes, and also rejects shell commands that write into the project. Hand-editing applies only when no editor is attached; then the notes below apply.

Godot 4.7 writes, for example:
```
[gd_scene format=3 uid="uid://..."]
[ext_resource type="Script" uid="uid://..." path="res://features/enemy/enemy.gd" id="1_ab12c"]
[sub_resource type="CircleShape2D" id="CircleShape2D_x1"]
[node name="Enemy" type="CharacterBody2D" unique_id=123456789]
script = ExtResource("1_ab12c")
[node name="Shape" type="CollisionShape2D" parent="." unique_id=987654321]
shape = SubResource("CircleShape2D_x1")
```
- `load_steps=` in the header is gone from current output (older 4.x files still have it). Node `unique_id=` attributes appear in 4.6+ output (verify the exact version). Don't invent ids. Let the editor regenerate them, or omit them and resave from the editor.
- `parent="."` = child of root, `parent="A/B"` = path from root. Instanced scenes appear as `instance=ExtResource(...)` on the node line, and inherited scenes put `instance=` on the root node line.
- Scripts and other non-imported files have sidecar `.uid` files (4.4+). When moving or renaming files outside the editor, move the `.uid` with them and fix `path=` in every referencing `.tscn`/`.tres`. Otherwise do the move in the editor's FileSystem dock, which updates references.
- Prefer building scenes in the editor or with a `@tool`/EditorScript that sets `owner` and saves via `ResourceSaver`. Hand-edit text only for small, surgical changes.

Deeper: Godot 4 Best Practices ch.2 "Balancing composition and inheritance", PDF pp. 70–80, and ch.3 "Creating modular scene hierarchies" to "Avoiding Scene Tree bloat", PDF pp. 83–100
