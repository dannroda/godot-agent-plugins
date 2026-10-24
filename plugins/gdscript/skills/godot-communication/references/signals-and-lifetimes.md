# Signals, await and object lifetimes: deep reference

Read this when you write coroutines (`await`), connect to long-lived emitters (autoloads, shared Resources), reuse pooled nodes, or touch the tree from physics callbacks. Behaviour marked "verified" was observed on Godot 4.7.2 and 4.8-beta1 with headless probes.

## 1. Facts about `await`

- `await sig` connects a one-shot resumption to `sig`. Nothing else holds the coroutine.
- **Emitter freed before emitting**: the coroutine is never resumed. There is no error, only a leaked function state at exit (verified).
- **Awaiting object freed**: the coroutine is never resumed (verified). Code after the `await` is dead.
- **Tween bound to a freed node**: `create_tween()` binds the tween to the calling node. If that node is freed, or the tween is `kill()`ed, `finished` never fires (verified).
- `await` on a function call that doesn't itself await returns immediately. That makes `await cmd.execute()` safe for both sync and async commands.
- A function containing `await` returns to its caller at the first `await`. In `_ready`, the node's `ready` signal fires at that point, before the rest of `_ready` has run.
- There is no built-in cancel and no built-in "await any of these". Use the helpers below.

## 2. Helper: await with timeout (verified)

```gdscript
## Resolves `finished(true)` if `sig` fires first, `finished(false)` on timeout.
## `arg_count` = number of arguments `sig` carries (they are dropped).
class_name AwaitRace extends RefCounted
signal finished(fired: bool)
var _done := false

func _init(sig: Signal, seconds: float, arg_count: int = 0, pausable: bool = true) -> void:
    sig.connect(_finish.bind(true).unbind(arg_count), CONNECT_ONE_SHOT)
    var tree := Engine.get_main_loop() as SceneTree
    tree.create_timer(seconds, not pausable).timeout.connect(_finish.bind(false))

func _finish(fired: bool) -> void:
    if _done:
        return
    _done = true
    finished.emit(fired)
```
Usage:
```gdscript
anim.play(&"windup")
var ok: bool = await AwaitRace.new(anim.animation_finished, 2.0, 1).finished
if not ok or not is_instance_valid(target) or not is_inside_tree():
    return
target.apply_hit(damage)
```
If the emitter is freed, the timeout still fires, so the caller always continues.

## 3. Helper: cancellation by generation token (verified)

A coroutine can't be cancelled from outside. Make stale ones bail out when they resume:

```gdscript
var _gen: int = 0

func start_attack() -> void:
    _gen += 1
    var my_gen := _gen
    await get_tree().create_timer(0.4, false).timeout
    if my_gen != _gen:
        return  # superseded or cancelled
    _deal_damage()

func cancel_actions() -> void:
    _gen += 1  # every pending coroutine of this object becomes stale
```
Use the same trick in FSM states: increment in `exit()` so a delayed transition from an old state is ignored.

## 4. Connections

| Situation | Rule |
|---|---|
| Target freed | The connection is removed automatically, including lambdas created inside the target (verified) |
| Lambda captures *another* object that dies | Error "Lambda capture at index N was freed" when it runs. Capture `get_instance_id()` and resolve with `instance_from_id`, or connect a method of that object |
| Same callable connected twice | Error. Guard with `is_connected`, or connect once at creation. `CONNECT_REFERENCE_COUNTED` allows intentional double connects with matching disconnects |
| Pooled node subscribing to an autoload/shared Resource | Subscribe on activate, unsubscribe on deactivate (or `_enter_tree`/`_exit_tree` if the pool removes nodes from the tree). The node never dies, so nothing auto-disconnects |
| Need the emitter's identity in the callback | `sig.connect(_on_x.bind(emitter))`. Bound args come after the signal args |
| Pass a signal around | `Signal` is a value: `func wait_for(sig: Signal)`. `Signal(obj, &"name")` builds one by name. Check `is_instance_valid(sig.get_object())` before awaiting |
| Inspect who listens | `sig.get_connections()` returns an array of dictionaries with `callable` and `flags` |

## 5. Physics callbacks (`body_entered`, `area_entered`, `_integrate_forces`, contact signals)

During these, the physics server is flushing queries. Changing the physics state from them errors with "Can't change this state while flushing queries" (verified, adding an `Area2D` inside `body_entered`).

| Allowed directly | Defer it |
|---|---|
| Reading anything, emitting signals, `queue_free()`, setting `velocity` (applied on the next `move_and_slide`) | `add_child` of any `CollisionObject2D/3D` or a scene containing one |
| Changing non-physics properties (visibility, modulate, animation) | `CollisionShape*.disabled` → `set_deferred(&"disabled", true)` |
| | `Area*.monitoring` / `monitorable` → `set_deferred` |
| | Reparenting physics nodes, changing `process_mode` of physics nodes |

Spawning from a hit is the common case: `container.add_child.call_deferred(explosion)`. See `godot-patterns` (factory) for setting the transform before adding.

## 6. Deletion

- `queue_free()` deletes at the end of the frame. Until then the node is valid, still in the tree, and still emits and receives signals. Calling `queue_free()` twice is harmless.
- Guard reuse with `is_queued_for_deletion()`, for example when a target picked this frame was already killed by another bullet this frame.
- `free()` deletes immediately. Never call it on a node from inside its own signal callbacks, or during physics.
- `is_instance_valid(x)` is the only safe check for "might be freed". `x != null` is not enough for a freed Object reference.
- `_exit_tree` runs on every removal (including `remove_child` and scene change). Free-time cleanup that must also cover non-tree removal goes in `NOTIFICATION_PREDELETE`.

## 7. Timers, pause and time scale

| API | Pauses with tree? | Time scale? |
|---|---|---|
| `get_tree().create_timer(t)` | **No**: `process_always` defaults to `true` (verified signature) | Yes, unless `ignore_time_scale = true` |
| `get_tree().create_timer(t, false)` | Yes | Yes |
| `Timer` node | Follows the node's `process_mode` | Yes, unless `ignore_time_scale = true` |
| `create_tween()` | Follows the bound node's `process_mode` | Yes. `set_ignore_time_scale(true)` for UI |

Gameplay waits use pausable timers. Menu, fade and transition waits use `PROCESS_MODE_ALWAYS` nodes or `process_always` timers.

## 8. Tweens

- Bind tweens to the node they animate (`node.create_tween()`), so they die with it. Use `get_tree().create_tween()` only for objects that outlive any node.
- Keep a handle and kill the old tween before starting a new one on the same property: `if _tw and _tw.is_valid(): _tw.kill()`.
- A killed tween never emits `finished`. Anything awaiting it hangs (§1).

## 9. Debugging an EventBus (verified)

Log every bus emission in debug builds. This uses a variadic callback (GDScript 4.5+, verify the minimum version):

```gdscript
# inside event_bus.gd
func _ready() -> void:
    if OS.is_debug_build():
        for s: Dictionary in (get_script() as Script).get_script_signal_list():
            connect(s.name, _log_emit.bind(s.name))

func _log_emit(...args: Array) -> void:
    print("[bus] ", args.back(), " ", args.slice(0, -1))  # bound name is last
```
For namespaced buses, run the same loop over each channel object. Combine this with a `source` argument on game-flow events to find who fired them.

Deeper: Godot 4 Best Practices ch.6 "Using signals to decouple systems" and "Trade-offs of Event-Driven Architecture", PDF pp. 163–169
