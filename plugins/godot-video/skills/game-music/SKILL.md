---
name: "game-music"
description: "Use when a game trailer, devlog or other video needs simple instrumental music and the user has no track: synthesizes it locally from a tempo, mood and section list, with no model, account or network, and with beats at exact times to cut on. Not for songs with vocals, or for a game's finished soundtrack."
---

# Game music

`scripts/make_music.py` writes a simple instrumental track. It needs only Python 3 and takes a few seconds. The result is plain and synthetic: good for a prototype trailer or until there's a real track. Offer to use the user's own music whenever they have it.

Its advantage is timing: the tempo is exact, so a cut placed on a beat stays on the beat.

## 1. Ask what the user wants

Don't pick for them when it matters. Ask these, offering your suggestion for each, and use defaults for what they leave open:

| Choice | Options | Ask |
|---|---|---|
| Sound | `synth`, `chiptune`, `orchestral`, `ambient` | What should it sound like? Offer `chiptune` for retro games. |
| Mood | `tense`, `heroic`, `epic`, `mysterious`, `sad`, `cozy`, `playful` | What should the player feel? |
| Energy over time | The section list below | Should it build slowly, or hit hard from the start? |
| Layers | `drums`, `bass`, `pad`, `arp`, `melody`, `riser`, `impacts` | Anything to leave out, such as no melody under narration? |
| Key, chords, meter | `--key`, `--progression`, `--meter` | Only if they have a musical preference. |

If they're unsure, generate two or three short versions with different sounds or moods and let them choose by ear. It only takes seconds. For a melody they don't like, try other `--seed` values before changing anything else.

## 2. Plan from the edit

Choose a tempo where the cuts fall on beats. One beat lasts `60 / BPM` seconds. With a finished cut list, 120 BPM (0.5 s per beat) suits cuts at multiples of 0.5 s. If a cut misses the grid, move the cut rather than the tempo: shots are easier to change.

Map the video to sections, in beats:

| Section | Sounds like | Use for |
|---|---|---|
| `calm` | Soft chords and arpeggio | Explaining, building, quiet moments |
| `build` | Adds bass and drums, ending in a riser | Rising stakes. Put it right before a `peak` or `end`. |
| `peak` | Full drums and a melody, opens with a boom | The hook and the biggest moments |
| `rest` | Silence, plus any tail still ringing | A held breath before a big hit or the title |
| `end` | One long chord over a boom, no rhythm | The end card |

## 3. Generate

```bash
python3 <skill>/scripts/make_music.py music.wav --bpm 120 --mood tense --sound synth \
  --sections peak:9,calm:12,build:19,peak:9,end:7 --hits 12,15,17
```

- Track length equals the total beats times `60 / BPM`. Here 56 beats make 28 s.
- `--hits` adds an impact at each time, in seconds, snapped to the nearest beat. Use it on the cuts that should land hard.
- `--seed` changes the melody. The same arguments always produce the same file.
- `--key F#` sets the tonic. Each mood has its own default.
- `--progression i,bVI,III,v` sets one chord per bar, repeating. Uppercase Roman numerals are major, lowercase minor, and `b` or `#` shifts one a semitone. Numerals count from the major scale, so the sixth chord of a minor key is `bVI`.
- `--meter 3` makes a waltz feel; the default is 4 beats per bar.
- `--mute drums,melody` leaves out layers. `ambient` mutes `drums`, `bass` and `melody` by default; pass your own list to change that, or `--mute ""` for everything.
- `music.cues.json` lists the time of every beat, bar, section and hit, plus the settings used, so a track can be recreated. Tell the user which settings you chose.

## 4. Check before you call it done

You may not be able to hear the result, so don't describe how it sounds. Measure what you can, and say the rest needs a listen:

```bash
ffmpeg -y -i music.wav -lavfi "showwavespic=s=1400x180:colors=white" wave.png
```

Bursts should line up with the cues, with visibly louder peak sections. For the final video, follow the mixing and checking steps in `godot-capture`. Then ask the user to watch it with sound. If it doesn't fit, ask what feels wrong and change that one choice.

## Boundaries

The script generates every sound itself, with no samples or trained models, so nothing in it comes from another song. Chord progressions like these are common, so it can't promise to be unlike all existing music. If a track matters commercially, have a person review it, and replace it with a composed one.

To check the script after changing it, run `python3 test_make_music.py` in its folder.
