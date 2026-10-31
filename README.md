# Godot Agent plugins

Skills for coding agents working on Godot 4 games. They come from the [Godot Agent Harness](https://github.com/dannroda/godot-agent) project. Each one is a plain `SKILL.md` in the [Agent Skills](https://agentskills.io) format, so they work in Codex, Cursor, Gemini CLI, OpenCode, Claude Code and other agents that read that format.

| Plugin | Skills | For |
|---|---|---|
| `gdscript` | `godot-architecture`, `godot-communication`, `godot-patterns`, `godot-data-driven`, `godot-code-review` | Designing and reviewing GDScript: where code and data live, signals and autoloads, state machines, components, pools, commands, Resources, saves and mods, and a review checklist. |
| `shaders` | `godot-shader-techniques` | Non-trivial Godot 4.6+ shaders: spaces and matrices, custom `light()`, color spaces, normal maps, procedural shapes, vertex effects, post-processing and ray marching. |
| `blender` | `blender-scripting`, `blender-to-godot` | Build and check assets with headless Blender 5 Python, then bring them to Godot with the right axes, collisions, materials and animations. |
| `godot-video` | `godot-capture`, `godot-trailer`, `game-music`, `trailer-music`, `godot-gdd`, `godot-gamedev` | Videos from real footage of your game: repeatable capture, trailers with structured prompt and cue analysis, simple generated music, design document checks and explainers, and development films. Needs only Godot, ffmpeg and Python. |
| `godot-testing` | `godot-visual-test`, `godot-performance` | Check the game by running it: screenshot tests against approved images, and before and after performance comparisons. |

These skills go past the basics. For the basics, the Claude Code marketplace also lists four plugins from [awesome-gamedev-agent-skills](https://github.com/gamedev-skills/awesome-gamedev-agent-skills) (Apache 2.0). They install straight from that repo, so you get its updates; nothing is copied here.

| Plugin | For |
|---|---|
| `godot` | Godot basics: GDScript, nodes and scenes, signals, physics, UI, animation, shaders, export, headless tests. |
| `disciplines` | Engine-neutral practice: game AI, procedural generation, saves, game feel, cameras, input, audio, performance. |
| `genres` | Genre playbooks: platformer, roguelike, RPG, FPS, card game, puzzle… |
| `workflows` | Game jams, fast prototypes, publishing on Steam and itch.io. |

If you already installed them from the awesome-gamedev-agent-skills marketplace, keep one copy: the skills are the same.

## Install

Any agent, with the [skills CLI](https://github.com/vercel-labs/skills), which asks which skills and agents to install for:

```
npx skills add dannroda/godot-agent-plugins
```

Without it, copy the skill folders you want (`plugins/<plugin>/skills/<skill>/`) to the folder your agent reads, often `.agents/skills/` in your project. Skills in `godot-video` name `godot-capture`, so install it with them.

In Claude Code, as plugins:

```
/plugin marketplace add dannroda/godot-agent-plugins
/plugin install gdscript@godot-agent
/plugin install shaders@godot-agent
/plugin install godot@godot-agent
/plugin install blender@godot-agent
/plugin install godot-video@godot-agent
/plugin install godot-testing@godot-agent
```

Or from a terminal: `claude plugin marketplace add dannroda/godot-agent-plugins`, then `claude plugin install gdscript@godot-agent`.

## Sources

The skills cite two books for further reading, by chapter and page: *Godot 4 Best Practices* and *The Godot Shaders Bible*. The text and code are original; they summarize and check the ideas against the engine (shader facts are compile-checked on Godot 4.6, 4.7 and 4.8). Buy the books for the full explanations.

The `blender`, `godot-video` and `godot-testing` facts were checked by running them on Blender 5.2.3, Godot 4.7.2 and 4.8 beta 2, and ffmpeg 9.0.

The skills work in any agent, but they've only been tested on Linux. The commands that record or test the game with no visible window use `gamescope` or Xvfb, which are Linux-only; on other systems, run the game normally and don't touch the mouse.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE)
