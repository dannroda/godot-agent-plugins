# Changelog

## 0.4.0

Lessons from a trailer session on a Godot 4.5.1 pixel-art metroidvania.

| Skill | Change | Lesson |
|---|---|---|
| godot-trailer | Brief asks "Who plays the takes?" (a person, by default for action games) | Scripted play with an enemy-aware autopilot never produced convincing combat or climaxes |
| godot-capture | Record a person's inputs and replay them under Movie Maker is the primary path (`scripts/replay_rec.gd`, `references/replay.md`). The scripted driver stays for UI, walking and title cards | Same |
| both | Switch to a person playing after two failed scripted attempts | Many scripted iterations were spent before switching |
| godot-capture | Run the binary that matches `config/features`, never `godot` on PATH. Reproduce errors on that version before calling them game bugs | 4.7.2 raised typed-return errors on a 4.5 project, which were reported as a game bug |
| godot-trailer | Brief asks what the player has in each area and what must not be shown. Shots use only what's unlocked where they're shot | Abilities were granted with debug commands in areas the player reaches before them |
| godot-capture | Find out how the game scales its view before changing resolution; `viewport_width`/`height` dropped from the default `override.cfg` | 1920x1080 showed area beyond the room in a game that upscales a per-room SubViewport |
| godot-capture | `--resolution` row corrected: ignored with stretch mode `viewport`. With `canvas_items` it sets the size on 4.5.1, but not on 4.7.2 under Xvfb | The old row held only for `viewport` |
| godot-capture | No crop or zoom in post for pixel art: a native 1920x1080 SubViewport sharing `world_2d` copies the game camera on `frame_pre_draw`, or follows with an integer zoom | Upscaled pixel art; the native view needs no game changes |
| godot-capture | Determinism checklist and caveats for record-and-replay (`references/replay.md`) | A 28 s boss fight stayed in sync for 1700 frames with these rules |
| godot-capture | `--fixed-fps` ignores `max_fps`: live play is real-time only with vsync on a 60 Hz display | Measured: 300 frames in 0.5 s without vsync on 4.5.1 and 4.7.2 |
| godot-trailer | Check room triggers and the spawn point; enter as a player would, or run setup at fixed frames in both modes | A debug teleport put the player beside a trigger that killed them on spawn |
| godot-trailer | End card: title and one action ("Wishlist on Steam", or "Free demo on Steam"); no URL or platforms. Brief asks "Is there a public demo?" | The user found the URL and "PC" pointless on the card |
| godot-trailer | `references/genres.md` with metroidvania notes | The user's genre guidance; the default structure stays generic |
| godot-capture | Copy without `.git`, build output or secrets; a custom user dir in `override.cfg`; an open editor may rewrite `project.godot` | Keep real saves untouched, and don't blame the capture for editor writes |
| godot-capture | Contact sheets start at the first gameplay frame; `scripts/take_strips.sh` stacks one 1 fps strip per take | Reading many sheets per take was costly |
| godot-capture | `movie_writer/mjpeg_quality` replaced with `movie_writer/video_quality` | The old key had no effect on 4.5.1: same file size as the default |
