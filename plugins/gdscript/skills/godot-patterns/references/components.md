# Components: deep reference

Read this when you build or wire entity components: the health/hurtbox/hitbox set, multi-component routing, component lookup, collision-layer plan, spawner relay, and the inheritance-vs-composition decision. The code compiles and was run on Godot 4.7.2.

## 1. Inheritance vs composition vs scene inheritance

| Need | Use |
|---|---|
| Variants of the same thing that differ in data (red/blue slime) | One scene + different Resource data |
| Variants that share a scene layout and override a little (base door → locked door) | Inherited scene or `extends` one level deep |
| A feature shared by unrelated types (HP on ship, asteroid, turret) | Component node |
| Mix-and-match features (moves? shoots? heals?) | Components. A 3-level class tree here forces copy-paste or a god base class full of `can_x` flags |

Keep inheritance at most one or two levels deep. Composition is the default for cross-cutting features.

## 2. The health/hurtbox/hitbox set

Naming used here: **Hitbox deals** damage, **Hurtbox receives** it. Some codebases use the opposite, so state the convention in the project.

```gdscript
# health_component.gd
class_name HealthComponent extends Node
signal health_changed(current: float, max_value: float)
signal damaged(amount: float, source: Node)
signal died

@export var max_health: float = 100.0
var current: float

static func of(entity: Node) -> HealthComponent:  # typed lookup, no magic method strings
    for c in entity.get_children():
        if c is HealthComponent:
            return c
    return null

func _ready() -> void:
    reset()

func reset() -> void:
    current = max_health
    health_changed.emit(current, max_health)

func is_dead() -> bool:
    return current <= 0.0

func take_damage(amount: float, source: Node = null) -> void:
    if is_dead() or amount <= 0.0:
        return
    current = maxf(current - amount, 0.0)
    damaged.emit(amount, source)
    health_changed.emit(current, max_health)
    if is_dead():
        died.emit()

func heal(amount: float) -> void:
    if is_dead() or amount <= 0.0:
        return
    current = minf(current + amount, max_health)
    health_changed.emit(current, max_health)
```

```gdscript
# hurtbox_component.gd: receives hits, knows nothing about health
class_name HurtboxComponent extends Area2D
signal hurt(amount: float, source: Node)
@export var damage_multiplier: float = 1.0  # armour plate 0.5, weak spot 2.0
@export var invulnerable: bool = false

func receive_hit(amount: float, source: Node) -> void:
    if invulnerable:
        return
    hurt.emit(amount * damage_multiplier, source)
```

```gdscript
# hitbox_component.gd: deals hits on overlap
class_name HitboxComponent extends Area2D
signal hit_landed(target: HurtboxComponent)
@export var damage: float = 10.0
@export var source: Node  # who to credit; defaults to the scene owner

func _ready() -> void:
    if source == null:
        source = owner
    area_entered.connect(_on_area_entered)

func _on_area_entered(area: Area2D) -> void:
    var hurtbox := area as HurtboxComponent
    if hurtbox == null:
        return
    hurtbox.receive_hit(damage, source)
    hit_landed.emit(hurtbox)  # a bullet connects this to its own queue_free/release
```

Entity wiring (the "motherboard"):
```gdscript
class_name BreakableCrate extends StaticBody2D
@onready var _health: HealthComponent = $HealthComponent
@onready var _hurtbox: HurtboxComponent = $HurtboxComponent

func _ready() -> void:
    _hurtbox.hurt.connect(_health.take_damage)
    _health.died.connect(_on_died)

func _on_died() -> void:
    _hurtbox.set_deferred(&"monitorable", false)  # stop taking hits this frame
    queue_free()  # or play death anim first
```

- Several hurtboxes can feed one health pool, each with its own multiplier.
- `owner` is set only for nodes saved in a scene. For components created in code, pass `source` explicitly.
- Death often happens inside a physics callback chain (hitbox → hurtbox → health → died). Anything that changes physics state in `_on_died` must be deferred.

## 3. Collision-layer plan (friend/foe without `if`)

| Layer | Who is on it | Who masks it |
|---|---|---|
| `player_hurt` | Player hurtbox | Enemy hitboxes, enemy bullets |
| `enemy_hurt` | Enemy hurtboxes | Player hitboxes, player bullets |
| `pickups` | Pickups | Player body |

Name the layers in Project Settings → Layer Names. Friendly fire becomes one mask checkbox, not new code. Filtering by layers happens in the physics engine before any script runs, so it is also the cheapest check.

## 4. Routing between components (armour → weak point example)

The entity decides the order. The components stay dumb:

```gdscript
class_name ArmoredTurret extends StaticBody2D
@onready var _plating: HurtboxComponent = $PlatingHurtbox   # always active
@onready var _core: HurtboxComponent = $CoreHurtbox         # monitorable = false in the scene
@onready var _armor: HealthComponent = $ArmorHealth         # second HealthComponent as an armour pool
@onready var _hull: HealthComponent = $HullHealth

func _ready() -> void:
    _plating.hurt.connect(_route_damage)
    _core.hurt.connect(_hull.take_damage)    # weak point hits the hull directly
    _armor.died.connect(_expose_core)
    _hull.died.connect(queue_free)

func _route_damage(amount: float, source: Node) -> void:
    if not _armor.is_dead():
        _armor.take_damage(amount, source)
    else:
        _hull.take_damage(amount * 0.25, source)  # plating still deflects most damage

func _expose_core() -> void:
    _core.set_deferred(&"monitorable", true)  # we are inside a physics callback chain
```
Reusing `HealthComponent` as the armour pool avoids a near-duplicate `ArmorComponent`. Create a dedicated component only when the rules differ (regen delay, damage types).

## 5. Relay to the rest of the game

- The entity or its spawner turns component signals into game events. The spawner connects to `HealthComponent.of(enemy).died` at spawn and emits its own `enemy_defeated(score)`. A level coordinator or the EventBus takes it from there (`godot-communication` §5).
- Components never call autoloads. A component that emits `EventBus.health_changed` floods the bus with every crate's HP and is no longer portable.

## 6. Traps

| Symptom | Cause | Fix |
|---|---|---|
| Death effects play twice | `take_damage` after death emits `died` again | Guard on `is_dead()` |
| Component null-ref in `_ready` | It reads siblings or the owner, which may not be ready | The owner wires components in its own `_ready` (children are ready by then) |
| Pooled enemy respawns with 0 HP | `_ready` doesn't run again | Pool calls `reset()` on acquire |
| Bullet hits two hurtboxes in one frame | Two overlaps reported before `queue_free` takes effect | Bullet sets a `_spent` flag, or disables its hitbox with `set_deferred(&"monitoring", false)` on the first hit |
| Hit ignored because "enemy" was misspelled | Group string + `has_method` duck typing | Typed cast (`as HurtboxComponent`) + layers |
| Five scripts to follow one laser shot | Over-decomposition | Merge components that always appear together |

## 7. When not to use components

- Only one entity type has the behaviour: put `var hp` in its script.
- One-off props and set pieces.
- "Future-proofing": build the generic component when the second user arrives, not before.
- Trade-offs to accept when you do use them: a denser scene tree, data passing through signals, and more files. Keep component folders tidy (`components/health/…`).

Deeper: Godot 4 Best Practices ch.8 "Understanding the limits of inheritance" to "Understanding decoupled interactions in action", PDF pp. 223–241
