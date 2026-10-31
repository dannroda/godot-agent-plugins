# Autoloads and services: deep reference

Read this when you create, modify or remove an autoload, or write a global service (scene loading, audio, saving, settings). The rules summary is in SKILL.md §7–8.

## 1. Before adding an autoload

Answer all five. Any "no" means it is not an autoload:
1. Must it survive scene changes? (music, network peer, transition overlay, settings)
2. Is there exactly one per game, even with split-screen or a second player?
3. Is it a **service** (does work when asked), not a bag of gameplay state?
4. Is it light? Heavy UI, particles and textures stay in RAM for the whole session.
5. Would a `static func`, a `const` class, a shared `.tres` or an injected object not do?

## 2. Init order and lifecycle (verified on 4.7.2)

Probe: autoloads `A`, `B` (in that order) plus a main scene.

| Moment | What exists |
|---|---|
| `A._init()` | `B` global is still `null`. Main scene not created |
| `A._ready()` | `B.is_inside_tree() == true`, but `B._ready()` has **not** run. `get_tree().current_scene` is already set, but not ready |
| `B._ready()` | `A` is fully ready |
| Main scene `_ready()` | Every autoload is ready |

Consequences:
- In `_init`, touch no other autoload and no tree.
- In `_ready`, call only autoloads listed **above** this one, and don't read state from the main scene.
- To act once the first scene is ready: `await get_tree().process_frame` in the autoload's `_ready`. Better, have scenes register with the service in their own `_ready`.
- A `class_name` equal to the autoload name is a parse error ("Class "X" hides an autoload singleton"). Name the script `audio_service.gd` / `class_name AudioService` and the autoload `Audio`, or give it no class_name.
- `@tool` code and Resource setters also run in the editor. Don't assume autoloads exist there: guard with `Engine.is_editor_hint()`, or don't reference autoloads from them at all.

## 3. Scene changes (verified on 4.7.2)

- `get_tree().change_scene_to_file(path)` / `change_scene_to_packed(packed)` removes the current scene from the tree **immediately**. Right after the call, the old scene's code gets `null` from `get_tree()`. The new scene is added later, and `SceneTree.scene_changed` fires once it is current (the signal exists in 4.7/4.8; verify the minimum version).
- Code after `change_scene_*` in the old scene must not touch the tree. Make it the last statement, or let a SceneLoader autoload own the transition.
- Connections from level nodes to autoload signals disappear with the level (target freed). Connections an autoload made to level nodes' signals also vanish (emitter freed). Nothing to clean up in either case.
- Autoload state does **not** reset on scene change. Anything that must reset on "return to menu" doesn't belong in an autoload.

## 4. SceneLoader (transition service)

Autoload **scene** `scene_loader.tscn`: root `CanvasLayer` (layer 100) with a full-rect `ColorRect` child named `Fade`.

```gdscript
# core/scene_loader.gd  -> autoload "SceneLoader"
extends CanvasLayer
signal transition_finished(path: String)

@onready var _fade: ColorRect = $Fade
var _busy := false

func _ready() -> void:
    process_mode = Node.PROCESS_MODE_ALWAYS  # works while the game is paused
    _fade.color.a = 1.0
    _fade.modulate.a = 0.0
    _fade.mouse_filter = Control.MOUSE_FILTER_IGNORE

func go_to(path: String, fade_time: float = 0.25) -> void:
    if _busy:
        return
    _busy = true
    _fade.mouse_filter = Control.MOUSE_FILTER_STOP  # swallow input mid-transition
    ResourceLoader.load_threaded_request(path)
    await _fade_to(1.0, fade_time)
    while ResourceLoader.load_threaded_get_status(path) == ResourceLoader.THREAD_LOAD_IN_PROGRESS:
        await get_tree().process_frame
    var packed := ResourceLoader.load_threaded_get(path) as PackedScene
    if packed == null:
        push_error("SceneLoader: cannot load %s" % path)
    else:
        get_tree().paused = false
        get_tree().change_scene_to_packed(packed)
        await get_tree().scene_changed
    await _fade_to(0.0, fade_time)
    _fade.mouse_filter = Control.MOUSE_FILTER_IGNORE
    _busy = false
    transition_finished.emit(path)

func _fade_to(alpha: float, t: float) -> void:
    var tw := create_tween()  # bound to this ALWAYS node, so it runs while paused
    tw.tween_property(_fade, ^"modulate:a", alpha, t)
    await tw.finished
```
- For a progress bar, pass an array to `load_threaded_get_status(path, progress)` and read `progress[0]`.
- Levels call `SceneLoader.go_to(...)` as their last action, or emit a signal the game flow coordinator handles.
- Nothing in the **old** scene can listen to `transition_finished`: it is freed mid-transition and its connections go with it (verified). Listen from another autoload, or let the new scene do its own setup in `_ready`.
- Verified end-to-end on 4.7.2 (headless): threaded load, scene swap, fade back.

## 5. AudioService (pooled, survives emitter death)

Why: a sound played by a child `AudioStreamPlayer` of an enemy is cut off when the enemy is `queue_free()`d. A global pool keeps playing.

```gdscript
# core/audio_service.gd  -> autoload "Audio"
extends AudioPort  # @abstract contract (SKILL.md §8); use `extends Node` without one
const WORLD_VOICES := 16
const UI_VOICES := 4

var _world: Array[AudioStreamPlayer2D] = []
var _ui: Array[AudioStreamPlayer] = []
var _world_next := 0
var _ui_next := 0

func _ready() -> void:
    for i in WORLD_VOICES:
        var p := AudioStreamPlayer2D.new()
        p.bus = &"SFX"
        p.process_mode = Node.PROCESS_MODE_PAUSABLE  # world SFX pause with the game
        add_child(p)
        _world.append(p)
    for i in UI_VOICES:
        var u := AudioStreamPlayer.new()
        u.bus = &"UI"
        u.process_mode = Node.PROCESS_MODE_ALWAYS  # menu clicks while paused
        add_child(u)
        _ui.append(u)

func play_sfx(stream: AudioStream, at: Vector2 = Vector2.INF) -> void:
    if stream == null:
        return
    if at == Vector2.INF:
        var u := _ui[_ui_next]
        for c in _ui:
            if not c.playing:
                u = c
                break
        _ui_next = (_ui.find(u) + 1) % _ui.size()
        u.stream = stream
        u.play()
        return
    var p := _world[_world_next]  # fallback: steal round-robin
    for c in _world:
        if not c.playing:
            p = c
            break
    _world_next = (_world.find(p) + 1) % _world.size()
    p.stream = stream
    p.global_position = at  # parent is a plain Node, so global == local
    p.play()
```
- Cap the pool. When it is exhausted, steal (as above) or drop with a debug warning. Never grow it unbounded.
- For one emitter spamming the same sound (a machine gun), a single local player with `max_polyphony > 1` is simpler than the pool.
- Music lives in its own player (or two, for crossfades) with `PROCESS_MODE_ALWAYS`, on a `Music` bus.
- If gameplay renders inside a `SubViewport`, positional players under `/root` hear the wrong listener. Parent world SFX to a node inside that viewport instead.
- Pooling mechanics in general: `godot-patterns` §Pooling.

## 6. Stateless SaveService

The service receives data, writes it, and forgets it. It holds no `player_health`.

```gdscript
# core/save_service.gd  -> autoload "Saves"
extends Node
const DIR := "user://saves/"

func save_slot(slot: int, data: Dictionary) -> Error:
    DirAccess.make_dir_recursive_absolute(DIR)
    var path := DIR + "slot_%d.json" % slot
    var tmp := path + ".tmp"
    var f := FileAccess.open(tmp, FileAccess.WRITE)
    if f == null:
        return FileAccess.get_open_error()
    f.store_string(JSON.stringify(data))
    f.close()
    return DirAccess.rename_absolute(tmp, path)  # atomic-ish: never a half-written slot

func load_slot(slot: int) -> Dictionary:
    var path := DIR + "slot_%d.json" % slot
    if not FileAccess.file_exists(path):
        return {}
    var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
    return parsed if parsed is Dictionary else {}
```
- Who gathers the data: a coordinator (game flow or level) asks each system for a snapshot (`stats.to_dict()`) and passes it in. The service never reaches into the scene.
- Formats, versioning, migration and validation: `godot-data-driven` (save files).
- Save on `NOTIFICATION_WM_CLOSE_REQUEST` (desktop) **and** `NOTIFICATION_APPLICATION_PAUSED` (mobile). Handle both in this one service.

## 7. Settings service

- Load once in `_ready` from `user://settings.cfg` (`ConfigFile`), apply immediately: `AudioServer.set_bus_volume_db`, `DisplayServer.window_set_mode`, `InputMap` overrides.
- API is methods plus a change signal: `set_volume(bus: StringName, linear: float)` saves, applies, and emits `setting_changed(key, value)`.
- It is application-level config, so it is a legitimate autoload. Gameplay tuning numbers are not settings; they belong in Resources.

## 8. Contracts, fakes and tests

```gdscript
@abstract class_name AudioPort extends Node
@abstract func play_sfx(stream: AudioStream, at: Vector2 = Vector2.INF) -> void
```

```gdscript
# tests/fake_audio.gd
class_name FakeAudio extends AudioPort
var played: Array[AudioStream] = []
func play_sfx(stream: AudioStream, _at: Vector2 = Vector2.INF) -> void:
    played.append(stream)
```
- `@abstract` classes and methods: 4.5+. An abstract class can't be instantiated, and a concrete subclass must implement every abstract method.
- Consumers type their field as `AudioPort` and default to the autoload (SKILL.md §8). Tests assign a `FakeAudio` before `add_child`. You get silent tests and can assert "a sound would have played".
- If a real service breaks after an engine update, gameplay tests that use fakes still pass. That points the bug at the service.

## 9. Anti-patterns → fixes

| Smell | Fix |
|---|---|
| `Global.gd` holding HP, inventory, level name, volume, save/load, play_sound | Split: observable Resources for state, one service per concern |
| `GameManager.add_score()` called from a coin | Coin emits `collected(value)`; the level connects it to whatever tracks score |
| Autoload `_ready` reads `get_tree().current_scene.$Player` | Player registers itself, or the service waits a frame |
| Autoload holding references to level nodes | Clear them on `tree_exiting` of the node, or hold ids. Better: don't hold them |
| Pause menu autoload freezes when paused | `process_mode = PROCESS_MODE_ALWAYS` on that autoload |
| Same name for `class_name` and autoload | Rename one |
| Bus with `var current_lives` | Move the state to a Resource; the bus stays signals-only |

Deeper: Godot 4 Best Practices ch.5 "Using Autoloads and Singletons" (whole chapter), PDF pp. 136–158; ch.10 "Applying the Service Pattern to cross-cutting systems", PDF pp. 278–281
