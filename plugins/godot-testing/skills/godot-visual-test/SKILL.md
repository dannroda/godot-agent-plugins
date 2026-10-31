---
name: "godot-visual-test"
description: "Use when you need to see whether a change altered how a Godot 4 game looks: screenshot or visual regression tests, comparing against approved baseline images, producing a diff, or checking UI, lighting, materials and shaders after a refactor. Covers nondeterminism from the mouse, random seeds and different GPUs."
---

# Godot visual test

An agent can change a game without seeing it. This plays a scripted run, saves screenshots at chosen frames and compares them, pixel by pixel, with images a person approved.

Checked on Godot 4.7.2 with a real Forward+ game: repeated runs on one machine produced byte-identical PNGs, so the comparison defaults to **zero tolerance**.

## Set up a test

Work on a copy of the project, and use the two scripts in this skill's `scripts/` folder.

1. Copy `scripts/visual_driver.gd` into the project copy. Edit `STEPS` (keyboard input by frame) and `SHOTS` (frame and checkpoint name).
2. Add an `override.cfg` at the root of the copy, which leaves `project.godot` untouched:

   ```ini
   [autoload]
   VisualDriver="*res://visual_driver.gd"
   ```
3. Import once: `godot --headless --import --path copy`

Choose checkpoints that show the thing under test. The test only knows what those frames show: recoloring a part hidden behind another object passed, correctly, because no pixel changed.

## Run it

Don't run on a desktop you're using. On the normal desktop, moving the real mouse over the window changed the image: the game's build cursor followed it, and a test failed with no code change. Use one of these:

| Session | Command | Result |
|---|---|---|
| gamescope (Linux, GPU) | `gamescope --backend headless -W 1600 -H 900 -w 1600 -h 900 -- godot --path copy --fixed-fps 30 -- "$PWD/actual"` | Real GPU and Forward+, no visible window, no mouse. Same pixels as the desktop run. |
| Xvfb (software) | `xvfb-run -a -s '-screen 0 1920x1080x24' godot --path copy --fixed-fps 30 --rendering-driver opengl3 --rendering-method gl_compatibility -- "$PWD/actual"` | Repeatable, but uses the Compatibility renderer, so a Forward+ game looks different (about 80% of pixels changed). It can't test Forward+ visuals. |
| Desktop | `godot --path copy --fixed-fps 30 -- "$PWD/actual"` | Only if nobody touches the mouse. |

`--headless` can't take screenshots since it doesn't render. Vulkan under Xvfb failed with `None of the devices supports both graphics and present queues`. `--fixed-fps` is required, so frame numbers mean the same thing on every run. Give the output folder as an absolute path.

## Compare

```bash
godot --headless --script <skill>/scripts/compare_images.gd -- baseline actual diff
```

| Exit code | Meaning |
|---|---|
| 0 | Every checkpoint matches |
| 1 | A checkpoint differs, is missing from the run, or has no baseline |
| 2 | Bad arguments or an empty baseline folder |

Each failing checkpoint writes an image to `diff/` with changed pixels in red, and the log gives the percent changed, the largest difference and the changed area. A small change can matter: a recolored stripe on a flag changed 0.056% of the image.

Options, to use only after measuring noise from unchanged code:

- `--tolerance=N`: ignore per-channel differences up to N (0 to 255).
- `--max-percent=P`: pass while no more than P% of pixels changed.
- `--ignore=x,y,w,h`: skip a region; repeat as needed. Glow and similar effects spread beyond the object, so a region around the change still left pixels differing by 1.

Loose settings hide real problems: with `--tolerance=8 --max-percent=0.1`, that recolored stripe passed.

## Baselines

- Keep one baseline folder per GPU and renderer, such as `baselines/rx580-forward-plus/`. Other hardware or drivers may round differently, and a different renderer certainly will. Pixel results aren't portable between machines unless you've measured it.
- Before trusting a new baseline, run it twice and compare the runs. If they differ, fix that first (next section).
- Look at each baseline before approving it. It only records what the game did, right or wrong. If you can't view images, ask the user.
- When a test fails, look at the diff. If the change was intended, tell the user and replace that baseline, and say so in the commit. Never replace a baseline just to get the test to pass.

## When two identical runs differ

| Cause | Sign | Fix |
|---|---|---|
| Real mouse | Change around the pointer or a hover state | Use a headless session |
| Random numbers | Objects in other positions. Without `seed()`, the test game's sheep moved | `seed()` in the driver covers the global generator; a `RandomNumberGenerator` the game randomizes needs its own fixed seed |
| Clock time | Changes with time of day | Replace time reads in the copy, or hide that element |
| Threads, loading | Rare, inconsistent changes | Take the shot later, after loading finishes |

Report what the tests covered: which checkpoints, renderer and GPU. A pass means those frames didn't change. It doesn't mean the game plays well, and it says nothing about other scenes.
