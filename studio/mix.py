"""Mixing & mastering: role-based auto EQ, shared reverb bus, mono low end, LUFS loudness + true-peak limiting."""
from __future__ import annotations

import numpy as np
import pedalboard as pb

LOUDNESS = {"streaming": -14.0, "loud": -9.0, "club": -8.0, "dynamic": -18.0, "cinematic": -20.0}
TRUE_PEAK_DB = -1.0

ROLE_WORDS = [
    ("drums", ("drum", "kit", "perc")),
    ("bass", ("808", "synth:sub", "reese", "bass")),
    ("guitar", ("guitar",)),
    ("keys", ("piano", "rhodes", "organ", "keys", "clav", "harpsichord", "electric piano")),
    ("brass", ("horn", "trumpet", "trombone", "tuba", "brass")),
    ("woodwinds", ("flute", "oboe", "clarinet", "bassoon", "piccolo", "sax")),
    ("strings", ("violin", "viola", "cello", "contrabass", "string", "harp", "pizz")),
    ("pad", ("pad", "choir", "voice", "aahs", "oohs")),
    ("mallets", ("glock", "bell", "marimba", "xylo", "vibra", "music box", "celesta", "kalimba")),
    ("synth", ("synth:", "lead", "saw", "square", "pluck")),
]
# role -> (highpass Hz ceiling, reverb send when auto sends are on)
ROLE_SETTINGS = {
    "drums": (25, 0.06), "bass": (30, 0.0), "guitar": (90, 0.08), "keys": (60, 0.14), "brass": (60, 0.18),
    "woodwinds": (110, 0.18), "strings": (45, 0.22), "pad": (110, 0.22), "mallets": (150, 0.2),
    "synth": (120, 0.14), "vocal": (90, 0.15), "other": (40, 0.1),
}
REVERBS = {
    "room": {"room_size": 0.35, "damping": 0.6, "width": 0.9, "predelay": 0.01},
    "plate": {"room_size": 0.6, "damping": 0.25, "width": 1.0, "predelay": 0.02},
    "hall": {"room_size": 0.85, "damping": 0.4, "width": 1.0, "predelay": 0.03},
    "cathedral": {"room_size": 0.97, "damping": 0.3, "width": 1.0, "predelay": 0.04},
}


def infer_role(track: dict, info: dict) -> str:
    if track.get("role"):
        return track["role"]
    if info.get("drums"):
        return "drums"
    text = f"{track.get('instrument', '')} {track.get('name', '')}".lower()
    if "bassoon" in text:
        return "woodwinds"
    for role, words in ROLE_WORDS:
        if any(w in text for w in words):
            return role
    return "other"


def auto_eq(audio: np.ndarray, sr: int, role: str, lowest_hz: float | None) -> np.ndarray:
    """Gentle corrective EQ so parts don't fight: high-pass what doesn't need lows, trim mud."""
    hp = ROLE_SETTINGS.get(role, ROLE_SETTINGS["other"])[0]
    if lowest_hz and role not in ("drums", "bass"):
        hp = min(hp, max(30.0, 0.6 * lowest_hz))  # never cut the fundamental of the lowest note
    chain = [pb.HighpassFilter(cutoff_frequency_hz=hp)]
    if role in ("guitar", "keys", "pad", "synth", "strings"):
        chain.append(pb.PeakFilter(cutoff_frequency_hz=300, gain_db=-1.5, q=0.9))  # mud
    if role == "guitar":
        chain.append(pb.LowpassFilter(cutoff_frequency_hz=11000))  # fizz
    if role == "bass":
        chain.append(pb.PeakFilter(cutoff_frequency_hz=800, gain_db=1.0, q=0.8))  # audible on small speakers
    return pb.Pedalboard(chain)(audio, sr)


def reverb_bus(send_sum: np.ndarray, sr: int, spec: dict | str) -> np.ndarray:
    spec = {"type": spec} if isinstance(spec, str) else dict(spec)
    base = dict(REVERBS.get(spec.get("type", "room"), REVERBS["room"]))
    base.update({k: v for k, v in spec.items() if k in ("room_size", "damping", "width", "predelay")})
    chain = [pb.HighpassFilter(cutoff_frequency_hz=250)]
    if base["predelay"]:
        chain.append(pb.Delay(delay_seconds=base["predelay"], feedback=0.0, mix=1.0))
    chain += [pb.Reverb(room_size=base["room_size"], damping=base["damping"], width=base["width"],
                        wet_level=1.0, dry_level=0.0),
              pb.LowpassFilter(cutoff_frequency_hz=9000)]
    return pb.Pedalboard(chain)(send_sum, sr) * float(spec.get("level", 1.0))


def mono_bass(mix: np.ndarray, sr: int, hz: float = 120.0) -> np.ndarray:
    mid = (mix[0] + mix[1]) / 2
    side = (mix[0] - mix[1]) / 2
    side = pb.HighpassFilter(cutoff_frequency_hz=hz)(side[None, :].astype(np.float32), sr)[0]
    return np.stack([mid + side, mid - side]).astype(np.float32)


def true_peak_db(x: np.ndarray) -> float:
    from scipy.signal import resample_poly
    over = resample_poly(x, 4, 1, axis=1)
    return 20 * np.log10(float(np.max(np.abs(over))) + 1e-12)


def lufs(x: np.ndarray, sr: int) -> float:
    import pyloudnorm
    return float(pyloudnorm.Meter(sr).integrated_loudness(x.T.astype(np.float64)))


def limit(x: np.ndarray, sr: int, ceiling_db: float = TRUE_PEAK_DB - 0.3, lookahead_ms: float = 3.0,
          release_ms: float = 90.0) -> np.ndarray:
    """Transparent look-ahead peak limiter (no makeup gain), computed at a 32-sample control rate."""
    from scipy.ndimage import maximum_filter1d
    ceil = 10 ** (ceiling_db / 20)
    n = x.shape[1]
    hop = 32
    peak = np.max(np.abs(x), axis=0)
    nblk = -(-n // hop)
    pk = np.pad(peak, (0, nblk * hop - n)).reshape(nblk, hop).max(axis=1)
    la = max(1, int(lookahead_ms / 1000 * sr / hop) + 1)
    need = np.minimum(1.0, ceil / np.maximum(maximum_filter1d(pk, size=2 * la + 1), 1e-9))
    rel = np.exp(-hop / (release_ms / 1000 * sr))
    g = np.empty_like(need)
    cur = 1.0
    for i, v in enumerate(need):  # instant attack (thanks to look-ahead), smooth release
        cur = v if v < cur else v - (v - cur) * rel
        g[i] = cur
    gain = np.interp(np.arange(n), (np.arange(nblk) + 0.5) * hop, g)
    return np.clip(x * gain, -ceil, ceil).astype(np.float32)


def master(mix: np.ndarray, sr: int, song: dict, bpm: float) -> tuple[np.ndarray, dict]:
    from . import effects as fx
    target = song.get("loudness", "streaming")
    mix = mono_bass(mix, sr)
    peak = float(np.max(np.abs(mix))) or 1.0
    mix = (mix * (10 ** (-6 / 20) / peak)).astype(np.float32)  # consistent level into the bus processing
    master_fx = song.get("master_effects", ["glue"])
    if master_fx:
        mix = fx.build_chain(master_fx, bpm)(mix, sr)
    if target in (None, "off", False):  # legacy: just peak-normalize
        mix = mix * (10 ** (float(song.get("master_peak_db", -1.0)) / 20) / (float(np.max(np.abs(mix))) or 1.0))
        return mix.astype(np.float32), {"lufs": round(lufs(mix, sr), 1), "true_peak_db": round(true_peak_db(mix), 1)}
    if isinstance(target, str) and target not in LOUDNESS:
        raise ValueError(f"Unknown loudness {target!r}. Use {sorted(LOUDNESS)}, a LUFS number, or 'off'")
    target_lufs = float(LOUDNESS.get(target, target)) if isinstance(target, str) else float(target)
    pre = mix.astype(np.float32)
    start = lufs(pre, sr)
    if not np.isfinite(start):  # silence
        return pre, {"lufs": None, "true_peak_db": None, "target_lufs": target_lufs}

    def process(gain_db: float) -> np.ndarray:
        y = pre * 10 ** (gain_db / 20)
        if target_lufs > -11:  # loud masters: soft-clip transients so the limiter works less hard
            drive = 10 ** (1.5 / 20)
            y = np.tanh(y * drive) / np.tanh(drive)
        return limit(y, sr)

    gain = target_lufs - start
    out = process(gain)
    for _ in range(10):  # limiting lowers loudness, so nudge the gain until we hit the target
        err = target_lufs - lufs(out, sr)
        if abs(err) < 0.2 or gain > target_lufs - start + 12:  # don't crush the mix beyond 12 dB of limiting
            break
        gain += err * 1.3 if err > 0 else err
        out = process(gain)
    tp = true_peak_db(out)
    if tp > TRUE_PEAK_DB:  # inter-sample peaks
        out = out * 10 ** ((TRUE_PEAK_DB - tp) / 20)
    report = {"lufs": round(lufs(out, sr), 1), "true_peak_db": round(float(true_peak_db(out)), 1),
              "target_lufs": target_lufs}
    if report["lufs"] < target_lufs - 1:
        report["note"] = ("Stopped short of the target to avoid over-limiting (usually heavy sub bass). "
                          "Lower the bass/sub volume or use a quieter loudness target.")
    return out.astype(np.float32), report
