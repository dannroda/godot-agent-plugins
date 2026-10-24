# Spawning, pooling and building: deep reference

Read this when you write a spawner/factory, add placement randomizers, pool short-lived nodes, or assemble objects with a builder. The code compiles and was run on Godot 4.7.2.

## 1. Direct spawn vs factory

| Factor | Direct `instantiate()` in the caller | Factory / Spawner |
|---|---|---|
| Setup | 1–2 lines | Multi-step: inject data, randomize, route to a container |
| Callers | One script | Many scripts spawn the same kind of thing |
| Variety | Always the same scene | Picked from data, weights, or an exported array |
| Hierarchy | Child of the caller is correct | Must go to a world container |
| Knowledge | Caller knows how the product works | Caller only needs the finished product |

Start direct. Extract a spawner when the second or third copy appears.

## 2. Spawner with placement hooks

```gdscript
class_name Spawner extends Marker2D
signal spawning(product: Node2D)  # emitted BEFORE add_child: set properties only

@export var scenes: Array[PackedScene] = []
@export var container: Node              # world container; empty -> current scene

func spawn(config: Variant = null, deferred: bool = false) -> Node2D:
    if scenes.is_empty():
        push_error("%s: no scenes assigned" % name)
        return null
    var node := scenes.pick_random().instantiate() as Node2D
    var parent: Node = container if container else get_tree().current_scene
    var parent_xf := (parent as Node2D).global_transform if parent is Node2D else Transform2D.IDENTITY
    node.transform = parent_xf.affine_inverse() * global_transform
    if config != null and node.has_method(&"setup"):
        node.call(&"setup", config)
    spawning.emit(node)
    if deferred:
        parent.add_child.call_deferred(node)
    else:
        parent.add_child(node)
    return node
```

A placement component is composed next to the spawner and edits each product before it enters the tree:
```gdscript
class_name RingScatter extends Node
@export var spawner: Spawner
@export var min_radius: float = 100.0
@export var max_radius: float = 300.0

func _ready() -> void:
    spawner.spawning.connect(_place)

func _place(product: Node2D) -> void:
    var offset := Vector2.from_angle(randf() * TAU) * randf_range(min_radius, max_radius)
    product.position += offset  # parent-local; fine for unrotated containers
```
A `Timer` whose `timeout` is connected to `spawner.spawn` gives waves without a manager script. Stop decomposing there: a timer, spawner and randomizer per hazard is fine, but five factories for one bullet is not.

Relaying the products' events (score, wave cleared): the spawner connects to each product's signals right after creating it, and emits its own coarser signal (`godot-communication` §5 "Event relay").

## 3. Config (parameter) object

Use one when a factory needs many optional knobs: speed, colour, scale, damage, pierce.

```gdscript
class_name ProjectileConfig extends RefCounted
var speed: float = 500.0
var damage: float = 10.0
var tint: Color = Color.WHITE
var scale: float = 1.0
var pierce: int = 0
```
- The caller overrides only what differs: `var c := ProjectileConfig.new(); c.damage = 50.0; spawner.spawn(c)`.
- Use `extends Resource` + `@export` fields instead when designers keep presets as `.tres`. Then remember that presets are shared: never mutate one at runtime, `duplicate()` first.
- This is the middle ground between a bare factory and a builder. It covers most projectile and VFX variation.

## 4. NodePool

```gdscript
class_name NodePool extends Node
## Pooled nodes live under this plain Node, so their local transform == global.
@export var scene: PackedScene
@export var prewarm: int = 32
@export var max_size: int = 256
@export var steal_when_full: bool = true

var _free: Array[Node] = []
var _active: Array[Node] = []  # oldest first, for stealing

func _ready() -> void:
    for i in prewarm:
        _free.append(_create())

func acquire() -> Node:
    var n: Node
    if not _free.is_empty():
        n = _free.pop_back()
    elif _free.size() + _active.size() < max_size:
        n = _create()
    elif steal_when_full and not _active.is_empty():
        n = _active.pop_front()
        _deactivate(n)
    else:
        return null
    _active.append(n)
    n.set_deferred(&"process_mode", Node.PROCESS_MODE_INHERIT)  # safe inside physics callbacks
    if &"visible" in n:
        n.set(&"visible", true)
    if n.has_method(&"on_acquired"):
        n.call(&"on_acquired")
    return n

func release(n: Node) -> void:
    var i := _active.find(n)
    if i == -1:
        return  # double release or not ours
    _active.remove_at(i)
    _deactivate(n)
    _free.append(n)

func _create() -> Node:
    var n := scene.instantiate()
    if n.has_signal(&"finished"):            # connect ONCE, at creation
        n.connect(&"finished", release.bind(n))
    add_child(n)                             # _ready runs here, once in the node's life
    _deactivate(n)
    return n

func _deactivate(n: Node) -> void:
    n.set_deferred(&"process_mode", Node.PROCESS_MODE_DISABLED)  # also removes physics bodies
    if &"visible" in n:
        n.set(&"visible", false)
    if n.has_method(&"on_released"):
        n.call(&"on_released")
```

A pooled product:
```gdscript
class_name PooledBullet extends Area2D
signal finished
@export var speed: float = 600.0
var _velocity := Vector2.ZERO
var _life := 0.0
var _spent := false

func _ready() -> void:  # once
    area_entered.connect(_on_area_entered)

func on_acquired() -> void:  # every reuse: reset ALL per-use state
    _spent = false
    _life = 2.0

func on_released() -> void:
    _velocity = Vector2.ZERO

func launch(xf: Transform2D) -> void:
    global_transform = xf
    _velocity = xf.x * speed
    reset_physics_interpolation()  # no streak from the old position

func _physics_process(delta: float) -> void:
    position += _velocity * delta
    _life -= delta
    if _life <= 0.0:
        finished.emit()

func _on_area_entered(_area: Area2D) -> void:
    if _spent:
        return  # two overlaps in one frame
    _spent = true
    finished.emit()
```
Usage: `var b := pool.acquire() as PooledBullet; if b: b.launch(muzzle.global_transform)`.

Pool traps:

| Symptom | Cause | Fix |
|---|---|---|
| Reused enemy has 0 HP / old target | `_ready` doesn't rerun | Reset everything in `on_acquired` (components' `reset()`) |
| "Signal already connected" | Connecting in `on_acquired` | Connect once in `_create` / `_ready` |
| Ghost hits from inactive bullets | Only hidden, still monitoring | `PROCESS_MODE_DISABLED` (removes from physics via `disable_mode`) |
| "Flushing queries" error on release | Toggling physics state inside `area_entered` | `set_deferred` (as above) |
| Old coroutine fires on the reused node | `await` from the previous life resumes | Generation token bumped in `on_released` |
| Node freed while pooled | Product called `queue_free()` | Products only emit `finished`. Never free a pooled node |
| Stale tween keeps moving it | Tween from the previous life | Kill tweens in `on_released` |

When not to pool: anything spawned a few times per second, big unique scenes, or before a profiler has shown a problem.

## 5. Builder

```gdscript
class_name DialogBuilder extends RefCounted
var _root: VBoxContainer

func _init() -> void:
    _root = VBoxContainer.new()
    _root.add_theme_constant_override(&"separation", 8)

func title(text: String) -> DialogBuilder:
    var l := Label.new()
    l.text = text
    _root.add_child(l)
    return self

func button(text: String, on_press: Callable, disabled: bool = false) -> DialogBuilder:
    var b := Button.new()
    b.text = text
    b.disabled = disabled
    b.pressed.connect(on_press)
    _root.add_child(b)
    return self

func part(scene: PackedScene) -> DialogBuilder:  # prefer designer-made pieces over code styling
    _root.add_child(scene.instantiate())
    return self

func build() -> Control:
    var out := _root
    _root = null
    return out

func _notification(what: int) -> void:
    if what == NOTIFICATION_PREDELETE and is_instance_valid(_root):
        _root.free()  # abandoned before build(): free the orphan nodes
```

Editor preview with `@tool` (an `@export_tool_button` button in the Inspector, 4.4+):
```gdscript
@tool
extends Control
@export_tool_button("Rebuild preview") var rebuild_action: Callable = _rebuild

func _rebuild() -> void:
    for c in get_children():
        c.queue_free()
    add_child((DialogBuilder.new()
        .title("Merchant")
        .button("Buy potion", func() -> void: pass)
        .build()))
    # owner not set -> preview nodes are not saved into the .tscn (intended)
```
- `Node.new()` and `add_child` in a builder bypass the editor: no theme preview while authoring, more code to maintain. Builders pay off for runtime, data-dependent content (tooltips per item, procedural rooms, debug menus).
- Builders can build data too (a `Dictionary` level description, then a factory instantiates it). Keeping "what" and "how" separate makes seeds reproducible.

## 6. Factory vs builder vs config object

| Need | Pick |
|---|---|
| Many mostly-identical objects, one call | Factory |
| Same, plus a few optional knobs per call | Factory + config object |
| One object, many optional parts or nested children, order matters | Builder |
| 1–2 properties | Neither: instantiate and set them |

"100 of something now" → factory. "One thing in ten steps" → builder.

Deeper: Godot 4 Best Practices ch.9 "Using Factory and Builder Patterns" (whole chapter), PDF pp. 246–264; ch.10 "Applying the Service Pattern to cross-cutting systems" (audio pool), PDF pp. 278–281
