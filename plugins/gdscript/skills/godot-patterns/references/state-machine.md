# State machines: deep reference

Read this when you implement or debug an entity FSM: the full machine, a concrete state, small enum FSMs, hierarchical and pushdown variants, and debugging. The code compiles and was run on Godot 4.7.2.

## 1. Node FSM: full implementation

```gdscript
# state.gd
class_name State extends Node
signal transition_requested(from: State, to: StringName)

@export var id: StringName  # empty -> node name in snake_case
var actor: Node             # injected by the StateMachine before the first enter()
var machine: StateMachine

func enter(_msg: Dictionary = {}) -> void: pass
func exit() -> void: pass
func update(_delta: float) -> void: pass
func physics_update(_delta: float) -> void: pass
func handle_input(_event: InputEvent) -> void: pass

func request(to: StringName, _msg: Dictionary = {}) -> void:
    transition_requested.emit(self, to)
```

```gdscript
# state_machine.gd
class_name StateMachine extends Node
signal state_changed(from: StringName, to: StringName)

@export var actor: Node             # usually the entity root; required
@export var initial_state: State
var current: State
var _states: Dictionary[StringName, State] = {}
var _transitioning := false

func _ready() -> void:
    for child in get_children():
        var s := child as State
        if s == null:
            continue
        var key: StringName = s.id if s.id != &"" else StringName(String(s.name).to_snake_case())
        _states[key] = s
        s.actor = actor
        s.machine = self
        s.transition_requested.connect(_on_transition_requested)
    # Children are ready before their parent: wait for the actor so its @onready vars exist.
    if actor.is_node_ready():
        _start()
    else:
        actor.ready.connect(_start, CONNECT_ONE_SHOT)

func _start() -> void:
    _transitioning = true
    current = initial_state
    current.enter()
    _transitioning = false
    state_changed.emit(&"", current.name)

func _process(delta: float) -> void:
    if current:
        current.update(delta)

func _physics_process(delta: float) -> void:
    if current:
        current.physics_update(delta)

func _unhandled_input(event: InputEvent) -> void:
    if current:
        current.handle_input(event)

func _on_transition_requested(from: State, to: StringName) -> void:
    if _transitioning:  # requested from inside enter()/exit(): re-check after this switch
        _on_transition_requested.call_deferred(from, to)
        return
    if from != current:
        return  # stale request (old timer/await/signal of an exited state)
    transition_to(to)

func transition_to(to: StringName, msg: Dictionary = {}) -> void:
    if _transitioning:
        transition_to.call_deferred(to, msg)  # external call during a switch
        return
    var next: State = _states.get(to)
    if next == null:
        push_error("%s: unknown state '%s'" % [actor.name, to])
        return
    _transitioning = true
    var prev := current
    if prev:
        prev.exit()
    current = next  # BEFORE enter(), so requests made in enter() pass the stale guard
    current.enter(msg)
    _transitioning = false
    state_changed.emit(prev.name if prev else &"", current.name)
```

Scene layout:
```
Enemy (CharacterBody2D, enemy.gd)
├── Sprite2D, CollisionShape2D, ...
└── StateMachine (actor = Enemy, initial_state = Patrol)
    ├── Patrol (patrol_state.gd)
    ├── Chase  (chase_state.gd)
    └── Attack (attack_state.gd)
```

## 2. Concrete state

```gdscript
class_name ChaseState extends State
@export var speed: float = 150.0
@export var attack_range: float = 48.0
@export var give_up_range: float = 600.0
var _target: Node2D

func enter(_msg: Dictionary = {}) -> void:
    _target = get_tree().get_first_node_in_group(Groups.PLAYER) as Node2D

func physics_update(_delta: float) -> void:
    var body := actor as CharacterBody2D
    # 1. Transition guards first, each followed by return.
    if not is_instance_valid(_target):
        request(&"patrol")
        return
    var dist := body.global_position.distance_to(_target.global_position)
    if dist <= attack_range:
        request(&"attack")
        return
    if dist > give_up_range:
        request(&"patrol")
        return
    # 2. Then behaviour.
    body.velocity = body.global_position.direction_to(_target.global_position) * speed
    body.move_and_slide()
```

- The state holds only the parameters of its own behaviour (`@export` tunables). Shared entity data (HP, stats) lives on the actor or its components.
- `msg` passes context into a state: `transition_to(&"stunned", {"time": 1.5})`.
- Timed states: start a timer in `enter`, stop it in `exit`, or use a generation token for awaits (`godot-communication`, signals reference). Never let a stale callback call `request()` without the `from != current` guard.

## 3. Transition organization

| Approach | Use when |
|---|---|
| Each state decides its exits (above) | Default. Each file reads top-to-bottom |
| Global interrupts in the machine/actor (`health.died` → `transition_to(&"dead")` from any state) | Events that preempt every state: death, stun, cutscene |
| Transition table (`Dictionary[StringName, Array[StringName]]` of allowed moves) checked in `transition_to` | Designers edit the graph, or illegal transitions must assert |

Global interrupts are wired by the actor (`health.died.connect(machine.transition_to.bind(&"dead", {}))`). Writing "if dead" in every state is the boolean soup coming back.

## 4. Small enum FSM (when nodes are overkill)

For 2–4 trivial states with no per-state tunables:

```gdscript
enum Mode { IDLE, OPEN, CLOSING }
var _mode := Mode.IDLE

func _set_mode(m: Mode) -> void:
    if m == _mode:
        return
    match _mode:          # exit
        Mode.OPEN: _light.hide()
    _mode = m
    match _mode:          # enter
        Mode.OPEN: _light.show()
        Mode.CLOSING: _anim.play(&"close")

func _physics_process(_delta: float) -> void:
    match _mode:
        Mode.CLOSING:
            if not _anim.is_playing():
                _set_mode(Mode.IDLE)
```
Rule: once the per-frame `match` grows past ~50 lines, or states need their own exports, move to the node FSM.

## 5. Hierarchical and pushdown variants

- **Hierarchical**: a `State` that contains a child `StateMachine` (e.g. `Grounded` with sub-states `Idle`/`Run`). The parent state's `physics_update` handles shared rules (jump, fall) and then forwards to the sub-machine. Use it when several states share the same exits.
- **Pushdown (stack)**: keep `Array[State]`. `push(&"stunned")` exits/pauses the top and enters the new one; `pop()` returns to whatever was running. Use it for interruptions that must resume the previous state (stun, hit-reaction, pause menu flow). Decide whether a paused state gets `exit()` or a separate `pause()`/`resume()`, and be consistent.
- **Concurrent machines**: two independent machines on one actor (locomotion + weapon). Cheaper than multiplying states (`RunShooting`, `IdleShooting`, ...).

## 6. Debugging

- `state_changed` → a debug `Label` above the entity, or `print_rich` in debug builds.
- Remote Scene Tree (Debugger) shows the machine; inspect `current` on the StateMachine node.
- Log rejected stale requests while debugging. They often reveal timers that weren't stopped in `exit()`.

## 7. Performance and scale

- One StateMachine node plus N state nodes per entity is fine for players, bosses and a few dozen enemies.
- For hundreds of simple agents, use an enum FSM in one script, or a manager that updates plain data arrays. Don't put a node per state per bullet.
- States don't process on their own (no `_process` in state scripts), so inactive states cost nothing per frame.

Deeper: Godot 4 Best Practices ch.7 "Building a state machine in Godot using the State Pattern" to "Refactoring conditionals into patterns", PDF pp. 195–218
