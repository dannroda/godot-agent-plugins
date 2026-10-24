# Zero-trust loading and the mod pipeline

Read this when you write a JSON/CSV loader, a validator, a save loader, or a mod loader: anything that opens a file the game did not ship inside its `.pck`.
All code below was run headless on 4.7.2 against deliberately broken mod folders.

## 1. Threat model

External data comes from designers, translators, players and modders. Expect:
- **Typos**: `"max_hp": "lots"`, a misspelled key, a string where a number belongs.
- **Structural damage**: a missing comma, a deleted array, the wrong root type, JSON `null`.
- **Drift**: a file written for an older or newer game version.
- **Hostility**: huge numbers, a 2 GB "image", `../../` paths, files that are really Resources with embedded scripts.

Policy: every file must prove itself before gameplay sees it. A bad **entry** is skipped, a bad **file** is skipped, and the game keeps running. Every problem goes into one report with its location.

Two failure classes per entry:
- **Structural** (id missing/invalid, wrong container type): skip the entry.
- **Tunable** (bad number, unknown enum name, over-long text): log it, use a fallback or a clamped value, keep the entry.

## 2. Error-collecting reader

```gdscript
class_name DataReader extends RefCounted
## Reads untrusted JSON-shaped data. Never throws: records "where: what" and returns a fallback.

static var _id_re: RegEx = RegEx.create_from_string("^[a-z0-9_]{1,64}$")

var errors: Array[String] = []

func fail(where: String, msg: String) -> void:
	errors.append("%s: %s" % [where, msg])

func read_json(path: String, max_bytes: int = 1 << 20) -> Variant:
	var f := FileAccess.open(path, FileAccess.READ)
	if f == null:
		fail(path, "cannot open (%s)" % error_string(FileAccess.get_open_error()))
		return null
	if f.get_length() > max_bytes:
		fail(path, "larger than %d bytes" % max_bytes)
		return null
	var json := JSON.new()
	if json.parse(f.get_as_text()) != OK:
		fail("%s:%d" % [path, json.get_error_line()], json.get_error_message())
		return null
	return json.data

func as_dict(v: Variant, where: String) -> Dictionary:
	if v is Dictionary:
		return v
	fail(where, "expected an object, got %s" % type_string(typeof(v)))
	return {}

func array(d: Dictionary, key: String, where: String, max_items: int = 1000) -> Array:
	var v: Variant = d.get(key)
	if not v is Array:
		fail(where, "'%s' must be an array" % key)
		return []
	var a: Array = v
	if a.size() > max_items:
		fail(where, "'%s' has %d items; keeping the first %d" % [key, a.size(), max_items])
		return a.slice(0, max_items)
	return a

func number(d: Dictionary, key: String, where: String, fallback: float, lo: float, hi: float, required := true) -> float:
	var v: Variant = d.get(key)
	if v == null:
		if required:
			fail(where, "missing '%s'" % key)
		return fallback
	if typeof(v) != TYPE_FLOAT and typeof(v) != TYPE_INT:
		fail(where, "'%s' must be a number, got %s" % [key, type_string(typeof(v))])
		return fallback
	var f: float = v
	if f < lo or f > hi:
		fail(where, "'%s' = %s clamped to [%s, %s]" % [key, f, lo, hi])
	return clampf(f, lo, hi)

func integer(d: Dictionary, key: String, where: String, fallback: int, lo: int, hi: int, required := true) -> int:
	var f := number(d, key, where, fallback, lo, hi, required)
	if f != floorf(f):
		fail(where, "'%s' must be a whole number" % key)
	return int(f)

func text(d: Dictionary, key: String, where: String, fallback: String, max_len: int, required := true) -> String:
	var v: Variant = d.get(key)
	if v == null:
		if required:
			fail(where, "missing '%s'" % key)
		return fallback
	if not v is String:
		fail(where, "'%s' must be a string" % key)
		return fallback
	var s: String = v
	if s.length() > max_len:
		fail(where, "'%s' truncated to %d chars" % [key, max_len])
		s = s.left(max_len)
	return s

## Returns &"" when invalid; callers skip the entry.
func id(d: Dictionary, key: String, where: String) -> StringName:
	var s := text(d, key, where, "", 64)
	if _id_re.search(s) == null:
		fail(where, "'%s' = '%s' is not a valid id ([a-z0-9_], 1-64)" % [key, s])
		return &""
	return StringName(s)

## `enum_dict` is a named enum, e.g. `reader.enum_value(d, "phase", where, Phase, Phase.DAY)`.
func enum_value(d: Dictionary, key: String, where: String, enum_dict: Dictionary, fallback: int) -> int:
	var s := text(d, key, where, "", 64, false)
	if s.is_empty():
		return fallback
	if not enum_dict.has(s):
		fail(where, "'%s' = '%s' not one of %s" % [key, s, enum_dict.keys()])
		return fallback
	return enum_dict[s]

## Resolves `rel` inside `root`; returns "" for absolute paths, schemes or `..` escapes.
static func resolve_inside(root: String, rel: String) -> String:
	if rel.is_empty() or rel.is_absolute_path() or rel.contains(":"):
		return ""
	var base := root.simplify_path().trim_suffix("/") + "/"
	var full := base.path_join(rel).simplify_path()
	return full if full.begins_with(base) else ""
```

Notes:
- `d.get(key) == null` covers both "missing" and JSON `null`.
- JSON numbers always arrive as `float`; `integer()` rejects `12.5` but accepts `12.0`.
- `number()` clamps in float space before `int()`, so `1e300` can't overflow.
- `simplify_path()` collapses `..` and backslashes (`"user://mods/a/../../x.png"` → `"user://x.png"`), so the `begins_with(base)` check catches escapes.
- Reuse the same reader for base content, saves and mods. One code path means one set of bugs.

## 3. Building typed objects

Convert immediately; gameplay receives `EnemyData`, never a Dictionary.

```gdscript
func _build_enemy(d: Dictionary, where: String, root: String, placeholder: Texture2D) -> EnemyData:
	if d.is_empty():
		return null
	var e := EnemyData.new()
	e.id = reader.id(d, "id", where)
	if e.id == &"":
		return null  # structural key bad: skip the entry
	# Tunables: bad value -> logged + fallback, entry still loads.
	e.display_name = reader.text(d, "name", where, String(e.id), 64)
	e.max_hp = reader.integer(d, "max_hp", where, 10, 1, 100_000)
	e.speed = reader.number(d, "speed", where, 100.0, 0.0, 2000.0)
	e.behavior = reader.enum_value(d, "behavior", where, EnemyData.Behavior, EnemyData.Behavior.CHASE) as EnemyData.Behavior
	e.weapon_id = StringName(reader.text(d, "weapon", where, "", 128, false))  # resolved in pass 2
	e.texture = placeholder
	var sprite := reader.text(d, "sprite", where, "", 256, false)
	if not sprite.is_empty():
		var p := DataReader.resolve_inside(root, sprite)
		if p.is_empty():
			reader.fail(where, "'sprite' must be a relative path inside the mod folder")
		else:
			e.texture = ModAssets.texture(p, placeholder, reader)
	return e
```

- Ranges in the loader should match the `@export_range` on the Resource. Keep them as constants on the Resource class so both read the same numbers.
- Cross-references (`weapon_id`) are only names here. After every source is registered, run a resolve pass that looks each one up and drops or patches entries whose reference is dangling.
- Versioned files: read `"version"` first, run `migrate_v1_to_v2(d)` style functions in sequence, and reject versions newer than the build knows.

## 4. Loader security matrix (verified 4.7.2 / 4.8-beta1)

| Loader | Builds objects / runs code from file content? | Untrusted input |
|---|---|---|
| `JSON.parse()`, `JSON.parse_string()` | no | OK |
| `JSON.to_native(v)` (4.4+, `allow_objects` false by default) | no | OK |
| `FileAccess.get_var()`, `bytes_to_var()` | no (objects disabled by default) | OK |
| `get_var(true)`, `bytes_to_var_with_objects()` | yes | never |
| `str_to_var()`, `ConfigFile.load()/parse()` | **yes**: `Object(RefCounted,"script":Resource("res://x.gd"))` creates the object, and the script's `_init()` runs during parsing | never for shared/downloaded files |
| `load()`/`ResourceLoader.load()` on `.tres`/`.res`/`.tscn` | **yes**: a `[sub_resource type="GDScript"]` with `script/source` runs on load, including from `user://` | never |
| `ProjectSettings.load_resource_pack()` | yes, and `replace_files` (default true) overwrites `res://` content | only for code mods, as an explicit opt-in |
| `Image.load_*_from_buffer()`, `AudioStream*.load_from_file()` | no; decoders allocate | OK with byte and pixel caps |

Consequences:
- Player-shareable saves, presets, levels and mod data: JSON (or `store_var`/`get_var` with objects off).
- `ConfigFile` is fine for the game's own `user://settings.cfg`. Don't import a `.cfg` a player downloaded.
- "Export to `.tres` for the level editor" is fine inside the editor. A level-sharing feature in the shipped game must use JSON.
- Encrypting the `.pck` (custom export templates with a key) slows extraction. It does not make loaded external files safe.

## 5. External assets

```gdscript
class_name ModAssets extends RefCounted
## Loads images and audio from user-supplied files, with caps and a placeholder.

const MAX_BYTES := 8 << 20
const MAX_SIDE := 4096

static func texture(path: String, placeholder: Texture2D, reader: DataReader) -> Texture2D:
	var bytes := _read_capped(path, reader)
	if bytes.is_empty():
		return placeholder
	var img := Image.new()
	var err: Error
	match path.get_extension().to_lower():
		"png": err = img.load_png_from_buffer(bytes)
		"jpg", "jpeg": err = img.load_jpg_from_buffer(bytes)
		"webp": err = img.load_webp_from_buffer(bytes)
		_: err = ERR_FILE_UNRECOGNIZED
	if err != OK:
		reader.fail(path, "image decode failed (%s)" % error_string(err))
		return placeholder
	if img.get_width() > MAX_SIDE or img.get_height() > MAX_SIDE:
		reader.fail(path, "image larger than %dpx" % MAX_SIDE)
		return placeholder
	return ImageTexture.create_from_image(img)

static func audio(path: String, reader: DataReader) -> AudioStream:
	if _read_capped(path, reader).is_empty():
		return null
	var stream: AudioStream = null
	match path.get_extension().to_lower():
		"ogg": stream = AudioStreamOggVorbis.load_from_file(path)
		"wav": stream = AudioStreamWAV.load_from_file(path)
		"mp3": stream = AudioStreamMP3.load_from_file(path)
	if stream == null:
		reader.fail(path, "unsupported or corrupt audio")
	return stream

static func _read_capped(path: String, reader: DataReader) -> PackedByteArray:
	if path.is_empty():
		reader.fail("asset", "path rejected (outside the mod folder or empty)")
		return PackedByteArray()
	var f := FileAccess.open(path, FileAccess.READ)
	if f == null:
		reader.fail(path, "cannot open (%s)" % error_string(FileAccess.get_open_error()))
		return PackedByteArray()
	if f.get_length() > MAX_BYTES:
		reader.fail(path, "file larger than %d bytes" % MAX_BYTES)
		return PackedByteArray()
	return f.get_buffer(f.get_length())
```

- Dispatch on an allow-listed extension. `Image.load()` with any path is convenient, but the allow-list keeps formats and decoders under your control.
- The pixel check runs after decoding. A small PNG can declare huge dimensions (a decompression bomb). For strict limits, read the PNG header's width and height (bytes 16–23, big-endian) before decoding.
- Pixel art: set the sprite's `texture_filter` to nearest; an `ImageTexture` has no import flags.
- Never `Image.load("res://...")` for shipped art. It works in the editor and fails in exports. Ship art as imported textures and `load()` it.
- Mod text: build `Translation` objects in code (`add_message()`), then `TranslationServer.add_translation()`. Namespace the keys (`modid.enemy.dread.name`).

## 6. Mod pipeline

Layout:
```
user://mods/<mod_id>/mod.json        # {"id","name","version","game_api","load_after":[],"overrides":[]}
user://mods/<mod_id>/enemies.json
user://mods/<mod_id>/art/*.png
```

Discovery with manifest checks:

```gdscript
class_name ModLoader extends RefCounted

const MODS_DIR := "user://mods"
const GAME_API := 3

class ModInfo:
	var id: StringName
	var root: String
	var manifest: Dictionary

var reader := DataReader.new()

func discover() -> Array[ModInfo]:
	var mods: Array[ModInfo] = []
	var seen: Dictionary[StringName, bool] = {}
	DirAccess.make_dir_recursive_absolute(MODS_DIR)
	for folder in DirAccess.get_directories_at(MODS_DIR):
		var root := MODS_DIR.path_join(folder)
		var where := root.path_join("mod.json")
		var m := reader.as_dict(reader.read_json(where, 64 << 10), where)
		if m.is_empty():
			continue
		var mod_id := reader.id(m, "id", where)
		var api := reader.integer(m, "game_api", where, -1, -1, 1000)
		if mod_id == &"" or String(mod_id) != folder or seen.has(mod_id):
			reader.fail(where, "skipped: id must be valid, unique and equal the folder name")
			continue
		if api != GAME_API:
			reader.fail(where, "skipped: game_api %d, this build supports %d" % [api, GAME_API])
			continue
		seen[mod_id] = true
		var info := ModInfo.new()
		info.id = mod_id
		info.root = root
		info.manifest = m
		mods.append(info)
	mods.sort_custom(func(a: ModInfo, b: ModInfo) -> bool: return String(a.id) < String(b.id))
	return mods

func load_enemies(mod: ModInfo, db: ContentDB, placeholder: Texture2D) -> void:
	var path := mod.root.path_join("enemies.json")
	if not FileAccess.file_exists(path):
		return
	var file := reader.as_dict(reader.read_json(path), path)
	var entries := reader.array(file, "enemies", path, 500)
	for i in entries.size():
		var where := "%s enemies[%d]" % [path, i]
		var e := _build_enemy(reader.as_dict(entries[i], where), where, mod.root, placeholder)
		if e != null:
			db.register(StringName("%s:%s" % [mod.id, e.id]), e)
```

Steps and decisions:
1. **Discover** folders under `user://mods`. Require folder name == manifest id, so duplicates are impossible.
2. **Manifest**: valid id, `game_api` equals the build's (an integer you bump only on breaking data-format changes; not the game's display version). Apply the player's enabled/disabled list here.
3. **Order**: sort by id for determinism, then apply `load_after` with a topological sort; disable every mod in a cycle and say so.
4. **Data**: per file, the zero-trust reader; per entry, structural skip vs tunable fallback.
5. **Assets**: resolved with `resolve_inside(mod.root, rel)`; capped; placeholder on failure. Cache textures by path so 50 entries sharing one PNG decode it once.
6. **Build** Resources with `.new()` (no `.tres` loading).
7. **Register** as `modid:local_id`. Base content uses `base:` (or bare ids; choose once). Overrides: a mod may replace a base id only if it lists it in `"overrides"`; the last mod in load order wins; log every override.
8. **Resolve** cross-references across all sources; drop entries whose required refs dangle.
9. **Report** `reader.errors` in a mods screen, not only in the console that players never see. Show the folder path via `ProjectSettings.globalize_path("user://mods")` and an "Open folder" button (`OS.shell_open`).
10. **Freeze**: after boot, the registry is read-only. Reload mods only from the main menu, never mid-match.

Strong option: ship your own base content through the same pipeline (as JSON in `res://`, or as a built-in "base" mod). Then the mod path is tested every time you play.

Out of scope for data mods: scripts, `.tscn`, `.tres`, `.pck`. If the product wants code mods, that is a separate design: `load_resource_pack()` with `replace_files = false`, an explicit warning to the player, and no pretense of sandboxing.

## 7. Hot reload during development

- Bind a debug-only key (`OS.is_debug_build()`) that re-runs the loader, rebuilds the registry and restarts the current wave/level. Don't patch live entities field by field unless the system was designed for it.
- On reload, print `reader.errors` in an overlay so the designer sees the typo next to the game.
- Remember that `.tres` hot reload works differently (see `resource-traps.md`, `CACHE_MODE_REPLACE`).

## 8. Testing the loader

- Keep a `tests/fixtures/mods/` folder with one broken case per rule: bad JSON, wrong root, missing id, string-for-number, path escape, oversize image, wrong `game_api`, duplicate id, a `.tres` dropped in.
- A headless test copies the fixtures to a temp `user://` folder, runs the loader, and asserts two things: it did not crash, and the expected error lines are present (see `godot-gdscript-headless-testing` (awesome-gamedev-agent-skills)).

Deeper: Godot 4 Best Practices ch.11 "Externalizing data with JSON", PDF pp. 296–300; "Designing moddable systems" / "Loading external assets" / "The Mod Loading Pipeline", pp. 300–304
