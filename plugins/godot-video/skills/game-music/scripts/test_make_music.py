#!/usr/bin/env python3
"""Self-check for make_music.py: python3 test_make_music.py"""
import array
import json
import pathlib
import tempfile
import wave

import make_music


def frames(path):
    with wave.open(str(path)) as source:
        assert (source.getnchannels(), source.getframerate()) == (2, make_music.RATE)
        return array.array('h', source.readframes(source.getnframes()))


def energy(samples, start_seconds, seconds):
    start = int(start_seconds * make_music.RATE) * 2
    window = samples[start:start + int(seconds * make_music.RATE) * 2]
    return sum(v * v for v in window) / max(len(window), 1)


with tempfile.TemporaryDirectory() as folder:
    first, second, other = (pathlib.Path(folder) / name for name in ('a.wav', 'b.wav', 'c.wav'))
    cues = make_music.build(first, 120, 'tense', 'calm:8,build:8,peak:8,end:4', '3.1', 1)
    make_music.build(second, 120, 'tense', 'calm:8,build:8,peak:8,end:4', '3.1', 1)
    make_music.build(other, 120, 'tense', 'calm:8,build:8,peak:8,end:4', '3.1', 2)
    samples = frames(first)

    assert len(samples) == 14 * make_music.RATE * 2, 'length comes from the sections'
    assert cues['seconds'] == 14 and len(cues['beats']) == 28 and cues['bars'][:2] == [0, 2]
    assert cues['hits'] == [3.0], 'hits snap to the nearest beat'
    assert [s['start'] for s in cues['sections']] == [0, 4, 8, 12]
    assert json.loads(first.with_suffix('.cues.json').read_text()) == cues
    assert first.read_bytes() == second.read_bytes(), 'same input, same file'
    assert first.read_bytes() != other.read_bytes(), 'another seed changes the melody'
    assert max(abs(v) for v in samples) < 32767 * 0.9, 'no clipping'
    assert energy(samples, 8, 4) > energy(samples, 0, 3) * 2, 'the peak is louder than the calm section'
    assert energy(samples, 8, 0.05) > energy(samples, 8.15, 0.05), 'the kick lands on the beat'
    assert abs(samples[-1]) < 300, 'the end does not click'

    def variant(**options):
        make_music.build(other, 120, options.pop('mood', 'tense'), options.pop('sections', 'calm:8,peak:8,end:4'), **options)
        return other.read_bytes()

    plain = variant()
    for sound in make_music.SOUNDS:
        assert sound == 'synth' or variant(sound=sound) != plain, sound
    for mood in make_music.MOODS:
        assert mood == 'tense' or variant(mood=mood) != plain, mood
    assert variant(key='F#') != plain
    assert variant(progression='i,III,VII') != plain
    assert variant(meter=3) != plain
    assert variant(key='D', progression='i,bVI,i,v') == plain, 'naming the default key and chords changes nothing'
    assert variant(mute='melody') != plain
    assert variant(sound='ambient', mute='') != variant(sound='ambient'), 'an empty --mute turns the default mutes off'
    make_music.build(other, 120, 'tense', 'rest:8')
    assert max(abs(v) for v in frames(other)) == 0, 'only rest is silent'
    assert make_music.parse_key('Bb') == 46 and make_music.parse_key('C') == 36
    assert make_music.parse_progression('bVI,v') == [(8, make_music.MAJOR), (7, make_music.MINOR)]

for bad in (
    dict(bpm=10, mood='tense', sections_text='calm:4'),
    dict(bpm=120, mood='angry', sections_text='calm:4'),
    dict(bpm=120, mood='tense', sections_text='calm'),
    dict(bpm=120, mood='tense', sections_text='loud:4'),
    dict(bpm=120, mood='tense', sections_text='calm:0'),
    dict(bpm=120, mood='tense', sections_text='calm:4', hits_text='99'),
    dict(bpm=120, mood='tense', sections_text='calm:4', sound='kazoo'),
    dict(bpm=120, mood='tense', sections_text='calm:4', key='H'),
    dict(bpm=120, mood='tense', sections_text='calm:4', progression='i,X'),
    dict(bpm=120, mood='tense', sections_text='calm:4', progression='Iv'),
    dict(bpm=120, mood='tense', sections_text='calm:4', meter=5),
    dict(bpm=120, mood='tense', sections_text='calm:4', mute='cowbell'),
):
    try:
        make_music.build('unused.wav', **bad)
    except ValueError:
        continue
    raise AssertionError(f'should be rejected: {bad}')

print('ok')
