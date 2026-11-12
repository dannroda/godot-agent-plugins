---
name: "godot-strict-checks"
description: "Use when setting up or running checks that make the Godot 4 GDScript parser reject sloppy or made-up code: warning levels raised to errors (untyped declarations, unsafe method and property access, unused variables), checking every script headlessly with --check-only, a CI step, adopting strict warnings in an existing project, and @warning_ignore with a reason. Run it after an agent writes or edits GDScript."
---

# Strict GDScript checks

The cheapest reviewer is the parser. With Godot's default warnings, a method or property that doesn't exist on a typed variable (`sprite.velocty = 3`, `body.set_frame_magic()`) parses fine and only fails when that line runs. Raise a few warnings to errors and the parser rejects it before anything runs. Checked on Godot 4.7.2.

Use this with `godot-deslop`, which covers the noise the parser accepts.

## 1. Raise the warnings

In Project Settings → Debug → GDScript (turn on Advanced Settings), or under `[debug]` in `project.godot`. `2` is error, `1` warning, `0` off:

```ini
[debug]

gdscript/warnings/untyped_declaration=2
gdscript/warnings/unsafe_method_access=2
gdscript/warnings/unsafe_property_access=2
gdscript/warnings/unsafe_call_argument=2
gdscript/warnings/unused_variable=2
gdscript/warnings/unused_signal=2
gdscript/warnings/unreachable_code=2
gdscript/warnings/standalone_expression=2
gdscript/warnings/shadowed_variable=2
gdscript/warnings/missing_await=1
gdscript/warnings/unsafe_cast=1
```

What each catches that defaults let through:

| Warning | Catches |
|---|---|
| `unsafe_method_access`, `unsafe_property_access` | Made-up or misspelled members on a typed value, Godot 3 method names (`get_tree().change_scene()`, `packed.instance()`), and calls on untyped `get_node()` results. Off by default. |
| `untyped_declaration` | `var x = 3`, untyped parameters and missing return types. Without types, the two above can't check anything. |
| `unsafe_call_argument` | A `Variant` (from a Dictionary, JSON or `get()`) passed where a typed parameter is expected. |
| `unused_variable`, `unused_signal`, `unreachable_code`, `standalone_expression` | Leftovers from rewrites: dead locals, signals nobody emits, code after `return`, a bare `x == 1` line. |

Already errors by default: `inference_on_variant` (`var v := dict.get("k")`), `onready_with_export`, `get_node_default_without_onready`, `native_method_override`. Removed Godot 3 syntax (`yield`, `onready var`, `export var`, `KinematicBody2D`, `connect("sig", self, "m")`) is always a parse error.

`addons/` is excluded by `debug/gdscript/warnings/directory_rules` (default `{ "res://addons": 0 }`), so third-party plugins don't break the build.

Leave `inferred_declaration` off: it bans `:=`, which is the house style in these skills. Leave `return_value_discarded` off: it fires on every `connect()` and `tween_property()`.

## 2. Fix the errors, don't hide them

| Error | Fix |
|---|---|
| Method not present on `Node` after `$Player` or `get_node()` | `@onready var player: Player = $Player`, or `%Player as Player` |
| Method not present on a typed class | It doesn't exist. Look it up (the class reference, or `ClassDB.class_has_method(&"Sprite2D", &"name")` in a headless script); don't guess another name |
| Variant from a Dictionary or JSON | Read it through a typed accessor: `var hp: int = data.get("hp", 0)`, with the type checks in `godot-data-driven` |
| Unused parameter in a callback | Prefix it: `_delta` |

When a dynamic call is the design (a plugin API without types, `Object.call` on mod content), silence that line only, and say why:

```gdscript
@warning_ignore("unsafe_method_access")  # mods define on_load() without a base class
mod.on_load()
```

For a block, `@warning_ignore_start("unsafe_method_access")` … `@warning_ignore_restore("unsafe_method_access")`. Never lower a level in `project.godot` to make a change pass; that hides the same mistake everywhere.

## 3. Check every script

`scripts/check_project.py` parses every `.gd` in the project (except `addons/` and `.godot/`) with the project's own warning levels, and exits 1 with the errors if any file fails:

```bash
python3 scripts/check_project.py path/to/project          # uses $GODOT or `godot`
```

It imports the project first when `.godot/` is missing, so `class_name` types resolve. Under the hood it runs `godot --headless --path PROJECT --check-only --script res://file.gd` per file; that command's exit code is the real signal (`1` on any error). Parsing doesn't run the game: add a headless run or tests (`godot-gdscript-headless-testing` in the `godot` plugin) for behavior.

Run it after every batch of GDScript edits, before saying the change works. In CI, run it after installing Godot, like the repo's own workflow does.

## 4. Existing projects

Turning everything to `2` at once can stop a big project from loading. Instead:
1. Set the warnings to `1`, run the project once, and count them per file in the Output panel or the check script.
2. Fix the files you're touching anyway. Raise each warning to `2` once it's at zero.
3. Raise `unsafe_method_access` and `unsafe_property_access` first: they catch real bugs. `untyped_declaration` is the long tail.

Don't type a whole project in one diff the user didn't ask for. Strict checks are worth it on the files that change.
