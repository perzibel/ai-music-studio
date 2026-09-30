"""Builds pedalboard effect chains from simple JSON descriptions."""
from __future__ import annotations

import pedalboard as pb

# type -> (plugin class, {friendly param name: pedalboard param name}, default kwargs)
EFFECTS = {
    "distortion": (pb.Distortion, {"drive": "drive_db"}, {"drive_db": 20}),
    "reverb": (pb.Reverb, {"room": "room_size", "size": "room_size", "wet": "wet_level", "dry": "dry_level"},
               {"room_size": 0.5, "wet_level": 0.22, "dry_level": 1.0, "damping": 0.5}),
    "delay": (pb.Delay, {"time_s": "delay_seconds", "seconds": "delay_seconds"},
              {"delay_seconds": 0.375, "feedback": 0.3, "mix": 0.2}),
    "chorus": (pb.Chorus, {"rate": "rate_hz"}, {"rate_hz": 1.0, "depth": 0.25, "mix": 0.4}),
    "phaser": (pb.Phaser, {"rate": "rate_hz"}, {"rate_hz": 0.5, "depth": 0.5, "mix": 0.4}),
    "compressor": (pb.Compressor, {"threshold": "threshold_db", "attack": "attack_ms", "release": "release_ms"},
                   {"threshold_db": -16, "ratio": 3, "attack_ms": 10, "release_ms": 120}),
    "limiter": (pb.Limiter, {"threshold": "threshold_db", "release": "release_ms"}, {"threshold_db": -1}),
    "highpass": (pb.HighpassFilter, {"hz": "cutoff_frequency_hz", "cutoff": "cutoff_frequency_hz"},
                 {"cutoff_frequency_hz": 80}),
    "lowpass": (pb.LowpassFilter, {"hz": "cutoff_frequency_hz", "cutoff": "cutoff_frequency_hz"},
                {"cutoff_frequency_hz": 8000}),
    "lowshelf": (pb.LowShelfFilter, {"hz": "cutoff_frequency_hz", "gain": "gain_db"},
                 {"cutoff_frequency_hz": 200, "gain_db": 0}),
    "highshelf": (pb.HighShelfFilter, {"hz": "cutoff_frequency_hz", "gain": "gain_db"},
                  {"cutoff_frequency_hz": 6000, "gain_db": 0}),
    "eq": (pb.PeakFilter, {"hz": "cutoff_frequency_hz", "gain": "gain_db"},
           {"cutoff_frequency_hz": 1000, "gain_db": 0, "q": 1.0}),
    "gain": (pb.Gain, {"db": "gain_db"}, {"gain_db": 0}),
    "bitcrush": (pb.Bitcrush, {"bits": "bit_depth"}, {"bit_depth": 10}),
    "noisegate": (pb.NoiseGate, {"threshold": "threshold_db"}, {"threshold_db": -45}),
    "clipping": (pb.Clipping, {"threshold": "threshold_db"}, {"threshold_db": -6}),
    "pitchshift": (pb.PitchShift, {}, {"semitones": 0}),
    "filter": (pb.LadderFilter, {"hz": "cutoff_hz"}, {"cutoff_hz": 2000, "resonance": 0.2}),
}
EFFECTS["peak"] = EFFECTS["eq"]

PRESETS = {
    "metal_amp": [
        {"type": "highpass", "hz": 100}, {"type": "noisegate", "threshold_db": -50},
        {"type": "eq", "hz": 900, "gain_db": 4, "q": 0.8},
        {"type": "distortion", "drive_db": 34},
        {"type": "eq", "hz": 450, "gain_db": -5, "q": 1.0},
        {"type": "eq", "hz": 2600, "gain_db": 3, "q": 1.0},
        {"type": "lowpass", "hz": 7000}, {"type": "highpass", "hz": 90},
        {"type": "compressor", "threshold_db": -18, "ratio": 3},
    ],
    "rock_amp": [
        {"type": "highpass", "hz": 90}, {"type": "distortion", "drive_db": 22},
        {"type": "eq", "hz": 800, "gain_db": 2.5, "q": 0.9}, {"type": "lowpass", "hz": 7500},
        {"type": "compressor", "threshold_db": -16, "ratio": 2.5},
    ],
    "crunch": [
        {"type": "highpass", "hz": 90}, {"type": "distortion", "drive_db": 12},
        {"type": "lowpass", "hz": 6500},
    ],
    "clean_guitar": [
        {"type": "compressor", "threshold_db": -18, "ratio": 3}, {"type": "chorus", "mix": 0.25},
        {"type": "reverb", "room_size": 0.3, "wet_level": 0.15},
    ],
    "bass_amp": [
        {"type": "compressor", "threshold_db": -18, "ratio": 4, "attack_ms": 15},
        {"type": "distortion", "drive_db": 8}, {"type": "lowpass", "hz": 4500},
        {"type": "highpass", "hz": 35},
    ],
    "drum_bus": [
        {"type": "compressor", "threshold_db": -14, "ratio": 4, "attack_ms": 12, "release_ms": 100},
        {"type": "highshelf", "hz": 8000, "gain_db": 2},
    ],
    "lofi": [
        {"type": "highpass", "hz": 120}, {"type": "lowpass", "hz": 5000}, {"type": "bitcrush", "bit_depth": 11},
        {"type": "compressor", "threshold_db": -18, "ratio": 3},
    ],
    "vinyl_warmth": [
        {"type": "lowshelf", "hz": 150, "gain_db": 2}, {"type": "highshelf", "hz": 9000, "gain_db": -4},
        {"type": "distortion", "drive_db": 4},
    ],
    "room_reverb": [{"type": "reverb", "room_size": 0.35, "wet_level": 0.15, "damping": 0.6}],
    "hall_reverb": [{"type": "reverb", "room_size": 0.85, "wet_level": 0.28, "damping": 0.4, "width": 1.0}],
    "edm_lead": [
        {"type": "highpass", "hz": 150}, {"type": "chorus", "mix": 0.3},
        {"type": "delay", "time_beats": 0.75, "feedback": 0.3, "mix": 0.18},
        {"type": "reverb", "room_size": 0.6, "wet_level": 0.2},
    ],
    "808_saturation": [{"type": "distortion", "drive_db": 6}, {"type": "lowpass", "hz": 4000}],
    "glue": [{"type": "compressor", "threshold_db": -12, "ratio": 2.0, "attack_ms": 25, "release_ms": 200}],
    "master": [
        {"type": "compressor", "threshold_db": -10, "ratio": 2.0, "attack_ms": 20, "release_ms": 200},
        {"type": "limiter", "threshold_db": -1.0, "release_ms": 100},
    ],
}


def expand(effects: list) -> list[dict]:
    out = []
    for fx in effects or []:
        if isinstance(fx, str):
            fx = {"preset": fx} if fx in PRESETS else {"type": fx}
        if "preset" in fx:
            if fx["preset"] not in PRESETS:
                raise ValueError(f"Unknown effect preset {fx['preset']!r}. Available: {sorted(PRESETS)}")
            out += expand(PRESETS[fx["preset"]])
        else:
            out.append(fx)
    return out


def build_chain(effects: list, bpm: float) -> pb.Pedalboard:
    plugins = []
    for fx in expand(effects):
        kind = str(fx.get("type", "")).lower()
        if kind == "vst3":
            plugin = pb.load_plugin(fx["path"])
            for k, v in (fx.get("params") or {}).items():
                setattr(plugin, k, v)
            plugins.append(plugin)
            continue
        if kind not in EFFECTS:
            raise ValueError(f"Unknown effect type {kind!r}. Available: {sorted(EFFECTS) + ['vst3']} "
                             f"or presets: {sorted(PRESETS)}")
        cls, aliases, defaults = EFFECTS[kind]
        kwargs = dict(defaults)
        for k, v in fx.items():
            if k == "type":
                continue
            if k == "time_beats":
                kwargs["delay_seconds"] = float(v) * 60.0 / bpm
                continue
            kwargs[aliases.get(k, k)] = v
        try:
            plugins.append(cls(**kwargs))
        except TypeError as e:
            raise ValueError(f"Bad parameters for effect {kind!r}: {e}") from e
    return pb.Pedalboard(plugins)
