---
name: "godot-capture"
description: "Use when recording footage from a Godot 4 game for any video: Movie Maker (--write-movie), a scripted input driver, setting resolution without editing the project, capture with no display, and ffmpeg recipes to trim, join, add music and export. Used by godot-trailer, godot-gdd and godot-gamedev."
---

# Godot capture

Checked on Godot 4.7.2 and 4.8 beta 2, and ffmpeg 9.0. This produces repeatable footage from a real run of the game.

## Work on a copy

Copy the project and capture from the copy. Capture files never belong in the game, and saves or settings may change during a run. Note the source commit, so you know which build the footage shows.

## Configure with `override.cfg`

Put this at the root of the copy. Godot reads it on top of `project.godot`, which stays untouched:

```ini
[display]
window/size/viewport_width=1920
window/size/viewport_height=1080

[editor]
movie_writer/mjpeg_quality=0.95

[autoload]
CaptureDriver="*res://capture_driver.gd"
```

## Record

```bash
godot --path copy --write-movie take01.avi --fixed-fps 60
```

| Behavior | Detail |
|---|---|
| Output format | `.avi` (MJPEG + PCM audio), or `.png` for a frame sequence plus a `.wav`. `.mp4` aborts: `Can't find movie writer`. |
| Relative output path | Written inside the project folder. |
| `--resolution` | Did not change the recorded size. Use `override.cfg`. |
| `--headless` | Records nothing: a 0-byte file and a null texture error. A renderer is required. |
| Real mouse | Moving the pointer over the window can change the footage, such as hover states and cursors that follow it. Record in a headless session, or don't touch the mouse. |
| Headless session with GPU (Linux) | `gamescope --backend headless -W 1920 -H 1080 -w 1920 -h 1080 -- godot --path copy --write-movie "$PWD/take01.avi" --fixed-fps 60`. Real GPU and Forward+, with no window on the desktop. |
| No GPU or display | `xvfb-run -a -s '-screen 0 1920x1080x24' godot --rendering-driver opengl3 --rendering-method gl_compatibility --path copy --write-movie take01.avi --fixed-fps 60`. This is the Compatibility renderer: a Forward+ game looks different, and Vulkan under Xvfb failed to start. |
| Time | The game runs on fixed time, so slow machines still give smooth video. |
| Ending | `get_tree().quit()` or `--quit-after <frames>` closes the file properly. |

## Input driver

Play through the game's normal input. Keep inputs in a timeline, so a take can be repeated and adjusted. Count in `_process`: with `--fixed-fps 30` and 60 physics ticks per second, `_physics_process` runs twice per video frame.

```gdscript
extends Node

# frame, action, pressed
const TIMELINE := [
	[60, "ui_right", true],
	[150, "ui_right", false],
	[180, "ui_accept", true],
	[186, "ui_accept", false],
]
const LAST_FRAME := 300

var frame := 0

func _ready() -> void:
	seed(12345)

func _process(_delta: float) -> void:
	frame += 1
	for step in TIMELINE:
		if step[0] == frame:
			var event := InputEventAction.new()
			event.action = step[1]
			event.pressed = step[2]
			Input.parse_input_event(event)
	if frame == LAST_FRAME:
		get_tree().quit()
```

`parse_input_event` reaches `_input()` handlers and action polling. `Input.action_press` only updates polling. `seed()` only fixes the global generator: a `RandomNumberGenerator` the game randomizes itself will still vary, as will anything that depends on real time.

A driver may read game state to decide what to press. It must not move the player, skip collisions or set a win flag: the footage is meant to show what the game really does. If a staged view is needed (a debug overlay, a posed shot), label it on screen.

## Assemble with ffmpeg

A 1080p take at the quality above uses about 4.5 MB per second, so check free disk space. To choose cuts, make a sheet with timestamps. Times start at the `-ss` value, so add it back:

```bash
ffmpeg -y -ss 24 -to 52 -i take01.avi -vf "fps=1/2,scale=384:-1,drawtext=text='%{pts\:flt}':x=4:y=4:fontsize=22:fontcolor=white:box=1:boxcolor=black,tile=4x4" -frames:v 1 sheet.png
```

Text cards: `scripts/title_card.gd` in this skill records one with the project's font. Use the same `--fixed-fps` as the takes:

```bash
godot --path copy --fixed-fps 24 --write-movie "$PWD/card.avi" --script <skill>/scripts/title_card.gd -- 3.5 "TITLE" "Subtitle"
```

Choose cuts from the final take. Any change to the run can move them: on the test game, hiding the HUD made the same script finish 2 seconds later, with a different battle.

Code excerpts: `scripts/code_card.gd` records lines straight from the source file, so they can't drift from it. Long lines shrink the text, and it prints a notice when they do:

```bash
godot --path copy --fixed-fps 24 --write-movie "$PWD/code.avi" --script <skill>/scripts/code_card.gd -- 4 "$PWD/copy/player.gd" 88 94
```

Cut each take, in a consistent format so they can be joined (match `-r` to the takes):

```bash
ffmpeg -y -ss 0.5 -to 3.5 -i take01.avi -an -c:v libx264 -crf 16 -pix_fmt yuv420p -r 60 shot01.mp4
```

Join, with `shots.txt` holding one `file 'shot01.mp4'` line per shot, in order:

```bash
ffmpeg -y -f concat -safe 0 -i shots.txt -c copy picture.mp4
```

Add music, fade the end and export. `-shortest` stops at the shorter input; set fades from the real duration:

```bash
ffmpeg -y -i picture.mp4 -i music.wav -map 0:v -map 1:a -c:v copy -c:a aac -b:a 192k -ar 48000 -shortest \
  -af "afade=t=out:st=58:d=2,loudnorm=I=-14:TP=-1:LRA=11,alimiter=limit=0.8:level=false" -movflags +faststart final.mp4
```

Keep `-ar 48000`: `loudnorm` otherwise raises the output to 192 kHz, and the file measured above 0 dBFS. Keep `alimiter` too: a track with strong hits still passed 0 dBFS without it. Leave out `afade` if the track already ends by itself. To keep game sound, cut without `-an`, and mix it with the music using `amix`.

## Check the result

```bash
ffprobe -v error -show_entries format=duration:stream=codec_name,width,height,r_frame_rate -of default=nw=1 final.mp4
ffmpeg -y -i final.mp4 -vf "fps=1/5,scale=480:-1,tile=4x4" -frames:v 1 contact_sheet.png
```

Measure the sound too. `Peak` should stay below 0 dBFS:

```bash
ffmpeg -hide_banner -i final.mp4 -af ebur128=peak=true -f null - 2>&1 | grep -E '^ +(I:|Peak:)'
```

Look at the contact sheet for black frames, wrong shots and unreadable text. The format checks all passed on a video whose title cards were nearly invisible; only the sheet showed it. If you can't view images, ask the user to check the video. Then a person should watch the whole video with sound: no tool judges pacing or mix.
