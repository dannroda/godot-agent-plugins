# SOLID applied to Godot nodes, scenes and scripts

Read this when designing a class hierarchy or a set of components, or when refactoring a script that keeps growing.

Mental model: a script with `class_name` is a class and a contract (registered globally, typable, usable in `is`). A scene is composition plus encapsulation: a prefab built from single-purpose parts whose internals stay hidden behind the root script. Godot coupling and bloat problems are ordinary OOP problems, and the fixes map onto nodes, signals and Resources.

These are heuristics. Apply them where they pay: long-lived projects, teams, or a system with three or more variants. In a jam, a 150-line player script is fine.

## Summary table

| Principle | Godot mechanism | Smell in a Godot project | Fix |
|---|---|---|---|
| **S** one reason to change | Child component nodes, separate RefCounted models, signals for side effects | Root script holds `@onready` refs to UI labels, audio players and save code; `_physics_process` is one 60-line block; `GameManager` does score + UI + saving + scene changes | Dispatcher `_physics_process`; emit state signals; extract components; split the manager into model, service and view |
| **O** extend without editing | Subclass + override, strategy Resources, new `.tres`, new component | `match enemy_type` or `if body.name == "Archer"` in the *consumer*; adding content means editing Player/Manager | Polymorphic method on a base type; `@export var behavior: Strategy`; content as data |
| **L** subtypes honor the contract | Static typing makes the parser check override signatures | Override that `pass`es or errors ("not supported"); subclass stops emitting the base's signals; variant scene lacks a node the base script uses; callers test `is SpecialCase` to work around it | Same types, units, signals and side effects; new needs → new methods; `super()` in lifecycle overrides |
| **I** small contracts | Minimal base classes, capability components, focused signals, `@abstract` (4.5+) | Base `Entity` with `fly()`, `swim()`, `cast()` stubs; signal `updated(data: Dictionary)`; a component that needs five specific siblings | Base holds only universal state and verbs; capabilities are optional child nodes; one signal per fact |
| **D** depend on abstractions | Signals, typed `@export` injection, `setup()` injection, event bus / services | `get_node("../Player")`, `get_parent().method()`, `/root/Main/HUD` paths; an enemy writes `player.health -= 5`; scene can't run with F6 | Signal up; inject down; cross-tree via bus/service; call the owner's API, never its fields |

## S: Single Responsibility

- The root script of an actor **coordinates**. It reads intent, calls its components and emits state. Feedback (UI, sound, VFX, saving) listens to signals.
- Treat `_process`/`_physics_process` as a dispatcher of named steps. Each step is one small function.
- Split by **reason to change**, not by line count. Input mapping, movement feel, health rules and HUD look change for different reasons and often get changed by different people.
- Merge conflicts on one huge `.gd` or `.tscn` are an SRP signal in teams.
- A child node with a script owns its details. The parent calls `footsteps.play_step()`, not pitch randomization code.

```gdscript
func _physics_process(delta: float) -> void:
	var intent := _read_intent()
	_steer(intent, delta)
	_apply_knockback(delta)
	move_and_slide()
	_publish_state()  # emits signals only when values changed
```

## O: Open/Closed

- Consumers call one verb on a base type or strategy. New variants are new files.
- The ranking of extension tools, cheapest first: a new `.tres` (numbers) → a new strategy Resource subclass (algorithm) → a new component (capability) → a new subclass (identity).
- `match` on an enum **inside** the owner (an FSM's own states) is fine. The smell is a consumer switching on the producer's concrete type.

```gdscript
@abstract class_name HitEffect extends Resource  # @abstract: 4.5+
@abstract func apply(target: Node, source: Node) -> void
```

```gdscript
# weapon.gd: closed for modification
@export var on_hit: Array[HitEffect] = []
func _resolve_hit(target: Node) -> void:
	for effect in on_hit:
		effect.apply(target, self)
```
`@abstract` keeps the base out of the "New Resource" dialog and makes a subclass that forgets `apply()` a parse error.

## L: Liskov Substitution

What GDScript enforces (tested 4.7.2): an override with a different return type, a different parameter list, or an untyped override that returns the wrong type is a **parse error** ("function signature doesn't match the parent"). Extra parameters **with defaults** are allowed.

What it does not enforce, so you must:
- **Semantics**: units, ranges, and "returns -1 for none" conventions. A subclass that returns something technically valid but different breaks callers.
- **Lifecycle chaining**: overriding `_ready`/`_process`/`_physics_process` replaces the base version. Godot 4 doesn't call the parent automatically (tested 4.7.2). Call `super()` unless replacement is the intent, and say so in a comment when it is.
- **Signals**: if the base emits `died`, every subclass path that ends the entity must emit it.
- **Scene structure**: if the base script uses `%Hurtbox`, every inherited or variant scene must have it. Validate with `_get_configuration_warnings()` in a `@tool` base.
- **Duck-typed calls** (`has_method`, `call`, `call_group`) are invisible to the parser. Keep them rare and documented.

Smell: callers that write `if enemy is Boss: ... else: ...` to compensate for a subclass that behaves differently.

## I: Interface Segregation

GDScript has no interfaces. Use, in order of strictness:

| Mechanism | Check | Use when |
|---|---|---|
| Base class (`is Damageable`) | Parser + runtime type | Things truly share an identity |
| Component node (`HealthComponent` child) | Find via exported ref or `get_node_or_null(^"Health") as HealthComponent` | Capability shared across unrelated identities |
| Group tag + method (`is_in_group(&"interactable")`) | Runtime only | Loose, designer-assigned categories |
| `has_method(&"interact")` | Runtime only, no rename safety | Last resort, cross-plugin boundaries |

- Base classes contain only universal state and verbs (for example health, `take_damage()`, `die()`). Attack styles live in subclasses or strategies.
- Signals carry one fact each with typed args: `health_changed(current: int, max_value: int)`, not `stats_updated(data: Dictionary)`.
- A component asks for the fewest collaborators possible, ideally none (it emits; the actor root wires it).

## D: Dependency Inversion

- **Local** dependency: a typed `@export` slot, filled in the Inspector.
  - Type the slot to the narrowest *base* that offers the needed API. A concrete class gives autocomplete and safety but rejects alternative implementations.
  - A `@tool` script can implement `_get_configuration_warnings()` to flag an empty slot in the Scene dock. `@tool` makes the whole script run in the editor, so guard gameplay code with `if Engine.is_editor_hint(): return`, and call `update_configuration_warnings()` from the slot's setter.
- **Runtime-created** dependency: the spawner calls `setup(deps)` before `add_child`.
- **Upward/outward**: emit signals. The listener depends on the emitter, not the reverse.
- **Global**: an autoload event bus (abstraction) instead of calling a concrete `AudioManager` from leaf code. Let services be swappable for tests. Details in godot-communication.
- Ask the owner to change its state (`target.take_damage(5)`), never write its fields.

## Combined example: a hit system that never needs editing

```gdscript
class_name Hurtbox extends Area2D
signal hit_received(amount: int, source: Node)

func receive_hit(amount: int, source: Node) -> void:
	hit_received.emit(amount, source)
```
```gdscript
# melee_swing.gd: knows only the abstraction
@export var hit_area: Area2D
@export var actor: Node2D  # who gets credit for the hit
@export var damage: int = 3

func strike() -> void:
	for area in hit_area.get_overlapping_areas():
		var hurtbox := area as Hurtbox
		if hurtbox:
			hurtbox.receive_hit(damage, actor)
```
Any actor, crate or destructible wall becomes hittable by adding a `Hurtbox` and connecting `hit_received` to its own health logic.
- S: the swing doesn't do health math.
- O: new hittable things don't touch the swing.
- I: `Hurtbox` exposes one verb.
- D: both sides depend on `Hurtbox`, not on each other.

## When not to apply

- Prototypes and jams: hard-code, find the fun, then extract when the same behavior is needed a second or third time.
- One-off bosses or set pieces: one dedicated script is simpler than a component kit.
- Every layer of indirection costs readability. If a reader needs four files to follow one hit, collapse something.

Deeper: Godot 4 Best Practices ch.1 "Applying SOLID Principles in Godot", PDF pp. 28–54: SRP pp. 29–38, OCP pp. 38–42, LSP pp. 42–45, ISP pp. 45–48, DIP pp. 48–51, combined example pp. 51–53
