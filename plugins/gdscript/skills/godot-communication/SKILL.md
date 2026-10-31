---
name: "godot-communication"
description: "Use for how Godot 4 systems talk and live globally: signal design, await/signal lifetimes, deferred calls, EventBus (namespaces, event objects, relays), observable Resources, autoloads and services, init order and races, scene-change timing, dependency injection and service locators, notifications, groups. Triggers: signal, connect, await, call_deferred, EventBus, autoload, singleton, GameManager, service, _notification, race condition, get_parent."
---

# Godot 4 Communication & Global Systems

Use statically typed GDScript throughout, targeting Godot 4.6+. Pattern implementations (FSM, strategy, components, factories, pools, commands) live in `godot-patterns`; this skill covers how those pieces talk to each other and which systems are allowed to be global.

## 1. The routing rule: call down, signal up, event out

Pick the channel by the relationship between sender and receiver:

| Relationship | Channel |
|---|---|
| Parent → own child | Direct call (`hitbox.enable()`), via `@export` or `@onready` reference |
| Child → parent / owner | Signal emitted by the child; the parent connects |
| Siblings in the same scene | The shared parent wires them in its `_ready` |
| Unrelated branches / different scenes | EventBus signal (§5) |
| Persistent state read by many (HP, ammo, volume) | Observable Resource shared via `@export` (§6) |
| Ordered multi-step reaction ("score, then check victory, then save") | One coordinator calls the steps directly. Never a chain of events |
| Engine lifecycle (focus, close, pause, predelete) | `_notification(what)` (§10) |
| Same trivial operation on many nodes (pause AI, mute all) | Group with a constant name (§11) |

- A node must keep working if its parent changes. A script that needs `get_parent()` or `../` paths is coupled; fix that first.
- A child reports *what happened* (`health_depleted`), never *what to do* (`get_parent().die()`).

Deeper: Godot 4 Best Practices ch.6 "Expanding the golden rule – Call Down, Signal Up, Event Out", PDF pp. 161–163

## 2. Designing signals

- Name them in the past tense or as a state change: `died`, `health_changed(current, max_value)`, `item_picked_up(item)`. They announce facts; `please_die` is a command in disguise.
- Type every parameter: `signal health_changed(current: int, max_value: int)`. Type the callback to match.
- Emit **after** the state has changed and is consistent, as the last statement of the mutation. Listeners may read the emitter back, or even free it.
- Connect in code with callables: `enemy.died.connect(_on_enemy_died)`. Add context with `bind`; bound arguments are appended **after** the signal's own arguments: `health.died.connect(_on_died.bind(enemy))` → `func _on_died(enemy: Enemy)`.
- Drop unwanted signal arguments with `unbind(n)`: `button.toggled.connect(_refresh.unbind(1))`.
- Connect once. A second `connect` of the same callable is an error ("already connected"). For pooled or re-added nodes, connect at creation or guard with `if not sig.is_connected(cb)`.
- Flags: `CONNECT_ONE_SHOT` for single-use events, `CONNECT_DEFERRED` to run the callback at the end of the frame (safe for physics/tree changes).
- Godot removes a connection automatically when the **target** object is freed. That includes lambdas created inside that object (verified 4.7.2). Disconnect manually only when the receiver lives on but should stop listening, such as a pooled node that subscribed to an autoload signal. Do it in `_exit_tree()` or on deactivate.
- Editor connections (Node dock) are fine for static scene wiring. Anything spawned at runtime connects in code.
- Signal emission is synchronous: `emit()` runs every callback before returning, in connection order. Don't rely on that order across unrelated listeners.

## 3. Signal and await lifetimes

`await sig` suspends the function and resumes it when `sig` fires. The traps (verified on 4.7.2):

| Symptom | Cause | Fix |
|---|---|---|
| Code after `await x.done` never runs, no error | Emitter freed (or never emits); the coroutine is silently dropped | Race the signal against a timeout (`references/signals-and-lifetimes.md`), or await signals of objects you own |
| Code after `await` never runs, no error | The awaiting node itself was freed; its coroutine is dropped | Put must-run cleanup before the `await`, or in `_exit_tree` |
| `await tween.finished` hangs forever | The tween's bound node was freed or the tween was killed; `finished` never fires | Bound timeout, or don't block a queue on it |
| Crash on the line after `await` | The world changed while suspended | Re-validate after **every** await: `is_instance_valid(target)`, `is_inside_tree()`, state still current |
| Parent's `_ready` sees a half-initialized child | Child's `_ready` contains `await`; `ready` fires at the first await | No `await` in `_ready`; call an explicit async `start()` after setup |
| "Lambda capture … was freed" | Lambda captured another object that died | Capture an id/WeakRef, or connect a method of the object instead |
| Awaited timer keeps running while paused | `create_timer(t)` defaults to `process_always = true` | Gameplay waits: `create_timer(t, false)` |
| "Can't change this state while flushing queries" | Adding/enabling physics objects inside `body_entered` and other physics callbacks | `call_deferred` / `set_deferred` (§4) |

Helpers (await-with-timeout, cancellation by generation token), connection rules for pooled nodes, the physics-callback table, timers vs pause, and EventBus logging are in `references/signals-and-lifetimes.md`. Read it before writing any multi-step coroutine or a node that is reused.

Deeper: Godot 4 Best Practices ch.6 "Connecting signals via code", PDF pp. 164–165

## 4. Deferred calls and frame timing

| Tool | When it runs | Use for |
|---|---|---|
| `obj.method.call_deferred(args)` | End of the current frame (idle time) | Tree edits from physics callbacks; wiring after siblings are ready |
| `set_deferred(&"disabled", true)` | Same queue | `CollisionShape2D.disabled`, `Area2D.monitoring` inside physics callbacks |
| `CONNECT_DEFERRED` | Same queue | Reacting after the emitter finished its frame's work |
| `queue_free()` | End of frame; the node stays valid and in the tree until then | Normal deletion. Check `is_queued_for_deletion()` before reusing it |
| `await get_tree().process_frame` | Next process frame | Let one frame of ready/layout pass |
| `await get_tree().physics_frame` | Next physics tick | Query physics after moving/adding bodies |

- Use the Godot 4 form `node.add_child.call_deferred(child)`, not `call_deferred("add_child", child)`.
- A deferred `add_child` means the child is **not** in the tree when your function returns: its `@onready` vars are null and `global_position` writes are relative to nothing. Configure it before adding (`setup()`, `position`) and read tree state only after it enters.
- `call_deferred` or `await process_frame` is a fix for one known ordering problem. Used everywhere "to be safe", it hides real ordering bugs.

## 5. EventBus

One autoload that only declares signals, with no logic and no state:

```gdscript
# core/event_bus.gd  -> autoload "EventBus"
extends Node
@warning_ignore_start("unused_signal")  # bus signals are emitted elsewhere
signal enemy_defeated(event: EnemyDefeatedEvent)
signal player_died
signal wave_started(index: int)
signal level_completed(source: Node, reason: StringName)
@warning_ignore_restore("unused_signal")
```

`@warning_ignore_start/restore` works in 4.7 (verify the minimum version). On older versions, put `@warning_ignore("unused_signal")` on each signal.

Rules:
- Emit from the system that knows the fact; listen wherever needed.
- Only for events that cross boundaries. Parent/child traffic never goes through the bus.
- **One-hop rule**: a bus callback does a final reaction (update UI, play a sound, set a flag). It does not emit another bus event. Chains become unreadable and can loop.
- **No ordering**: listeners run in connection order, which nobody controls. If B must run after A, a coordinator listens and calls A then B directly.
- **Traceability**: for game-flow events (level end, game over), require `source: Node` (and a reason). The listener can log it, or reject a source it doesn't expect.
- **Stateless**: the bus holds no `current_score`. State lives in an observable Resource or service (§6), which late listeners pull from.
- Past ~25 signals, namespace the bus.

### Namespacing (organizes the channels)
```gdscript
# event_bus.gd
extends Node
var combat := CombatEvents.new()
var ui := UIEvents.new()
```

```gdscript
# combat_events.gd
class_name CombatEvents extends RefCounted
@warning_ignore_start("unused_signal")
signal enemy_defeated(event: EnemyDefeatedEvent)
signal player_hit(amount: int)
```
Usage: `EventBus.combat.enemy_defeated.connect(...)`. Name the vars in snake_case (`combat`); avoid PascalCase vars that shadow class names. Use separate `class_name` files rather than inner classes, so the type is reusable in typed callbacks.

### Event objects (organize the payload)
When a signal carries several values or its data will grow, send one object:
```gdscript
class_name EnemyDefeatedEvent extends RefCounted
var enemy_id: StringName
var position: Vector2
var score: int
var source: Node  # may be freed by the time a deferred listener reads it

func _init(p_id: StringName, p_pos: Vector2, p_score: int, p_source: Node = null) -> void:
    enemy_id = p_id; position = p_pos; score = p_score; source = p_source
```
Adding a field later breaks no receiver. Copy plain values into the event (position, id) instead of making listeners read a node that may already be freed. Large projects use both: event objects over namespaced channels.

### Event relay
Generic components emit generic signals (`HealthComponent.died`). The owner or spawner translates them into game events with context (`EventBus.combat.enemy_defeated.emit(event)`). Components never touch the bus. That keeps them reusable, and keeps the bus free of every barrel's HP ticks.

### When not to use the bus
- Parent/child or same-scene traffic: use direct signals.
- Sequential, dependent logic: use a coordinator with direct calls.
- High-frequency data (per-frame positions, HP of 300 enemies): use local signals or polling by the one consumer.
- A jam game with three scenes: direct signals are enough.

Deeper: Godot 4 Best Practices ch.6 "Exploring the Event Bus Pattern" through "Namespacing versus Event Objects", PDF pp. 165–173

## 6. Observable Resources: state vs events

| Kind | Example | Channel |
|---|---|---|
| Action (verb), fleeting | jumped, boss died, bullet fired | Signal / EventBus |
| State (noun), persists, many readers | HP, ammo, master volume, upgrades | Observable Resource shared by reference |

```gdscript
class_name PlayerStats extends Resource
signal lives_changed(value: int)
@export var lives: int = 3:
    set(v):
        v = maxi(v, 0)
        if v == lives:
            return
        lives = v
        lives_changed.emit(lives)
        emit_changed()
```
- The same `.tres` given to Player, HUD and SaveService is one object in memory: every holder sees every change.
- The setter runs while the `.tres` loads. Emit only the Resource's own signals there. Never reach an autoload from a Resource setter: it runs in the editor and in tool code, where the autoload may not exist. If the change must go global, a coordinator relays it to the bus.
- Shared by default: a per-enemy stats Resource must be `duplicate()`d or marked `resource_local_to_scene`. See `godot-data-driven`.
- Guard against equal values. It stops redundant UI work and setter feedback loops.

When not: values that change every frame (positions, timers), where a signal per frame costs more than the one consumer polling. Also skip it for data only one node ever reads.

Deeper: Godot 4 Best Practices ch.6 "Observable Resources", PDF pp. 175–177

## 7. Autoloads

Autoloads are nodes added under `/root` beside the current scene. They survive `change_scene_to_*`, are reachable by name from any script, and exist once. Use them for **services**: EventBus, AudioService, SceneLoader/transitions, Settings, SaveService, input remapping, networking (the peer must outlive menu → level changes).

Never use them for **gameplay state or rules**: player HP, inventory, score, wave logic. That gives you a god object, hidden coupling, state you must reset by hand on "return to menu", and a design that breaks the day you add a second player. "Global access" does not mean "global storage".

Never put heavy content in them: big UI, particles, textures. It stays in memory for the whole session. Instance those per level.

Rules:
- **Init order (verified 4.7.2)**: all autoloads are instantiated first, in list order. In `_init`, autoloads further down are still `null`. Then all autoloads and the main scene enter the tree, and `_ready` runs in list order, then the main scene's. In an autoload's `_ready`, autoloads below it and the main scene are in the tree but **not ready** (`@onready` vars are null). An autoload may only use autoloads above it in `_ready`. It never uses any autoload in `_init`.
- Don't give a script a `class_name` equal to its autoload name; that is a parse error ("hides an autoload singleton").
- Autoloads inherit the root's pause behaviour. Transition, fade, pause-menu and UI-audio services need `process_mode = PROCESS_MODE_ALWAYS`.
- Use a scene (`.tscn`) autoload when the service needs child nodes (a CanvasLayer fade, pooled players). Otherwise a script.
- Keep each autoload to one responsibility. Expose methods, not mutable fields (`Settings.set_volume(bus, v)`).
- `change_scene_to_file()` removes the old scene **immediately** and adds the new one on a later frame (4.7.2: `get_tree()` is null in the old scene's code right after the call). Make it the last thing a scene does, or drive transitions from a SceneLoader autoload.

### Alternatives (ask "does this really need to be global?")
| Need | Use instead of an autoload |
|---|---|
| Stateless helpers / math | `static func` on a `class_name` script (no node, no registration, portable) |
| Constants (group names, layers) | `const` on a `class_name` script, not an autoload |
| Shared state between some objects | One `.tres` observable Resource via `@export` |
| Per-level / per-match state | Domain object owned by the level and injected |
| Batch op on many nodes | Group with a constant name |

Static funcs have no `self`, no lifecycle and no tree. Pass a node in, or use `Engine.get_main_loop() as SceneTree`. A `static var` is shared global state with all the autoload problems, and it is not thread-safe.

Service skeletons (SceneLoader, pooled AudioService, stateless SaveService), mocks and the full init-order detail: `references/autoloads-and-services.md`. Read it when you create or modify an autoload.

Deeper: Godot 4 Best Practices ch.5 "Exploring use cases for Autoloads" to "Choosing the right approach", PDF pp. 139–154

## 8. Dependency injection and service lookup

Prefer passing dependencies over looking them up. In order of preference:

```gdscript
# 1. Inspector injection (designer-wired, typed)
@export var stats: PlayerStats

# 2. Setup injection by the creator (spawner/level), BEFORE add_child
func setup(state: LevelState, audio: AudioPort) -> void:
    _state = state
    _audio = audio

# 3. Default-to-singleton with override (keeps call sites decoupled, mockable)
var audio: AudioPort  # typed to the contract, not to the autoload script
func _ready() -> void:
    if audio == null:
        audio = get_node_or_null(^"/root/Audio") as AudioPort
```
- The creator calls `setup()` **before** `add_child()`, so `_ready` already has everything.
- Writing the autoload name directly (`Audio.play(...)`) is a compile-time dependency: the script fails to parse in a project without that autoload. Leaf objects (pickups, props, components) emit signals and let the level wire them to services. Only coordinators talk to autoloads.
- For a contract, use an `@abstract` base class (4.5+). Both the real autoload script and the test fake extend it: see `references/autoloads-and-services.md`, section 8.
- Duck typing (`has_method(&"x")`) is the loose fallback for unrelated objects. It is untyped and fails silently on typos. Prefer `is SomeType`, a shared abstract base, or a component lookup.

Deeper: Godot 4 Best Practices ch.5 "Using dependency injection with Singletons", PDF pp. 147–150

## 9. Init order and races

- `_ready` runs children before parents, and siblings in tree order. The order is deterministic, but it changes when someone reorders the tree. Never depend on it implicitly.
- A signal emitted in `_ready` (or earlier) is lost if the listener hasn't connected yet.
- Fix with **push/pull**: keep the truth in a shared Resource or service. Listeners *pull* the current value in `_ready`, then subscribe for *pushes*:

```gdscript
# hud.gd
@export var stats: PlayerStats
func _ready() -> void:
    _show_lives(stats.lives)                  # pull
    stats.lives_changed.connect(_show_lives)  # push
```
- When a parent must touch fully-ready children, do it in the parent's `_ready` (children are ready by then). When a child needs its owner ready, `await owner.ready` is a single, explicit wait. Use it only if `owner.is_node_ready()` is false.
- Use `call_deferred` or `await get_tree().process_frame` only for one known ordering problem, never as a habit.

Deeper: Godot 4 Best Practices ch.6 "Architectural note: race conditions", PDF pp. 189–190

## 10. Notifications

Override `_notification(what: int)` for engine events without dedicated callbacks. Notifications are engine → this object. They are not broadcasts.

| Notification | Use |
|---|---|
| `NOTIFICATION_WM_CLOSE_REQUEST` | Desktop close button. With the default `auto_accept_quit = true` the app quits right after the handler, so a **synchronous** save works. For an async save or a confirm dialog, set `get_tree().auto_accept_quit = false` and call `get_tree().quit()` yourself |
| `NOTIFICATION_APPLICATION_PAUSED` | Mobile app backgrounded. Save here; the OS may kill the app without a close request |
| `NOTIFICATION_WM_GO_BACK_REQUEST` | Android back button (see `quit_on_go_back`) |
| `NOTIFICATION_APPLICATION_FOCUS_OUT` / `_IN` | Whole app lost focus: auto-pause, mute |
| `NOTIFICATION_WM_FOCUS_OUT` / `_IN` | This window lost focus (multi-window aware) |
| `NOTIFICATION_PAUSED` / `_UNPAUSED` | Pausable nodes when `SceneTree.paused` toggles |
| `NOTIFICATION_PREDELETE` | Last-chance cleanup. The object is still valid, but don't touch the tree; prefer `_exit_tree` |
| `NOTIFICATION_TRANSLATION_CHANGED` | Re-fetch localized strings built in code |

Close and focus notifications reach every node. Handle them in **one** place (a SaveService or App autoload), not in every scene.

Deeper: Godot 4 Best Practices ch.6 "Applying Notifications effectively", PDF pp. 173–175

## 11. Groups done safely

```gdscript
# core/groups.gd
class_name Groups
const ENEMY := &"enemy"
const DESTRUCTIBLE := &"destructible"
```
- Names are semantic (`destructible`, never `group1`), with one concept per group. Keep them as constants on a class, not as strings in code.
- Use groups for tagging and batch operations where a missing method doesn't matter: `get_tree().call_group(Groups.ENEMY, &"pause_ai")`.
- `call_group` is untyped. A typo in the method name does nothing, with no error (verified 4.7.2), and a node without the method is skipped. For anything that must not fail silently, use typed signals or the EventBus.
- To find "the player", `get_tree().get_first_node_in_group(Groups.PLAYER)` is acceptable in AI code. Injecting it is better.

## 12. Testing communication

- Assert that signals fire: connect a lambda that appends its arguments to an array, run the action, check the array.
- Mock services with fakes that extend the same `@abstract` base (or expose the same methods and signals). Inject them through `setup()` or the override var.
- Test that systems work when nobody listens (emitting with zero connections is safe) and when the listener connects late (push/pull).
- Test awaits with a bound timeout so a hung coroutine fails the test instead of hanging the runner.

Deeper: Godot 4 Best Practices ch.10 "Testing Command and Service patterns", PDF pp. 281–283
