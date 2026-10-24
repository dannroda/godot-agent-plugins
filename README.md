# Godot Agent plugins

Skills for coding agents working on Godot 4 projects, packaged as a [Claude Code](https://code.claude.com) plugin marketplace. They come from the [Godot Agent Harness](https://github.com/dannroda/godot-agent) project but work in any agent that loads Claude Code plugins.

| Plugin | Skills | For |
|---|---|---|
| `gdscript` | `godot-architecture`, `godot-communication`, `godot-patterns`, `godot-data-driven`, `godot-code-review` | Designing and reviewing GDScript: where code and data live, signals and autoloads, state machines, components, pools, commands, Resources, saves and mods, and a review checklist. |
| `shaders` | `godot-shader-techniques` | Non-trivial Godot 4.6+ shaders: spaces and matrices, custom `light()`, color spaces, normal maps, procedural shapes, vertex effects, post-processing and ray marching. |

These skills go past the basics. For the basics of each Godot area (GDScript syntax, nodes, physics, UI, export…) and the headless test runner they mention, also install [awesome-gamedev-agent-skills](https://github.com/gamedev-skills/awesome-gamedev-agent-skills).

## Install

In Claude Code:

```
/plugin marketplace add dannroda/godot-agent-plugins
/plugin install gdscript@godot-agent
/plugin install shaders@godot-agent
```

Or from a terminal: `claude plugin marketplace add dannroda/godot-agent-plugins`, then `claude plugin install gdscript@godot-agent`.

## Sources

The skills cite two books for further reading, by chapter and page: *Godot 4 Best Practices* and *The Godot Shaders Bible*. The text and code are original; they summarize and check the ideas against the engine (shader facts are compile-checked on Godot 4.6, 4.7 and 4.8). Buy the books for the full explanations.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE)
