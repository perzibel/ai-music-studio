"""Synthesized drum-machine kits (808 / 909 / trap), written to WAV one-shots + an SFZ map.

The TR-808 and TR-909 were analog synthesizers, so modelling them gives authentic electronic drums.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from scipy.signal import butter, sosfilt

SR = 44100
ROOT = Path(__file__).resolve().parent.parent
GEN_DIR = ROOT / "libraries" / "_generated"
_rng = np.random.default_rng(808)


def _t(sec):
    return np.arange(int(sec * SR)) / SR


def _env(t, decay, attack=0.0005):
    return np.minimum(1.0, t / attack) * np.exp(-t / decay)


def _bp(x, lo, hi, order=2):
    return sosfilt(butter(order, [lo, hi], "bandpass", fs=SR, output="sos"), x)


def _hp(x, f, order=2):
    return sosfilt(butter(order, f, "highpass", fs=SR, output="sos"), x)


def _lp(x, f, order=2):
    return sosfilt(butter(order, f, "lowpass", fs=SR, output="sos"), x)


def _noise(n):
    return _rng.standard_normal(n)


def _sine_sweep(t, f_start, f_end, sweep_time):
    f = f_end + (f_start - f_end) * np.exp(-t / sweep_time)
    return np.sin(2 * np.pi * np.cumsum(f) / SR)


def _metal(t, base=1.0):
    # 808 hi-hat/cymbal: six detuned square waves
    freqs = np.array([205.3, 304.4, 369.6, 522.7, 540.0, 800.0]) * base
    return sum(np.sign(np.sin(2 * np.pi * f * t + i)) for i, f in enumerate(freqs)) / 6


def kick808(decay=0.6):
    t = _t(decay * 3)
    body = _sine_sweep(t, 160, 48, 0.035) * _env(t, decay)
    click = _lp(_noise(len(t)), 3000) * _env(t, 0.004) * 0.3
    return np.tanh((body + click) * 1.4)


def kick909():
    t = _t(0.9)
    body = _sine_sweep(t, 230, 52, 0.025) * _env(t, 0.28)
    click = _hp(_noise(len(t)), 1500) * _env(t, 0.006) * 0.5
    return np.tanh((body * 1.2 + click) * 2.2) * 0.9


def snare808():
    t = _t(0.5)
    tone = (np.sin(2 * np.pi * 180 * t) * 0.6 + np.sin(2 * np.pi * 330 * t) * 0.4) * _env(t, 0.06)
    noise = _bp(_noise(len(t)), 1500, 9000) * _env(t, 0.12)
    return tone * 0.8 + noise * 0.7


def snare909():
    t = _t(0.5)
    tone = _sine_sweep(t, 300, 185, 0.03) * _env(t, 0.07)
    noise = _hp(_noise(len(t)), 1800) * _env(t, 0.16)
    return np.tanh((tone * 0.9 + noise * 0.9) * 1.5)


def clap():
    t = _t(0.6)
    n = _bp(_noise(len(t)), 900, 3500)
    env = np.zeros_like(t)
    for d in (0.0, 0.011, 0.023):  # the famous multi-burst
        env += (t >= d) * np.exp(-np.maximum(0, t - d) / 0.008)
    env += (t >= 0.034) * np.exp(-np.maximum(0, t - 0.034) / 0.12) * 0.7
    return n * env


def rim():
    t = _t(0.1)
    return (np.sin(2 * np.pi * 1700 * t) * 0.6 + _bp(_noise(len(t)), 2000, 6000) * 0.4) * _env(t, 0.012)


def hat(decay, base=1.0):
    t = _t(decay * 5)
    return _hp(_bp(_metal(t, base), 6000, 16000, 3), 7000) * _env(t, decay) * 1.6


def cymbal(decay=1.2, base=1.0):
    t = _t(decay * 4)
    m = _hp(_metal(t, base) * 0.6 + _noise(len(t)) * 0.4, 4000)
    return m * _env(t, decay, attack=0.002)


def tom(freq, decay=0.3):
    t = _t(decay * 4)
    return _sine_sweep(t, freq * 1.6, freq, 0.04) * _env(t, decay)


def cowbell():
    t = _t(0.6)
    sq = np.sign(np.sin(2 * np.pi * 540 * t)) + np.sign(np.sin(2 * np.pi * 800 * t))
    return _bp(sq, 500, 2500) * (_env(t, 0.03) * 0.7 + _env(t, 0.25) * 0.3)


def shaker():
    t = _t(0.15)
    return _hp(_noise(len(t)), 5000) * np.sin(np.pi * np.minimum(1, t / 0.06)) ** 2 * _env(t, 0.03)


def conga(freq):
    t = _t(0.5)
    return _sine_sweep(t, freq * 1.2, freq, 0.01) * _env(t, 0.12)


def kits() -> dict[str, dict[int, np.ndarray]]:
    common = {
        39: clap(), 37: rim(), 56: cowbell(), 70: shaker(), 69: shaker() * 0.7, 54: hat(0.12, 1.3) * 0.7,
        62: conga(330), 63: conga(330) * 0.6, 64: conga(220), 60: conga(420), 61: conga(300), 75: rim() * 0.8,
    }
    return {
        "808_kit": {**common, 36: kick808(0.6), 35: kick808(1.1), 38: snare808(), 40: snare808() * 0.9,
                    42: hat(0.045), 44: hat(0.03) * 0.7, 46: hat(0.35), 49: cymbal(1.3), 57: cymbal(1.0, 1.1),
                    51: cymbal(0.9, 1.4) * 0.6, 52: cymbal(0.9, 0.8), 55: cymbal(0.5, 1.2),
                    50: tom(180), 48: tom(145), 47: tom(120), 45: tom(95), 43: tom(80), 41: tom(65)},
        "909_kit": {**common, 36: kick909(), 35: kick808(0.4), 38: snare909(), 40: snare909() * 0.9,
                    42: hat(0.035, 1.25), 44: hat(0.025, 1.25) * 0.7, 46: hat(0.25, 1.25),
                    49: cymbal(1.5, 1.3), 57: cymbal(1.1, 1.35), 51: cymbal(1.0, 1.6) * 0.6, 52: cymbal(1.0, 0.9),
                    55: cymbal(0.6, 1.4), 50: tom(200, 0.25), 48: tom(165, 0.25), 47: tom(135, 0.25),
                    45: tom(110, 0.25), 43: tom(90, 0.3), 41: tom(75, 0.3)},
        # trap: long booming kick, crisp clap-snare layer, tight hats
        "trap_kit": {**common, 36: kick808(0.9), 35: kick909(), 38: np.tanh((snare909() * 0.6 + clap()[:22050] * 0.8) * 1.3),
                     40: snare808(), 42: hat(0.03, 1.15), 44: hat(0.02, 1.15) * 0.7, 46: hat(0.28, 1.15),
                     49: cymbal(1.4, 1.2), 57: cymbal(1.0, 1.25), 51: cymbal(0.9, 1.5) * 0.6, 52: cymbal(0.9, 0.9),
                     55: cymbal(0.5, 1.3), 50: tom(190), 48: tom(155), 47: tom(125), 45: tom(100), 43: tom(82), 41: tom(66)},
    }


def ensure_kits() -> dict[str, Path]:
    """Generate the kits once; returns kit name -> sfz path."""
    from pedalboard.io import AudioFile
    paths = {}
    built = None
    for name in ("808_kit", "909_kit", "trap_kit"):
        sfz = GEN_DIR / name / f"{name}.sfz"
        paths[name] = sfz
        if sfz.exists():
            continue
        built = built or kits()
        sfz.parent.mkdir(parents=True, exist_ok=True)
        lines = ["// synthesized by ai-music-studio drumsynth", "<global> loop_mode=one_shot amp_veltrack=85"]
        for key, audio in sorted(built[name].items()):
            audio = (audio / (np.max(np.abs(audio)) + 1e-9) * 0.9).astype(np.float32)
            wav = sfz.parent / f"{key}.wav"
            with AudioFile(str(wav), "w", SR, 1, bit_depth=24) as f:
                f.write(audio[None, :])
            # closed/pedal hats (group 1) cut off a ringing open hat (group 2)
            choke = " group=1" if key in (42, 44) else " group=2 off_by=1" if key == 46 else ""
            lines.append(f"<region> key={key}{choke} sample={wav.name}")
        sfz.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return paths
