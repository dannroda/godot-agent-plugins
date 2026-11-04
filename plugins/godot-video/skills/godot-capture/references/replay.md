# Record a person, replay under Movie Maker

A person plays the capture copy normally while `scripts/replay_rec.gd` records every input event with its frame. Then the game replays those events under Movie Maker, headless and at 1080p, and checks frame by frame that it still matches the recording.

Validated on Godot 4.5.1, on a pixel-art metroidvania played with keyboard and gamepad: a 28 s boss fight stayed in sync for all 1700 frames. That check replayed real keyboard and gamepad events, not synthetic `InputEventAction` (the scripted driver) and not the mouse. `replay_rec.gd` is a game-agnostic version of that recorder. On a small test project with real X11 key presses, it stayed in sync on 4.5.1 and 4.7.2; its replay recorded 1920x1080 on 4.5.1 but only the 640x360 base size on 4.7.2.

## Flow

```bash
# once per build: copy the project and the script; override.cfg as in SKILL.md, with
#   [autoload] ReplayRec="*res://replay_rec.gd"
# snapshot the capture user dir (the custom_user_dir_name folder) before recording
tar -czf sessions/boss.userdir.tar.gz -C "$USER_DIR" --exclude=logs --exclude=shader_cache .
# record (normal window; F9 marks a moment; close the game to finish)
godot --path copy --fixed-fps 60 -- --replay-mode=record --session="$PWD/sessions/boss"
# before every replay: restore the snapshot
rm -rf "$USER_DIR"/saves && tar -xzf sessions/boss.userdir.tar.gz -C "$USER_DIR"
# replay to video (headless session with GPU, see SKILL.md)
gamescope --backend headless -W 1920 -H 1080 -w 1920 -h 1080 -- \
  godot --path copy --fixed-fps 60 --write-movie "$PWD/sessions/boss/render.avi" -- --replay-mode=replay --session="$PWD/sessions/boss"
```

Fill in the GAME HOOKS section of the script first: RNGs, player, room, setup commands and HUD. Adjust the restore to wherever the game keeps its saves. A replay with `desync.txt` matches the play only up to the time it names. Close the game normally to end a recording: a killed process leaves `events.bin` truncated, and the replay stops at the last complete event.

## Determinism checklist

- `--fixed-fps 60` both when recording and when replaying. `--fixed-fps` ignores `application/run/max_fps`: without vsync, 300 frames ran in 0.5 s on 4.5.1 and 4.7.2. Live play is in real time only when vsync holds it to a 60 Hz display. Before a long session, check that a few seconds of play give about 60 frames per second in `state.csv`.
- Record raw events from `get_tree().root.window_input`, stamped with a frame counter that goes up in `_process` at `process_priority = -1000`.
- On replay, call `Input.parse_input_event` in `_process` for the events stamped with frame k. They flush before frame k+1, as live input does. Inject frame-0 events in `_ready`.
- `Input.use_accumulated_input = false` in both modes.
- Seed the global RNG and every `RandomNumberGenerator`: static ones directly, per-instance ones on `node_added`.
- Snapshot the user dir (saves, settings) when recording starts, and restore it before every replay.
- While recording, log the player's position and room every frame. On replay, compare them and report the first frame that differs.
- Offer `--write-movie` during live play as a fallback: it keeps the game's own camera, and it's the footage to use after a desync.

## Caveats

- A debug console in its own OS window isn't recorded. Put setup commands (new game, teleport, loadout) in the session's `setup.txt`, which runs them at fixed frames in both modes.
- Mouse events are in window coordinates and depend on the window size. Replay is reliable with keyboard or gamepad; menus driven by the mouse may vary.
- Threaded loading or reads of real time (`Time`, OS clocks) can differ between recording and replay. Check the game for them first.
- A session recorded on one build may not replay on another. Note the source commit with each session, and record again after code changes.

## Pixel art at 1080p

The script's replay mode adds a 1920x1080 SubViewport that shares the game's `world_2d`. On `RenderingServer.frame_pre_draw` it sets its `canvas_transform`:

- `game`: `scale(1920 / game_vp.size.x) * game_vp.canvas_transform`, so room zoom, shake and transitions match the game exactly.
- `follow`: centred on the player with an integer zoom, inside the game camera's limits, keeping its offset.

Nearest filtering and pixel snapping are on, and the game needs no changes. In `game` mode, a game view whose width doesn't divide 1920 (1280 px is ×1.5) gives uneven pixels; `follow` with an integer zoom avoids it. Camera segments go in `camera.json` in the session; change them and replay again, without playing again.
