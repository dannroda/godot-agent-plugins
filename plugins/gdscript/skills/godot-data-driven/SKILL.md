---
name: "godot-data-driven"
description: "Use for deep work on data-driven Godot 4 content and gameplay-logic layering: custom Resource design (sharing, duplicate, local_to_scene, caching traps), content databases/registries, JSON or CSV import with zero-trust validation, save files, mod loading pipelines and loader security, splitting god classes into domain/presentation/persistence layers with contexts, and designer-facing tooling."
---

# Godot 4 Data-Driven Design

Detailed version of the data and macro-architecture sections of `godot-architecture`.
Core idea: code defines the **rules** (hard architecture); data defines the **content** (soft architecture). New content takes a new file, not new code. Gameplay rules live in plain objects; nodes only display them.

Book for "Deeper" pointers: *Godot 4 Best Practices* ("BP" below; page numbers are the PDF edition's).

References (read when the task goes deep):
- `references/resource-traps.md`: read before sharing, duplicating, caching, exporting or hot-reloading Resources, or when a stat "changes on every enemy".
- `references/zero-trust-and-mods.md`: read when writing a JSON/CSV loader, a validator, a mod loader, or anything that opens player-supplied files.
- `references/gameplay-layers.md`: read when splitting a god class, writing a context, or deciding where state, rules and saving live.

## 0. Where does this value live?

| Value | Home |
|---|---|
| Engine/physics constant, never tuned | `const` in script |
| Tuned per scene instance (one door's open time) | `@export` on the node |
| Shared stats of a kind (all scouts) | `.tres` of a custom Resource |
| Edited outside Godot (writers, spreadsheets, modders) | JSON/CSV, converted to Resources at load |
| Changes during play (current HP, cooldown left) | runtime state object or node var, **never** the shared `.tres` |
| Survives sessions | save file in `user://` built from state objects |

If a designer would ever ask you to change it, it is not a `const`.

## 1. Custom Resources

```gdscript
class_name WeaponData extends Resource

@export var id: StringName
@export var display_name: String
@export_group("Stats")
@export_range(0.05, 5.0, 0.05, "suffix:s") var cooldown: float = 0.25
@export_range(1, 999) var damage: int = 1
@export_group("Visuals")
@export var icon: Texture2D
@export var projectile_scene: PackedScene
```

Rules:
- Every Resource referenced by ID has a stable `id: StringName`. IDs, not paths, cross file boundaries.
- Constrain input: `@export_range`, `@export_enum`, `@export_flags`, `@export_group`. Typed containers: `Array[ItemData]`, `Dictionary[StringName, int]` (typed dictionaries: 4.4+).
- `_init()` must be callable with zero arguments (give every parameter a default). The loader and `duplicate()` call it without arguments.
- Never rename an `@export var` casually: existing `.tres` files keep the old key and the value is silently lost on load. Rename with a migration (see resource-traps).
- Plain data Resources hold no logic beyond small computed getters. Behavior in a Resource is allowed only as a **stateless strategy**: a method that takes everything it needs as arguments and returns a result (`calc_velocity(pos, target, speed) -> Vector2`). A strategy that stores per-entity state in its own fields is a shared-state bug.
- Editor validation: `@tool` + `_validate_property()` to hide fields; nodes using the data report problems via `_get_configuration_warnings()`.

### Prototype vs instance
The `.tres` is the **prototype** (shared, read-only at runtime). The node or a RefCounted state object is the **instance** (current HP, position, status effects). Copy what you need from the prototype in `_ready()`/`setup()` and mutate only the instance.

| Need | Do |
|---|---|
| Read-only stats | Reference the shared `.tres`; never write to it |
| Per-entity mutable copy of the whole Resource | `duplicate_deep(Resource.DEEP_DUPLICATE_ALL)` (4.5+) at spawn |
| Embedded sub-resource unique per scene instance | `resource_local_to_scene = true` on it |
| Mutable runtime fields | separate state object; keep the template untouched (preferred) |

Godot traps (details and verified behavior in `references/resource-traps.md`):
- `load()` twice returns the **same object**; writing a field changes every user.
- `duplicate(true)` copies embedded sub-resources but **shares external `.tres` sub-resources**; `duplicate(false)` shares nested Arrays/Dictionaries too.
- `duplicate*()` copies only stored properties; a plain `var` (no `@export`/`@export_storage`) resets to its default in the copy.
- `.tres` files have no inheritance. An "Armored Drone based on Drone" does not pick up later edits to Drone unless you build that yourself.

Deeper: BP ch.11 "Using Resources for data management", PDF pp. 291–296

### Composition through nesting
`EnemyData` → `movement: MovementStrategy`, `weapon: WeaponData`, `loot: LootTable`. Variants come from swapping sub-resources in the Inspector, not from new scripts. Keep the node tree flat and the data tree rich.

## 2. Databases and registries

```gdscript
class_name ContentDB extends RefCounted

var _by_id: Dictionary[StringName, Resource] = {}

func register(id: StringName, res: Resource, allow_override: bool = false) -> bool:
	if _by_id.has(id) and not allow_override:
		push_warning("Duplicate id rejected: %s" % id)
		return false
	_by_id[id] = res
	return true

func get_weapon(id: StringName) -> WeaponData:
	return _by_id.get(id) as WeaponData
```

- Populate from an Inspector-filled `Array[WeaponData]` (small projects) or a folder scan.
- Folder scans in exported builds see `x.tres.remap` and `x.png.import`, not `x.tres`/`x.png`. Use `ResourceLoader.list_directory()` (4.4+) and `ResourceLoader.exists()`, never `FileAccess.file_exists()` on `res://` resources. Test the scan in an export.
- Build the DB once at boot (a service or a context) and inject it. No `load()` per lookup.
- Base content and mod content go through the same `register()`; gameplay never knows the origin. Mod IDs are namespaced: `modid:laser_mk2`.
- Cross-references (enemy → weapon id) resolve in a second pass after everything is registered; report dangling IDs.

## 3. External text data (JSON / CSV)

Use for content edited outside Godot. JSON: nested content (enemies, waves, dialogue). CSV: balance tables, localization (Godot imports CSV as translations by default; for a raw data CSV, switch its import mode to keep the file as-is (verify the option name in the Import dock)).

### Zero-trust loading
Treat every external file (JSON, CSV, saves, mods) as broken or hostile. Fail per entry, never per game; collect all errors into one report.

Gauntlet, in order; each failure logs and skips:
1. File exists and opens (`FileAccess.open()` returns null on failure; read `FileAccess.get_open_error()`). Size under a cap.
2. Parses (`JSON.new().parse()` → `OK`, else report `get_error_line()`/`get_error_message()`).
3. Root is the expected type (`Dictionary`/`Array`).
4. `"version"` present; migrate old, reject future.
5. Each required key exists with the right `typeof()`.
6. Ranges clamped, strings length-limited, arrays size-capped, IDs well-formed and unique, references resolve.
7. Asset paths resolve inside the allowed root (no `..`, no absolute paths, no `res://`/`user://` escapes).
8. Convert to typed Resources/RefCounted **immediately**. Gameplay never touches raw Dictionaries.

JSON facts that bite (verified 4.7):
- Every number parses as `float`; integers above 2^53 lose precision. Store big IDs as strings.
- `JSON.stringify()` writes `Vector2`/`Color` as strings like `"(1.0, 2.0)"` and turns int keys into string keys. Serialize vectors as `[x, y]`, or use `JSON.from_native()`/`to_native()` (4.4+).
- Typed arrays: `typed.assign(json_array)` converts floats to int; on an incompatible element it errors and leaves the array **empty**. Check the size after.
- Enums: store the **name** (`Phase.find_key(v)`), load with `Phase.get(name, fallback)`. Names survive enum reordering; ints don't.

A reusable error-collecting reader and the full loader are in `references/zero-trust-and-mods.md`.

Deeper: BP ch.11 "Externalizing data with JSON", PDF pp. 296–300

## 4. Loader security (what may open what)

Verified on 4.7.2 and 4.8-beta1:

| Loader | Untrusted file (download, mod, shared save)? |
|---|---|
| `JSON.parse()` / `parse_string()` | Safe (data only) |
| `FileAccess.get_var()` / `bytes_to_var()` (objects off, the default) | Safe |
| `get_var(true)` / `bytes_to_var_with_objects()` | **Unsafe**: builds objects |
| `ConfigFile.load()/parse()`, `str_to_var()` | **Unsafe**: `Object(Class,"script":Resource("path"))` instantiates the object and runs that script's `_init()` |
| `load()` of `.tres`/`.res`/`.tscn` | **Unsafe**: embedded `GDScript` sub-resources run on load |
| `ProjectSettings.load_resource_pack()` | Full code execution, and can replace `res://` files |
| `Image`/`AudioStream*` `load_*` | Safe to decode; cap sizes (allocation) |

Rule: anything a player can download or share is JSON (or `get_var` with objects off). `ConfigFile` only for the game's own settings file. Never `load()` a Resource from `user://` or a download. `.pck` encryption is obfuscation, not protection.

## 5. Save files

- Save **domain state objects** (`to_dict()` / `static from_dict()`), never nodes or node paths.
- `user://` only. Write to `save.json.tmp`, then rotate: current → `.bak`, tmp → current. On load, fall back to `.bak` if the main file fails validation.
- `"version"` in every save; migrate stepwise on load (`v1 → v2 → v3`).
- Saves are external data: run them through the same zero-trust reader (players edit saves).
- Formats: JSON for readability/modding; `store_var()` for compact binary (objects off); `ConfigFile` for local settings.
- Save on quit needs `get_tree().auto_accept_quit = false` + handle `NOTIFICATION_WM_CLOSE_REQUEST`, then `get_tree().quit()`. On mobile also save on `NOTIFICATION_APPLICATION_PAUSED`.
- Ensure the folder exists once at boot: `DirAccess.make_dir_recursive_absolute()`.

Snippets in `references/gameplay-layers.md` (persistence section).

## 6. Gameplay logic: domain vs presentation

Split every non-trivial gameplay system into:

| Layer | Godot type | Knows about | Never |
|---|---|---|---|
| State | `RefCounted` (or `Resource` if it needs Inspector editing) | its own fields, `to_dict()` | nodes, signals to UI |
| Domain rules | `RefCounted` with signals | state, injected services | `get_tree()`, `$Node`, Timers, Tweens, UI |
| Presentation | Nodes (HUD, sprites, audio) | how to draw a value it is handed | game math, win/lose checks |
| Context | Node owning a scene section | builds state + rules, wires rules → views | gameplay math |
| Persistence | Service (autoload OK: stateless utility) | file I/O, versioning | which node holds what |

Rules:
- The rules object owns the truth. A `ProgressBar.value`, a `Timer.time_left` or a sprite's `global_position` is never the source of a gameplay decision.
- Time enters the domain as `tick(delta)` called by the context; cooldowns are floats in state, not Timer nodes.
- Views expose methods (`show_score(int)`) and emit input/animation-finished signals. The context connects `rules.score_changed` → `hud.show_score`, then **pushes the current value once**, because signals fire only on change.
- Domain classes are `RefCounted`, not `Node`. A `Node` with a required-argument `_init()` cannot be placed in a scene or duplicated; if it must be a Node, use `setup(...)`.
- Gameplay state is not global. The match context holds it and injects it; the main menu cannot reach it. Global autoloads are for stateless services (audio, persistence, content DB).
- A missing cosmetic node must not stop the rules: rules never call presentation, so a deleted `AudioStreamPlayer` can't abort a score update halfway.
- Domain rules are tested headlessly with fake state (see `godot-gdscript-headless-testing` (awesome-gamedev-agent-skills)).

God-class smell: one script does input + math + UI + audio + save, has a dozen unrelated `@onready` paths, or listens to a global event bus for everything. Refactor recipe and full code: `references/gameplay-layers.md`.

Skip the layering for jams, prototypes and small games: a node script with `@onready` refs is fine when the project will never be big.

Deeper: BP ch.12 "Separating Presentation from Logic", PDF pp. 311–314; "Introducing Pure Data, Contexts, and Persistence", pp. 314–318; "Refactoring a monolithic script", pp. 318–326

## 7. Mod pipeline (data mods)

1. **Discover**: list `user://mods/*/`; each mod is a folder with `mod.json` (id, name, version, `game_api`, optional `load_after`). Honor a player-editable enabled list.
2. **Validate manifest**: id format, API compatibility; skip incompatible mods with a logged reason.
3. **Order**: base content first, then mods by `load_after`, then by id for determinism.
4. **Parse data** with the same zero-trust reader as base content.
5. **Load assets** from inside the mod folder only: images via `Image.load_*_from_buffer()` → `ImageTexture.create_from_image()`; audio via `AudioStreamOggVorbis/WAV/MP3.load_from_file()` (all present in 4.6+). Cap bytes and pixel size; use a placeholder on failure.
6. **Build prototypes in code**: `EnemyData.new()`, fill from validated values, attach loaded textures.
7. **Register** with namespaced IDs. Override policy is explicit: add-only by default; replacing base IDs only through a declared `"overrides"` list, logged.
8. **Resolve cross-references** in a second pass; drop entries with dangling refs.
9. **Report**: one in-game screen or log listing every skipped file/entry and why; offer a button that opens the folder (`OS.shell_open(ProjectSettings.globalize_path("user://mods"))`).

Data only. Script or `.pck` mods are a separate, explicit product decision: they run arbitrary code with the player's permissions.

Deeper: BP ch.11 "Designing moddable systems" / "Loading external assets" / "The Mod Loading Pipeline", PDF pp. 300–304

## 8. Designer workflow

- Tunables live in `.tres` (or JSON), never in a script `const`. If a number appears in two files, one is wrong.
- Live tuning from the editor: edit the runtime object in the Remote scene tree, or reload data on a debug key.
- Hot reload of `.tres` during a debug run: `ResourceLoader.load(path, "", ResourceLoader.CACHE_MODE_REPLACE)` reloads into the **same instance** (verified 4.7), so every holder sees new values; then re-derive any values copied in `_ready()`.
- Hot reload of JSON: re-run the full loader + validation, rebuild the registry, re-apply to live entities or restart the wave/level.
- `@tool` previews that draw ranges or spawn patterns from the data; `emit_changed()` in setters so previews refresh.

Deeper: BP ch.11 "Separating Logic from Configuration" / "Hard architecture versus soft architecture", PDF pp. 288–291

## 9. When not to go data-driven

- A one-off mechanic or boss whose logic is the content: write code.
- Jam scope: Resources for tunables, yes. JSON, mods, registries and layers only if the theme needs them.
- Don't build a generic system for content with three instances.
