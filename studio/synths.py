"""Small built-in synthesizers for sounds SoundFonts do badly: 808s, supersaws, subs, plucks, pads."""
from __future__ import annotations

import numpy as np

from .song import Note, pitch_curve

SYNTH_TYPES = {
    # type: default parameters
    "808": dict(attack=0.002, decay=1.8, sustain=0.0, release=0.12, pitch_drop=7.0, pitch_time=0.04,
                drive=2.5, voices=1, detune=0.0, wave="sine", level=0.3),
    "sub": dict(attack=0.005, decay=0.2, sustain=0.9, release=0.08, drive=1.0, voices=1, detune=0.0,
                wave="sine", level=0.45),
    "supersaw": dict(attack=0.01, decay=0.3, sustain=0.8, release=0.25, voices=7, detune=22.0,
                     wave="saw", level=0.35, drive=1.0),
    "pluck": dict(attack=0.002, decay=0.28, sustain=0.0, release=0.12, voices=5, detune=14.0,
                  wave="saw", level=0.45, drive=1.0),
    "pad": dict(attack=0.6, decay=1.0, sustain=0.8, release=1.2, voices=7, detune=18.0,
                wave="saw", level=0.25, drive=1.0),
    "saw": dict(attack=0.005, decay=0.2, sustain=0.85, release=0.12, voices=2, detune=8.0,
                wave="saw", level=0.4, drive=1.0),
    "square": dict(attack=0.005, decay=0.2, sustain=0.85, release=0.12, voices=2, detune=6.0,
                   wave="square", level=0.35, drive=1.0),
    "reese": dict(attack=0.01, decay=0.2, sustain=0.9, release=0.15, voices=3, detune=30.0,
                  wave="saw", level=0.3, drive=1.6),
}


def _polyblep(ph: np.ndarray, dt: np.ndarray) -> np.ndarray:
    out = np.zeros_like(ph)
    m = ph < dt
    x = ph[m] / dt[m]
    out[m] = x + x - x * x - 1.0
    m = ph > 1.0 - dt
    x = (ph[m] - 1.0) / dt[m]
    out[m] = x * x + x + x + 1.0
    return out


def _osc(wave: str, freq: np.ndarray, sr: int, phase0: float) -> np.ndarray:
    inc = freq / sr
    ph = (phase0 + np.cumsum(inc)) % 1.0
    if wave == "sine":
        return np.sin(2 * np.pi * ph)
    saw = 2.0 * ph - 1.0 - _polyblep(ph, inc)
    if wave == "saw":
        return saw
    ph2 = (ph + 0.5) % 1.0
    saw2 = 2.0 * ph2 - 1.0 - _polyblep(ph2, inc)
    return (saw - saw2) * 0.5  # square


def _envelope(n_total: int, n_on: int, sr: int, a: float, d: float, s: float, r: float) -> np.ndarray:
    t = np.arange(n_total) / sr
    env = np.empty(n_total)
    a = max(a, 1e-4)
    # attack -> exponential decay toward sustain
    decay_curve = s + (1.0 - s) * np.exp(-(t - a) / max(d, 1e-4) * 3.0)
    env[:] = np.where(t < a, t / a, decay_curve)
    # release from the level reached at note-off
    if n_on < n_total:
        level = env[n_on - 1] if n_on > 0 else 0.0
        tr = t[n_on:] - t[n_on]
        env[n_on:] = level * np.clip(1.0 - tr / max(r, 1e-4), 0.0, 1.0)
    return env


def render_synth(kind: str, notes: list[Note], params: dict, sr: int, length: int, seed: int = 0) -> np.ndarray:
    if kind not in SYNTH_TYPES:
        raise ValueError(f"Unknown synth {kind!r}. Available: {sorted(SYNTH_TYPES)}")
    p = {**SYNTH_TYPES[kind], **(params or {})}
    rng = np.random.default_rng(seed)
    out = np.zeros((2, length), dtype=np.float64)
    voices = max(1, int(p["voices"]))
    for n in notes:
        start = int(n.start * sr)
        n_on = max(1, int(n.dur * sr))
        n_total = n_on + int(p["release"] * sr)
        if start >= length:
            continue
        n_total = min(n_total, length - start)
        n_on = min(n_on, n_total)
        base = 440.0 * 2 ** ((n.pitch - 69) / 12.0)
        t = np.arange(n_total) / sr
        freq = np.full(n_total, base)
        if p.get("pitch_drop"):
            freq = base * 2 ** (p["pitch_drop"] * np.exp(-t / max(p["pitch_time"], 1e-4)) / 12.0)
        if n.expressive:  # bends, 808 slides, vibrato
            freq = freq * 2 ** (pitch_curve(n, n.start + t) / 12.0)
        sig = np.zeros((2, n_total))
        for v in range(voices):
            spread = 0.0 if voices == 1 else (v / (voices - 1)) * 2 - 1  # -1..1
            cents = spread * p["detune"]
            wave = _osc(p["wave"], freq * 2 ** (cents / 1200.0), sr, rng.random() if voices > 1 else 0.0)
            pan = spread * 0.8
            sig[0] += wave * np.sqrt((1 - pan) / 2)
            sig[1] += wave * np.sqrt((1 + pan) / 2)
        sig /= np.sqrt(voices)
        if p["drive"] and p["drive"] != 1.0:
            sig = np.tanh(sig * p["drive"]) / np.tanh(p["drive"])
        env = _envelope(n_total, n_on, sr, p["attack"], p["decay"], p["sustain"], p["release"])
        # tiny fade at the very end to avoid clicks
        fade = min(64, n_total)
        env[-fade:] *= np.linspace(1, 0, fade)
        out[:, start:start + n_total] += sig * env * p["level"] * (n.vel / 127.0)
    return out.astype(np.float32)
