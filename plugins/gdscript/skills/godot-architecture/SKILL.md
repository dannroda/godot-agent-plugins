---
name: "godot-architecture"
description: "Use when starting or structuring a Godot 4 project or system: where code/data should live; Node vs Resource vs RefCounted vs Object (lifecycle, leaks, shared-resource traps); scenes vs scripts; scene inheritance vs instancing vs components; editable children, scene-unique % nodes, owner; SOLID for nodes and scripts; folders, naming, layers, spawning, data-driven content, saves and mods."
---

# Godot 4 Architecture

Target: Godot 4.6+, GDScript statically typed everywhere (`var hp: int`, `-> void`).
Guiding rule: clarity over minimalism. Every scene, node and script exists for one reason, and every scene runs on its own (F6).

References (read when the task goes deep):
- `references/object-lifecycle.md`: choosing a base class; leaks, freed refs, Resource cache/duplicate semantics, `_init` rules, static vars.
- `references/scene-organization.md`: instancing vs inherited scenes vs components; editable children; `%` names; `owner`; spawning; editing `.tscn` text.
- `references/solid-in-godot.md`: each SOLID principle as a Godot mechanism, its concrete smell, its fix, and when to skip it.

Related skills: godot-communication (signals, bus, autoloads, injection, init order), godot-data-driven (Resources, databases, JSON, saves, mods, layering), godot-patterns (FSM, strategy, components, factories).

## 1. Pick the right container

Ask "what is this thing?" before creating a node:

| It is... | Use | Why |
|---|---|---|
| Renders, collides, plays audio, gets input, needs `_process`, or needs a parent transform | **Node / Scene** | Lives in the SceneTree |
| Tree-clock utilities (`Timer`, `AnimationPlayer`, `AudioStreamPlayer`) | **Node** | They need the tree or a server, even without visuals |
| Data or config (stats, items, abilities, wave tables, settings) | **Resource** (`class_name X extends Resource`, `.tres`) | Inspector-editable, serializable, shareable, no tree cost |
| Pure logic or runtime state (inventory model, damage calc, FSM model, rules) | **RefCounted** | Auto-freed, testable without a scene |
| Stateless helpers (math, formatting, queries) | `static func` on a `class_name` script | No instance, no autoload |
| Thousands of records owned and freed by one manager | **Object** | Rare; you must `free()` it yourself |
| Bulk numeric data (bullets, grid cells) | Packed arrays / Dictionary in one owner node | No per-item object at all |

Anti-pattern: an `Inventory` node with `Item` child nodes, using `add_child` to store and `get_children()` to read. It means a tree-bound, hard-to-save inventory that dies with the UI. Use an `Inventory` RefCounted/Resource holding `Array[ItemData]`; a UI scene only *displays* it.

Lifecycle traps (verified on 4.7.2, details in `references/object-lifecycle.md`):
- **Nodes are not ref-counted.** `remove_child()` without `queue_free()` leaks an orphan.
- **RefCounted cycles leak** (A↔B). The back-reference must be a `weakref()`.
- **RefCounted can't be an `@export` slot** (parse error). Exposing it in the Inspector means making it a Resource.
- **Resource `_init` must accept zero args.** Otherwise loading and duplicating fail. Give every parameter a default, or use a static factory.
- **`load()` returns the cached shared instance.** Runtime mutations leak to every user and survive scene reloads.
- **Never `load()` a `.tres` from `user://`** or from downloads. Resources can carry scripts.

Deeper: Godot 4 Best Practices ch.4 "When Not to Use Nodes", PDF pp. 110–125

## 2. Scenes vs scripts

- A scene is declarative (what exists, layout, values). A script is imperative (behavior).
- Put **constant** structure in the scene, not in `_ready()` code that calls `new()`/`add_child()` and sets textures. The scene is faster to instantiate, visible in the editor, and editable by non-programmers.
- Put **volatile or large** data in scripts or `.tres`, not in scene properties. `.tscn` diffs get noisy.
- A script-only file is right when there is no visual or spatial presence: models, calculators, save serializers, generators. Extend RefCounted (or Resource if it needs saving/Inspector).
- `class_name` puts a Node script in the Create Node dialog, making it a lightweight custom node without a `.tscn`.
- Use `@tool` for editor previews (`_draw()` a range circle), validation via `_get_configuration_warnings()`, and live updates in export setters. The whole script runs in the editor, so guard gameplay with `if Engine.is_editor_hint(): return`. Editor-side mutations of Resources get saved to disk.
- Hybrid is the norm. Example: a weapon is a scene (sprite, sound, muzzle `Marker2D`), a `.tres` (fire rate, damage) and a pure script (ballistics math).

Loading cost (instantiate is synchronous):

| Situation | Use |
|---|---|
| Small scene spawned often (projectile, pickup) | `const X: PackedScene = preload(...)` |
| Designer-chosen scene | `@export var scene: PackedScene` (UID-safe, swappable) |
| Path computed at runtime, or a rarely used heavy asset | `load()` at the moment of need |
| Level or huge scene | `ResourceLoader.load_threaded_request()`, poll `load_threaded_get_status()` each frame, then `load_threaded_get()`, behind a loading screen |

Never `load(...).instantiate()` inside a hot gameplay call. Add threaded loading only when a hitch is felt or measured.

Deeper: Godot 4 Best Practices ch.2 "When to use scenes" to "Extending scripts into the editor", PDF pp. 57–70

## 3. Reuse: instancing vs inheritance vs composition

| Difference between variants | Tool |
|---|---|
| Only numbers or assets | Same scene, different `.tres` in an `@export` slot |
| A capability some things have (takes damage, can fly, interactable) | **Component**: child node with its own script, or a strategy Resource |
| Same node layout and identity, different visuals or exported values | **Inherited scene** (one level deep) |
| Same identity, overridden behavior | **Script inheritance** (`extends Base`, at most two levels); the inherited scene uses the subclass script |
| A part inside a bigger thing, or many copies in a level | **Instancing** |

Rules:
- A subclass that overrides nothing should be a component or a `.tres`.
- Inherited scenes store only overrides against the base. You can't delete inherited nodes, and renaming base nodes orphans the overrides. Keep bases small and put optional parts in components.
- **Editable Children** is a per-placement escape hatch, never architecture. Its overrides are keyed by internal path and silently break when the inner scene changes. If more than one instance needs it, expose an `@export` on the inner root.
- Overriding `_ready`/`_process`/`_physics_process` **replaces** the base version. Godot 4 does not chain it, so call `super()`.
- Shared identity plus capabilities is the common shape: base scene `enemy_base.tscn` + components (`Hurtbox`, `Health`) + per-enemy `.tres`.
- Prototype first. Extract a component or base when the second or third copy appears.

Deeper: Godot 4 Best Practices ch.2 "Balancing composition and inheritance", PDF pp. 70–80, and ch.3 "Using Inherited Scenes for specialization", PDF pp. 86–87

## 4. Scene hierarchy rules

1. **One idea per scene**, named by its root. Shallow gameplay trees: extract subtrees into scenes instead of nesting "folder" nodes. UI is the exception, because nested Containers are how layout works.
2. **Runs standalone (F6).** No `get_node("../../X")`, no `/root/Main/...` paths. The scene exposes `@export` slots, `setup()` and signals.
3. **Call down, signal up.** The parent calls its children directly; children emit signals. Siblings never reference each other: the parent listens to one and calls the other. Unrelated scenes communicate by injection, an event bus or a service (godot-communication).
4. **`_ready` runs children first.** A parent may use its children in `_ready`; a child must not assume its parent is ready.
5. **References inside a scene:**
   - `%UniqueName` (scene-unique) for internals that may move. It is scoped to the scene's owner, so you can't reach `%X` inside an instanced child.
   - `@export var x: Type` for per-placement or out-of-subtree refs, and for the scene's public slots.
   - `$Child` only for fixed direct children.
6. **`owner` is the saved scene's root, not the parent.** Nodes created by code have `owner == null`. `PackedScene.pack()` drops them, and `find_child()` skips them (default `owned = true`). `@tool` code that creates nodes sets `node.owner = get_tree().edited_scene_root` after `add_child`.
7. **Groups are tags**, not structure, and group names are constants. `call_group()` silently skips members that lack the method, so a typo does nothing. Prefer typed signals for broadcasts that matter.
8. **Never branch on `node.name`.** Duplicates get auto-renamed (`@Enemy@2`). Use types, groups or ids.
9. **Spawn into a level-owned container** (injected), never `get_tree().root`. Root children survive `change_scene_to_*`. Configure with `setup()` before `add_child`. Place it before `add_child` with a local transform relative to the parent (`node.position = parent.to_local(world_pos)`, or `parent.global_transform.affine_inverse() * xform`). `global_*` before adding is wrong: 2D silently treats it as local, so the parent's offset is added; 3D errors with `!is_inside_tree()` (tested 4.7.2). Setting it after adding makes `_ready` run at the origin.
10. **Free what you don't need** (`queue_free()`), and spawn on demand instead of placing thousands of objects in the editor.

Bloat diagnosis:

| Symptom | Fix |
|---|---|
| Endless scrolling in the Scene dock | Split branches into instanced scenes |
| Null-instance errors after moving a node | `%Unique` names, exports or signals instead of paths |
| Same edit repeated on many copies | Base scene or shared `.tres` |
| Nodes that only hold data | Resource / RefCounted |
| Hitch when a level opens | Spawn heavy content on demand; threaded load |

Deeper: Godot 4 Best Practices ch.3 "Creating modular scene hierarchies" to "Troubleshooting Scene Tree bloat", PDF pp. 83–101

## 5. SOLID in Godot (smell → fix)

| | Smell | Fix |
|---|---|---|
| **S** | Actor script holds UI label/audio/save refs; 60-line `_physics_process`; god `GameManager` | Dispatcher loop of named steps; emit state signals; extract components; split model/service/view |
| **O** | Consumer does `match type` / `if body.name == "Archer"`; new content edits Player | One polymorphic verb on a base type or strategy Resource; content as `.tres` |
| **L** | Override that `pass`es or errors; subclass skips base signals; variant scene lacks a node the base script uses; `super()` missing | Keep types, units, signals and side effects; add methods for extras; validate structure with config warnings |
| **I** | Base `Entity` with `fly/swim/cast` stubs; `updated(data: Dictionary)` signal | Minimal base (universal state + verbs); capability components; one typed signal per fact; `@abstract` (4.5+) for contracts |
| **D** | `get_node("../Player")`, `get_parent().x()`, enemy writes `player.health` | Typed `@export` or `setup()` injection; signals up; bus/service across trees; call the owner's API |

The GDScript parser enforces override **signatures** when the code is typed (4.7.2: a mismatch is a parse error). It cannot check semantics, emitted signals, required child nodes or `has_method`/`call_group` calls. Type everything so the parser catches what it can.

Capability checks, strictest first: `is BaseClass` → component lookup → group tag → `has_method` (last resort).

Skip the ceremony in jams and for one-off bosses. Full treatment: `references/solid-in-godot.md`.

Deeper: Godot 4 Best Practices ch.1 "Applying SOLID Principles in Godot", PDF pp. 28–54

## 6. Project layout (default: feature-based)

Group by feature so a feature can be copied to another project as one folder:

```
res://
  core/            # autoloads, services, event bus, shared base classes
  features/
    player/        # player.tscn, player.gd, player_stats.tres, sprites
    enemies/grunt/
    ui/hud/
  data/            # shared .tres databases, JSON
  shared/          # generic components (health_component.gd, hurtbox.gd)
  addons/
```

- A type-based layout (`assets/`, `scenes/`, `scripts/`) is acceptable if the project already uses it. Consistency beats preference, so follow the existing layout and don't mix styles.
- Files and folders: `snake_case` (`enemy_controller.gd`, `main_menu.tscn`).
- `class_name` matches the file in PascalCase (`enemy_controller.gd` → `EnemyController`). Scene root node in PascalCase.
- Name nodes by role (`HealthLabel`, `ShootTimer`) so `$HealthLabel` and `health` never collide.
- Never give an autoload's script a `class_name` equal to the autoload name.
- Groups and other string keys are constants, never literals (see godot-patterns).
- **Agents with editor tools** (`godot.*` MCP tools, as in the Godot Agent Harness): create and edit scenes through them, write scripts with the file tools, and never write `.tscn`/`.uid`/`.import` or project files from the shell.
- **Agents editing files on disk:** scripts have sidecar `.uid` files (4.4+). Move or rename a file together with its `.uid` and fix `path=` in the referencing `.tscn`/`.tres`, or do the move in the editor's FileSystem dock. Prefer `@export var scene: PackedScene` over path strings.

Deeper: Godot 4 Best Practices ch.1 "Organizing for scalability", PDF p. 54, and ch.3 "Naming conventions for teams" and "Project folder organization", PDF pp. 94–96

## 7. Data-driven design

Separate **hard architecture** (rules, code) from **soft architecture** (content, numbers).

- Every tunable number lives in a Resource, not in a script constant.
- Nest Resources for mix-and-match (`EnemyData` has `movement: MovementData`, `weapon: WeaponStrategy`).
- Behavior Resources (strategy pattern) are fine when the Resource is a swappable algorithm (`execute(user, target)`). Mark the base `@abstract` (4.5+).
- Shared `.tres` instances are shared state. Copying them:
  - `duplicate(true)` copies embedded sub-resources, but file-backed ones stay shared.
  - `duplicate_deep(Resource.DEEP_DUPLICATE_ALL)` (4.5+) copies everything.
  - `resource_local_to_scene` only affects resources embedded in an instantiated scene.
  - Often simpler: keep the template read-only and copy the values into a RefCounted state.
- Assigning an `@export` property or mutating an array does not emit `changed`. Call `emit_changed()` in setters or mutators.
- A UI binds to a model: `bind(model)` → draw once → connect `model.changed`. It never stores the data.

```gdscript
class_name EnemyData extends Resource
@export var max_hp: int = 10
@export var speed: float = 120.0
@export var weapon: WeaponStrategy
```

External data and mods (details in godot-data-driven):
- JSON is zero-trust: check that the file exists, `JSON.parse()` returns `OK`, the root type is right, each key exists with the right `typeof()`, and values are clamped. On failure, `push_warning()`, skip the entry and keep running.
- Mods: read from `user://mods/`, not `res://` (the exported .pck is sealed). Load images with `Image.load_from_file()` → `ImageTexture.create_from_image()` after validating. Mods supply data, never `.tres`/`.gd` to execute, unless that is an explicit, sandboxed design choice.

Deeper: Godot 4 Best Practices ch.4 "Using Resources for data" and "Data-driven patterns in Godot", PDF pp. 117–127

## 8. Macro-architecture (mid/large projects)

- **Presentation layer**: nodes, animation, UI. Reads state and emits user intent.
- **Domain layer**: RefCounted state and rules (`LevelState`, `Inventory`). No node references, no `get_tree()`. The owning node calls `tick(delta)` if it needs time.
- **Contexts**: `RootContext` (main scene, owns global services) → `MainMenuContext` / `GameplayContext`. A context builds its children and **injects** dependencies (`controller.setup(state)`, `hud.bind(state)`). Children never look dependencies up globally.
- **Persistence**: save the domain data (to Dictionary/JSON), never node paths. `GameplayContext` hands its state to a `SaveService`.

## 9. Scale the architecture to the project

- **Jam or prototype (≤ 2 weeks)**: Resources for tunables, signals, one EventBus, one AudioService. Skip contexts, layers and commands unless the core mechanic needs them.
- **Long-lived game**: everything above, plus tests for the domain layer.
- Refactor trigger: the same behavior is needed a second or third time, two people keep editing one file, or a change in one feature breaks another. Before that: YAGNI (see godot-code-review).
