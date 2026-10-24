# Commands: deep reference

Read this when you implement command objects for input/AI sharing, a turn queue, undo/redo, input buffering or replays. The code compiles and was run on Godot 4.7.2 (queue timeout, undo/redo and source swapping included).

## 1. Roles

| Role | In Godot | Example |
|---|---|---|
| Client / source | Node that decides what to do | `PlayerCommandSource` reads `Input`; `ChaseAISource` reads the world |
| Command | `RefCounted` data + `execute(actor)` / `undo(actor)` | `MoveCommand`, `FireCommand`, `GridMoveCommand` |
| Invoker | Runs commands: immediately, or through a queue | `ActorController`, `CommandQueue` |
| Receiver / actor | The entity with the real methods | `Ship.steer()`, `GridUnit.move_to()` |

Commands talk to a **typed** receiver (`actor as Ship`) and bail out if the cast fails. Avoid `has_method("fire")`.

## 2. Real-time: sources + immediate execution

```gdscript
# command.gd
class_name Command extends RefCounted
func execute(_actor: Node) -> void: pass
func undo(_actor: Node) -> void: pass
func is_undoable() -> bool: return false

# ship.gd: the receiver
class_name Ship extends CharacterBody2D
@export var speed: float = 300.0
var _shots: int = 0
func steer(dir: Vector2) -> void:
    velocity = dir * speed
    move_and_slide()
func fire() -> void:
    _shots += 1  # spawn via a spawner in real code

# move_command.gd / fire_command.gd
class_name MoveCommand extends Command
var direction: Vector2
func _init(dir: Vector2) -> void:
    direction = dir
func execute(actor: Node) -> void:
    var ship := actor as Ship
    if ship:
        ship.steer(direction)

class_name FireCommand extends Command
func execute(actor: Node) -> void:
    var ship := actor as Ship
    if ship:
        ship.fire()

# command_source.gd: player, AI, network and replay all implement this
class_name CommandSource extends Node
func poll() -> Array[Command]:
    return []

class_name PlayerCommandSource extends CommandSource
func poll() -> Array[Command]:
    var out: Array[Command] = []
    var dir := Input.get_vector(&"move_left", &"move_right", &"move_up", &"move_down")
    out.append(MoveCommand.new(dir))  # zero vector too, so the ship stops
    if Input.is_action_just_pressed(&"fire"):
        out.append(FireCommand.new())
    return out

# actor_controller.gd: the invoker for action games
class_name ActorController extends Node
@export var actor: Node
@export var source: CommandSource  # swap at runtime: player <-> AI <-> replay

func _physics_process(_delta: float) -> void:
    if not is_instance_valid(actor) or source == null:
        return
    for c in source.poll():  # move + fire in the same tick, no waiting
        c.execute(actor)
```
- An AI source (`ChaseAISource extends CommandSource`) returns the same commands from its own decision logic. One `Ship` script then serves players, enemies, demo mode and automated tests.
- Status effects become source decorators: a `ConfusedSource` wraps another source and inverts `MoveCommand.direction` for 3 seconds. The ship's code doesn't change.
- Allocating a few `RefCounted` commands per tick is cheap. For hundreds of agents, reuse command instances or skip the pattern for the crowd.

## 3. Turn-based: queue with timeout, undo/redo

```gdscript
# command_runner.gd: runs one possibly-async command with a guaranteed end
class_name CommandRunner extends RefCounted
signal done(completed: bool)
var is_done := false

func start(c: Command, actor: Node, as_undo: bool, timeout: float) -> void:
    var tree := Engine.get_main_loop() as SceneTree
    tree.create_timer(timeout, false).timeout.connect(_finish.bind(false))
    if as_undo:
        await c.undo(actor)
    else:
        await c.execute(actor)
    _finish(true)

func _finish(completed: bool) -> void:
    if is_done:
        return
    is_done = true
    done.emit(completed)
```

```gdscript
# command_queue.gd
class_name CommandQueue extends Node
signal command_finished(cmd: Command, completed: bool)
const MAX_HISTORY := 64
@export var actor: Node
@export var timeout: float = 3.0
enum Op { DO, UNDO, REDO }
var undo_stack: Array[Command] = []
var redo_stack: Array[Command] = []
var _ops: Array[Array] = []  # [Op, Command or null]; undo/redo are queued too
var _busy := false

func push(c: Command) -> void:
    _enqueue(Op.DO, c)

func undo() -> void:
    _enqueue(Op.UNDO, null)

func redo() -> void:
    _enqueue(Op.REDO, null)

func _enqueue(op: Op, c: Command) -> void:
    _ops.append([op, c])
    if not _busy:  # calls made from inside a command_finished listener just enqueue
        _drain()

func _drain() -> void:
    _busy = true
    while not _ops.is_empty():
        var entry: Array = _ops.pop_front()
        if not is_instance_valid(actor):
            _ops.clear()  # receiver died: drop the rest
            break
        match entry[0]:
            Op.DO:
                var c: Command = entry[1]
                var ok := await _run(c, false)
                if ok and c.is_undoable():
                    undo_stack.append(c)
                    if undo_stack.size() > MAX_HISTORY:
                        undo_stack.pop_front()  # cap memory
                    redo_stack.clear()  # a new action discards the redo future
                command_finished.emit(c, ok)
            Op.UNDO:
                if undo_stack.is_empty():
                    continue  # mashing undo on an empty history is a no-op
                var c: Command = undo_stack.pop_back()
                await _run(c, true)
                redo_stack.append(c)
            Op.REDO:
                if redo_stack.is_empty():
                    continue
                var c: Command = redo_stack.pop_back()
                await _run(c, false)
                undo_stack.append(c)
    _busy = false

func _run(c: Command, as_undo: bool) -> bool:
    var r := CommandRunner.new()
    r.start(c, actor, as_undo, timeout)
    if r.is_done:  # finished synchronously
        return true
    return await r.done
```

An undoable command and its receiver:
```gdscript
class_name GridUnit extends Node2D
const CELL := 32
var cell := Vector2i.ZERO

func move_to(target: Vector2i) -> void:
    cell = target  # logic changes NOW; the tween is only presentation
    var tw := create_tween()
    tw.tween_property(self, ^"position", Vector2(target * CELL), 0.15)
    await tw.finished

class_name GridMoveCommand extends Command
var step: Vector2i
var _from: Vector2i

func _init(p_step: Vector2i) -> void:
    step = p_step

func is_undoable() -> bool:
    return true

func execute(actor: Node) -> void:
    var unit := actor as GridUnit
    if unit == null:
        return
    _from = unit.cell  # cache in the SAME space undo restores
    await unit.move_to(unit.cell + step)

func undo(actor: Node) -> void:
    var unit := actor as GridUnit
    if unit:
        await unit.move_to(_from)
```

Rules:
- Update **logical** state synchronously and animate afterwards. If the tween is interrupted or the node is skipped, undo still restores the right state.
- Cache undo data in the same space you restore: cell → cell, `position` → `position`. Caching `global_position` and tweening `position` is a classic bug.
- Every awaited command needs a guaranteed end. The runner's timeout covers freed tweens, deleted UI and signals that never fire.
- Queue undo/redo requests too; don't drop them when busy. `emit()` runs listeners synchronously, so a `command_finished` listener that calls `undo()` re-enters while the queue is still busy. A first version that returned early on `_busy` silently lost that undo (verified).
- Validate the actor before each command. The queue may run seconds after the command was issued.
- Cap history. Commands that hold references to nodes keep reading them; prefer ids and plain data inside commands.
- Clear redo on any new command (standard "new timeline" behaviour).

## 4. Input buffering

```gdscript
const BUFFER_SEC := 0.15
var _buffered: Command
var _buffered_at := 0.0

func buffer(c: Command) -> void:
    _buffered = c
    _buffered_at = Time.get_ticks_msec() / 1000.0

func take_buffered() -> Command:  # call when the actor can act again (landed, attack ended)
    if _buffered and Time.get_ticks_msec() / 1000.0 - _buffered_at <= BUFFER_SEC:
        var c := _buffered
        _buffered = null
        return c
    _buffered = null
    return null
```
Feel tuning (window length, coyote time): `input-systems` and `game-feel` skills.

## 5. Replays and networking

- Record `(physics_tick, serialized command)` from the source, not from the actor. Give commands `to_dict()` / `static from_dict()`.
- Exact playback needs: fixed physics tick, a seeded `RandomNumberGenerator` per system (no global `randf()`), no wall-clock reads in gameplay, and the same initial state.
- Built-in physics (GodotPhysics, Jolt) is not guaranteed deterministic across machines or builds. Also store periodic state snapshots and correct drift, or keep replayed movement kinematic.
- A `ReplaySource extends CommandSource` feeds recorded commands back through the same `ActorController`: same path as live input.

## 6. Tests (no scene needed)

```gdscript
func test_grid_move_undo() -> void:
    var unit := GridUnit.new()
    add_child(unit)  # tweens need the tree
    var q := CommandQueue.new()
    q.actor = unit
    add_child(q)
    q.push(GridMoveCommand.new(Vector2i.RIGHT))
    await q.command_finished
    assert(unit.cell == Vector2i(1, 0))
    q.undo()
    await get_tree().create_timer(0.3).timeout
    assert(unit.cell == Vector2i.ZERO)

func test_hung_command_times_out() -> void:
    # a command awaiting a signal that never fires must not jam the queue
    var q := CommandQueue.new()
    q.actor = Node.new()
    q.timeout = 0.1
    add_child(q)
    q.push(NeverEndsCommand.new())
    var ok: bool = (await q.command_finished)[1]  # multi-arg signal -> Array
    assert(not ok)
```
- Test the empty-undo path (no-op, no error), a freed actor (queue drops the rest), and history capping.
- Fakes: a minimal receiver subclass, or an `@abstract` receiver contract (4.5+) with a recording fake.

Deeper: Godot 4 Best Practices ch.10 "Applying Command and Service Patterns" (whole chapter), PDF pp. 266–284
