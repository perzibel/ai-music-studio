"""Generates examples/rock_vocals.json: an upbeat classic-rock song with lyrics for the AI singer.

Shows how to build a song programmatically. Usage: .venv\\Scripts\\python.exe tools\\make_rock_vocals_example.py
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Sections: (name, first bar, chords one per bar)
SECTIONS = [
    ("intro", 0, ["A", "D", "A", "E"]),
    ("verse", 4, ["A", "D", "A", "E", "A", "D", "E", "E"]),
    ("chorus", 12, ["D", "A", "E", "F#m", "D", "A", "E", "A"]),
    ("verse", 20, ["A", "D", "A", "E", "A", "D", "E", "E"]),
    ("chorus", 28, ["D", "A", "E", "F#m", "D", "A", "E", "A"]),
    ("outro", 36, ["D", "E", "A", "A"]),
]
POWER = {"A": ("A5", 2), "D": ("D5", 3), "E": ("E5", 2), "F#m": ("F#5", 2)}
ROOT_NOTE = {"A": "A1", "D": "D2", "E": "E1", "F#m": "F#1"}
LYRICS = """[intro]

[verse]
Windows down on a Sunday drive
Radio loud and we feel alive
Coffee spilling on the dashboard light
You laugh at me and it all feels right

[chorus]
Turn it up, turn it up tonight
Every little road leads back to your light
Sing it loud till the morning comes
You and me, we're the lucky ones

[verse]
No map, no plan and a tank half full
Your hand in mine and the sky so blue
Every mile is a brand new song
With you beside me I can't go wrong

[chorus]
Turn it up, turn it up tonight
Every little road leads back to your light
Sing it loud till the morning comes
You and me, we're the lucky ones

[outro]
You and me, we're the lucky ones"""


def eighths(chords, oct_override=None):
    """Power chords in 8th notes, one chord per bar."""
    out = []
    for c in chords:
        name, oc = POWER[c]
        out += [{"chord": name, "oct": oc}] * 8
    return out


guitar_clips, chug_clips, bass_clips, drum_clips, piano_clips, organ_clips = [], [], [], [], [], []
for name, bar, chords in SECTIONS:
    n = len(chords)
    last = bar + n - 1
    if name in ("chorus", "intro"):
        guitar_clips.append({"bar": bar, "every": 0.5, "d": 0.45, "v": 105, "chords": eighths(chords)})
    elif name == "verse":
        chug_clips.append({"bar": bar, "every": 0.5, "d": 0.3, "v": 95, "chords": eighths(chords)})
    else:  # outro: hits, then a big ringing A
        guitar_clips.append({"bar": bar, "every": 0.5, "d": 0.45, "v": 105, "chords": eighths(chords[:2])})
        guitar_clips.append({"bar": bar + 2, "notes": [{"chord": "A5", "oct": 2, "t": 0, "d": 7, "v": 120}]})
    bass_notes = []
    for i, c in enumerate(chords):
        if name == "outro" and i >= 2:
            bass_notes.append({"p": ROOT_NOTE[c], "t": i * 4, "d": 7 if i == 2 else 0.1, "v": 115})
            continue
        bass_notes += [{"p": ROOT_NOTE[c], "t": i * 4 + k * 0.5, "d": 0.45, "v": 100 if k % 2 == 0 else 85}
                       for k in range(8)]
    bass_clips.append({"bar": bar, "notes": [b for b in bass_notes if b["d"] > 0.1]})
    # drums
    groove = ({"kick": "x.....x.x.x.....", "snare": "....x.......x...", "ride": "x.x.x.x.x.x.x.x."}
              if name == "chorus" else
              {"kick": "x.......x.x.....", "snare": "....x.......x...", "hihat": "x.o.x.o.x.o.x.o."})
    if name == "outro":
        drum_clips.append({"bar": bar, "repeat": 2, "length_bars": 1, "pattern": groove})
        drum_clips.append({"bar": bar + 2, "notes": [{"p": "kick", "t": 0, "v": 120}, {"p": "crash", "t": 0, "v": 120},
                                                       {"p": "crash2", "t": 0, "v": 110}]})
    else:
        drum_clips.append({"bar": bar, "repeat": n - 1, "length_bars": 1, "pattern": groove})
        fill = dict(groove)
        fill["snare"] = "....x.......xxxX" if name != "intro" else "....x...x.x.xxxX"
        fill["tom_high"] = "........xx......"
        fill["tom_floor"] = "..........xx...."
        drum_clips.append({"bar": last, "pattern": fill})
    drum_clips.append({"bar": bar, "notes": [{"p": "crash", "t": 0, "v": 110}]})
    if name == "chorus":
        piano_clips.append({"bar": bar, "notes": [
            {"chord": c if c != "F#m" else "F#m", "oct": 4, "t": i * 4 + beat, "d": 0.4, "v": 80}
            for i, c in enumerate(chords) for beat in (1, 3)]})
        organ_clips.append({"bar": bar, "every": 4, "d": 3.9, "oct": 3, "v": 75, "chords": chords})

song = {
    "title": "Lucky Ones",
    "bpm": 132,
    "reverb": {"type": "plate"},
    "loudness": "streaming",
    "tracks": [
        {"name": "Drums", "instrument": "sfz:acoustic_drums", "volume": 0.9,
         "humanize": {"timing_ms": 6, "velocity": 8}, "effects": ["drum_bus"], "clips": drum_clips},
        {"name": "Rhythm Guitar", "instrument": "sfz:electric_guitar", "amp": "classic_rock", "volume": 0.55,
         "double_track": True, "strum_ms": 5, "humanize": {"timing_ms": 7, "velocity": 8}, "clips": guitar_clips},
        {"name": "Verse Guitar", "instrument": "sfz:electric_guitar_mute", "amp": "classic_rock", "volume": 0.45,
         "double_track": True, "humanize": {"timing_ms": 6, "velocity": 8}, "clips": chug_clips},
        {"name": "Bass", "instrument": "sfz:bass_guitar", "volume": 0.9, "humanize": {"timing_ms": 5, "velocity": 6},
         "clips": bass_clips},
        {"name": "Piano", "instrument": "sfz:grand_piano", "volume": 0.5, "pan": 0.3,
         "humanize": {"timing_ms": 8, "velocity": 8}, "clips": piano_clips},
        {"name": "Organ", "instrument": "Rock Organ", "volume": 0.35, "pan": -0.3, "clips": organ_clips},
    ],
    "vocals": {
        "lyrics": LYRICS,
        "style": "male classic rock vocalist, warm slightly raspy voice, upbeat and joyful, 1970s rock anthem",
        "language": "en",
    },
}

if __name__ == "__main__":
    path = os.path.join(ROOT, "examples", "rock_vocals.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(song, f, indent=1)
    print("wrote", path)
