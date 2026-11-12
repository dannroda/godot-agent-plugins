---
name: "godot-deslop"
description: "Use when writing GDScript and you want the smallest code that works, or when cleaning up generated or bloated Godot 4 code without changing behavior: editor template comments and empty callbacks, comments that restate code, defensive null checks that hide broken scenes, has_method duck typing, hand-rolled timers, tweens, input and pausing the engine already provides, Godot 3 leftovers, Managers and layers with one caller, and exports or signals nobody uses. Includes a checker script."
---

# Remove slop from GDScript

Slop is code that runs but shouldn't exist: noise an agent (or a tired person) adds by habit. It hides the lines that matter, and much of it hides bugs. This skill covers what to cut and what to write instead. Checked on Godot 4.7.2.

Related: `godot-strict-checks` makes the parser reject made-up members and untyped code; `godot-code-review` covers architecture and engine bugs; `godot-patterns` says when a pattern is worth it.

## Workflow

1. **Parser first.** Run `godot-strict-checks`. Fix what it reports before anything else; a made-up method is worse than a style problem.
2. **Checker.** `python3 scripts/find_slop.py res_folder_or_files...` flags what the parser accepts (rules below). It skips `addons/` and `.godot/`, and exits 1 when it finds something. Put `# noslop` on a line that's meant to stay, with the reason.
3. **Read the rest by hand** with the tables below. The script can't see a comment that restates code or a Manager with one caller.
4. **Prove nothing changed.** Re-run the parser check, then run the scene or the tests. A cleanup that changes behavior is a bug, not a cleanup.

Scope: clean the code the task touches. Don't sweep the whole project in a diff the user asked for something else; offer it as its own change.

## While writing: don't add it

- Write the feature the task needs. No "for later" parameters, exports, signals, flags or settings.
- Look for what the engine or the project already has before writing it (table below). A built-in node or method beats twenty lines of `_process`.
- Type everything, so the parser can check it. Never guess an API: if you aren't sure a method exists in Godot 4, check the class reference or `ClassDB.class_has_method()`.
- A required child is required. Let a missing one fail loudly; don't wrap it in `if sprite:`.
- Comment the why, once. Never the what.
- Delete the debug `print()` calls before you finish.

## `find_slop.py` rules

| Rule | Slop | Instead |
|---|---|---|
| `template-comment` | `# Called when the node enters the scene tree for the first time.`, `# Called every frame. 'delta' is …` | Delete. They're the editor's new-script template. |
| `empty-callback` | `_ready`, `_process`, `_input`… whose body is only `pass` | Delete. An empty `_process` or `_physics_process` still turns on per-frame processing (`is_processing()` is `true`), so it costs a call every frame on every instance. |
| `null-and-valid` | `x != null and is_instance_valid(x)` | `is_instance_valid(x)`; it's already `false` for `null`. |
| `bool-compare` | `if dead == true`, `!= false` | `if dead`, `if not dead`. Skipped on lines with `get(`: there `== false` also rules out `null`. |
| `has-method` | `if body.has_method("take_damage")` | `var hurtbox := area as Hurtbox` then `if hurtbox:`, or `is Type`. A typo in the string fails silently. Keep it for untyped plugin or mod APIs. Skipped in `test_*.gd` files, where checking that an API exists is the point. |
| `root-path` | `get_node("/root/Main/HUD")`, `get_tree().root.get_node(…)` | The autoload by name, an `@export`, or `setup()` injection (`godot-communication`). The path breaks when the scene moves and the scene won't run alone (F6). |
| `tween-new` | `Tween.new()` (Godot 3 style) | `create_tween()`. `Tween.new()` parses, then errors at runtime ("Tween can't be created directly") and the tween is invalid. |
| `placeholder` | `# TODO: implement`, `# your code here`, a comment that's only `...` | Implement it, or delete the stub and say what's missing. A plain `# TODO: <specific thing>` is fine. |

## The engine already does it

| Hand-rolled | Use |
|---|---|
| `elapsed += delta; if elapsed >= 2.0:` in `_process` | A `Timer` node, or `await get_tree().create_timer(2.0, false).timeout` (`false` so it stops while paused) |
| Moving a value toward a target over time, frame by frame, for a one-off effect | `create_tween().tween_property(self, "modulate:a", 0.0, 0.3)` |
| `if x > target: x -= step` / `if x < target: x += step` | `x = move_toward(x, target, step)` |
| An `if`/`elif` clamp | `clampf()`, `clampi()`, `clamp()` |
| Four `Input.is_action_pressed` checks building a direction, then `.normalized()` | `Input.get_vector(&"left", &"right", &"up", &"down")` (already clamped to length 1) |
| `Input.is_key_pressed(KEY_A)` in gameplay | An Input Map action; players can rebind it |
| An `is_paused` flag checked at the top of every `_process` | `get_tree().paused` plus each node's `process_mode` |
| `static var instance` singleton | An autoload, if it must be global at all (`godot-communication`) |
| An array of callables you call by hand as "listeners" | A signal |
| `load("res://scenes/" + name + ".tscn")` | `@export var scene: PackedScene`, or a `const` `preload` |
| `await get_tree().process_frame` to dodge "can't change this during a physics callback" | `call_deferred()` / `set_deferred()` |
| Code that sets sprite frames on a timer | `AnimatedSprite2D` or `AnimationPlayer` |

## Defensive noise

Validate at trust boundaries: save files, JSON, mods, network, user text (`godot-data-driven`). Inside your own code, checks that can't fail only hide mistakes:

| Noise | Why it hurts | Instead |
|---|---|---|
| `if not sprite: return` for an `@onready` child the scene must have | A broken scene runs silently wrong | No check. Or `assert(sprite)`, or `_get_configuration_warnings()` in a `@tool` script for an `@export` slot |
| `push_error("…"); return null` for a call with a wrong argument from your own code | The caller carries on with `null` | `assert()` with a message; it stops in debug builds |
| `typeof(x) == TYPE_INT` checks on a typed parameter | The type annotation already guarantees it | Delete |
| `is_instance_valid(self)` | `self` can't be freed while its own code runs | Delete |
| `if signal_x.is_connected(f): signal_x.disconnect(f)` around every disconnect | Usually means nobody knows who connects | Connect in one place; disconnect there |

`is_instance_valid()` after an `await` is not noise: the object may have been freed while waiting (`godot-communication`).

## Structure with one caller

| Slop | Instead |
|---|---|
| `PlayerManager`, `ScoreHandler`, `InputService` used by one script | Inline it into that script |
| A base class or `@abstract` contract with one implementation and no second one planned | The concrete class |
| A config Resource holding one value | An `@export` on the node |
| An EventBus signal between a parent and its child | Call down, signal up, directly |
| A 60-line script split into five files | One file |
| `@export` slots, signals or parameters nobody sets, connects or passes | Delete (`unused_signal` catches the signals) |
| Getter/setter pairs that only read and write the backing field | A plain `var` |

Add the abstraction when the second or third real case shows up (`godot-patterns`).

## Comments

- Delete comments that restate the line below (`# Set the velocity` over `velocity = …`), section banners in short files, and a `##` doc on every private helper.
- Keep comments that give a reason the code can't show: a workaround, an engine quirk, a unit, a tuned number's origin.
- `##` doc comments on a `class_name` script's public members are worth keeping: they show in the editor's built-in help.

## Godot 3 leftovers

The parser rejects removed syntax: `yield`, `onready var`, `export var`, `setget`, `KinematicBody2D`, `connect("sig", self, "m")`, `rand_range()`, `deg2rad()`. It does **not** reject old method names on typed engine objects with default warnings (`get_tree().change_scene()`, `packed.instance()`); `godot-strict-checks` makes those errors. `Tween.new()` only fails at runtime; the checker flags it.
