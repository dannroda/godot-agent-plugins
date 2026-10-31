---
name: "trailer-music"
description: "Use when a game trailer's music will come from outside: an external generator such as the Gemini app, Suno or Udio, or a track the user supplies. Writes the request, then builds a beat grid from the audio, checks it by ear and finds impacts for godot-trailer cut points. Needs ffmpeg and Python. To synthesize simple music locally, use game-music."
---

# Trailer music

Use this skill when the music comes from outside: the Gemini app, Suno, Udio, a composer or a library. It writes the request, then finds cut points in the track you get back. It generates no audio itself. For simple music made locally, with beats at exact times, use `game-music`.

## 1. Design the Trailer Track Structure

A standard trailer track follows an escalating 4-stage arc:
- **Intro (0s – ~6s):** Atmospheric pad, hook motif, low energy. Establishes mood while the premise appears.
- **Buildup (~6s – ~14s):** Driving rhythm enters, BPM locked, percussion rises, stakes escalate.
- **Peak / Climax (~14s – ~24s):** Loudest moment, full instrumentation, brass/synth swells, fastest cut montage.
- **Stinger / Outro (~24s – ~28s):** Abrupt impact, sudden drop into silence or decaying reverb for the title and wishlist end card.

Generate an optimized prompt with:

```bash
python3 <skill>/scripts/prompt_music.py --genre action --bpm 128 --length 30.0 --notes "cyberpunk brass and glitch hits"
```

Available genres: `action`, `sci-fi`, `fantasy`, `horror`, `retro`, `cozy`.

The script outputs:
- **Timeline prompt:** Detailed section-by-section timestamps.
- **Compact prompt:** One concise paragraph constructed from genre, custom notes and target duration, ready to copy into web interfaces (the Gemini app, Suno, Udio).

## 2. Generate or Source the Audio

Copy the compact prompt into the tool the user chooses, such as the Gemini app, Suno or Udio, or use a track they already have. Save the audio in the trailer workspace, such as `trailer/music.mp3`.

Before publishing, have the user read the terms of the tool or library that supplied the track, since commercial use varies. Record the tool, date, prompt and license in `CREDITS.md`.

## 3. Build the Beat Grid

Generators may not follow a requested tempo, and tempo detection can be wrong too. Treat every tempo as a guess until someone has heard it against the music.

1. If the tempo isn't known, list candidates. This writes nothing:

   ```bash
   python3 <skill>/scripts/analyze_music.py trailer/music.mp3
   ```

   If you requested a BPM, try it first, even if it isn't listed: on a Gemini track asked for 120 BPM, the candidates were 60.3, 200.3 and 63.1, and a grid at exactly 120 fit within 10 ms. Otherwise, up to three candidates appear, and they may be half or double the real tempo. An empty list means no clear pulse: ask the user for the tempo, or don't cut to a grid.
2. Build the grid, plus a copy of the track with a click on every beat:

   ```bash
   python3 <skill>/scripts/analyze_music.py trailer/music.mp3 --bpm 128 --click trailer/music.click.wav
   ```

3. If there's a warning that the grid doesn't fit, try the other candidates first. It also appears when the tempo really changes, or when the beat is hard to detect.
4. **Ask the user to listen to the click track.** Clicks should stay with the beat to the end, with the higher click on the first beat of each bar. A passing check can't confirm this: it can't tell one beat of a bar from another, and you may not be able to hear it. Until they confirm, report the grid as unverified.
5. To fix what they hear, pass another `--bpm`, set the first beat with `--first-beat 0.52`, or use `--meter 3`. Add `--force` to replace the earlier analysis.

If the tempo changes during the track, one grid can't fit it. Cut by ear, or on `hits`, instead.

`trailer/music.analysis.json` holds:

- `beats` and `bars`: times to cut on, starting from `first_beat_seconds`.
- `grid_offset_ms`: the largest distance found between the grid and the beat in any quarter of the track.
- `hits`: sharp jumps in volume, each with its `real_time` and `nearest_beat`. They don't depend on the grid. In a dense track many are just strong drum hits, so listen to choose the ones that matter; a jump after a quiet section is usually the one to build around.
- `warnings`, plus `bpm_candidates`.

## 4. Fit the Track to the Edit

Generators may ignore the requested length: that Gemini track came back at 125 s for a 28 s request. Expect to edit it:

1. Find the moment to build around, such as the first big hit, and match it to the biggest moment in the story, not just any cut. Check the exact frame, then start the excerpt so the hit lands on it. To put a hit at 24.14 s on a moment at 12 s, start at 12.12 s, since a hit can register slightly before its measured time.
2. Offer a version with no join whenever possible: the last stretch of the track, ending naturally, or a fade over the end card. Joins are the riskiest edit here.
3. If you need the track's real ending too, join only on a bar line, at the same point in the phrase on both sides: jump by a whole multiple of 4 bars, and try to place it right after a big hit. Compare the harmony and level on each side if you have the tools. A join that ignored this was audibly wrong on the test track; one that followed it was found by checking many pairs.

   ```bash
   ffmpeg -y -ss 7.14 -to 26.205 -i music.mp3 -c:a pcm_s16le part1.wav
   ffmpeg -y -ss 113.955 -to 123.14 -i music.mp3 -c:a pcm_s16le part2.wav
   ffmpeg -y -i part1.wav -i part2.wav -filter_complex "[0][1]acrossfade=d=0.25:c1=qsin:c2=qsin" edit.wav
   ```

   Each side overlaps the bar line by half the fade, here 0.125 s. The fade shortens the total by its own length.
4. Numbers can't tell whether a join sounds right. Ask the user to listen, and give them a no-join version to compare.

## 5. Feed into `godot-trailer`

Use `music.analysis.json` when building `shots.md` in `godot-trailer`:
- Place regular shot cuts on **bars** (starting from `first_beat_seconds`).
- Place the climax montage on **beats** (fast cuts every beat or half-beat).
- Align big moments and title drops with `real_time` from `hits`.
- Align the end card exactly with the final **stinger**.

## 6. Check Before Final Render

1. Verify waveforms and detected peaks:
   ```bash
   ffmpeg -y -i trailer/music.wav -lavfi "showwavespic=s=1200x200:colors=cyan" trailer/wave.png
   ```
2. Check that the audio ends cleanly without abrupt clicks or unexpected mid-bar cuts.
3. Follow the mixing and loudness checks in `godot-capture`.
4. Confirm that the user has checked the terms, and that `CREDITS.md` is complete.

## Checking the Scripts

Run `python3 test_trailer_music.py` in the `scripts` folder after changing them. Cases that use real synthesized music are skipped if `game-music` isn't installed.

Timings were checked on tracks made by `game-music`, with known beats, and on one track from the Gemini app, where tempos from 119.5 to 120.5 BPM could be told apart. One track says little about other generators or genres.
