# Object, RefCounted, Resource, Node: choosing and lifecycle traps

Read this when deciding what base class a new script extends, when something leaks or "changes everywhere at once", or when a reference becomes invalid.
Behaviors marked "tested 4.7.2" were checked headless on 4.7.2-stable.

## 1. Decision

Ask in order, stop at the first yes:

1. Does it draw, collide, play audio, receive input, need the frame/physics loop, or need a parent/child transform? → **Node** (usually a scene).
   - Utility nodes count: `Timer`, `AudioStreamPlayer`, `AnimationPlayer`, `Tween` owners. They need the tree clock or servers.
2. Must a designer edit it in the Inspector, must it be saved to disk, or is it shared read-only config? → **Resource**.
3. Does it hold state or logic that lives only in memory (rules, model, FSM, calculator, request)? → **RefCounted**.
4. Is it stateless? → `static func` on a `class_name` script (no instance at all).
5. Thousands of tiny records owned by one manager, profiled as a bottleneck, and you will free them yourself? → **Object**. Almost never right in gameplay code.

Plain `Dictionary`/`Array`/packed arrays beat all of the above for bulk numeric data (bullets, particles, grid cells): one owner node iterates them, or use a server API. Don't make 10,000 RefCounted bullets either.

| Base | Freed by | Inspector `@export` slot | Saved by `ResourceSaver` | Gets tree callbacks |
|---|---|---|---|---|
| Object | you: `free()` | no | no | no |
| RefCounted | last strong ref dropped | **no** (parse error, tested 4.7.2) | no | no |
| Resource | last strong ref dropped (+ cache) | yes | yes (`.tres`/`.res`) | no |
| Node | you: `queue_free()` / parent freed | yes (same-scene refs) | via `PackedScene` (owned nodes only) | yes |

A script with no `extends` line extends RefCounted. Write `extends RefCounted` anyway so the memory model is visible.

## 2. Node lifecycle traps

| Symptom | Cause | Fix |
|---|---|---|
| Memory grows, "orphan nodes" in Monitors | `remove_child()` without freeing; nodes created with `new()`/`instantiate()` never added | Nodes are not ref-counted. `queue_free()` what you remove unless you re-add it. Debug with `Node.print_orphan_nodes()` |
| "Attempt to call on a previously freed instance" | Cached a node reference, node was freed | `is_instance_valid(ref)` before use, or connect to its `tree_exiting` and null the ref |
| Base class setup (groups, connections) silently missing in subclass | Override of `_ready`/`_process`/`_physics_process` without `super()`. Godot 4 does **not** chain engine callbacks to the parent script (tested 4.7.2) | Call `super()` first in every override that the base implements |
| Spawned object lands offset by its parent (2D, silent) or at the origin with error `!is_inside_tree()` (3D) | `global_position`/`global_transform` set before `add_child`: outside the tree it is applied as local (tested 4.7.2) | Before adding, set the local transform: `node.position = parent.to_local(world_pos)` (or `parent.global_transform.affine_inverse() * xform`). Setting it after adding works, but `_ready` then runs at the origin |
| Projectiles/pickups survive a level change | Spawned as children of `get_tree().root`; `change_scene_to_*` only frees `current_scene` | Spawn into a container owned by the level (injected or `@export`), never into `root` |
| `find_child("X")` returns null for spawned node | Default `owned = true` skips nodes without an owner, and runtime-added nodes have none (tested 4.7.2) | `find_child("X", true, false)`, or better, keep a reference when spawning |

## 3. RefCounted traps

- **Cycles leak.** A holds B, B holds A → neither is freed (tested 4.7.2: no PREDELETE, ObjectDB leak at exit). Typical: parent model ↔ child model, state ↔ state machine. Fix: the child stores `weakref(parent)` (`WeakRef.get_ref()`), or the owner breaks the link in a `dispose()`.
- **Holding a Node does not keep the Node alive.** A model that stores a Node can outlive it. Check `is_instance_valid()` or don't store nodes in the domain layer at all.
- **Signal connections do not keep the target alive.** A `Callable` to a method stores the object id, so connecting a RefCounted's method somewhere doesn't own it. If nothing else holds it, it is freed and the connection is dropped. Keep a member variable.
- **Lifetime is scope.** `var calc := DamageCalc.new()` inside a function dies at function end. Fine for throwaway calculators; store it as a member for long-lived state (it dies with its owner, no cleanup code).
- `FileAccess` is RefCounted: dropping the last reference closes the file. Still call `close()` before re-opening the same path in the same function.
- No `_ready`, no `_process`. If logic needs time, the owning Node calls `tick(delta)` on it. That keeps the model testable without a tree.

## 4. Resource traps

- **Cache = shared instance.** `load()`/`preload()` of the same path returns the same object (tested 4.7.2). Mutating it changes every user, and the change survives `reload_current_scene()` because the cache outlives the scene. Treat file-backed Resources as read-only templates at runtime.
- **Per-instance copies.**
  - `duplicate()` (shallow): arrays, dictionaries and sub-resources are shared with the original (tested 4.7.2).
  - `duplicate(true)`: copies *internal* (embedded) sub-resources, including ones inside typed arrays, but **file-backed** sub-resources stay shared (tested 4.7.2).
  - `duplicate_deep(Resource.DEEP_DUPLICATE_ALL)`: also copies file-backed sub-resources (4.5+, tested 4.7.2).
  - `resource_local_to_scene = true`: each *instantiated scene* gets its own copy of that embedded resource. It does nothing for resources you `load()` in code.
  - Often cleaner: copy the few mutable fields into a RefCounted runtime state and never touch the template.
- **`_init` must be callable with no arguments.** Loading or duplicating calls `_init()` with zero args. Required parameters make loading fail with "Method expected 1 argument(s)" and the script is lost (tested 4.7.2). Give every `_init` parameter a default, or use a static factory (`static func create(...) -> MyRes`).
- **`changed` is not automatic.** Assigning an `@export` property or mutating an array does not emit `changed`. Call `emit_changed()` from setters or mutating methods.
- **Saving a Resource that references other `.tres` files** writes path references, not copies. Editing the referenced file later changes old saves. Snapshot values (ids + numbers) in save data.
- **Never `load()` a `.tres`/`.res` from `user://` or from a download.** Resources can embed scripts, so loading one can run code. Save files and mods use JSON/`ConfigFile`/`store_var` (with `allow_objects = false`) and validate. See godot-data-driven.
- **`@tool` scripts mutating a Resource in the editor write it to disk** on the next save. Guard with `Engine.is_editor_hint()`.
- `class_name` on a Resource script is what puts it in "New Resource…" and makes it typable in `@export`. Mark templates that must not be created `@abstract` (4.5+).

## 5. Object traps

- Must be `free()`d exactly once. A second `free()` or any access afterwards errors. Every reference to it becomes dangling, and `is_instance_valid()` is the only guard.
- Only worth it when one owner creates and frees all instances (the engine's `Tree` control owns its `TreeItem`s this way). If ownership is shared, use RefCounted.

## 6. Static members

- `static func`: stateless helpers (math, formatting, queries that take the context node as a parameter). No autoload or node needed.
- `static var` exists (4.1+). It is process-global state: it survives scene changes, isn't reset by `reload_current_scene()`, and is shared by every user. Same rules as an autoload. Prefer it only for caches and registries, and give it an explicit `reset()` for tests.

Deeper: Godot 4 Best Practices ch.4 "The hierarchy of lightweight objects" and "Separating logic from presentation", PDF pp. 114–125
