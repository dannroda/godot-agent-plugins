---
name: "godot-capture"
description: "Use when recording footage from a Godot 4 game for any video: Movie Maker (--write-movie), a scripted input driver, setting resolution without editing the project, capture with no display, and ffmpeg recipes to trim, join, add music and export. Used by godot-trailer, godot-gdd and godot-gamedev."
---

# Godot capture

Checked on Godot 4.7.2 and ffmpeg 9.0. This produces repeatable footage from a real run of the game.

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
| No display | `xvfb-run -a -s '-screen 0 1920x1080x24' godot --rendering-driver opengl3 --path copy --write-movie take01.avi --fixed-fps 60`. Software rendering can look different from a GPU, and takes longer. |
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

Cut each take, in a consistent format so they can be joined:

```bash
ffmpeg -y -ss 0.5 -to 3.5 -i take01.avi -an -c:v libx264 -crf 16 -pix_fmt yuv420p -r 60 shot01.mp4
```

Join, with `shots.txt` holding one `file 'shot01.mp4'` line per shot, in order:

```bash
ffmpeg -y -f concat -safe 0 -i shots.txt -c copy picture.mp4
```

Add music, fade the end and export. `-shortest` stops at the shorter input; set fades from the real duration:

```bash
ffmpeg -y -i picture.mp4 -i music.wav -map 0:v -map 1:a -c:v copy -c:a aac -b:a 192k -shortest \
  -af "afade=t=out:st=58:d=2,loudnorm=I=-14:TP=-1:LRA=11" -movflags +faststart final.mp4
```

To keep game sound, cut without `-an`, and mix it with the music using `amix`.

## Check the result

```bash
ffprobe -v error -show_entries format=duration:stream=codec_name,width,height,r_frame_rate -of default=nw=1 final.mp4
ffmpeg -y -i final.mp4 -vf "fps=1/5,scale=480:-1,tile=4x4" -frames:v 1 contact_sheet.png
```

Look at the contact sheet for black frames, wrong shots and unreadable text. If you can't view images, ask the user to check the video. Then a person should watch the whole video with sound: no tool judges pacing or mix.
