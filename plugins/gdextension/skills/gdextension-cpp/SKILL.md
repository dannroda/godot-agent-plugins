---
name: "gdextension-cpp"
description: "Use when writing a Godot 4 GDExtension in C++ with godot-cpp: starting the project (godot-cpp 10 and api_version, SCons or CMake, the .gdextension file, entry symbol), registering classes, methods, properties, signals, enums, static and virtual methods that GDScript overrides, Ref and memnew, engine singletons, overriding _process and _ready, doc XML, hot reload, and testing the extension headless. Builds and exports are in gdextension-build, crashes and review in gdextension-debug, wrapping a C or C++ library in gdextension-wrap-library."
---

# GDExtension in C++

Checked with godot-cpp 10.0.0-stable on Godot 4.7.2 and 4.8 beta 2, Linux, SCons 4.11 and CMake. Each fact below comes from building a test extension and running it headless; error messages are copied from those runs.

References:
- `references/binding-api.md`: read when binding anything beyond a plain method: properties and hints, groups, signals, enums and bitfields, default arguments, static and vararg methods, virtuals GDScript overrides, typed arrays, callables, singletons.
- `scripts/extension_tests.gd`: a headless test runner for the extension. Copy it into the test project.

## Is GDExtension the right tool?

Use it for hot loops GDScript can't make fast enough, for an existing C or C++ library, or for engine-level types that should feel built in. For gameplay logic, GDScript is faster to change, and a GDExtension adds a native build per platform, a crash surface and an ABI to keep. Measure first (see `godot-performance` in the `godot-testing` plugin) and move only the hot part.

## Never load a new build into the editor the user has open

A segfault in the extension takes the whole editor down with it, along with the agent driving it. A library replaced under a running editor isn't reloaded either, unless hot reload is set up (below). Build, then test in a separate headless Godot on the test project, and tell the user when to restart their editor.

## Project layout

godot-cpp-template (github.com/godotengine/godot-cpp-template) has this layout. The skills in this plugin assume it:

```
my_ext/
  godot-cpp/                 git submodule, checked out at 10.0.0-stable
  SConstruct                 or CMakeLists.txt
  src/                       register_types.cpp and your classes
  doc_classes/               class reference XML (optional)
  project/                   a small Godot project for testing
    project.godot
    bin/my_ext.gdextension
    bin/<platform>/libmy_ext.<platform>.<target>.<arch>.so   build output
    tests/test_*.gd
    extension_tests.gd       copied from this skill's scripts/
```

Pin godot-cpp to a release tag (`-b` takes branches, not tags):

```bash
git submodule add https://github.com/godotengine/godot-cpp
git -C godot-cpp checkout 10.0.0-stable
git add godot-cpp
```

Older projects pin a tag like `godot-4.5-stable` and have no `api_version`; that line ended at 4.5.

## Pick the API version

Starting with 10.0, godot-cpp is versioned on its own and builds against one of the API files it ships (4.3 to 4.7 in 10.0.0). An extension built for an older API loads in newer Godot; the reverse fails:

| Built with | Godot 4.7.2 | Godot 4.8 beta 2 |
|---|---|---|
| `api_version=4.3` | loads | loads |
| `api_version=4.7` | loads | loads |
| `custom_api_file` dumped from 4.8 beta 2 | `Cannot load a GDExtension built for Godot 4.8.0 using an older version of Godot (4.7.2).` | loads |

Pick the oldest version that has the API you need, and set it in the SConstruct so a plain `scons` uses it: `SConscript("godot-cpp/SConstruct", {"api_version": "4.7"})`. SCons stops with `'api_version' must be provided` without it; CMake defaults `GODOTCPP_API_VERSION` to 4.7. For an API newer than the bundled files: `godot --headless --dump-extension-api`, then `scons custom_api_file=extension_api.json`.

Put the same version in `compatibility_minimum`. A Godot older than it refuses the extension: `GDExtension only compatible with Godot version 4.8.0 or later`.

## The .gdextension file

```ini
[configuration]
entry_symbol = "my_ext_library_init"
compatibility_minimum = "4.7"
reloadable = true

[libraries]
linux.debug.x86_64 = "./linux/libmy_ext.linux.template_debug.x86_64.so"
linux.release.x86_64 = "./linux/libmy_ext.linux.template_release.x86_64.so"
windows.debug.x86_64 = "./windows/libmy_ext.windows.template_debug.x86_64.dll"
windows.release.x86_64 = "./windows/libmy_ext.windows.template_release.x86_64.dll"
```

- Paths starting with `./` are relative to the `.gdextension` file, so the folder can move inside the project.
- The editor and debug exports load the `debug` entry; release exports load `release`. With only a release entry, the editor prints `No GDExtension library found for current OS and architecture (linux.x86_64)`.
- The Windows file name depends on the compiler: MinGW keeps the `lib` prefix (`libmy_ext.windows...dll`) and MSVC drops it. Copy names from the build output, not from a template.
- After adding or renaming a `.gdextension`, run `godot --headless --import --path project` once. Godot lists extensions in `.godot/extension_list.cfg`; without that file a headless run loads nothing, and scripts fail with `Identifier "MyClass" not declared in the current scope`.

`gdextension-build` has a script that checks this file against the libraries on disk.

## Entry point and registration

```cpp
// register_types.cpp
#include <gdextension_interface.h>
#include <godot_cpp/core/class_db.hpp>
#include <godot_cpp/godot.hpp>
#include "my_node.h"

using namespace godot;

static void initialize_my_ext(ModuleInitializationLevel p_level) {
	if (p_level != MODULE_INITIALIZATION_LEVEL_SCENE) {
		return;
	}
	GDREGISTER_CLASS(MyNode);          // base classes before the classes that extend them
}

static void uninitialize_my_ext(ModuleInitializationLevel p_level) {}

extern "C" GDExtensionBool GDE_EXPORT my_ext_library_init(GDExtensionInterfaceGetProcAddress p_get_proc_address,
		GDExtensionClassLibraryPtr p_library, GDExtensionInitialization *r_initialization) {
	GDExtensionBinding::InitObject init_obj(p_get_proc_address, p_library, r_initialization);
	init_obj.register_initializer(initialize_my_ext);
	init_obj.register_terminator(uninitialize_my_ext);
	init_obj.set_minimum_library_initialization_level(MODULE_INITIALIZATION_LEVEL_SCENE);
	return init_obj.init();
}
```

The function name must equal `entry_symbol`. A mismatch prints `GDExtension entry point 'x' not found in library`.

| Macro | Result |
|---|---|
| `GDREGISTER_CLASS` | Normal class: `.new()`, Create dialog |
| `GDREGISTER_VIRTUAL_CLASS` | Marked as meant to be extended. It does **not** block instancing: `.new()` and `ClassDB.can_instantiate()` both worked. |
| `GDREGISTER_ABSTRACT_CLASS` | Can't be instanced: `.new()` printed `Class 'X' or its base class cannot be instantiated.`, and so did a GDScript that extends it. Use it for C++ bases with pure virtual methods. |
| `GDREGISTER_INTERNAL_CLASS` | Usable from C++, hidden from scripts and docs |
| `GDREGISTER_RUNTIME_CLASS` | Runs only in the game. Its `_process` ran in a game run, and never with its scene open in the editor. It can't extend a non-runtime class of your own extension: `Extension runtime class 'B' cannot descend from 'A' which isn't also a runtime class.` and B isn't registered. |

## A class

```cpp
// my_node.h
#pragma once
#include <godot_cpp/classes/node2d.hpp>

namespace godot {

class MyNode : public Node2D {
	GDCLASS(MyNode, Node2D)
	double speed = 100.0;

protected:
	static void _bind_methods();

public:
	void set_speed(double p_speed) { speed = p_speed; }
	double get_speed() const { return speed; }
	void _process(double p_delta) override;
};

} // namespace godot
```

```cpp
void MyNode::_bind_methods() {
	ClassDB::bind_method(D_METHOD("set_speed", "speed"), &MyNode::set_speed);
	ClassDB::bind_method(D_METHOD("get_speed"), &MyNode::get_speed);
	ADD_PROPERTY(PropertyInfo(Variant::FLOAT, "speed", PROPERTY_HINT_RANGE, "0,1000,0.1,suffix:px/s"), "set_speed", "get_speed");
}
```

Rules that hold in the runs:
- Every class declares `static void _bind_methods()`, even an empty one. A `static_assert` in godot-cpp stops the build without it.
- A property needs both its setter and its getter bound first. A missing one doesn't fail the build; it prints `Getter method 'MyNode::get_speed()' not found for property 'MyNode::speed'` at load, and the property reads `null`.
- Engine virtuals (`_process`, `_ready`, `_physics_process`, `_input`) are overridden with `override` and need no binding. Overriding `_process` turns processing on by itself.
- **Every GDExtension class runs in the editor**, like a `@tool` script. A `_process` override ticked with `Engine::is_editor_hint() == true` when its scene was opened in the editor. Guard gameplay with `if (Engine::get_singleton()->is_editor_hint()) return;`, or call `set_process(!Engine::get_singleton()->is_editor_hint())` in `NOTIFICATION_READY`.
- Objects are created with `memnew(T)` and non-RefCounted objects freed with `memdelete`; RefCounted ones live in `Ref<T>` (`Ref<T> r; r.instantiate();`). Plain `new` compiles, then crashes at runtime after `BUG: Godot Object created without binding callbacks. Did you forget to use memnew()?`.
- Report bad input with `ERR_FAIL_COND_MSG(cond, "msg")` / `ERR_FAIL_V_MSG`. It prints the C++ file and line plus the GDScript backtrace, and returns without crashing.
- With a `build_profile`, headers come in through fewer includes, and code that compiled before can fail with `incomplete type 'godot::Ref<...>'`. Include what you use (`godot_cpp/classes/ref.hpp` for `Ref`).

## Docs in the editor

Generate XML stubs from the loaded extension, fill them in, and the template's SConstruct (`env.GodotCPPDocData`) or CMake (`target_doc_sources`) compiles them into editor and debug builds:

```bash
cd project && godot --headless --doctool .. --gdextension-docs
```

That writes `../doc_classes/<Class>.xml` for every class of the extension.

## Hot reload

The editor swaps in a rebuilt library without restarting only when both are true:
- `reloadable = true` in `[configuration]`
- the library was built with `use_hot_reload=yes` (CMake: `-DGODOTCPP_USE_HOT_RELOAD=ON`). In godot-cpp 10 it is **off by default**.

Built without it, a reload in the editor printed `Unable to recreate GDExtension instance - does this extension support hot reloading?` and later calls failed with `Cannot call invalid GDExtension method bind`. Built with it, existing instances survived, and only bound properties kept their values: a private field without a property came back at its default. Reloading is editor-only: in a game run it printed `GDExtension reloading is disabled.`. Even when it works, test risky changes headless first: a crash during reload still takes the editor down.

## Test headless

Copy `scripts/extension_tests.gd` to the test project. Put tests in `project/tests/test_*.gd`:

```gdscript
extends RefCounted

func test_speed(t) -> void:
	var n := MyNode.new()
	n.speed = 50.0
	t.check(n.get_speed() == 50.0, "speed setter")
	n.free()
```

```bash
godot --headless --import --path project
timeout 120 godot --headless --path project --script res://extension_tests.gd -- --dir=res://tests --class=MyNode
```

Exit 0 means all passed, 1 means a check failed, and 2 means the extension or a class didn't load, or no tests ran. Keep the `timeout`: when the extension fails to load, scripts that use its classes fail to parse, and a game can be left running forever. The runner waits one frame before testing, because in `_initialize` the tree isn't running yet and a scene call from another thread prints no error there.

Run it on every Godot version you claim to support. Next steps: `gdextension-build` for other platforms and exports, `gdextension-debug` when it crashes.
