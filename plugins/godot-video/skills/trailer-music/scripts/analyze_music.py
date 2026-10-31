#!/usr/bin/env python3
"""Find cut points in a music track (WAV, MP3, OGG, M4A). Needs ffmpeg.

    analyze_music.py music.mp3                                    # tempo candidates and hits; writes nothing
    analyze_music.py music.mp3 --bpm 128 --click music.click.wav  # beat grid, plus a copy with a click to check by ear

Tempo detection is only a suggestion: it can be wrong on music with no steady beat, so a grid needs --bpm.
"""

import argparse
import array
import json
import math
import pathlib
import subprocess
import sys

RATE = 44100
HOP = 441  # the envelope has one value per 10 ms
FPS = RATE / HOP
MIN_BPM, MAX_BPM = 30, 320
GRID_WARNING_RATIO = 0.2  # of a beat


def load_envelope(path):
    """Returns the loudness of the track per 10 ms, and its duration in seconds."""
    decoded = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(RATE), "-f", "s16le", "-"],
        check=True, capture_output=True,
    ).stdout
    samples = array.array("h", decoded[:len(decoded) // 2 * 2])
    envelope = []
    for start in range(0, len(samples), HOP):
        chunk = samples[start:start + HOP]
        envelope.append(math.sqrt(sum(s * s for s in chunk) / len(chunk)))
    return envelope, len(samples) / RATE


def onsets(envelope):
    """Returns how much the loudness rises at each step."""
    return [max(0.0, envelope[i] - envelope[i - 1]) for i in range(1, len(envelope))]


def tempo_candidates(envelope, flux):
    """Returns up to three likely tempos, strongest repeat first. Empty if nothing in the track pulses."""
    if len(flux) < 2 * FPS:
        return []
    mean_level = sum(envelope) / len(envelope)
    # A steady tone or noise barely rises from one step to the next.
    if mean_level < 1.0 or max(flux) / mean_level < 0.25:
        return []
    mean_flux = sum(flux) / len(flux)
    centered = [f - mean_flux for f in flux]
    first_lag, last_lag = int(FPS * 60 / 200), min(int(FPS * 60 / 60) + 1, len(flux) // 2)
    repeat = {
        lag: sum(centered[i] * centered[i + lag] for i in range(len(centered) - lag)) / (len(centered) - lag)
        for lag in range(first_lag - 1, last_lag + 2)
    }
    peaks = [lag for lag in range(first_lag, last_lag + 1)
             if repeat[lag] > 0 and repeat[lag] >= repeat[lag - 1] and repeat[lag] > repeat[lag + 1]]
    candidates = []
    for lag in sorted(peaks, key=repeat.get, reverse=True):
        curve = repeat[lag - 1] - 2 * repeat[lag] + repeat[lag + 1]
        exact_lag = lag + (0.5 * (repeat[lag - 1] - repeat[lag + 1]) / curve if curve else 0.0)
        bpm = round(FPS * 60 / exact_lag, 1)
        if all(abs(bpm - other) > 2 for other in candidates):
            candidates.append(bpm)
        if len(candidates) == 3:
            break
    return candidates


def best_phase(flux, period):
    """Returns the offset, in steps, where a grid of this period catches the most onsets."""
    def score(phase):
        positions = range(int((len(flux) - phase) / period) + 1)
        picks = [max(flux[max(0, round(phase + n * period) - 1):round(phase + n * period) + 2], default=0.0)
                 for n in positions]
        return sum(picks) / len(picks)
    return max(range(max(1, round(period))), key=score)


def find_first_beat(envelope, flux, bpm):
    """Fits the grid to the whole track, then returns its first beat where the track is already sounding."""
    period = FPS * 60 / bpm
    phase = best_phase(flux, period)
    if period - phase < 2.5:  # within 25 ms of the start of the next beat: the same grid
        phase = 0
    threshold = 0.05 * max(envelope, default=0.0)
    position = phase
    while position < len(envelope):
        index = round(position)
        if max(envelope[max(0, index - 2):index + 5], default=0.0) > threshold:
            return round(position / FPS, 3)
        position += period
    return round(phase / FPS, 3)


def grid_offset(flux, bpm, first_beat):
    """Returns the worst distance, in seconds, between the grid and the beat in any quarter of the track."""
    quarter = len(flux) // 4
    if quarter < 1.5 * FPS:
        return None
    period = FPS * 60 / bpm
    beat = 60 / bpm
    worst = 0.0
    for q in range(4):
        found = (q * quarter + best_phase(flux[q * quarter:(q + 1) * quarter], period)) / FPS
        apart = (found - first_beat) % beat
        worst = max(worst, min(apart, beat - apart))
    return worst


def detect_hits(envelope):
    """Returns the times of sharp jumps to near the track's top level, at least 0.8 s apart."""
    if not envelope or max(envelope) <= 0:
        return []
    top = max(envelope)
    hits = []
    for i in range(1, len(envelope)):
        time = i / FPS
        if envelope[i] >= 0.7 * top and envelope[i] - envelope[i - 1] > 0.3 * top:
            if not hits or time - hits[-1] >= 0.8:
                hits.append(round(time, 3))
    return hits


def write_click(track, beats, meter, out):
    """Mixes a click on every beat over the track, higher on the first beat of each bar."""
    clicks_path = pathlib.Path(out).with_suffix(".clicks.raw")
    length = int((beats[-1] + 1) * RATE)
    clicks = array.array("h", bytes(length * 2))
    for number, beat in enumerate(beats):
        pitch = 1760 if number % meter == 0 else 880
        start = int(beat * RATE)
        for i in range(int(0.03 * RATE)):
            if start + i < length:
                clicks[start + i] = int(16000 * math.sin(2 * math.pi * pitch * i / RATE) * (1 - i / (0.03 * RATE)))
    clicks_path.write_bytes(clicks.tobytes())
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", str(track), "-f", "s16le", "-ar", str(RATE), "-ac", "1",
             "-i", str(clicks_path), "-filter_complex", "[0:a][1:a]amix=inputs=2:duration=first:normalize=0",
             str(out)],
            check=True,
        )
    finally:
        clicks_path.unlink()


def analyze(track, bpm=None, first_beat=None, meter=4, click=None, force=False):
    """Without bpm, returns tempo candidates and hits. With bpm, also builds the grid and writes <track>.analysis.json."""
    track = pathlib.Path(track)
    if not track.exists():
        raise FileNotFoundError(f"Track not found: {track}")
    if bpm is not None and not MIN_BPM <= bpm <= MAX_BPM:
        raise ValueError(f"BPM must be between {MIN_BPM} and {MAX_BPM}, got {bpm}")
    if first_beat is not None and (bpm is None or first_beat < 0):
        raise ValueError("--first-beat needs --bpm and can't be negative")
    if click and bpm is None:
        raise ValueError("--click needs --bpm: pick a tempo first")
    if meter not in (3, 4):
        raise ValueError("Meter must be 3 or 4 beats per bar")
    analysis_path = track.with_suffix(".analysis.json")
    if bpm is not None and analysis_path.exists() and not force:
        raise FileExistsError(f"{analysis_path} already exists. Use --force to replace it.")

    envelope, duration = load_envelope(track)
    flux = onsets(envelope)
    candidates = tempo_candidates(envelope, flux)
    hits = detect_hits(envelope)
    result = {
        "source": str(track),
        "duration_seconds": round(duration, 2),
        "bpm": bpm,
        "bpm_candidates": candidates,
        "hits": [{"real_time": hit, "nearest_beat": None} for hit in hits],
        "warnings": [],
    }
    if bpm is None:
        if not candidates:
            result["warnings"].append("No clear pulse found. Ask the user for the tempo, or don't cut to a beat grid.")
        return result

    if first_beat is None:
        first_beat = find_first_beat(envelope, flux, bpm)
    beat = 60 / bpm
    beats = [round(first_beat + n * beat, 3) for n in range(int(max(duration - first_beat, 0) / beat) + 1)
             if first_beat + n * beat < duration]
    offset = grid_offset(flux, bpm, first_beat)
    if offset is not None and offset / beat > GRID_WARNING_RATIO:
        result["warnings"].append(
            f"The grid doesn't fit the track: up to {round(offset * 1000)} ms off a beat. "
            "The BPM may be wrong, the tempo may change, or the beat may be hard to detect. Check it by ear."
        )
    for hit in result["hits"]:
        hit["nearest_beat"] = min(beats, key=lambda b: abs(b - hit["real_time"])) if beats else None
    result.update({
        "meter": meter,
        "first_beat_seconds": first_beat,
        "beat_interval": round(beat, 4),
        "grid_offset_ms": round(offset * 1000) if offset is not None else None,
        "total_beats": len(beats),
        "beats": beats,
        "bars": beats[::meter],
    })
    analysis_path.write_text(json.dumps(result, indent=2))
    if click and beats:
        write_click(track, beats, meter, click)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("track", help="audio file")
    parser.add_argument("--bpm", type=float, help="tempo of the track; needed to build a beat grid")
    parser.add_argument("--first-beat", type=float, help="time of the first beat in seconds, if detection got it wrong")
    parser.add_argument("--meter", type=int, default=4, help="beats per bar: 3 or 4")
    parser.add_argument("--click", help="also write this audio file: the track with a click on every beat")
    parser.add_argument("--force", action="store_true", help="replace an existing .analysis.json")
    parser.add_argument("--json", action="store_true", help="print the full result as JSON")
    args = parser.parse_args()
    try:
        result = analyze(args.track, args.bpm, args.first_beat, args.meter, args.click, args.force)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(result, indent=2))
        return
    print(f"{result['source']}: {result['duration_seconds']} s")
    print(f"Tempo candidates (estimates): {result['bpm_candidates'] or 'none'}")
    if result["bpm"] is None:
        print("Run again with --bpm and --click to build a grid and check it by ear.")
    else:
        print(f"Grid: {result['bpm']} BPM, first beat at {result['first_beat_seconds']} s, {result['total_beats']} beats, "
              f"up to {result['grid_offset_ms']} ms off")
    print(f"Hits: {[hit['real_time'] for hit in result['hits']]}")
    for warning in result["warnings"]:
        print(f"Warning: {warning}")


if __name__ == "__main__":
    main()
