---
name: "gdextension-debug"
description: "Use when a Godot 4 C++ GDExtension doesn't load, crashes, leaks or misbehaves, or when reviewing godot-cpp code: what each load error means, getting a readable backtrace (debug_symbols, addr2line, gdb), leaked ObjectDB instances and Ref cycles, wrong-thread errors, code that runs in the editor, and a review checklist. Writing the extension is in gdextension-cpp, builds in gdextension-build."
---

# Debug and review a GDExtension

Checked with godot-cpp 10.0.0-stable on Godot 4.7.2 and 4.8 beta 2, Linux, gdb 18. The messages below were copied from runs that triggered each problem on purpose.

## Reproduce outside the user's editor

A crash in the extension kills the process that loaded it. Reproduce in a headless Godot on the test project (or a copy of the game), never in the editor the user has open:

```bash
godot --headless --import --path project
timeout 120 godot --headless --path project --script res://extension_tests.gd -- --dir=res://tests
```

With the Godot Agent Harness tools, `godot.run {"method": "test_extension", ...}` does this: it imports when a `.gdextension` isn't registered yet (except in the project the editor has open), runs the tests headless, and after a crash returns only the extension's frames, resolved to function and line with `addr2line` when the build has `debug_symbols=yes`. Use `addr2line` and `gdb` by hand, below, for crashes it doesn't reproduce.

To reproduce something that only happens in the editor, run the editor headless on a copy: `timeout 60 godot --headless --editor --path copy res://scene.tscn --quit-after 200`. It opens the scene, runs editor-side code such as `_process` in the editor, then quits.

## Builds the harness rolled back

The harness's `restart_editor` runs the editor under a crash supervisor. When a new build crashes the editor while it starts, the supervisor:
- renames each changed library to `<file>.crashed` and puts back the last copy that started fine;
- renames a `.gdextension` with no good copy (it never started fine) to `<name>.gdextension.disabled`;
- reopens the editor, and the agent's session continues with a message naming those files and the backtrace.

Debug the `.crashed` library headless, as above. After the fix, rebuild, and rename the `.gdextension.disabled` file back to `.gdextension`: until then, neither the editor nor exports load the extension. Delete the `.crashed` files once you're done with them.

## Load errors

| Message | Cause |
|---|---|
| `Identifier "MyNode" not declared in the current scope` and no extension error | `.godot/extension_list.cfg` is missing. Run `godot --headless --import` once. |
| `No GDExtension library found for current OS and architecture (linux.x86_64)` | No `[libraries]` key matches. The editor needs a `debug` key and release exports a `release` key. |
| `Can't open dynamic library, file not found: '.../x.so'` | The path in the `.gdextension` is wrong. Paths starting with `./` are relative to the `.gdextension` file. |
| `Can't open dynamic library: ... Error: libfoo.so.1: cannot open shared object file` | A library your library needs isn't next to it, or isn't listed in `[dependencies]` for exports |
| `GDExtension entry point 'x' not found in library` | `entry_symbol` differs from the `extern "C"` function name, or the function isn't `GDE_EXPORT` |
| `GDExtension only compatible with Godot version 4.8.0 or later` | `compatibility_minimum` is above the running Godot |
| `Cannot load a GDExtension built for Godot 4.8.0 using an older version of Godot (4.7.2).` | Built with a newer `api_version` or `custom_api_file` than the running Godot. Rebuild with an older API. |
| `Getter method 'C::get_x()' not found for property 'C::x'` | The getter, or setter, wasn't bound before `ADD_PROPERTY` |
| `Extension runtime class 'B' cannot descend from 'A' which isn't also a runtime class.` | `GDREGISTER_RUNTIME_CLASS` on a subclass of a normal class of your own; B isn't registered |

`gdextension-build/scripts/check_gdextension.py` finds the path, entry symbol and debug or release problems before Godot runs.

## Crashes

The crash handler prints frames inside the extension only as offsets, even with symbols:

```
[2] ... (liblab.linux.template_debug.x86_64.so+8463c) - .../liblab.linux.template_debug.x86_64.so(+0x8463c)
```

godot-cpp builds with no debug symbols by default (`debug_symbols` is on only with `dev_build=yes`). Rebuild with `debug_symbols=yes`, rerun, then do either of these:

```bash
# turn the offsets from the crash log into functions and lines
addr2line -f -C -i -e project/bin/linux/liblab.linux.template_debug.x86_64.so 0x8463c 0x76110

# or run under gdb and print the stack at the crash
gdb -q -batch -ex run -ex bt --args godot --headless --path project --script res://extension_tests.gd
```

Both gave function, file and line, down to the line in your code that called into godot-cpp. Keep the same build: offsets change with every rebuild. On Windows use the `.pdb` from an MSVC build with a debugger; MinGW builds without `debug_symbols=yes` are linked with `-s`, which strips symbols. For no optimization as well, use `dev_build=yes`; it adds `.dev` to the file name, which the template's SConstruct removes.

Common crashes:
- `BUG: Godot Object created without binding callbacks. Did you forget to use memnew()?`, then signal 4: an object created with `new`. Use `memnew`.
- Using an `Object *` after it was freed. Keep an `ObjectID` (`obj->get_instance_id()`) and look it up with `ObjectDB::get_instance(id)` when the object may be freed by someone else, or hold a `Ref<T>` for RefCounted types.
- A C library calling back into an object that was already freed. See `gdextension-wrap-library`.

## Leaks

At exit, Godot prints `WARNING: 3 ObjectDB instances were leaked at exit (run with --verbose for details).`. With `--verbose` it lists them:

```
Leaked instance: Node:26759661011 - Node path:
Leaked instance: :9223372063631214036
```

- A node created with `memnew` and never added to the tree or freed shows its class. Free it with `memdelete`, `queue_free()`, or give it a parent.
- Two `Ref<T>` pointing at each other never reach zero and show with no class name. Break the cycle: keep one side as a raw pointer or an `ObjectID`, or clear it in `_notification(NOTIFICATION_PREDELETE)` of the owner.
- An engine singleton you `memnew` must be `memdelete`d in uninitialize.

## Threads

Checked on a running scene tree:

| From a worker thread | Result |
|---|---|
| `emit_signal(...)` | Handlers run **on the worker thread**, including GDScript ones |
| `get_child_count()` on a node in the tree | `The caller thread can't call the function 'get_child_count()' on this node. Use call_deferred() or call_deferred_thread_group() instead.` |
| `add_child` on a node in the tree | `Adding children to a node inside the SceneTree is only allowed from the main thread. Use call_deferred("add_child",node).` |
| `callable_mp(this, &C::f).call_deferred(args)` | Runs on the main thread at the next idle time, in order |

These checks don't fire during `SceneTree._initialize()`, before the tree runs: a test there passed while doing the wrong thing. The test runner in `gdextension-cpp` waits one frame first. Protect shared C++ state with `std::mutex`, or godot-cpp's `Mutex` and `MutexLock` from `godot_cpp/templates/mutex.hpp` (the RefCounted `Mutex` that scripts use is `godot::CoreBind::Mutex` in `godot_cpp/classes/mutex.hpp`); `_THREAD_SAFE_CLASS_` with `_THREAD_SAFE_METHOD_` locks a whole class.

## Code that runs in the editor

Every GDExtension class runs in the editor like a `@tool` script: a `_process` override ticked with its scene open in the editor. Symptoms: nodes move, spawn or save state while being edited, or the editor crashes when opening a scene. Guard with `Engine::get_singleton()->is_editor_hint()`, or register game-only classes with `GDREGISTER_RUNTIME_CLASS`.

## Review checklist

- [ ] `api_version` and `compatibility_minimum` are the oldest version that has the API used, and tests ran on each supported version.
- [ ] Every property has both accessors bound; validation in setters uses `ERR_FAIL_*_MSG`.
- [ ] No `new`/`delete` on Godot objects; RefCounted objects live in `Ref<T>`.
- [ ] No raw `Object *` kept across frames for objects others can free; an `ObjectID` or `Ref` is used instead.
- [ ] `_process`, `_physics_process`, `_ready` and `_notification` are safe in the editor, or guarded.
- [ ] Nothing touches the scene tree from a worker thread; results come back with `call_deferred`.
- [ ] Anything holding a pointer to `this` (threads, C callbacks, timers) is stopped in the destructor.
- [ ] Engine singletons are unregistered and freed in uninitialize.
- [ ] `.gdextension` has debug and release entries for every shipped platform, and `[dependencies]` for third-party shared libraries (`check_gdextension.py --require`).
- [ ] No leaked instances at exit in the test run (`--verbose`).
- [ ] The hot path really is faster than GDScript. Each call from GDScript into C++ has a cost, so a call per element in a loop can cancel the gain; pass whole arrays instead.
