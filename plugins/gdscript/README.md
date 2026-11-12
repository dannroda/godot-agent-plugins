# gdscript

Skills for designing and reviewing Godot 4 GDScript:

- `godot-architecture`: Node vs Resource vs RefCounted, scenes vs scripts, composition, SOLID, folders and naming.
- `godot-communication`: signals, await lifetimes, deferred calls, EventBus, autoloads and services, init order.
- `godot-patterns`: state machines, strategies, components, spawners and pools, builders, commands and undo.
- `godot-data-driven`: custom Resources and their traps, content databases, JSON/CSV with validation, saves, mods, splitting god classes.
- `godot-code-review`: a review checklist for scripts, scenes and shaders.
- `godot-deslop`: write the smallest GDScript that works, and clean up generated or bloated code without changing behavior. Includes `find_slop.py`, a checker for noise the parser accepts.
- `godot-strict-checks`: warning levels that make the parser reject made-up methods and untyped code, and `check_project.py`, which parses every script headlessly for CI.

`godot-deslop` and `godot-code-review` name `godot-strict-checks`, so install it with them. The scripts need Python 3; `check_project.py` also needs Godot.

Install: `/plugin install gdscript@godot-agent` after `/plugin marketplace add dannroda/godot-agent-plugins`.
