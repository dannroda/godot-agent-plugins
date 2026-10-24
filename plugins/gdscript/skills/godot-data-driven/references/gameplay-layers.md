# Gameplay layers: state, rules, presentation, contexts, persistence

Read this when you split a god class, write a gameplay context, decide where match state lives, or wire saving.
All code compiles and runs on 4.7.2. Class names are illustrative: rename them to fit the project.

## 1. The layers

| Layer | Base type | Owns | May reference | Must not |
|---|---|---|---|---|
| **State** | `RefCounted` | fields only, `to_dict()`/`from_dict()` | other state objects | nodes, signals, rules |
| **Rules (domain)** | `RefCounted` + signals | the truth: every gameplay decision | state, config Resources, injected services | `get_tree()`, `$`/`%` paths, Timer, Tween, UI, audio, autoload event buses |
| **Presentation** | Nodes | sprites, animation, UI, audio, input capture | its own children | game math, win/lose checks, storing gameplay values |
| **Context** | `Node` at a scene boundary | building and wiring the others | everything inside its scene | gameplay math |
| **Persistence** | stateless service (autoload is fine) | file I/O, rotation, versions | `DataReader` | knowledge of which node holds what |

Data flows one way: input/events → rules → state → signals → presentation. Saving reads state only.

Why rules are `RefCounted` and not `Node`:
- No lifecycle surprises (`queue_free`, pause, tree order), so they can be tested headlessly with no scene.
- They can take constructor arguments. A `Node` whose `_init()` requires arguments cannot be placed in a `.tscn` or duplicated. The book's controller example is a Node with a required-argument `_init`; if a rule object really must be a Node (it needs `_physics_process`), give it `setup(state, config)` instead.
- `RefCounted` can declare and emit signals, so you lose nothing.

Time: the context calls `rules.tick(delta)` from `_physics_process`. Cooldowns and spawn timers are floats in state. A `Timer` node is presentation (it can drive a blinking label), never the authority for "can fire again".

## 2. Diagnosing a god class

Refactor when two or more apply:
- One script mixes three of: input handling, game math, UI updates, audio/VFX, saving, scene changes.
- A dozen or more `@onready` paths into unrelated branches (`$HUD/Margin/ScoreLabel`, `$ExplosionPlayer`, `$Spawner`).
- Gameplay values stored in UI (`progress_bar.value -= dmg`) or read back from nodes to decide (`if label.text == ...`, `if sprite.global_position.x > ...` for a rule).
- It listens to a global event bus for everything, so an event from a test scene or another level changes its state.
- One handler does math and then calls a cosmetic node; deleting that node (a missing `AudioStreamPlayer`) aborts the handler halfway, after the state changed but before the UI update.
- Saving requires finding this node in the tree.

Not a god class: a long script that does one job (a big but cohesive state machine). Size alone is not the signal; mixed responsibilities are.

## 3. Refactor recipe

1. **Type everything first** (`var score: int`, `-> void`). Moving code between files with typed signatures turns wiring mistakes into editor errors instead of runtime nulls.
2. **Extract state** into a `RefCounted` with the variables only.
3. **Extract rules** into a `RefCounted` that takes the state (and a config Resource) in `_init`, mutates it, and emits result signals.
4. **Shrink the view** to methods that take final values (`show_score(int)`) plus signals for input and animation-finished.
5. **Write the context**: build state (fresh or from a save), build rules, connect rules → views and entities → rules, push initial values.
6. **Replace global listens** (`Events.enemy_died.connect`) with connections the context makes to the entities it spawns.
7. **Move tunables** (points per wave, start HP) from code into a config Resource.
8. **Test the rules** headlessly with a fresh state and config.

## 4. Code

State (versioned, zero-trust load; `DataReader` is in `zero-trust-and-mods.md`):

```gdscript
class_name MatchState extends RefCounted
## Pure state: no nodes, no signals, no rules. Everything a save needs.

enum Phase { DAY, NIGHT }
const VERSION := 2

var score: int = 0
var wave: int = 1
var hull: int = 100
var phase: Phase = Phase.DAY
var spawn_timer: float = 0.0
var game_over: bool = false

func to_dict() -> Dictionary:
	return {
		"version": VERSION, "score": score, "wave": wave, "hull": hull,
		"phase": Phase.find_key(phase),  # name, not int: survives enum reordering
	}

## Returns null for saves from a newer build. Uses the zero-trust reader: players edit saves.
static func from_dict(d: Dictionary, reader: DataReader) -> MatchState:
	var version := reader.integer(d, "version", "save", 1, 1, 999)
	if version > VERSION:
		reader.fail("save", "version %d is newer than this build (%d)" % [version, VERSION])
		return null
	if version < 2:
		d = _migrate_v1(d)
	var s := MatchState.new()
	s.score = reader.integer(d, "score", "save", 0, 0, 2_000_000_000)
	s.wave = reader.integer(d, "wave", "save", 1, 1, 10_000)
	s.hull = reader.integer(d, "hull", "save", 100, 0, 100_000)
	s.phase = reader.enum_value(d, "phase", "save", Phase, Phase.DAY) as Phase
	return s

static func _migrate_v1(d: Dictionary) -> Dictionary:
	var out := d.duplicate()
	out["hull"] = out.get("health", 100)  # v1 called it "health"
	out.erase("health")
	return out
```

Rules:

```gdscript
class_name MatchRules extends RefCounted
## Domain rules. Owns the truth, mutates MatchState, announces results. Knows no nodes.

signal score_changed(score: int)
signal hull_changed(hull: int)
signal wave_started(wave: int)
signal spawn_requested(wave: int)
signal game_over

var _state: MatchState
var _config: MatchConfig  # Resource: points_per_wave, start_hull, spawn_interval

func _init(state: MatchState, config: MatchConfig) -> void:
	_state = state
	_config = config

func tick(delta: float) -> void:
	if _state.game_over:
		return
	_state.spawn_timer -= delta
	if _state.spawn_timer <= 0.0:
		_state.spawn_timer += _config.spawn_interval
		spawn_requested.emit(_state.wave)

func enemy_destroyed(points: int) -> void:
	if _state.game_over:
		return
	_state.score += points
	score_changed.emit(_state.score)
	if _state.score >= _state.wave * _config.points_per_wave:
		_state.wave += 1
		wave_started.emit(_state.wave)

func damage_hull(amount: int) -> void:
	if _state.game_over:
		return
	_state.hull = maxi(_state.hull - amount, 0)
	hull_changed.emit(_state.hull)
	if _state.hull == 0:
		_state.game_over = true
		game_over.emit()
```

Note: the rules decide *that* a spawn happens (`spawn_requested`); a spawner node decides *how* it looks. The rules never instantiate scenes.

Presentation:

```gdscript
class_name HudView extends CanvasLayer
## Presentation: draws what it is told. No math, no state checks, no autoload listeners.

signal restart_pressed

@onready var _score: Label = %ScoreLabel
@onready var _hull: ProgressBar = %HullBar
@onready var _game_over: Control = %GameOverPanel

func show_score(value: int) -> void:
	_score.text = "SCORE %d" % value

func show_hull(value: int) -> void:
	_hull.value = value

func show_game_over() -> void:
	_game_over.visible = true
```

Context:

```gdscript
class_name MatchContext extends Node
## Builds state + rules, wires rules -> views and entities -> rules. Holds no game math.

@export var config: MatchConfig
@export var hud: HudView
@export var spawner: EnemySpawner

var state: MatchState
var rules: MatchRules

func _ready() -> void:
	var reader := DataReader.new()
	var saved := SaveService.read("slot1", reader)
	state = MatchState.from_dict(saved, reader) if not saved.is_empty() else null
	if state == null:
		state = MatchState.new()
		state.hull = config.start_hull
	for e in reader.errors:
		push_warning(e)

	rules = MatchRules.new(state, config)
	rules.score_changed.connect(hud.show_score)
	rules.hull_changed.connect(hud.show_hull)
	rules.game_over.connect(hud.show_game_over)
	rules.spawn_requested.connect(_on_spawn_requested)
	# Signals fire only on change: push the current values once.
	hud.show_score(state.score)
	hud.show_hull(state.hull)

func _physics_process(delta: float) -> void:
	rules.tick(delta)

func _on_spawn_requested(wave: int) -> void:
	var enemy := spawner.spawn_for_wave(wave)
	enemy.died.connect(rules.enemy_destroyed)       # died(points: int)
	enemy.hit_player.connect(rules.damage_hull)     # hit_player(damage: int)

## Called by the root context before a scene change or quit.
func snapshot() -> Dictionary:
	return state.to_dict()
```

Context rules:
- Exported node references (`@export var hud: HudView`) beat hard-coded paths: the scene can be rearranged and the Inspector shows a missing link.
- Rules → views is a signal connection made by the context. The view never connects to the rules itself, and the rules never hold a view.
- Entities → rules is also connected by the context (or the spawner it owns). An enemy emits `died(points)`; it doesn't call a global.
- Pushing the initial state after connecting is mandatory. Without it the HUD shows defaults until the first change, and after loading a save the HUD is wrong.
- One context per major mode (`MainMenuContext`, `MatchContext`), under a `RootContext` main scene that owns global services and scene swaps. Match state lives in `MatchContext`; the menu cannot reach it.

## 5. Persistence

```gdscript
extends Node
## Autoload "SaveService": stateless file utility. Knows files, not gameplay.

const DIR := "user://saves"

func _ready() -> void:
	DirAccess.make_dir_recursive_absolute(DIR)

func write(slot: String, data: Dictionary) -> Error:
	var path := DIR.path_join(slot + ".json")
	var tmp := path + ".tmp"
	var f := FileAccess.open(tmp, FileAccess.WRITE)
	if f == null:
		return FileAccess.get_open_error()
	f.store_string(JSON.stringify(data, "\t"))
	var err := f.get_error()
	f.close()
	if err != OK:
		return err
	if FileAccess.file_exists(path):  # rotate: current -> .bak, tmp -> current
		DirAccess.remove_absolute(path + ".bak")
		DirAccess.rename_absolute(path, path + ".bak")
	return DirAccess.rename_absolute(tmp, path)

## Returns {} when neither the save nor its backup passes parsing.
func read(slot: String, reader: DataReader) -> Dictionary:
	var path := DIR.path_join(slot + ".json")
	for p: String in [path, path + ".bak"]:
		if FileAccess.file_exists(p):
			var d := reader.as_dict(reader.read_json(p), p)
			if not d.is_empty():
				return d
	return {}
```

Who triggers saves:

```gdscript
class_name RootContext extends Node
## Main scene. Owns quitting and scene swaps, so it decides when to save.

var active: Node  # current MatchContext or MainMenuContext

func _ready() -> void:
	get_tree().auto_accept_quit = false

func _notification(what: int) -> void:
	if what == NOTIFICATION_WM_CLOSE_REQUEST:
		_save_active()
		get_tree().quit()

func go_to(scene: PackedScene) -> void:
	_save_active()  # before freeing: the state object is still intact
	if active:
		active.queue_free()
	active = scene.instantiate()
	add_child(active)

func _save_active() -> void:
	if active and active.has_method(&"snapshot"):
		var err: Error = SaveService.write("slot1", active.call(&"snapshot"))
		if err != OK:
			push_error("Save failed: %s" % error_string(err))
```

Decisions:
- **Pull, from one owner.** The node that owns transitions and quitting asks the active context for a snapshot. The book's variant (the persistence service emits a "about to switch" signal and contexts respond) works, but it hides who saves and when. Prefer the explicit call.
- Without `auto_accept_quit = false`, closing the window quits before your handler can save.
- Mobile: also save on `NOTIFICATION_APPLICATION_PAUSED` (the OS may kill the app without a close request). Web: save on meaningful checkpoints; tab close is unreliable.
- Rotation avoids overwrite-in-place, so a crash mid-write leaves either the old file or the `.bak`. Removing `.bak` before renaming makes this work the same on every OS.
- Save format = `to_dict()` of state objects. Never node paths, never `var_to_str` of Objects, never `.tres` in `user://` (see the security matrix in `zero-trust-and-mods.md`).
- Every save carries `version`; `from_dict` migrates stepwise and refuses newer versions instead of half-loading them.

## 6. Testing the rules

```gdscript
func test_wave_advances_on_threshold() -> void:
	var cfg := MatchConfig.new()
	cfg.points_per_wave = 100
	var rules := MatchRules.new(MatchState.new(), cfg)
	var waves: Array[int] = []
	rules.wave_started.connect(func(w: int) -> void: waves.append(w))
	rules.enemy_destroyed(60)
	rules.enemy_destroyed(60)
	assert(waves == [2])
```

No scene, no HUD, no autoloads. Run it with the headless runner from `godot-gdscript-headless-testing` (awesome-gamedev-agent-skills). If a rule cannot be tested this way, it still depends on a node.

## 7. Scale it to the project

| Project | Use |
|---|---|
| Jam / prototype / tiny mobile game | Node scripts with `@onready` refs; Resources for tunables; one save function. Layers are overkill. |
| Mid-size (months, one or two devs) | State + rules objects for the core loop and anything saved; contexts per mode; SaveService. |
| Long-lived / data-heavy / team | Everything above, folders by feature (`features/match/`, not `scripts/`), rule tests in CI. |

Introduce the layers when the first pain shows: a cosmetic change breaks gameplay, saving needs to find nodes, or two people keep editing the same script.

Deeper: Godot 4 Best Practices ch.12 "Studying the architecture roadmap" / "Identifying God classes in Godot", PDF pp. 308–311; "Separating Presentation from Logic", pp. 311–314; "Introducing Pure Data, Contexts, and Persistence", pp. 314–318; "Refactoring a monolithic script", pp. 318–326
