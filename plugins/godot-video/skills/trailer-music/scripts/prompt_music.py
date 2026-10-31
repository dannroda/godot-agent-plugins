#!/usr/bin/env python3
"""Build trailer music prompts aligned to game genres, BPM, and video sections."""

import argparse
import json
import re

GENRE_PALETTES = {
    "action": {
        "descriptors": "orchestral hybrid, aggressive synth bass, cinematic brass stabs, heavy taiko drums, trailer impacts",
        "reference": "epic blockbuster trailer, driving high-intensity pace",
        "default_bpm": 128,
        "buildup": "driving rhythm enters, tempo established, stakes rise",
        "peak": "maximum intensity, loudest melody, powerful percussion and brass swells",
        "stinger": "sudden sharp cutoff impact with echoing stinger",
    },
    "sci-fi": {
        "descriptors": "cyberpunk analog synths, dark sub-bass, industrial percussion, glitch textures, futuristic arpeggios",
        "reference": "dystopian high-tech trailer, brooding atmosphere rising to energetic peak",
        "default_bpm": 120,
        "buildup": "rhythmic bass pulse enters, synth sequencing accelerates, tension climbs",
        "peak": "maximum intensity, distorted analog leads, heavy cybernetic impacts",
        "stinger": "sudden electronic cutoff with sub-bass drop and fading synth tail",
    },
    "fantasy": {
        "descriptors": "sweeping orchestral strings, Celtic whistle, thunderous war drums, choir swells, majestic horns",
        "reference": "heroic adventure trailer, noble themes building to epic battle climax",
        "default_bpm": 110,
        "buildup": "orchestral percussion enters, brass fanfares build, heroic melody develops",
        "peak": "triumphant full orchestral swell, soaring choir and thunderous percussion",
        "stinger": "dramatic final orchestral hit with ringing bell and decaying reverb",
    },
    "horror": {
        "descriptors": "dissonant strings, metallic scrapes, sub-bass braams, erratic heartbeat pulse, shocking impacts",
        "reference": "psychological horror trailer, claustrophobic dread erupting into terror",
        "default_bpm": 90,
        "buildup": "rhythmic heartbeat pulse enters, dissonant textures thicken, creeping panic",
        "peak": "overwhelming wall of harsh sound, screeching strings, sudden shocking impacts",
        "stinger": "jarring jump-scare hit followed by dead silence or eerie sub-rumble",
    },
    "retro": {
        "descriptors": "8-bit chiptune leads layered with modern synthwave bass, punchy electro drums, sidechained chords",
        "reference": "arcade indie trailer, upbeat nostalgic adrenaline",
        "default_bpm": 130,
        "buildup": "fast arpeggiated bassline enters, 4-on-the-floor beat kicks in, tempo drives forward",
        "peak": "high-octane chiptune solo over pumping synthwave rhythm and loud impacts",
        "stinger": "sharp arcade sound effect hit with decaying echo",
    },
    "cozy": {
        "descriptors": "warm acoustic guitar, playful marimba, soft upright piano, gentle brushes on snare, whimsical melodies",
        "reference": "whimsical indie adventure trailer, charming, lighthearted, emotional resolution",
        "default_bpm": 105,
        "buildup": "lively acoustic rhythm enters, gentle percussion joins, playful harmonies bloom",
        "peak": "joyful full arrangement with all instruments joining in celebratory crescendo",
        "stinger": "clean acoustic chord strum, sweet final chime, gentle decaying silence",
    },
}


def format_timestamp(seconds: float) -> str:
    m = int(seconds) // 60
    s = int(seconds) % 60
    return f"{m:02d}:{s:02d}"


def sanitize_descriptors(descriptors_str: str, notes_str: str) -> str:
    """If user notes explicitly forbid or replace instruments (e.g. 'ukulele only', 'no drums'),

    filter contradictory items out of the default palette descriptors.
    """
    notes_lower = notes_str.lower()
    items = [item.strip() for item in descriptors_str.split(",")]
    filtered = []

    # Detect negative phrases
    # e.g., 'no drums', 'no brass', 'no synth', 'without percussion'
    negations = re.findall(r"(?:no|without|never)\s+([a-z0-9_-]+)", notes_lower)

    # Detect exclusive phrases e.g. 'ukulele only', 'solo piano'
    is_exclusive = "only" in notes_lower or "solo" in notes_lower

    for item in items:
        item_lower = item.lower()
        # Check against negations
        negated = False
        for neg in negations:
            if neg in item_lower:
                negated = True
                break
        if negated:
            continue

        # If user specified something 'only' (e.g. ukulele only), don't list acoustic guitar / brass / marimba
        if is_exclusive:
            # Check if this item is explicitly mentioned in notes
            if not any(word in item_lower for word in notes_lower.split() if len(word) > 3):
                continue

        filtered.append(item)

    if not filtered:
        return ""
    return ", ".join(filtered)


def build_sections_for_genre(genre: str, palette: dict, notes: str, length: float):
    notes_lower = notes.lower()
    has_no_drums = "no drum" in notes_lower or "without drum" in notes_lower or "no percussion" in notes_lower

    # Intro
    intro_desc = "sparse atmosphere, setting the scene, gentle hook motif"
    # Buildup
    if has_no_drums:
        buildup_desc = "energy begins to build, layered harmonies enter, stakes rise"
    else:
        buildup_desc = palette["buildup"]

    # Peak
    if "cozy" in genre:
        peak_desc = palette["peak"]
    elif has_no_drums:
        peak_desc = "maximum emotional intensity and fullest harmonic arrangement"
    else:
        peak_desc = palette["peak"]

    # Stinger
    stinger_desc = palette["stinger"]

    # Standard relative ratios: intro (20%), buildup (30%), peak (35%), stinger (15%)
    d_intro = round(length * 0.20, 1)
    d_build = round(length * 0.30, 1)
    d_peak = round(length * 0.35, 1)
    d_stinger = round(length - (d_intro + d_build + d_peak), 1)

    return [
        ("intro", d_intro, intro_desc),
        ("buildup", d_build, buildup_desc),
        ("peak", d_peak, peak_desc),
        ("stinger", d_stinger, stinger_desc),
    ]


def build_compact_prompt(genre: str, notes: str = "", length: float = 28.0, bpm: int = None) -> str:
    palette = GENRE_PALETTES[genre]
    bpm_val = bpm or palette["default_bpm"]
    notes_clean = notes.strip()

    # Filter contradictory descriptors
    clean_desc = sanitize_descriptors(palette["descriptors"], notes_clean)

    parts = [f"Cinematic {genre} video game trailer music, {bpm_val} BPM, ~{round(length)}s."]
    if clean_desc:
        parts.append(clean_desc + ".")
    if notes_clean:
        parts.append(notes_clean.rstrip(".") + ".")

    # Pacing arc adapted to genre and notes
    notes_lower = notes_clean.lower()
    has_no_drums = "no drum" in notes_lower or "without percussion" in notes_lower
    if genre == "cozy":
        parts.append(
            "Starts with a gentle intro, builds lively warmth and charming harmonies, "
            "reaching a joyful peak, finishing on a sweet final chord and decaying chime."
        )
    elif has_no_drums:
        parts.append(
            "Starts quietly, gradually layers rich harmonies into an emotional climax, "
            "finishing on an echoing final tone."
        )
    else:
        parts.append(
            f"Starts with quiet intro, builds driving momentum, reaches full climax, "
            f"finishing on {palette['stinger']}."
        )

    return " ".join(parts)


def generate_prompt(genre: str, bpm: int = None, length: float = None, custom_sections=None, extra_notes: str = "") -> dict:
    if genre not in GENRE_PALETTES:
        valid = ", ".join(GENRE_PALETTES.keys())
        raise ValueError(f"Unknown genre '{genre}'. Available: {valid}")

    palette = GENRE_PALETTES[genre]

    if bpm is not None:
        if bpm <= 0:
            raise ValueError(f"BPM must be positive, got {bpm}")
        if bpm < 40 or bpm > 300:
            raise ValueError(f"BPM {bpm} is out of realistic musical range [40, 300]")
        bpm_val = bpm
    else:
        bpm_val = palette["default_bpm"]

    if length is not None:
        if length <= 0:
            raise ValueError(f"Length must be positive, got {length}")
        if length < 5.0 or length > 600.0:
            raise ValueError(f"Length {length}s is out of realistic range [5.0, 600.0]")
        length_val = length
    else:
        length_val = 28.0

    bpm = bpm_val
    length = length_val

    clean_desc = sanitize_descriptors(palette["descriptors"], extra_notes)

    sections = custom_sections or build_sections_for_genre(genre, palette, extra_notes, length)
    total_seconds = sum(dur for _, dur, _ in sections)
    beat_length = 60.0 / bpm
    total_beats = round(total_seconds / beat_length)

    timeline_lines = []
    elapsed = 0.0
    for name, dur, desc in sections:
        t_str = format_timestamp(elapsed)
        timeline_lines.append(f"[{t_str}] {name.upper()}: {desc}")
        elapsed += dur

    prompt_lines = [
        f"Cinematic trailer soundtrack for a {genre} video game.",
        f"Tempo: {bpm} BPM.",
    ]
    if clean_desc:
        prompt_lines.append(f"Style: {clean_desc}.")
    prompt_lines.extend([
        f"Total duration: ~{round(total_seconds)}s.",
        f"Mood / Reference: {palette['reference']}.",
    ])
    if extra_notes.strip():
        prompt_lines.append(f"Direction: {extra_notes.strip()}")

    prompt_lines.append("\nTrack Structure & Timing:")
    prompt_lines.extend(timeline_lines)

    prompt_text = "\n".join(prompt_lines)
    compact_prompt = build_compact_prompt(genre, notes=extra_notes, length=total_seconds, bpm=bpm)

    return {
        "genre": genre,
        "bpm": bpm,
        "total_seconds": round(total_seconds, 2),
        "total_beats": total_beats,
        "prompt_full": prompt_text,
        "prompt_compact": compact_prompt,
        "sections": [
            {"name": name, "start": round(sum(s[1] for s in sections[:i]), 2), "duration": round(dur, 2)}
            for i, (name, dur, _) in enumerate(sections)
        ],
    }


def main():
    parser = argparse.ArgumentParser(description="Generate structured music prompts for game trailers")
    parser.add_argument("--genre", default="action", choices=list(GENRE_PALETTES.keys()), help="Music style palette")
    parser.add_argument("--bpm", type=int, help="Target BPM (default depends on genre)")
    parser.add_argument("--length", type=float, default=28.0, help="Target duration in seconds (default: 28.0s)")
    parser.add_argument("--notes", default="", help="Extra creative directions or specific instruments")
    parser.add_argument("--json", action="store_true", help="Output full JSON data")

    args = parser.parse_args()
    data = generate_prompt(args.genre, bpm=args.bpm, length=args.length, extra_notes=args.notes)

    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print("=== TRAILER MUSIC PROMPT ===")
        print(data["prompt_full"])
        print("\n=== COMPACT PROMPT (FOR WEB UI / GEMINI / SUNO) ===")
        print(data["prompt_compact"])
        print(f"\nTarget: {data['bpm']} BPM, {data['total_seconds']}s ({data['total_beats']} beats)")


if __name__ == "__main__":
    main()
