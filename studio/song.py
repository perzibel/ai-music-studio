"""Turns a song spec (JSON/dict) into timed note events for each track."""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, replace

import numpy as np

from .theory import chord_to_midi, note_to_midi

PATTERN_VELOCITY = {"x": 100, "X": 127, "o": 70, "g": 40}
PATTERN_REST = set(".-_")
PATTERN_IGNORE = set(" |")


class SongError(ValueError):
    pass


@dataclass
class Note:
    start: float  # beats (before timing) or seconds (after timing)
    dur: float
    pitch: int
    vel: int
    # expression (semitones / fractions of the note; times in beats before timing, seconds after)
    bend: float = 0.0        # bend up (or down if negative) by this many semitones
    bend_at: float = 0.25    # when the bend starts, as a fraction of the note
    bend_time: float = 0.12  # how long the bend takes (seconds)
    slide_to: int | None = None  # glide to this pitch at the end of the note
    slide_time: float = 0.1      # glide duration (seconds)
    vib: float = 0.0         # vibrato depth in semitones (e.g. 0.3)
    vib_rate: float = 5.5    # vibrato speed in Hz

    @property
    def expressive(self) -> bool:
        return bool(self.bend or self.slide_to is not None or self.vib)


def _get(d: dict, *keys, default=None):
    for k in keys:
        if k in d:
            return d[k]
    return default


def bar_beats(song: dict) -> float:
    num, den = song.get("time_signature", [4, 4])
    return num * 4.0 / den


def _expression(item: dict) -> dict:
    ex = {}
    if "bend" in item:
        ex["bend"] = float(item["bend"])
    for k in ("bend_at", "bend_time", "slide_time", "vib_rate"):
        if k in item:
            ex[k] = float(item[k])
    if "vib" in item or "vibrato" in item:
        ex["vib"] = float(_get(item, "vib", "vibrato"))
    if "slide_to" in item or "slide" in item:
        ex["slide_to"] = note_to_midi(_get(item, "slide_to", "slide"))
    return ex


def _note_items(item: dict, where: str) -> list[Note]:
    t = float(_get(item, "t", "time", "beat", default=0.0))
    d = float(_get(item, "d", "dur", "duration", default=1.0))
    v = int(_get(item, "v", "vel", "velocity", default=90))
    if "chord" in item:
        pitches = chord_to_midi(item["chord"], int(_get(item, "oct", "octave", default=4)), int(item.get("inv", 0)))
    else:
        p = _get(item, "p", "pitch", "note", "notes")
        if p is None:
            raise SongError(f"{where}: note needs 'p' (pitch) or 'chord': {item}")
        pitches = [note_to_midi(x) for x in (p if isinstance(p, list) else [p])]
    ex = _expression(item)
    return [Note(t, d, pitch, max(1, min(127, v)), **ex) for pitch in pitches]


def _pattern_notes(pattern: dict, step: float, where: str) -> list[Note]:
    notes = []
    for key, steps in pattern.items():
        pitch = note_to_midi(key)
        i = 0
        for ch in steps:
            if ch in PATTERN_IGNORE:
                continue
            if ch in PATTERN_VELOCITY:
                notes.append(Note(i * step, step, pitch, PATTERN_VELOCITY[ch]))
            elif ch not in PATTERN_REST:
                raise SongError(f"{where}: bad pattern char {ch!r} in {key!r}. Use x X o g for hits, . or - for rests")
            i += 1
    return notes


def _pattern_length(pattern: dict, step: float) -> float:
    return max((sum(1 for c in s if c not in PATTERN_IGNORE) for s in pattern.values()), default=0) * step


def _chord_notes(clip: dict, where: str) -> list[Note]:
    every = float(clip.get("every", 4))
    octave = int(_get(clip, "oct", "octave", default=4))
    v = int(_get(clip, "v", "vel", default=80))
    d = float(_get(clip, "d", "dur", default=every))
    notes = []
    for i, entry in enumerate(clip["chords"]):
        if entry in (None, "", "-", "."):
            continue
        # entries are "Am7" or {"chord": "Am7", "oct": 3, "inv": 1} for per-chord voicing
        if isinstance(entry, dict):
            name = entry.get("chord")
            if not name:
                raise SongError(f"{where}: chord entry needs 'chord': {entry}")
            oct_, inv = int(_get(entry, "oct", "octave", default=octave)), int(entry.get("inv", clip.get("inv", 0)))
        else:
            name, oct_, inv = entry, octave, int(clip.get("inv", 0))
        for pitch in chord_to_midi(name, oct_, inv):
            notes.append(Note(i * every, d, pitch, v))
    return notes


def clip_notes(clip: dict, song: dict, where: str) -> tuple[list[Note], float]:
    """Returns notes relative to clip start (in beats) and the clip's natural length in beats."""
    notes: list[Note] = []
    for i, item in enumerate(clip.get("notes", [])):
        notes += _note_items(item, f"{where} note {i}")
    step = float(clip.get("step", 0.25))
    pattern_len = 0.0
    if "pattern" in clip:
        notes += _pattern_notes(clip["pattern"], step, where)
        pattern_len = _pattern_length(clip["pattern"], step)
    if "chords" in clip:
        notes += _chord_notes(clip, where)
    bb = bar_beats(song)
    if "length_bars" in clip:
        length = float(clip["length_bars"]) * bb
    elif "length_beats" in clip:
        length = float(clip["length_beats"])
    else:
        end = max([n.start + n.dur for n in notes] + [pattern_len, float(clip.get("every", 0)) * len(clip.get("chords", []))])
        length = max(bb, math.ceil(end / bb - 1e-9) * bb)
    transpose = int(clip.get("transpose", 0))
    vel_scale = float(clip.get("vel_scale", 1.0))
    for n in notes:
        n.pitch += transpose
        if n.slide_to is not None:
            n.slide_to += transpose
        n.vel = max(1, min(127, round(n.vel * vel_scale)))
    return notes, length


def track_notes_beats(track: dict, song: dict) -> list[Note]:
    """All notes of a track in absolute beats."""
    name = track.get("name", "?")
    bb = bar_beats(song)
    out: list[Note] = []
    # Top-level notes/pattern on the track behave like a clip starting at bar 0.
    base = {k: track[k] for k in ("notes", "pattern", "step", "chords", "every", "oct", "octave", "v") if k in track}
    clips = list(track.get("clips", []))
    if base:
        clips.insert(0, {**base, "bar": 0})
    for ci, clip in enumerate(clips):
        where = f"track {name!r} clip {ci}"
        notes, length = clip_notes(clip, song, where)
        start = float(_get(clip, "bar", "start_bar", default=0)) * bb + float(clip.get("beat", 0))
        for r in range(int(clip.get("repeat", 1))):
            offset = start + r * length
            out += [replace(n, start=n.start + offset) for n in notes]
    transpose = int(track.get("transpose", 0))
    for n in out:
        n.pitch = max(0, min(127, n.pitch + transpose))
        if n.slide_to is not None:
            n.slide_to = max(0, min(127, n.slide_to + transpose))
    return out


def _swing(beat: float, amount: float, unit: float) -> float:
    if amount <= 0:
        return beat
    pos = beat % (2 * unit)
    if abs(pos - unit) < 1e-6:
        return beat + amount * unit
    return beat


def track_events(track: dict, song: dict, seed: int = 0) -> list[Note]:
    """Notes in seconds, with swing, strum, sustain pedal, humanize and same-pitch overlap cleanup applied."""
    bpm = float(song["bpm"])
    spb = 60.0 / bpm
    swing = float(track.get("swing", song.get("swing", 0.0)))
    swing_unit = float(track.get("swing_unit", song.get("swing_unit", 0.25)))
    hum = track.get("humanize") or {}
    t_ms = float(hum.get("timing_ms", 0))
    v_rand = float(hum.get("velocity", 0))
    strum = float(track.get("strum_ms", 0)) / 1000.0
    rng = random.Random(f"{track.get('name')}-{seed}")
    pedal = [(float(a) * spb, float(b) * spb) for a, b in track.get("sustain", [])]

    notes = track_notes_beats(track, song)
    notes.sort(key=lambda n: (n.start, n.pitch))
    out = []
    chord_idx: dict[float, int] = {}
    for n in notes:
        start = _swing(n.start, swing, swing_unit) * spb
        end = _swing(n.start + n.dur, swing, swing_unit) * spb
        if strum:
            k = chord_idx.get(n.start, 0)
            chord_idx[n.start] = k + 1
            start += k * strum
        if t_ms:
            start += max(-2.5, min(2.5, rng.gauss(0, 1))) * t_ms / 1000.0 / 2.5
        vel = n.vel
        if v_rand:
            vel = round(vel + rng.uniform(-v_rand, v_rand))
        start = max(0.0, start)
        for a, b in pedal:  # sustain pedal: notes released while the pedal is down ring until it's lifted
            if a <= end < b:
                end = b
        out.append(replace(n, start=start, dur=max(0.01, end - start), vel=max(1, min(127, vel))))

    # A new hit on the same pitch cuts off the previous one (prevents stuck/killed notes).
    out.sort(key=lambda n: (n.start, n.pitch))
    last: dict[int, Note] = {}
    for n in out:
        prev = last.get(n.pitch)
        if prev and prev.start + prev.dur > n.start:
            prev.dur = max(0.005, n.start - prev.start)
        last[n.pitch] = n
    return out


def pitch_curve(n: Note, times: np.ndarray) -> np.ndarray:
    """Pitch offset in semitones at absolute times (seconds) for an expressive note."""
    off = np.zeros_like(times, dtype=np.float64)
    rel = times - n.start
    if n.bend:
        b0 = n.bend_at * n.dur
        off += n.bend * np.clip((rel - b0) / max(n.bend_time, 1e-3), 0, 1)
    if n.slide_to is not None:
        s0 = max(0.0, n.dur - n.slide_time)
        off += (n.slide_to - n.pitch) * np.clip((rel - s0) / max(n.slide_time, 1e-3), 0, 1)
    if n.vib:
        ramp = np.clip(rel / 0.25, 0, 1)  # vibrato fades in like a player's would
        off += n.vib * ramp * np.sin(2 * np.pi * n.vib_rate * np.maximum(rel, 0))
    return off


def cc_events(track: dict, song: dict, step_beats: float = 1 / 32) -> list[tuple[float, int, int]]:
    """Track "cc": {"11": [[beat, value], ...]} -> [(seconds, cc, value)], linearly interpolated."""
    spb = 60.0 / float(song["bpm"])
    out = []
    for num, points in (track.get("cc") or {}).items():
        pts = sorted((float(b), float(v)) for b, v in points)
        if not pts:
            continue
        out.append((pts[0][0] * spb, int(num), int(round(pts[0][1]))))
        for (b0, v0), (b1, v1) in zip(pts, pts[1:]):
            steps = max(1, int((b1 - b0) / step_beats))
            last = None
            for i in range(1, steps + 1):
                val = int(round(v0 + (v1 - v0) * i / steps))
                if val != last:
                    out.append(((b0 + (b1 - b0) * i / steps) * spb, int(num), val))
                    last = val
    return out


def automation_curve(points: list, song: dict, length: int, sr: int, default: float) -> np.ndarray:
    """[[beat, value], ...] -> per-sample curve (linear interpolation, held at the ends)."""
    spb = 60.0 / float(song["bpm"])
    pts = sorted((float(b) * spb * sr, float(v)) for b, v in points)
    if not pts:
        return np.full(length, default, dtype=np.float32)
    xs, ys = zip(*pts)
    return np.interp(np.arange(length), xs, ys).astype(np.float32)


def validate(song: dict) -> list[str]:
    """Raises SongError on fatal problems, returns non-fatal warnings."""
    if not isinstance(song, dict):
        raise SongError("Song must be a JSON object")
    if "bpm" not in song:
        raise SongError("Song needs 'bpm'")
    if not 20 <= float(song["bpm"]) <= 400:
        raise SongError("bpm must be between 20 and 400")
    tracks = song.get("tracks")
    if not tracks:
        raise SongError("Song needs a non-empty 'tracks' list")
    names = [t.get("name") for t in tracks]
    if any(not n for n in names):
        raise SongError("Every track needs a 'name'")
    if len(set(names)) != len(names):
        raise SongError(f"Track names must be unique: {names}")
    warnings = []
    for t in tracks:
        if not track_notes_beats(t, song):
            warnings.append(f"Track {t['name']!r} has no notes")
    return warnings
