---
name: "godot-performance"
description: "Use when checking whether a change made a Godot 4 game slower or heavier, or measuring a scene: frame time, GPU time, script time, draw calls, primitives, nodes, memory, before and after comparisons, FPS caps that hide problems, and noisy timings. Not a guide to optimizing; it tells you what changed."
---

# Godot performance

This runs the same stretch of the game before and after a change, and compares the reports. Checked on Godot 4.7.2 with a real Forward+ game.

## Set up

Work on a copy of the project, and use the two scripts in this skill's `scripts/` folder.

1. Copy `scripts/perf_probe.gd` into the copy. Edit `STEPS` so the run reaches the state you care about (a big battle, a full menu) before `WARMUP_FRAMES` ends. The warmup skips loading and first-use shader compilation.
2. Add `override.cfg` at the root of the copy:

   ```ini
   [autoload]
   PerfProbe="*res://perf_probe.gd"
   ```
3. Import once: `godot --headless --import --path copy`

## Measure

Run this for the version before and the version after, with nothing else heavy on the machine:

```bash
godot --disable-vsync --path copy --fixed-fps 60 -- "$PWD/before.json"
```

On Linux, this runs on the GPU with no window on the desktop:

```bash
ENABLE_GAMESCOPE_WSI=0 gamescope --backend headless -W 1600 -H 900 -w 1600 -h 900 -- godot --disable-vsync --path copy --fixed-fps 60 -- "$PWD/before.json"
```

Both flags matter:

| Without | What happens |
|---|---|
| `--fixed-fps` | Game time follows real time, so a faster run reaches a different game state at the same frame. Node counts varied from 552 to 579. With it, draw calls, primitives and nodes matched exactly on every run. It doesn't slow frames down: they still take as long as they need. |
| An uncapped frame rate | Frame time just reads the cap. Under gamescope's default presentation it stayed at 16.66 ms, even with `--disable-vsync`, and hid 885 extra draw calls. `ENABLE_GAMESCOPE_WSI=0` removes the cap (about 7.8 ms on the same scene). A median sitting at exactly 16.67 or 6.94 ms means a cap, not a measurement. |

`--headless` doesn't render, so it says nothing about graphics.

## Compare

```bash
godot --headless --script <skill>/scripts/compare_perf.gd -- before.json after.json
```

| Exit code | Meaning |
|---|---|
| 0 | Nothing got worse beyond the limits |
| 1 | At least one metric got worse |
| 2 | Bad input, or the runs can't be compared: another GPU, renderer or size, or the second run lost over half its nodes or draw calls. A game that fails to load produces a very fast, empty report, so read the run's errors too. |

Limits default to `--time-percent=10` and `--count-percent=1`.

## Read the numbers

| Metric | Measures | On the test game |
|---|---|---|
| `script_ms` | `_process` and `_physics_process` in all scripts | Median 1.00 to 1.04 ms across runs. A 2 ms loop raised it 189%, while frame time rose 1.3%. |
| `gpu_ms` | GPU time for the frame | Median varied under 1% |
| `frame_ms` | Full frame | Median varied about 2% in a quiet session, and up to 5% across all sessions. It hides CPU work when the GPU sets the pace, so watch all three. |
| `draw_calls`, `primitives`, `nodes` | Work submitted, scene size | Exact on every run. The most reliable signal for comparing. |
| `static_memory_mb`, `video_memory_mb` | Memory | Stable |
| `orphan_nodes` | Nodes out of the tree that nobody freed | Reported at the end of the run. A number that grows on a longer run suggests a leak. |

p99 and max are printed for reference and never fail the check. p99 moved more than 10% between runs of unchanged code. Godot's `TIME_PROCESS` monitor isn't used since it moved up to 68% the same way. To study a stutter, compare p99 over several runs on each side.

## Report it honestly

- Say what you measured: scene or state, GPU, renderer and resolution. Compare only like with like. Absolute numbers on this machine say little about a player's machine.
- A run from the editor binary includes debug overhead, which is why this is good for before and after comparisons, not for promising a frame rate. For that, measure an exported release build on target hardware.
- Rerun once if a time metric fails narrowly. Exact counts need no rerun.
- More draw calls aren't automatically a bug. Say what changed and what it costs, and let the user judge the tradeoff.
- To find why, use the editor's profiler and visual profiler. This skill only tells you that something changed.
