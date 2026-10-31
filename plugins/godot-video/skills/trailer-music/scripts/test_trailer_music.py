#!/usr/bin/env python3
"""Self-check for trailer-music: python3 test_trailer_music.py. Music cases need the game-music skill, and are skipped without it."""

import array
import json
import math
import pathlib
import random
import sys
import tempfile
import wave

import analyze_music
import prompt_music

# Skills can be installed one at a time, so game-music may be missing.
GAME_MUSIC_SCRIPTS = pathlib.Path(__file__).resolve().parent.parent.parent / "game-music" / "scripts"
sys.path.insert(0, str(GAME_MUSIC_SCRIPTS))
try:
    import make_music
except ImportError:
    make_music = None


def synthesize_clicks(wav_path: pathlib.Path, bpm: float, duration_sec: float, start_delay_sec: float = 0.0, hits=None, is_silent: bool = False):
    """Synthesize clean sine clicks/bursts for controlled baseline tests."""
    sample_rate = 44100
    total_frames = int(duration_sec * sample_rate)
    samples = array.array("h", [0] * total_frames)

    if not is_silent:
        beat_interval = 60.0 / bpm
        cur_t = start_delay_sec

        while cur_t < duration_sec:
            start_frame = int(cur_t * sample_rate)
            burst_frames = int(0.04 * sample_rate)
            for f in range(burst_frames):
                if start_frame + f < total_frames:
                    val = math.sin(2 * math.pi * 90.0 * (f / sample_rate)) * 14000 * (1.0 - (f / burst_frames))
                    samples[start_frame + f] = int(val)
            cur_t += beat_interval

        if hits:
            for hit_t in hits:
                start_frame = int(hit_t * sample_rate)
                burst_frames = int(0.08 * sample_rate)
                for f in range(burst_frames):
                    if start_frame + f < total_frames:
                        val = math.sin(2 * math.pi * 60.0 * (f / sample_rate)) * 26000 * (1.0 - (f / burst_frames))
                        samples[start_frame + f] = max(-32767, min(32767, samples[start_frame + f] + int(val)))

    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(samples.tobytes())


def synthesize_oscillating_tempo(wav_path: pathlib.Path, duration_sec: float = 14.0):
    """Synthesize audio with an oscillating tempo (drifting by +/- 35% beat to beat)."""
    sample_rate = 44100
    total_frames = int(duration_sec * sample_rate)
    samples = array.array("h", [0] * total_frames)
    t = 0.0
    k = 0
    while t < duration_sec:
        interval = 0.5 + 0.18 * math.sin(k * 0.7)
        f_start = int(t * sample_rate)
        burst_frames = int(0.04 * sample_rate)
        for f in range(burst_frames):
            if f_start + f < total_frames:
                val = math.sin(2 * math.pi * 90.0 * (f / sample_rate)) * 14000 * (1.0 - (f / burst_frames))
                samples[f_start + f] = int(val)
        t += interval
        k += 1

    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(samples.tobytes())


def synthesize_continuous_signal(wav_path: pathlib.Path, kind: str = "noise", duration_sec: float = 5.0):
    """Synthesize continuous un-rhythmic audio: pure white noise or a 440 Hz pure sine wave."""
    sample_rate = 44100
    total_frames = int(duration_sec * sample_rate)
    samples = array.array("h")
    if kind == "noise":
        samples = array.array("h", [int((random.random() * 2 - 1) * 10000) for _ in range(total_frames)])
    elif kind == "tone":
        samples = array.array("h", [int(math.sin(2 * math.pi * 440.0 * (i / sample_rate)) * 10000) for i in range(total_frames)])

    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(samples.tobytes())


def test_prompt_consistency_and_validation():
    # 1. Negative inputs must be rejected
    for bad_bpm in (0, -10, -120):
        try:
            prompt_music.generate_prompt("action", bpm=bad_bpm)
            assert False, f"Should reject negative or zero BPM: {bad_bpm}"
        except ValueError:
            pass

    for bad_len in (0, -5.0, -30.0):
        try:
            prompt_music.generate_prompt("action", length=bad_len)
            assert False, f"Should reject negative or zero length: {bad_len}"
        except ValueError:
            pass

    # 2. Cozy with negative constraints must omit contradictory instruments & pacing
    res = prompt_music.generate_prompt("cozy", extra_notes="ukulele only, no drums")
    full = res["prompt_full"].lower()
    compact = res["prompt_compact"].lower()

    assert "ukulele only, no drums" in full
    assert "ukulele only, no drums" in compact
    # Must not contain contradictory default instruments or drum driving phrasing
    assert "acoustic guitar" not in compact and "marimba" not in compact and "brass" not in compact
    assert "driving rhythm" not in compact
    assert "massive climax" not in compact
    assert "wishlist" not in full and "montage" not in full
    print("test_prompt_consistency_and_validation: passed")


def expect_rejected(error, **options):
    try:
        analyze_music.analyze(**options)
    except error:
        return
    raise AssertionError(f"should be rejected: {options}")


def phase_error_ms(first_beat, bpm, offset=0.0):
    beat = 60 / bpm
    apart = (first_beat - offset) % beat
    return min(apart, beat - apart) * 1000


def test_invalid_input():
    with tempfile.TemporaryDirectory() as tmpdir:
        wav = pathlib.Path(tmpdir) / "test.wav"
        synthesize_clicks(wav, 120.0, 4.0)
        for bad_bpm in (0, -5, 0.0001, 1000):
            expect_rejected(ValueError, track=wav, bpm=bad_bpm)
        expect_rejected(ValueError, track=wav, first_beat=1.0)
        expect_rejected(ValueError, track=wav, bpm=120, first_beat=-1)
        expect_rejected(ValueError, track=wav, click="out.wav")
        expect_rejected(ValueError, track=wav, bpm=120, meter=5)
        expect_rejected(FileNotFoundError, track=pathlib.Path(tmpdir) / "missing.wav")
    print("test_invalid_input: passed")


def test_no_pulse_gives_no_candidates():
    with tempfile.TemporaryDirectory() as tmpdir:
        for kind in ("noise", "tone"):
            wav = pathlib.Path(tmpdir) / f"{kind}.wav"
            synthesize_continuous_signal(wav, kind=kind)
            data = analyze_music.analyze(wav)
            assert data["bpm_candidates"] == [] and data["warnings"], kind
        wav = pathlib.Path(tmpdir) / "silent.wav"
        synthesize_clicks(wav, 120.0, 6.0, is_silent=True)
        assert analyze_music.analyze(wav)["bpm_candidates"] == []
    print("test_no_pulse_gives_no_candidates: passed")


def test_no_grid_without_bpm():
    with tempfile.TemporaryDirectory() as tmpdir:
        wav = pathlib.Path(tmpdir) / "clicks.wav"
        synthesize_clicks(wav, 120.0, 10.0, hits=[3.12])
        data = analyze_music.analyze(wav)
        assert data["bpm"] is None and "beats" not in data
        assert any(abs(c - 120) < 1 for c in data["bpm_candidates"]), data["bpm_candidates"]
        assert any(abs(h["real_time"] - 3.12) < 0.03 for h in data["hits"]) and data["hits"][0]["nearest_beat"] is None
        assert not wav.with_suffix(".analysis.json").exists(), "an estimate writes nothing"
    print("test_no_grid_without_bpm: passed")


def test_grid_late_start_and_first_beat_override():
    with tempfile.TemporaryDirectory() as tmpdir:
        wav = pathlib.Path(tmpdir) / "late.wav"
        synthesize_clicks(wav, bpm=100.0, duration_sec=14.0, start_delay_sec=1.5)
        data = analyze_music.analyze(wav, bpm=100)
        assert abs(data["first_beat_seconds"] - 1.5) < 0.03, data["first_beat_seconds"]
        assert data["beats"][0] == data["first_beat_seconds"] and abs(data["beats"][1] - data["beats"][0] - 0.6) < 0.002
        assert not data["warnings"], data["warnings"]
        assert data["bars"] == data["beats"][::4]
        data = analyze_music.analyze(wav, bpm=100, first_beat=0.9, meter=3, force=True)
        assert data["beats"][0] == 0.9 and data["bars"] == data["beats"][::3]
    print("test_grid_late_start_and_first_beat_override: passed")


def test_grid_warns_when_it_does_not_fit():
    with tempfile.TemporaryDirectory() as tmpdir:
        steady = pathlib.Path(tmpdir) / "steady.wav"
        synthesize_clicks(steady, 120.0, 30.0)
        assert not analyze_music.analyze(steady, bpm=120)["warnings"]
        for wrong in (110, 126):
            assert analyze_music.analyze(steady, bpm=wrong, force=True)["warnings"], wrong
        changing = pathlib.Path(tmpdir) / "changing.wav"
        synthesize_oscillating_tempo(changing, duration_sec=14.0)
        assert analyze_music.analyze(changing, bpm=120)["warnings"]
    print("test_grid_warns_when_it_does_not_fit: passed")


def test_click_lands_on_the_beats():
    with tempfile.TemporaryDirectory() as tmpdir:
        wav = pathlib.Path(tmpdir) / "silent.wav"
        out = pathlib.Path(tmpdir) / "click.wav"
        synthesize_clicks(wav, 120.0, 4.0, is_silent=True)
        analyze_music.analyze(wav, bpm=120, first_beat=0.25, click=out)
        with wave.open(str(out)) as source:
            assert source.getframerate() == 44100
            samples = array.array("h", source.readframes(source.getnframes()))
        step = len(samples) // (source.getnframes())
        def peak(seconds):
            start = int(seconds * 44100) * step
            return max(abs(v) for v in samples[start:start + 400 * step])
        assert peak(0.25) > 3000 and peak(0.75) > 3000
        assert peak(0.5) == 0 and peak(0.0) == 0
        assert not list(pathlib.Path(tmpdir).glob("*.raw")), "no temporary file left"
    print("test_click_lands_on_the_beats: passed")


def test_refuses_to_overwrite():
    with tempfile.TemporaryDirectory() as tmpdir:
        wav = pathlib.Path(tmpdir) / "track.wav"
        synthesize_clicks(wav, 120.0, 6.0)
        analyze_music.analyze(wav, bpm=120)
        saved = json.loads(wav.with_suffix(".analysis.json").read_text())
        assert saved["bpm"] == 120 and "bpm_confidence" not in saved
        expect_rejected(FileExistsError, track=wav, bpm=120)
        analyze_music.analyze(wav, bpm=120, force=True)
    print("test_refuses_to_overwrite: passed")


def test_with_music():
    if make_music is None:
        print("test_with_music: skipped, game-music is not installed")
        return
    cases = [
        (160, "tense", "synth", "calm:8,build:8,peak:16,end:4"),
        (120, "tense", "chiptune", "calm:8,build:8,peak:16,end:4"),
        (90, "tense", "synth", "calm:8,build:8,peak:16,end:4"),
    ]
    with tempfile.TemporaryDirectory() as tmpdir:
        for bpm, mood, sound, sections in cases:
            wav = pathlib.Path(tmpdir) / f"{sound}_{bpm}.wav"
            make_music.build(wav, bpm, mood, sections, sound=sound)
            data = analyze_music.analyze(wav, bpm=bpm)
            assert not data["warnings"], (bpm, sound, data["warnings"])
            assert phase_error_ms(data["first_beat_seconds"], bpm) < 30, (bpm, sound, data["first_beat_seconds"])
        wav = pathlib.Path(tmpdir) / "hits.wav"
        truth = make_music.build(wav, 120, "tense", "peak:9,calm:12,build:19,peak:9,end:7", hits_text="12,15,17")
        known = sorted(truth["hits"] + [s["start"] for s in truth["sections"] if s["kind"] in ("peak", "end")])
        found = [h["real_time"] for h in analyze_music.analyze(wav)["hits"]]
        assert len(found) == len(known) and all(abs(a - b) < 0.03 for a, b in zip(found, known)), (found, known)
    print("test_with_music: passed")


if __name__ == "__main__":
    test_prompt_consistency_and_validation()
    test_invalid_input()
    test_no_pulse_gives_no_candidates()
    test_no_grid_without_bpm()
    test_grid_late_start_and_first_beat_override()
    test_grid_warns_when_it_does_not_fit()
    test_click_lands_on_the_beats()
    test_refuses_to_overwrite()
    test_with_music()
    print("All trailer-music tests passed successfully.")
