---
name: "godot-patterns"
description: "Use when implementing or refactoring gameplay systems in Godot 4: state machines (FSM), strategies, components (health/hitbox/hurtbox), spawners/factories, object pools, builders and config objects, commands (input, AI, buffering, queues, undo/redo, replays). Triggers: giant match/if-elif, boolean flags, enum state, weapon types, deep inheritance, copy-pasted spawn code, bullet pooling, undo. Signals/EventBus/autoloads/services live in godot-communication."
---

# Godot 4 Gameplay Patterns

Use statically typed GDScript, targeting Godot 4.6+. Each pattern below has a skeleton, its Godot traps and a "when not" line. Read the "when not" line before reaching for the pattern.

How the pieces talk (signals, EventBus, relays, await lifetimes, autoloads, services such as pooled audio and scene loading) is covered in **`godot-communication`**. This skill doesn't repeat it.

## 0. Pick by smell

| Smell in the code | Pattern |
|---|---|
| `enum` + `match` in `_physics_process` past ~50 lines; 4+ `is_x` booleans checked together | **State** (§1) |
| Same action, swappable algorithm (weapons, movement styles, status effects, interactables) | **Strategy** (§2) |
| Adding one weapon/effect means edits in 4+ places ("shotgun surgery") | **Strategy** Resource (§2) |
| Same logic copy-pasted across unrelated entity types; `Boss extends Enemy extends Character` with features you don't want | **Component** (§3) |
| Same instantiate + parent + transform + setup code in 3+ scripts | **Factory/Spawner** (§4) |
| A `spawn()` with 5+ positional parameters | **Config object** (§4) |
| Profiler shows instantiate/free spikes for one short-lived type | **Pool** (§5) |
| Multi-step assembly of one complex object (procedural room, generated menu) | **Builder** (§6) |
| AI must drive the same actor as the player; buffering, replays, undo, turn queues | **Command** (§7) |
| Simple on/off, one-off object, one variant | Plain code. A `bool` is fine |

Default to YAGNI: write it plainly first. Extract the pattern when the second or third duplicate appears (DRY). A pattern that spreads one laser shot across five scripts is worse than the `match` it replaced.

## 1. State (node FSM)

Use for mutually exclusive modes of one entity, each with its own per-frame behaviour and exit rules (Idle/Run/Air, Patrol/Chase/Attack, boss phases).

```gdscript
class_name State extends Node
signal transition_requested(from: State, to: StringName)
@export var id: StringName  # empty -> node name in snake_case; survives renames
var actor: Node             # injected by the machine; cast in subclasses

func enter(_msg: Dictionary = {}) -> void: pass
func exit() -> void: pass
func update(_delta: float) -> void: pass
func physics_update(_delta: float) -> void: pass
func handle_input(_event: InputEvent) -> void: pass
```
The `StateMachine` node maps its `State` children by id, injects `actor`, forwards `_process`/`_physics_process`/`_unhandled_input` to the current state only, and performs every switch (`exit` old → set current → `enter` new). Full tested implementation: `references/state-machine.md`.

Rules:
- A state decides **when** to leave and emits `transition_requested(self, &"chase")`. The machine decides **how**. States never call siblings or `get_parent()`.
- In `physics_update`: guard clauses that decide a transition come first, each followed by `return`; then movement.
- Ignore requests where `from != current`. A delayed timer or await from an exited state must not switch states.

Godot traps:

| Symptom | Cause | Fix |
|---|---|---|
| `actor.sprite` is null in the first `enter()` | Machine `_ready` runs before the actor's (children first) | Start the machine on `actor.ready` (the reference does it) |
| Transition requested inside `enter()` is lost, or nests inside the running switch | `current` assigned after `enter()` (stale guard rejects it), or the switch is re-entered | Set `current` before `enter()`, and defer requests made during a switch (the reference does both; verified) |
| Two states act in the same frame | State scripts define `_process`/`_physics_process` | States only implement `update`/`physics_update` |
| Old state's delayed attack fires after leaving | `await` in a state outlives `exit()` | Generation token incremented in `exit()` (`godot-communication`, signals reference) |
| Rename of a state node breaks transitions | Transitions keyed by node name | Use the `id` export |

When not: a door (`is_open`), 5,000 particles (no node per particle), or 2–3 trivial states. A small `enum` + `match` with explicit `_enter_state()` is fine there; see the reference. `AnimationTree` state machines drive animation. They don't replace gameplay state.

Deeper: Godot 4 Best Practices ch.7 "Building a state machine in Godot using the State Pattern" and "Organizing state transitions", PDF pp. 195–205

## 2. Strategy (Resource)

Use when the caller always does "the same thing" and only the algorithm varies. Strategies don't manage their own transitions; the owner calls them.

```gdscript
# weapon_strategy.gd
@abstract class_name WeaponStrategy extends Resource  # @abstract: 4.5+
@export var cooldown: float = 0.25
@export var projectile: PackedScene
@abstract func fire(ctx: FireContext) -> void

# fire_context.gd: everything the strategy needs from the world
class_name FireContext extends RefCounted
var origin: Transform2D
var container: Node     # where projectiles go (never the shooter: it would drag them)
var shooter: Node2D

# spread_shot.gd
class_name SpreadShot extends WeaponStrategy
@export var count: int = 3
@export var spread_deg: float = 15.0
func fire(ctx: FireContext) -> void:
    for i in count:
        var t := 0.0 if count == 1 else float(i) / (count - 1) - 0.5
        var p := projectile.instantiate() as Node2D
        p.transform = ctx.origin.rotated_local(deg_to_rad(spread_deg) * t * 2.0)
        ctx.container.add_child(p)
```
The owner holds `@export var weapon: WeaponStrategy` and calls `weapon.fire(ctx)`. Swap at runtime by assigning another `.tres`.

Rules and traps:
- **Strategies are stateless.** One `.tres` is shared by every holder. Per-user runtime state (cooldown timer, ammo, charge) lives in the owner, or `duplicate()` the Resource on equip.
- A Resource has no tree access (`add_child`, `get_tree`). Pass a context object, not five parameters.
- If variants differ only in numbers, that's data: one Resource class with fields, no subclasses (`godot-data-driven`).
- If the strategy needs `_process`, signals of its own or child nodes, it's a component (§3), not a Resource.
- Pre-4.5: a base with `push_error("override fire()")` instead of `@abstract`.

When not: one weapon; behaviours that change by internal rules over time (that is State).

Other good fits: status effects, interactables (`InteractStrategy` on door/chest/switch), AI targeting policies, damage formulas.

Deeper: Godot 4 Best Practices ch.7 "Using the Strategy Pattern for gameplay variation" to "Injecting strategies into the Player", PDF pp. 205–215

## 3. Components (composition)

Use when several unrelated entity types share a behaviour (HP on player, enemy, crate, turret).

- Small single-purpose nodes: `HealthComponent` (data + rules, `extends Node`), `HurtboxComponent` (`Area2D` that **receives** hits), `HitboxComponent` (`Area2D` that **deals** them), `MovementComponent`, `ShooterComponent`.
- The entity root is a thin "motherboard": it holds `@export`/`@onready` references and wires component signals in `_ready`. It routes and decides (armour pool first, then hull).
- Components never assume their parent's type, never call `get_parent()`, and never emit on the EventBus. The owner or spawner relays (`godot-communication` §5 "Event relay").
- Find components on *another* entity by type, not by magic string: `area as HurtboxComponent`, or a static `HealthComponent.of(node)` helper. Not `is_in_group("enemy") and has_method("damage")`.
- Friend/foe filtering belongs to collision layers and masks (player hurtbox on layer `player_hurt`, enemy hitboxes mask it). Avoid `if` checks in scripts.

```gdscript
class_name HealthComponent extends Node
signal health_changed(current: float, max_value: float)
signal died
@export var max_health: float = 100.0
var current: float

func _ready() -> void:
    reset()

func reset() -> void:  # pools call this on reuse
    current = max_health
    health_changed.emit(current, max_health)

func take_damage(amount: float, _source: Node = null) -> void:
    if current <= 0.0 or amount <= 0.0:
        return  # dead entities don't die twice
    current = maxf(current - amount, 0.0)
    health_changed.emit(current, max_health)
    if current == 0.0:
        died.emit()
```
Wiring in the entity: `hurtbox.hurt.connect(health.take_damage)` (the hurtbox emits `hurt(amount, source)`), then `health.died.connect(_on_died)`. A hitbox finds its target with `area as HurtboxComponent`.

Traps: `died` emitted on every hit after death (guard as above); components that query their owner in `_ready` (the owner isn't ready yet; let the owner push in); a component per trivial line of code.

When not: a single entity type (put `var hp` in its script); one-off props; a feature you "might need later".

Full Health/Hurtbox/Hitbox set, an armour→weak-point routing example, component lookup, layer plan and spawner relay: `references/components.md`.

Deeper: Godot 4 Best Practices ch.8 "Designing modular components" to "Handling communication between components and systems", PDF pp. 225–241

## 4. Factory / Spawner + config object

Use when 3+ places create the same kind of thing, or creation needs routing, injection or randomization.

```gdscript
class_name Spawner extends Marker2D
signal spawning(product: Node2D)  # before add_child: set properties only
@export var scene: PackedScene
@export var container: Node              # empty -> current scene; never self

func spawn(config: Variant = null, deferred: bool = false) -> Node2D:
    if scene == null:
        push_error("%s: no scene assigned" % name)
        return null
    var node := scene.instantiate() as Node2D
    var parent: Node = container if container else get_tree().current_scene
    var parent_xf := (parent as Node2D).global_transform if parent is Node2D else Transform2D.IDENTITY
    node.transform = parent_xf.affine_inverse() * global_transform  # place BEFORE adding
    if config != null and node.has_method(&"setup"):  # generic spawner: duck-typed on purpose
        node.call(&"setup", config)                   # inject BEFORE _ready
    spawning.emit(node)
    if deferred:
        parent.add_child.call_deferred(node)   # from physics callbacks
    else:
        parent.add_child(node)
    return node
```
Config object instead of telescoping arguments: `class_name ProjectileConfig extends RefCounted` (or a Resource for designer presets) with defaulted fields. The caller overrides two fields and passes one object.

Traps:
- Spawning **as a child of the shooter/spawner** drags every product along when it moves. Use a world container.
- Set the **local** transform before adding, as above. After `add_child`, `_ready` has already run at the origin, so anything it spawns or reads from `global_position` is wrong. `global_*` before adding is worse: 2D silently treats it as local, so the parent's offset is added, and 3D errors (tested 4.7.2).
- `deferred = true` returns a node that is **not** in the tree yet: `@onready` vars are null and `get_tree()` is null. Configure it; don't query it.
- Spawning a physics body from `body_entered`/`area_entered` must be deferred ("flushing queries" error).
- Hardcoded `preload("res://...")` per type: use `@export var scene: PackedScene` or `Array[PackedScene]`. Inspector references survive moves via UID.

When not: one boss spawned once; one script that always spawns one scene as its own child. Two lines of `instantiate()` don't need a class.

Spawner with placement components (radial/area randomizers), relay of spawned entities' signals, and a decision table: `references/spawning-and-pooling.md`.

Deeper: Godot 4 Best Practices ch.9 "Implementing a Factory Pattern for Nodes" and "Procedural generation with Factories", PDF pp. 247–252, 258–261

## 5. Pooling

Use only when profiling shows churn: hundreds of bullets or hit effects per second, or frame spikes on `instantiate()`/`queue_free()`. Otherwise plain spawning is fine. Pooling bugs (stale state, double release) cost more than the churn.

Rules:
- Prewarm at level load, cap the size, and decide what happens when it's exhausted (grow up to the cap, steal the oldest, or drop).
- Pooled nodes stay in the tree under the pool. Deactivate with `process_mode = PROCESS_MODE_DISABLED` plus `hide()`: physics bodies are removed from the space (`CollisionObject.disable_mode = REMOVE`). Activate with `PROCESS_MODE_INHERIT` plus `show()`.
- From physics callbacks, toggle with `set_deferred(&"process_mode", ...)`.
- `_ready` runs **once**. Per-use init goes in `on_acquired()`, cleanup in `on_released()`: reset HP, kill tweens, stop timers, bump the generation token, reset velocity. Call `reset_physics_interpolation()` after teleporting if physics interpolation is on.
- Connect signals once at creation, never on acquire ("already connected"). Subscriptions to autoloads go on acquire/release.
- Never `queue_free()` a pooled node; route its "I'm done" through `pool.release(self)` or a `finished` signal. Guard double release.

Full `NodePool` (tested): `references/spawning-and-pooling.md`. Audio voice pools: `godot-communication` (autoloads and services reference).

## 6. Builder (and when a config object is enough)

Use for one object assembled in many optional steps: a procedural room, a generated dialog or tooltip, a debug menu.

```gdscript
class_name DialogBuilder extends RefCounted
var _root := VBoxContainer.new()

func title(text: String) -> DialogBuilder:
    var l := Label.new()
    l.text = text
    _root.add_child(l)
    return self

func button(text: String, on_press: Callable) -> DialogBuilder:
    var b := Button.new()
    b.text = text
    b.pressed.connect(on_press)
    _root.add_child(b)
    return self

func build() -> Control:
    var out := _root
    _root = null
    return out

func _notification(what: int) -> void:
    if what == NOTIFICATION_PREDELETE and is_instance_valid(_root):
        _root.free()  # never built: Nodes aren't ref-counted, so they would leak
```
Usage: `add_child(DialogBuilder.new().title("Merchant").button("Buy potion", _buy_potion).build())`. Wrap multi-line chains in parentheses, or end lines with `\`.

- Static, designer-owned UI is built in the editor. Builders are for content that is data-dependent at runtime. Inside a builder, instance small `.tscn` parts instead of styling nodes in code.
- `@tool` previews: nodes added in the editor without `owner` set are not saved into the scene, which is what you want for previews. Clear old preview children before rebuilding.

When not: an object with 1–2 settings (use a factory or config object); a static menu.

Deeper: Godot 4 Best Practices ch.9 "Building complex objects with the Builder Pattern" and "Choosing between Factory and Builder patterns", PDF pp. 252–256, 261–263

## 7. Command

Encapsulate an action as a `RefCounted` object with `execute(actor)` and optionally `undo(actor)`. Input sources (player, AI, network, replay) produce commands; the actor runs them, blind to the source.

```gdscript
# command.gd
class_name Command extends RefCounted
func execute(_actor: Node) -> void: pass  # may await; then callers must await it
func undo(_actor: Node) -> void: pass
func is_undoable() -> bool: return false

# move_command.gd
class_name MoveCommand extends Command
var direction: Vector2
func _init(dir: Vector2) -> void: direction = dir
func execute(actor: Node) -> void:
    var ship := actor as Ship  # typed receiver, not has_method
    if ship:
        ship.steer(direction)
```

Rules:
- **Action games**: produce and execute commands in the same `_physics_process`, in parallel (move + shoot in one tick). No queue, no awaits.
- **Turn-based/puzzle**: a queue that awaits each command. Check `is_instance_valid(actor)` before every execute, give every awaited command a timeout or guaranteed exit (a freed tween never finishes), and cap history (`MAX_HISTORY`).
- **Undo/redo**: two stacks. `execute` caches what undo needs (the start position, in the **same space** it restores). A new command clears the redo stack.
- **Replays**: record `(physics_tick, command data)`. Playback is only exact with fixed-tick simulation, seeded RNG and no wall-clock reads. Engine physics isn't guaranteed deterministic, so also keep periodic state snapshots.
- **Buffering**: timestamp commands and drop ones older than the window (~0.1–0.2 s).

When not: remapping alone. `InputMap` plus rebinding already decouples keys from actions, so don't build commands just for that. Also skip commands for one player-only actor with no AI, replay or undo.

Queue, undo manager, AI source, replay recorder and tests: `references/commands.md`.

Deeper: Godot 4 Best Practices ch.10 "Understanding the Command Pattern" to "Action games: Parallel execution", PDF pp. 267–278

## 8. Testing

Domain objects, strategies, commands and components are testable without full scenes. Build them with fakes (a `RefCounted` or minimal node with the same methods, or a subclass of the `@abstract` contract), run the action, and assert the result. Test failure paths too: freed actor, missing scene, empty pool, empty undo stack, a command that never finishes (it must time out). Headless runner setup: `godot-gdscript-headless-testing` (awesome-gamedev-agent-skills).

Deeper: Godot 4 Best Practices ch.10 "Testing Command and Service patterns", PDF pp. 281–283
