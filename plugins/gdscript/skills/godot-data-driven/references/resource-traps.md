# Resource traps: sharing, copying, caching, exporting

Read this before you share, duplicate, cache, export or hot-reload Resources, or when you debug "changing one enemy changed all of them".
Behavior marked "verified" was tested headless on 4.7.2-stable and 4.8-beta1.

## 1. Identity and the cache

- `load(path)` / `preload(path)` return the **cached instance** for that path (verified). Every node that loads `scout.tres` holds the same object.
- `Resource.new()` has no `resource_path`, is not cached, and is unique.
- A Resource stays cached while anything references it. Changing a field at runtime affects every holder until the game restarts. The file on disk stays the same unless you call `ResourceSaver.save()`.

`ResourceLoader.load(path, type_hint, cache_mode)`:

| Mode | Main resource | External sub-resources | Use |
|---|---|---|---|
| `CACHE_MODE_REUSE` (default) | cached object | cached | normal loading |
| `CACHE_MODE_IGNORE` | fresh object | **still the cached ones** (verified) | a private copy whose external refs may stay shared |
| `CACHE_MODE_IGNORE_DEEP` | fresh | fresh (verified) | a fully private copy straight from disk |
| `CACHE_MODE_REPLACE` | **reloads into the existing cached object** (verified: old references see the disk values) | cached | hot reload during development |
| `CACHE_MODE_REPLACE_DEEP` | reloads in place | reloads in place | hot reload of a tree of `.tres` |

Symptom → cause → fix:
- Shooting one enemy drains every enemy's HP → `current_hp` lives on the shared `.tres` → move it to the node or a state object; the `.tres` holds `max_hp` only.
- Hot-reloaded `.tres` but the entity didn't change → it copied the value in `_ready()` → re-read from the Resource after reload, or connect to `changed`.
- Edited `.tres` in the editor while the game runs, nothing happens → the running game has its own copy in memory → edit through the Remote tree, or trigger a `CACHE_MODE_REPLACE` reload from a debug key.

## 2. duplicate semantics (verified 4.7.2 / 4.8-beta1)

Setup: `root` holds `sub` (embedded, no path), `list: Array[TItem]` with one external `.tres` and one embedded resource, plus a non-exported `var`.

| Call | Embedded sub-resource | Embedded inside Array/Dict | External `.tres` sub-resource | Nested Array/Dict container | Plain `var` |
|---|---|---|---|---|---|
| `duplicate()` / `duplicate(false)` | shared | shared | shared | **same container** (appending to the copy's array changes the original) | reset to default |
| `duplicate(true)` | copied | copied | **shared** | copied | reset to default |
| `duplicate_deep()` (default `DEEP_DUPLICATE_INTERNAL`, 4.5+) | copied | copied | shared | copied | reset to default |
| `duplicate_deep(Resource.DEEP_DUPLICATE_ALL)` | copied | copied | copied | copied | reset to default |

Rules:
- Only properties with storage usage are copied: `@export`, `@export_storage` (4.3+), or `_get_property_list()` entries with `PROPERTY_USAGE_STORAGE`. Runtime-only `var`s come back at their defaults.
- Before 4.5, `duplicate(true)` did not copy Resources inside Arrays/Dictionaries. On 4.6+ use `duplicate_deep()` and state the mode explicitly.
- `duplicate()` calls `_init()` with no arguments. A required-argument `_init` breaks it.
- Need a per-entity copy whose `weapon.tres` is also private → `DEEP_DUPLICATE_ALL`. Need it to keep pointing at the shared weapon → `duplicate(true)`.
- Cheaper than either: don't copy the Resource at all; copy the 3 fields you mutate into a state object.

## 3. resource_local_to_scene (verified)

- Set on a Resource that a scene file references. When the PackedScene is instantiated, that Resource is duplicated **once per scene instance**.
- Within one scene instance, every node that references it shares that one copy (two nodes in the same instance: same object).
- Works for embedded sub-resources and for external `.tres` files that have the flag. On an external `.tres` the flag affects **every** scene that uses it, so editing the base no longer reaches running instances, and memory grows per instance.
- Does nothing for Resources you `load()` in code or assign after `instantiate()`. Those stay shared.
- Typical correct use: a `ShaderMaterial` whose uniforms one instance animates, or a `Curve`/`Gradient` that an instance edits at runtime.
- Custom per-copy setup: override `_setup_local_to_scene()` (virtual on Resource; `get_local_scene()` gives the owner scene).
- Symptom: all doors flash together when one is hit → their shared `ShaderMaterial` → tick Local To Scene on the material, or `material = material.duplicate()` in `_ready()`.

## 4. Stability of stored data

- **Renaming an `@export var`**: the `.tres` keeps the old key; on load it is ignored **silently** (verified, no warning) and the new property gets its default. Migrate with `_set()`, which receives unknown keys during load (verified):

```gdscript
func _set(property: StringName, value: Variant) -> bool:
	if property == &"old_count":   # renamed to `count` in v2
		count = value
		return true
	return false
```
  Then open and re-save the affected `.tres` files (or run a `@tool` script that does), and delete the shim later.
- **Changing an export's type** (int → float, `Texture2D` → `SpriteFrames`): old values may fail to convert and reset. Treat this like a rename.
- **Renaming/moving scripts or `.tres`**: do it in the Godot FileSystem dock so references update. Since 4.4, `.uid` sidecar files hold stable IDs. Commit them and move them with their files.
- **`class_name` change**: `.tres` files store `script_class` and an ext_resource path. Keep the path stable or re-save the files.
- `_init()` with required parameters makes the `.tres` fail to load. Give every parameter a default.

## 5. Typed containers (4.4+ for typed Dictionary)

- `@export var drops: Array[ItemData]`, `@export var weights: Dictionary[StringName, float]`. The Inspector enforces the types.
- `var t: Array[int] = untyped_array` fails at runtime when the source is an untyped `Array`. Use `t.assign(src)` or `Array(src, TYPE_INT, &"", null)`.
- `assign()` converts compatible values (JSON floats → int, String → StringName keys in typed Dictionaries; verified). On an incompatible element it pushes an error and leaves the target **empty** (verified). Check `size()` after assigning untrusted data.
- Typed arrays of a custom class: `Array[ItemData]`. `assign()` rejects any element that is not that class.

## 6. Export-time differences (test in an exported build)

| In the editor | In an export | Do instead |
|---|---|---|
| `res://items/sword.tres` exists | text resources are converted to binary by default; the listing shows `sword.tres.remap` | `ResourceLoader.list_directory()` (4.4+) or strip `.remap`; `ResourceLoader.exists()` |
| `res://art/icon.png` exists | only `icon.png.import` + the imported file under `.godot/` | `load()` it as a Texture; never `Image.load("res://...png")` (warns, fails on export) |
| `FileAccess.file_exists("res://x.tres")` true | false when remapped | `ResourceLoader.exists()` |
| `.txt`, `.cfg`, `.md` read with `FileAccess` | not packed | add them to the preset's non-resource include filter (`*.txt`) |
| `.json` | recognized as a `JSON` resource (`.json` is a known extension) so it is packed (verify in your export) | read with `FileAccess` or `load()` as `JSON` |
| `.csv` | imported as translations by default | for data CSV, switch the import mode to keep the file (verify the option name) |

Always run the content scan and loaders once in an exported build (or `--export-pack` + run) before trusting them.

## 7. No inheritance between .tres files

The book's "sub-prototype inherits the base speed" is a design idea. Godot has no mechanism for it: a duplicated `.tres` copies values once, and later edits to the base do not propagate.

| Need | Option |
|---|---|
| Few variants, rarely rebalanced | Duplicate the `.tres` and accept no propagation |
| Many variants share most stats and are rebalanced often | `@export var base: EnemyData` plus explicit overrides: `func get_speed() -> float: return speed_override if has_speed_override else base.get_speed()` |
| Variants are whole entities (visuals + data) | Inherited scenes (`.tscn` inheritance does propagate) with the data `.tres` swapped |
| Balance lives in a spreadsheet | CSV/JSON rows with a `parent` column, flattened by the loader at boot |
| Code-defined archetypes | Script subclass that sets different defaults in `_init()` |

Pick one per project and write it down. Mixing them makes "where does this number come from" unanswerable.

## 8. Misc

- Big registries: `ResourceLoader.load_threaded_request()` + poll `load_threaded_get_status()` during a loading screen. Don't block the main thread on hundreds of `.tres`.
- `changed` signal: call `emit_changed()` in setters of `@tool` Resources so editor previews and listeners refresh. Runtime listeners must disconnect when freed (or connect from the node, which auto-disconnects on free).
- Resources referenced by a scene are loaded with it. A `PackedScene` field in a data Resource drags that whole scene into memory when the data loads. For large optional content, store the path (`@export_file("*.tscn")`) and load it on demand.

Deeper: Godot 4 Best Practices ch.11 "Using Resources for data management", PDF pp. 291–296
