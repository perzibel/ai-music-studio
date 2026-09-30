"""Music theory helpers: note names, chords, drum names, GM instrument names."""
from __future__ import annotations

import re

NOTE_OFFSETS = {"c": 0, "d": 2, "e": 4, "f": 5, "g": 7, "a": 9, "b": 11}

# Chord qualities as semitone intervals from the root.
CHORDS = {
    "": [0, 4, 7], "maj": [0, 4, 7], "M": [0, 4, 7],
    "m": [0, 3, 7], "min": [0, 3, 7], "-": [0, 3, 7],
    "5": [0, 7, 12],                       # power chord
    "dim": [0, 3, 6], "aug": [0, 4, 8], "+": [0, 4, 8],
    "sus2": [0, 2, 7], "sus4": [0, 5, 7], "sus": [0, 5, 7],
    "6": [0, 4, 7, 9], "m6": [0, 3, 7, 9],
    "7": [0, 4, 7, 10], "maj7": [0, 4, 7, 11], "M7": [0, 4, 7, 11],
    "m7": [0, 3, 7, 10], "min7": [0, 3, 7, 10], "mmaj7": [0, 3, 7, 11],
    "m7b5": [0, 3, 6, 10], "dim7": [0, 3, 6, 9],
    "9": [0, 4, 7, 10, 14], "maj9": [0, 4, 7, 11, 14], "m9": [0, 3, 7, 10, 14],
    "add9": [0, 4, 7, 14], "madd9": [0, 3, 7, 14],
    "11": [0, 4, 7, 10, 14, 17], "m11": [0, 3, 7, 10, 14, 17],
    "13": [0, 4, 7, 10, 14, 21], "7sus4": [0, 5, 7, 10],
}

# General MIDI percussion (channel 10) note numbers.
DRUMS = {
    "kick": 36, "kick2": 35, "bd": 36,
    "snare": 38, "snare2": 40, "sd": 38, "rim": 37, "sidestick": 37, "clap": 39,
    "hihat": 42, "hh": 42, "hihat_closed": 42, "chh": 42,
    "hihat_pedal": 44, "phh": 44,
    "hihat_open": 46, "oh": 46, "ohh": 46,
    "crash": 49, "crash2": 57, "ride": 51, "ride_bell": 53, "ride2": 59,
    "china": 52, "splash": 55,
    "tom_high": 50, "tom1": 50, "tom_himid": 48, "tom2": 48,
    "tom_mid": 47, "tom_lowmid": 47, "tom_low": 45, "tom3": 45,
    "tom_floor": 41, "tom_floor2": 43, "tom4": 41,
    "tambourine": 54, "cowbell": 56, "shaker": 70, "maracas": 70, "cabasa": 69,
    "conga_high": 62, "conga_low": 64, "conga_mute": 63,
    "bongo_high": 60, "bongo_low": 61, "timbale_high": 65, "timbale_low": 66,
    "claves": 75, "woodblock": 76, "triangle": 81, "triangle_mute": 80,
    "vibraslap": 58, "guiro": 73, "whistle": 72, "agogo": 67, "sticks": 31,
}

GM_NAMES = [
    "Acoustic Grand Piano", "Bright Acoustic Piano", "Electric Grand Piano", "Honky-tonk Piano",
    "Electric Piano 1", "Electric Piano 2", "Harpsichord", "Clavinet",
    "Celesta", "Glockenspiel", "Music Box", "Vibraphone", "Marimba", "Xylophone", "Tubular Bells", "Dulcimer",
    "Drawbar Organ", "Percussive Organ", "Rock Organ", "Church Organ", "Reed Organ", "Accordion", "Harmonica",
    "Tango Accordion",
    "Acoustic Guitar (nylon)", "Acoustic Guitar (steel)", "Electric Guitar (jazz)", "Electric Guitar (clean)",
    "Electric Guitar (muted)", "Overdriven Guitar", "Distortion Guitar", "Guitar Harmonics",
    "Acoustic Bass", "Electric Bass (finger)", "Electric Bass (pick)", "Fretless Bass",
    "Slap Bass 1", "Slap Bass 2", "Synth Bass 1", "Synth Bass 2",
    "Violin", "Viola", "Cello", "Contrabass", "Tremolo Strings", "Pizzicato Strings", "Orchestral Harp", "Timpani",
    "String Ensemble 1", "String Ensemble 2", "Synth Strings 1", "Synth Strings 2",
    "Choir Aahs", "Voice Oohs", "Synth Voice", "Orchestra Hit",
    "Trumpet", "Trombone", "Tuba", "Muted Trumpet", "French Horn", "Brass Section", "Synth Brass 1", "Synth Brass 2",
    "Soprano Sax", "Alto Sax", "Tenor Sax", "Baritone Sax", "Oboe", "English Horn", "Bassoon", "Clarinet",
    "Piccolo", "Flute", "Recorder", "Pan Flute", "Blown Bottle", "Shakuhachi", "Whistle", "Ocarina",
    "Lead 1 (square)", "Lead 2 (sawtooth)", "Lead 3 (calliope)", "Lead 4 (chiff)",
    "Lead 5 (charang)", "Lead 6 (voice)", "Lead 7 (fifths)", "Lead 8 (bass + lead)",
    "Pad 1 (new age)", "Pad 2 (warm)", "Pad 3 (polysynth)", "Pad 4 (choir)",
    "Pad 5 (bowed)", "Pad 6 (metallic)", "Pad 7 (halo)", "Pad 8 (sweep)",
    "FX 1 (rain)", "FX 2 (soundtrack)", "FX 3 (crystal)", "FX 4 (atmosphere)",
    "FX 5 (brightness)", "FX 6 (goblins)", "FX 7 (echoes)", "FX 8 (sci-fi)",
    "Sitar", "Banjo", "Shamisen", "Koto", "Kalimba", "Bagpipe", "Fiddle", "Shanai",
    "Tinkle Bell", "Agogo", "Steel Drums", "Woodblock", "Taiko Drum", "Melodic Tom", "Synth Drum", "Reverse Cymbal",
    "Guitar Fret Noise", "Breath Noise", "Seashore", "Bird Tweet", "Telephone Ring", "Helicopter", "Applause",
    "Gunshot",
]

# Friendly shortcuts -> GM program numbers.
ALIASES = {
    "piano": 0, "grand piano": 0, "bright piano": 1, "electric piano": 4, "rhodes": 4, "ep": 4, "wurlitzer": 5,
    "harpsichord": 6, "clav": 7, "celesta": 8, "glockenspiel": 9, "music box": 10, "vibes": 11, "marimba": 12,
    "bells": 14, "organ": 16, "hammond": 16, "rock organ": 18, "church organ": 19, "accordion": 21,
    "nylon guitar": 24, "classical guitar": 24, "acoustic guitar": 25, "steel guitar": 25, "jazz guitar": 26,
    "clean guitar": 27, "muted guitar": 28, "palm mute": 28, "overdrive guitar": 29, "overdriven guitar": 29,
    "distortion guitar": 30, "distorted guitar": 30, "metal guitar": 30, "harmonics": 31,
    "acoustic bass": 32, "upright bass": 32, "bass": 33, "finger bass": 33, "pick bass": 34, "fretless": 35,
    "slap bass": 36, "synth bass": 38,
    "violin": 40, "viola": 41, "cello": 42, "contrabass": 43, "double bass": 43, "tremolo strings": 44,
    "pizzicato": 45, "harp": 46, "timpani": 47, "strings": 48, "string ensemble": 48, "slow strings": 49,
    "synth strings": 50, "choir": 52, "aahs": 52, "oohs": 53, "orchestra hit": 55,
    "trumpet": 56, "trombone": 57, "tuba": 58, "french horn": 60, "horn": 60, "brass": 61, "synth brass": 62,
    "sax": 65, "alto sax": 65, "tenor sax": 66, "oboe": 68, "bassoon": 70, "clarinet": 71, "piccolo": 72,
    "flute": 73, "pan flute": 75, "square lead": 80, "saw lead": 81, "lead": 81, "pad": 89, "warm pad": 89,
    "polysynth": 90, "sitar": 104, "banjo": 105, "koto": 107, "kalimba": 108, "steel drums": 114, "taiko": 116,
}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


GM_LOOKUP = {_norm(n): i for i, n in enumerate(GM_NAMES)}
ALIAS_LOOKUP = {_norm(k): v for k, v in ALIASES.items()}

_NOTE_RE = re.compile(r"^([A-Ga-g])([#b]*)(-?\d+)$")
_CHORD_RE = re.compile(r"^([A-Ga-g])([#b]?)([^/]*)(?:/([A-Ga-g][#b]?))?$")


def note_to_midi(note) -> int:
    """'C4' -> 60, 'F#2' -> 42, 'Bb3' -> 58. Integers pass through. Drum names map to GM drums."""
    if isinstance(note, bool):
        raise ValueError(f"Invalid note: {note!r}")
    if isinstance(note, (int, float)):
        return int(note)
    s = str(note).strip()
    if s.lower() in DRUMS:
        return DRUMS[s.lower()]
    m = _NOTE_RE.match(s)
    if not m:
        raise ValueError(f"Invalid note {note!r}. Use names like 'C4', 'F#2', 'Bb3', a MIDI number, "
                         f"or a drum name like 'kick'.")
    letter, acc, octave = m.groups()
    value = NOTE_OFFSETS[letter.lower()] + acc.count("#") - acc.count("b") + (int(octave) + 1) * 12
    if not 0 <= value <= 127:
        raise ValueError(f"Note {note!r} is out of MIDI range")
    return value


def chord_to_midi(chord: str, octave: int = 4, inversion: int = 0) -> list[int]:
    """'Am7' -> [57, 60, 64, 67] (root placed in the given octave). Supports slash bass: 'C/E'."""
    m = _CHORD_RE.match(chord.strip())
    if not m:
        raise ValueError(f"Invalid chord {chord!r}")
    letter, acc, quality, bass = m.groups()
    if quality not in CHORDS:
        raise ValueError(f"Unknown chord quality {quality!r} in {chord!r}. Known: {sorted(k for k in CHORDS if k)}")
    root = note_to_midi(f"{letter}{acc}{octave}")
    notes = [root + i for i in CHORDS[quality]]
    for _ in range(inversion % max(len(notes), 1)):
        notes = notes[1:] + [notes[0] + 12]
    if bass:
        b = note_to_midi(f"{bass}{octave}")
        while b >= notes[0]:
            b -= 12
        notes = [b] + notes
    return notes
