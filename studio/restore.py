"""Enhance a user's own recording (phone / laptop mic / old demo): restoration + mastering that keeps the
performance, plus an optional AI re-synthesis on top (ACE-Step "cover", see enhance.py).

Restoration chain (all automatic, each step measured first and skipped when not needed):
  rumble/DC high-pass -> mains hum notches (50/60 Hz + harmonics) -> spectral noise reduction ->
  tonal-balance EQ toward a commercial-mix spectrum -> harmonic exciter for dull / band-limited highs ->
  gentle compression -> mono-compatible stereo widening (mono sources) -> LUFS mastering + true-peak limit.

Output: output/<name>/original.wav (decoded input), mix.wav/.mp3 (restored + mastered),
mix_enhanced.wav/.mp3 (AI pass, optional), song.json.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pedalboard as pb
from scipy import signal

SR = 44100
TARGET_SLOPE_DB_OCT = -4.5  # long-term spectrum slope of typical commercial mixes (PSD per Hz)


def load_any(path: str) -> tuple[np.ndarray, int]:
    """Decode an audio file to float32 (2, n). Tries pedalboard, then PyAV/ffmpeg (M4A/AAC phone memos)."""
    try:
        from pedalboard.io import AudioFile
        with AudioFile(path) as f:
            x, sr = f.read(f.frames), int(f.samplerate)
    except Exception:
        x, sr = _load_av(path)
    x = np.asarray(x, dtype=np.float32)
    x = np.repeat(x, 2, axis=0) if x.shape[0] == 1 else x[:2]
    if sr != SR:
        g = np.gcd(sr, SR)
        x = signal.resample_poly(x, SR // g, sr // g, axis=1).astype(np.float32)
    return x, sr


def _load_av(path: str) -> tuple[np.ndarray, int]:
    import av
    with av.open(path) as c:
        stream = c.streams.audio[0]
        sr = stream.rate
        resampler = av.AudioResampler(format="fltp", layout="stereo" if stream.channels > 1 else "mono", rate=sr)
        chunks = [f.to_ndarray() for frame in c.decode(stream) for f in resampler.resample(frame)]
        chunks += [f.to_ndarray() for f in resampler.resample(None)]
    return np.concatenate(chunks, axis=1), sr


def _sos(kind: str, hz, order: int = 4):
    return signal.butter(order, hz, btype=kind, fs=SR, output="sos")


def _ltas(mono: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Long-term average spectrum in dB (PSD per Hz)."""
    f, p = signal.welch(mono, SR, nperseg=8192)
    return f, 10 * np.log10(p + 1e-20)


def remove_rumble(x: np.ndarray) -> np.ndarray:
    return signal.sosfiltfilt(_sos("highpass", 30), x - x.mean(axis=1, keepdims=True), axis=1).astype(np.float32)


def remove_hum(x: np.ndarray) -> tuple[np.ndarray, dict | None]:
    """Find mains hum and notch it + harmonics. Hum is a razor-thin, rock-steady line exactly at 50/60 Hz
    multiples, so it's measured at 0.7 Hz resolution (bass notes are wider and rarely sit exactly there)."""
    f, p = signal.welch(x.mean(axis=0), SR, nperseg=65536)
    db = 10 * np.log10(p + 1e-20)

    def prominence(hz: float) -> float:
        peak = db[np.abs(f - hz) <= 0.7].max()
        around = db[(np.abs(f - hz) >= 2.5) & (np.abs(f - hz) <= 8)]
        return float(peak - np.median(around))

    base = max((50.0, 60.0), key=prominence)
    if prominence(base) < 15:
        return x, None
    notched = [h * base for h in range(1, 9) if prominence(h * base) >= 10]
    for hz in notched:
        b, a = signal.iirnotch(hz, Q=35, fs=SR)
        x = signal.filtfilt(b, a, x, axis=1)
    return x.astype(np.float32), {"mains_hz": base, "notched_hz": notched}


def reduce_noise(x: np.ndarray, strength: float) -> tuple[np.ndarray, dict | None]:
    """Spectral gating with a learned noise print: the noise spectrum is taken from the recording's quietest
    moments (e.g. the second before playing starts), like "learn noise" in Audacity/iZotope. Bins near that
    print are attenuated with a smoothed Wiener-style mask (avoids 'musical noise'). Skipped when there is
    no quiet section to learn from, or the floor is already inaudible."""
    if strength <= 0:
        return x, None
    nfft, hop = 2048, 512
    f, _, Z = signal.stft(x, SR, nperseg=nfft, noverlap=nfft - hop)  # (2, bins, frames)
    mag = np.abs(Z).mean(axis=0)
    power = mag ** 2
    e_db = 10 * np.log10(power.sum(axis=0) + 1e-20)
    quiet = np.argsort(e_db)[:max(20, len(e_db) // 50)]  # quietest 2% (at least ~0.25 s)
    gap_db = float(np.median(e_db) - e_db[quiet].mean())
    floor_db = float(10 * np.log10(power[:, quiet].mean(axis=1).sum() / np.median(power.sum(axis=0)) + 1e-20))
    # Real noise keeps the same spectrum from frame to frame; quiet music (fades, reverb tails) doesn't.
    edges = 1000 * 2.0 ** (np.arange(-12.5, 13) / 3)
    bands = np.array([power[(f >= a) & (f < b)][:, quiet].mean(axis=0) for a, b in zip(edges[:-1], edges[1:])])
    variation_db = float(np.median(np.std(10 * np.log10(bands + 1e-20), axis=1)))
    stats = {"noise_floor_db": round(floor_db, 1), "noise_print_variation_db": round(variation_db, 1)}
    if gap_db < 10 or variation_db > 2.6:
        return x, {"skipped": "no steady background noise found (to learn it, leave ~1 s of silence before "
                              "playing)", **stats}
    if floor_db < -70:
        return x, {"skipped": "background noise is already inaudible", **stats}
    noise = np.median(mag[:, quiet], axis=1, keepdims=True)
    eff = strength
    over = 1.0 + 2.0 * eff
    floor = 10 ** (-(6 + 14 * eff) / 20)
    gain = np.sqrt(np.maximum(1 - over * (noise / (mag + 1e-12)) ** 2, 0.0))  # Wiener-style
    mask = np.maximum(gain, floor)
    from scipy.ndimage import uniform_filter
    mask = uniform_filter(mask, size=(3, 5))  # smooth across frequency and time
    _, y = signal.istft(Z * mask[None], SR, nperseg=nfft, noverlap=nfft - hop)
    y = y[:, :x.shape[1]]
    y = np.pad(y, ((0, 0), (0, x.shape[1] - y.shape[1])))
    return y.astype(np.float32), {"strength": round(eff, 2), "max_reduction_db": round(-20 * np.log10(floor), 1),
                                  **stats}


def tonal_balance(x: np.ndarray, amount: float) -> tuple[np.ndarray, dict | None]:
    """Linear-phase EQ that nudges the long-term spectrum toward a commercial-mix slope (±6 dB max)."""
    if amount <= 0:
        return x, None
    f, db = _ltas(x.mean(axis=0))
    centers = 1000 * 2.0 ** (np.arange(-12, 13) / 3)  # 1/3 octaves, ~63 Hz - 16 kHz
    lvl = np.array([db[(f >= c / 2 ** (1 / 6)) & (f < c * 2 ** (1 / 6))].mean() for c in centers])
    octs = np.log2(centers / 1000)
    target = TARGET_SLOPE_DB_OCT * octs
    fit = (centers >= 100) & (centers <= 8000)
    target += np.mean(lvl[fit] - target[fit])  # same overall level, only the shape differs
    corr = np.clip((target - lvl) * amount, -6, 6)
    corr = np.convolve(np.pad(corr, 1, mode="edge"), np.ones(3) / 3, mode="valid")  # smooth
    corr[centers < 50] = 0
    corr[centers > 8000] = np.minimum(corr[centers > 8000], 3)  # missing air is the exciter's job, not EQ's
    gains = np.interp(np.log2(np.maximum(np.linspace(0, SR / 2, 2049), 1)), np.log2(centers), corr,
                      left=0.0, right=float(corr[-1]))
    fir = signal.firwin2(4097, np.linspace(0, 1, 2049), 10 ** (gains / 20))
    y = signal.fftconvolve(x, fir[None, :], mode="same", axes=1)
    bands = {f"{c:.0f}Hz": round(float(g), 1) for c, g in zip(centers, corr) if abs(g) >= 1.5}
    return y.astype(np.float32), {"changes_db": bands} if bands else None


def find_cutoff(mono: np.ndarray) -> tuple[float, float] | None:
    """Band-limited audio (phone mics, low-bitrate files, old gear) shows a 'cliff' in its spectrum: the
    level drops far faster than any natural mix. Returns (cutoff Hz, drop dB) or None."""
    from scipy.ndimage import uniform_filter1d
    f, db = _ltas(mono)
    db = uniform_filter1d(db, 9)
    fcs = np.geomspace(3000, 14000, 48)
    drops = np.array([db[(f > fc / 1.25) & (f < fc / 1.05)].mean() - db[(f > fc * 1.05) & (f < fc * 1.25)].mean()
                      for fc in fcs])
    hits = np.flatnonzero(drops > 15)  # natural mixes fall ~2-6 dB over this span
    if not len(hits):
        return None
    # The lowest cliff is the one that matters (a later one is e.g. the file's sample-rate limit).
    first = hits[0]
    region = np.arange(first, min(first + 6, len(fcs)))  # refine within ~1/3 octave
    i = region[np.argmax(drops[region])]
    return float(fcs[i]), float(drops[i])


def excite(x: np.ndarray, amount: float) -> tuple[np.ndarray, dict | None]:
    """Regenerate the top end above a detected cutoff from harmonics of the octave below it."""
    if amount <= 0:
        return x, None
    cut = find_cutoff(x.mean(axis=0))
    if not cut:
        return x, None
    fc, drop = cut
    src = signal.sosfiltfilt(_sos("bandpass", [fc / 2, fc * 0.95]), x, axis=1)
    harm = np.tanh(src / (np.abs(src).max() + 1e-9) * 4.0)
    harm = signal.sosfiltfilt(_sos("highpass", fc, 8), harm, axis=1)
    # A natural mix has about as much energy in the octave above fc as in the one below (-1.5 dB);
    # fill only part of that so the result stays smooth rather than fizzy.
    gain = 0.5 * amount * np.std(src) * 10 ** (-1.5 / 20) / (np.std(harm) + 1e-12)
    return (x + harm * gain).astype(np.float32), {"cutoff_hz": round(fc), "cliff_db": round(drop, 1)}


def compress(x: np.ndarray) -> np.ndarray:
    rms_db = 20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-9)
    return pb.Compressor(threshold_db=float(rms_db + 4), ratio=2.0, attack_ms=20, release_ms=180)(x, SR)


def widen(x: np.ndarray) -> tuple[np.ndarray, bool]:
    """Pseudo-stereo for mono recordings: a delayed, high-passed side signal (cancels out in mono)."""
    l, r = x
    if np.corrcoef(l, r)[0, 1] < 0.98:
        return x, False
    mid = (l + r) / 2
    d = int(0.011 * SR)
    side = signal.sosfiltfilt(_sos("highpass", 300), np.r_[np.zeros(d), mid[:-d]]) * 0.22
    return np.stack([mid + side, mid - side]).astype(np.float32), True


def restore(x: np.ndarray, denoise: float = 0.5, eq: float = 0.6, brighten: float = 0.6,
            stereo: bool = True) -> tuple[np.ndarray, dict]:
    report = {}
    x = remove_rumble(x)
    x, report["hum"] = remove_hum(x)
    x, report["noise_reduction"] = reduce_noise(x, denoise)
    x, report["eq"] = tonal_balance(x, eq)
    x, report["exciter"] = excite(x, brighten)
    x = compress(x)
    if stereo:
        x, report["widened_mono"] = widen(x)
    return x, {k: v for k, v in report.items() if v}


def enhance_recording(path: str, name: str | None = None, denoise: float = 0.5, eq: float = 0.6,
                      brighten: float = 0.6, stereo: bool = True, loudness: str | float = "streaming",
                      ai_style: str = "", faithfulness: float = 0.75, seed: int = -1) -> dict:
    from . import render
    from .enhance import save_mix
    from .mix import lufs, master, true_peak_db
    src = Path(path).expanduser()
    if not src.exists():
        return {"error": f"File not found: {src}"}
    x, orig_sr = load_any(str(src))
    d = render.OUTPUT_DIR / (name or ("rec_" + "".join(c if c.isalnum() else "_" for c in src.stem).lower()))
    d.mkdir(parents=True, exist_ok=True)
    for old in d.glob("mix*.*"):
        old.unlink()
    shutil.rmtree(d / "enhanced", ignore_errors=True)
    save_mix(x, SR, d / "original")
    (d / "original.mp3").unlink(missing_ok=True)
    before = {"lufs": round(lufs(x, SR), 1), "true_peak_db": round(true_peak_db(x), 1), "sample_rate": orig_sr}

    y, steps = restore(x, denoise=denoise, eq=eq, brighten=brighten, stereo=stereo)
    y, after = master(y, SR, {"loudness": loudness, "master_effects": []}, 120)
    files = save_mix(y, SR, d / "mix")
    spec = {"title": src.stem, "loudness": loudness, "tracks": [],
            "recording": {"source": str(src), "denoise": denoise, "eq": eq, "brighten": brighten}}
    (d / "song.json").write_text(json.dumps(spec, indent=2), encoding="utf-8")
    out = {"name": d.name, "restored": files, "original": str(d / "original.wav"), "before": before,
           "after": after, "processing": steps}
    if ai_style:
        from .enhance import enhance
        out["ai"] = enhance(d, ai_style, strength=faithfulness, seed=seed, loudness=loudness)
    out["note"] = ("play_song(name, 'mix') = restored, 'original' = untouched input, 'enhanced' = AI pass. "
                   "Restoration keeps the performance; raise denoise for hiss/room noise, lower it if the "
                   "sound gets watery. The AI pass re-performs the song (more polish, details may change).")
    return out
