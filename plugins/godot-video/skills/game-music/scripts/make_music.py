#!/usr/bin/env python3
"""Synthesizes simple instrumental trailer music, with beats at exact times. Python standard library only.

    make_music.py out.wav --bpm 120 --mood tense --sound synth --sections calm:16,build:16,peak:16,end:8 --hits 12,15

Section lengths are in beats. Writes out.wav and out.cues.json with the time of every beat, bar, section and hit.
Optional: --key F#, --progression i,bVI,III,v, --meter 3, --mute drums,melody, --seed 2.
"""
import argparse
import array
import functools
import json
import math
import pathlib
import random
import wave

RATE = 44100
SECTION_KINDS = ('calm', 'build', 'peak', 'end', 'rest')
LAYERS = ('drums', 'bass', 'pad', 'arp', 'melody', 'riser', 'impacts')
METERS = (3, 4)
NOTE_NAMES = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}
DEGREES = {'I': 0, 'II': 2, 'III': 4, 'IV': 5, 'V': 7, 'VI': 9, 'VII': 11}
MINOR, MAJOR = (0, 3, 7), (0, 4, 7)
# default key, then one chord per bar: uppercase is major, lowercase minor, b or # moves it a semitone
MOODS = {
    'tense': ('D', 'i,bVI,i,v'),
    'heroic': ('D', 'i,bVII,bVI,bVII'),
    'cozy': ('F', 'I,V,vi,IV'),
    'mysterious': ('E', 'i,bII,i,iv'),
    'playful': ('G', 'I,IV,V,IV'),
    'sad': ('A', 'i,iv,bVI,v'),
    'epic': ('C', 'i,bVI,bIII,bVII'),
}
# wave: note shape. attack: pad fade-in, s. brightness: pad and lead filter, relative. space: reverb, relative.
# tight: short, dry drums. default_mute: layers off unless --mute is given.
SOUNDS = {
    'synth': dict(wave='saw', attack=0.25, brightness=1.0, space=1.0, tight=False, hats=True, default_mute=()),
    'chiptune': dict(wave='square', attack=0.005, brightness=4.0, space=0.15, tight=True, hats=True, default_mute=()),
    'orchestral': dict(wave='saw', attack=0.6, brightness=0.6, space=1.6, tight=False, hats=False, default_mute=()),
    'ambient': dict(wave='saw', attack=1.2, brightness=0.5, space=2.0, tight=False, hats=False,
                    default_mute=('drums', 'bass', 'melody')),
}
# Steps per melody bar, in eighth notes: (position, index into the chord, plus an octave from 3 upward).
MOTIFS = [
    [(0, 0), (3, 1), (4, 2), (6, 1)],
    [(0, 2), (2, 1), (3, 0), (6, 3)],
    [(0, 0), (1, 1), (2, 2), (4, 3), (6, 2)],
    [(0, 3), (3, 2), (4, 1), (7, 2)],
]


def hertz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def samples_of(seconds):
    return int(round(seconds * RATE))


def low_pass(sound, cutoff):
    amount = 1 - math.exp(-2 * math.pi * cutoff / RATE)
    state = 0.0
    out = []
    for value in sound:
        state += amount * (value - state)
        out.append(state)
    return out


@functools.lru_cache(maxsize=None)
def tone(midi, seconds, cutoff, attack, release, wave_shape='saw', voices=2):
    """Detuned saw or square waves through a low-pass filter, with an attack and release envelope."""
    count = samples_of(seconds)
    mixed = [0.0] * count
    for voice in range(voices):
        step = hertz(midi) * (1 + 0.004 * (voice - (voices - 1) / 2)) / RATE
        phase = voice * 0.37 % 1
        for i in range(count):
            mixed[i] += 2 * phase - 1 if wave_shape == 'saw' else (0.7 if phase < 0.5 else -0.7)
            phase = (phase + step) % 1
    out = low_pass(mixed, cutoff)
    attack_samples = max(samples_of(attack), 1)
    release_samples = max(samples_of(release), 1)
    return tuple(
        value / voices * min(1.0, i / attack_samples, (count - i) / release_samples)
        for i, value in enumerate(out)
    )


@functools.lru_cache(maxsize=None)
def pluck(midi, seconds):
    count = samples_of(seconds)
    step = 2 * math.pi * hertz(midi) / RATE
    return tuple(
        (math.sin(i * step) + 0.3 * math.sin(2 * i * step)) * math.exp(-5.5 * i / RATE / seconds)
        * min(1.0, i / 40)
        for i in range(count)
    )


@functools.lru_cache(maxsize=None)
def drum(start_hz, end_hz, seconds, noise, seed):
    """A falling sine with a burst of noise: kick, tom or boom, depending on the values."""
    noise_source = random.Random(seed)
    count = samples_of(seconds)
    phase = 0.0
    out = []
    for i in range(count):
        t = i / count
        phase += 2 * math.pi * (end_hz + (start_hz - end_hz) * math.exp(-14 * t)) / RATE
        burst = noise * noise_source.uniform(-1, 1) * math.exp(-30 * t)
        out.append((math.sin(phase) + burst) * math.exp(-5 * t))
    return tuple(out)


@functools.lru_cache(maxsize=None)
def hat(seed):
    noise_source = random.Random(seed)
    count = samples_of(0.05)
    last = 0.0
    out = []
    for i in range(count):
        value = noise_source.uniform(-1, 1)
        out.append((value - last) * math.exp(-7 * i / count))
        last = value
    return tuple(out)


def riser(seconds, seed):
    noise_source = random.Random(seed)
    count = samples_of(seconds)
    state = 0.0
    out = []
    for i in range(count):
        t = i / count
        state += (0.02 + 0.5 * t * t) * (noise_source.uniform(-1, 1) - state)
        out.append(state * t * t)
    return out


class Mix:
    def __init__(self, seconds):
        self.size = samples_of(seconds)
        self.left = [0.0] * self.size
        self.right = [0.0] * self.size
        self.send = [0.0] * self.size

    def add(self, sound, at_seconds, gain=1.0, pan=0.0, send=0.0):
        start = samples_of(at_seconds)
        left_gain = gain * math.cos((pan + 1) * math.pi / 4)
        right_gain = gain * math.sin((pan + 1) * math.pi / 4)
        for offset, value in enumerate(sound):
            index = start + offset
            if index >= self.size:
                break
            self.left[index] += value * left_gain
            self.right[index] += value * right_gain
            if send:
                self.send[index] += value * send

    def add_reverb(self):
        """Parallel feedback delays, with different lengths per side so the tail is wide."""
        for target, delays in ((self.left, (0.0297, 0.0371, 0.0411)), (self.right, (0.0313, 0.0389, 0.0437))):
            for delay_seconds in delays:
                delay = samples_of(delay_seconds)
                line = [0.0] * self.size
                for i in range(delay, self.size):
                    line[i] = self.send[i - delay] + 0.82 * line[i - delay]
                for i in range(self.size):
                    target[i] += line[i] * 0.12


def parse_key(text):
    """Returns the MIDI note of a key name, in the bass range: C, F#, Bb."""
    name, accidental = text[:1].upper(), text[1:]
    if name not in NOTE_NAMES or accidental not in ('', '#', 'b'):
        raise ValueError(f'bad key "{text}": use a note such as C, F# or Bb')
    return 36 + (NOTE_NAMES[name] + {'': 0, '#': 1, 'b': -1}[accidental]) % 12


def parse_progression(text):
    """Returns (semitones above the key, triad) for each Roman numeral: i,bVI,III,v."""
    chords = []
    for numeral in text.split(','):
        shift = {'b': -1, '#': 1}.get(numeral[:1], 0)
        degree = numeral[1:] if shift else numeral
        if degree.upper() not in DEGREES or degree not in (degree.upper(), degree.lower()):
            raise ValueError(f'bad chord "{numeral}": use Roman numerals such as i, bVI or V')
        chords.append(((DEGREES[degree.upper()] + shift) % 12, MAJOR if degree.isupper() else MINOR))
    return chords


def parse_sections(text):
    sections = []
    for part in text.split(','):
        kind, separator, beats = part.partition(':')
        if not separator or kind not in SECTION_KINDS or not beats.isdigit() or int(beats) == 0:
            raise ValueError(f'bad section "{part}": use kind:beats, with kind in {", ".join(SECTION_KINDS)}')
        sections.append((kind, int(beats)))
    return sections


def compose(mix, bpm, root, progression, sound, meter, muted, sections, hits, seed):
    beat = 60.0 / bpm
    eighth = beat / 2
    style = SOUNDS[sound]
    wave_shape = style['wave']
    kick = drum(130.0, 48.0, 0.14, 0.5, 5) if style['tight'] else drum(130.0, 48.0, 0.3, 0.1, 5)
    tom = drum(190.0, 80.0, 0.14, 0.9, 7) if style['tight'] else drum(190.0, 80.0, 0.45, 0.45, 7)
    space = style['space']
    motif = random.Random(seed).sample(MOTIFS, 2)
    chord_at_end = (root + progression[0][0], progression[0][1])

    first_beat = 0
    for section_index, (kind, length) in enumerate(sections):
        section_start = first_beat * beat
        if kind in ('peak', 'end') and 'impacts' not in muted:
            mix.add(drum(70.0, 28.0, 2.5, 0.5, 11), section_start, 0.95, send=0.25 * space)
        for beat_index in range(first_beat, first_beat + length):
            position = beat_index - first_beat
            t = beat_index * beat
            on_bar = beat_index % meter == 0
            bar_index = beat_index // meter
            offset, triad = progression[bar_index % len(progression)]
            chord = [root + offset + note for note in triad]
            beats_left = first_beat + length - beat_index
            if kind in ('end', 'rest'):
                continue
            progress = position / max(length - 1, 1)
            if on_bar and 'pad' not in muted:
                held = min(meter, beats_left) * beat + 0.3
                cutoff = {'calm': 700, 'build': round(800 + 1400 * progress, -2), 'peak': 2800}[kind]
                for note in chord:
                    mix.add(tone(note + 12, held, cutoff * style['brightness'], style['attack'], 0.3, wave_shape),
                            t, 0.11, send=0.5 * space)
            if kind in ('calm', 'build') and 'arp' not in muted:
                for step in range(2):
                    index = (beat_index * 2 + step) % 6
                    note = chord[index % 3] + 24 + 12 * (index // 3)
                    mix.add(pluck(note, beat), t + step * eighth, 0.13 if kind == 'calm' else 0.16,
                            pan=0.45 if index % 2 else -0.45, send=0.45 * space)
            if kind == 'calm' and on_bar and 'drums' not in muted:
                mix.add(drum(95.0, 55.0, 0.7, 0.2, 3), t, 0.3, send=0.3 * space)
            if kind in ('build', 'peak'):
                for step in range(2):
                    if 'bass' not in muted:
                        mix.add(tone(chord[0], eighth * 0.95, 500 * style['brightness'], 0.004, 0.03, wave_shape),
                                t + step * eighth, 0.3)
                    if style['hats'] and 'drums' not in muted:
                        mix.add(hat(step), t + step * eighth + eighth / 2, 0.08, pan=0.3)
            if 'drums' not in muted:
                if kind == 'build' and (beat_index % 2 == 0 or progress > 0.5):
                    mix.add(kick, t, 0.6)
                if kind == 'peak':
                    mix.add(kick, t, 0.75)
                    if beat_index % 2 == 1:
                        mix.add(tom, t, 0.45, pan=-0.2, send=0.3 * space)
            if kind == 'peak' and on_bar and 'melody' not in muted:
                top = [note + 24 for note in triad] + [triad[0] + 36]
                for place, index in motif[bar_index % 2]:
                    if place < meter * 2:
                        mix.add(tone(root + offset + top[index], eighth * 1.8, 2600 * style['brightness'], 0.008, 0.12,
                                     wave_shape), t + place * eighth, 0.15, pan=0.1, send=0.45 * space)
            next_kind = sections[section_index + 1][0] if section_index + 1 < len(sections) else None
            if next_kind in ('peak', 'end') and beats_left == min(length, 4) and 'riser' not in muted:
                mix.add(riser(beats_left * beat, 21), t, 0.5, send=0.2 * space)
        if kind == 'end':
            note_root, triad = chord_at_end
            hold = length * beat
            for note in triad:
                if 'pad' not in muted:
                    mix.add(tone(note_root + note + 12, hold, 1300 * style['brightness'], 0.02, hold * 0.8, wave_shape),
                            section_start, 0.13, send=0.6 * space)
            if 'bass' not in muted:
                mix.add(tone(note_root, hold, 400 * style['brightness'], 0.02, hold * 0.8, wave_shape),
                        section_start, 0.3, send=0.2 * space)
        first_beat += length
    for hit in hits:
        mix.add(drum(150.0, 50.0, 0.9, 0.6, 13), hit, 0.7, send=0.4 * space)


def write_wave(path, mix):
    peak = max(max(abs(v) for v in mix.left), max(abs(v) for v in mix.right), 1e-9)
    scale = 0.89 / peak
    fade = samples_of(0.02)
    frames = array.array('h', bytes(mix.size * 4))
    for i in range(mix.size):
        edge = min(1.0, (mix.size - 1 - i) / fade)
        frames[2 * i] = int(mix.left[i] * scale * edge * 32767)
        frames[2 * i + 1] = int(mix.right[i] * scale * edge * 32767)
    with wave.open(str(path), 'wb') as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(frames.tobytes())


def build(out, bpm, mood, sections_text, hits_text='', seed=1, sound='synth', key=None, progression=None,
          meter=4, mute=None):
    """Writes the music and cue sheet, and returns the cues."""
    if not 40 <= bpm <= 240:
        raise ValueError('bpm must be between 40 and 240')
    if mood not in MOODS:
        raise ValueError(f'mood must be one of {", ".join(MOODS)}')
    if sound not in SOUNDS:
        raise ValueError(f'sound must be one of {", ".join(SOUNDS)}')
    if meter not in METERS:
        raise ValueError('meter must be 3 or 4 beats per bar')
    muted = SOUNDS[sound]['default_mute'] if mute is None else tuple(filter(None, mute.split(',')))
    if not set(muted) <= set(LAYERS):
        raise ValueError(f'mute takes layers from: {", ".join(LAYERS)}')
    root = parse_key(key or MOODS[mood][0])
    chords = parse_progression(progression or MOODS[mood][1])
    sections = parse_sections(sections_text)
    beat = 60.0 / bpm
    total_beats = sum(length for _, length in sections)
    seconds = total_beats * beat
    # Hits snap to the nearest beat, so a hit asked for at a cut stays on the grid.
    hits = sorted({round(float(h) / beat) * beat for h in hits_text.split(',') if h})
    if any(h < 0 or h >= seconds for h in hits):
        raise ValueError(f'hits must be inside the track, which lasts {seconds:.3f} s')
    mix = Mix(seconds)
    compose(mix, bpm, root, chords, sound, meter, muted, sections, hits, seed)
    mix.add_reverb()
    out = pathlib.Path(out)
    write_wave(out, mix)
    starts = []
    beat_index = 0
    for kind, length in sections:
        starts.append({'kind': kind, 'start': round(beat_index * beat, 4)})
        beat_index += length
    cues = {
        'bpm': bpm, 'mood': mood, 'sound': sound, 'key': key or MOODS[mood][0], 'meter': meter,
        'progression': progression or MOODS[mood][1], 'muted': list(muted), 'seed': seed, 'seconds': round(seconds, 4),
        'beats': [round(i * beat, 4) for i in range(total_beats)],
        'bars': [round(i * beat, 4) for i in range(0, total_beats, meter)],
        'sections': starts, 'hits': [round(h, 4) for h in hits],
    }
    out.with_suffix('.cues.json').write_text(json.dumps(cues, indent=1))
    return cues


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('out', help='output .wav file')
    parser.add_argument('--bpm', type=float, default=120)
    parser.add_argument('--mood', default='tense', help=', '.join(MOODS))
    parser.add_argument('--sections', default='calm:16,build:16,peak:16,end:8',
                        help='kind:beats, comma-separated; kinds: ' + ', '.join(SECTION_KINDS))
    parser.add_argument('--sound', default='synth', help=', '.join(SOUNDS))
    parser.add_argument('--key', help='tonic note, such as C, F# or Bb (default: set by the mood)')
    parser.add_argument('--progression', help='chords per bar in Roman numerals, such as i,bVI,III,v (default: set by the mood)')
    parser.add_argument('--meter', type=int, default=4, help='beats per bar: 3 or 4')
    parser.add_argument('--mute', help='layers to leave out, comma-separated: ' + ', '.join(LAYERS))
    parser.add_argument('--hits', default='', help='extra impacts, in seconds, comma-separated')
    parser.add_argument('--seed', type=int, default=1, help='changes the melody')
    args = parser.parse_args()
    try:
        cues = build(args.out, args.bpm, args.mood, args.sections, args.hits, args.seed, args.sound, args.key,
                     args.progression, args.meter, args.mute)
    except ValueError as error:
        parser.error(str(error))
    print(f'{args.out}: {cues["seconds"]} s, {len(cues["beats"])} beats, sections {cues["sections"]}, hits {cues["hits"]}')


if __name__ == '__main__':
    main()
