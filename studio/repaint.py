"""Redo one part of a finished song (ACE-Step "repaint") and keep everything else exactly as it was.

ACE-Step regenerates only the chosen time range. Its output is then spliced back into the ORIGINAL audio
(level-matched, short crossfades at both edges), so the parts you liked stay bit-identical instead of
going through the model's decoder again. To fix two parts, run it twice: the second time on the take you
kept from the first.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np

from .enhance import MAX_SECONDS, low_vram_args, run_ace, save_mix

MODEL = "acestep-v15-turbo"  # repaint works on turbo (8 steps); same model as generate
FADE_S = 0.3  # crossfade length at each edge of the replaced region


def _read(path: Path, sr: int | None = None):
    from pedalboard.io import AudioFile
    with AudioFile(str(path)) as f:
        if sr and f.samplerate != sr:
            with f.resampled_to(sr) as r:
                audio, rate = r.read(r.frames), sr
        else:
            audio, rate = f.read(f.frames), int(f.samplerate)
    audio = audio.astype("float32")
    if audio.shape[0] == 1:
        audio = np.repeat(audio, 2, axis=0)
    return audio, rate


def parse_time(t) -> float:
    """'1:12' / '1:12.5' / '72' -> seconds."""
    if isinstance(t, (int, float)):
        return float(t)
    parts = [float(p) for p in str(t).strip().split(":")]
    secs = 0.0
    for p in parts:
        secs = secs * 60 + p
    return secs


def splice(orig: np.ndarray, new: np.ndarray, sr: int, start: float, end: float) -> np.ndarray:
    """Original audio with [start, end] taken from `new`, level-matched and crossfaded at both edges."""
    n = min(orig.shape[1], new.shape[1])
    orig, new = orig[:, :n], new[:, :n]
    a, b = int(start * sr), min(int(end * sr), n)
    # Match the new take's level to the original using the parts that were NOT redone.
    keep = np.ones(n, bool)
    keep[a:b] = False
    if keep.any():
        rms_o = np.sqrt(np.mean(orig[:, keep] ** 2)) + 1e-9
        rms_n = np.sqrt(np.mean(new[:, keep] ** 2)) + 1e-9
        new = new * (rms_o / rms_n)
    # Mask: 0 = original, 1 = new; equal-power ramps centred on each edge.
    mask = np.zeros(n, "float32")
    mask[a:b] = 1.0
    f = int(FADE_S * sr)
    for edge, rising in ((a, True), (b, False)):
        lo, hi = max(0, edge - f // 2), min(n, edge + f // 2)
        if hi <= lo or (rising and edge == 0) or (not rising and edge >= n):
            continue
        x = np.linspace(0, 1, hi - lo, dtype="float32")
        mask[lo:hi] = np.sin(x * np.pi / 2) if rising else np.cos(x * np.pi / 2)
    g_new, g_old = np.sin(mask * np.pi / 2), np.cos(mask * np.pi / 2)  # equal-power mix
    out = orig * g_old + new * g_new
    peak = np.abs(out).max()
    return out / peak * 0.98 if peak > 0.98 else out


def repaint(src: str | Path, start, end, caption: str, lyrics: str = "", out_dir: str | Path | None = None,
            takes: int = 2, seed: int = -1, steps: int = 8, bpm: int | None = None,
            instrumental: bool = False) -> dict:
    if not lyrics.strip() and not instrumental:
        # Without lyrics ACE-Step renders the section as instrumental, which would drop the singer.
        return {"error": "Pass the song's lyrics (the whole song, with any new lines for this part), "
                         "or instrumental=True if the song has no vocals."}
    src = Path(src).resolve()
    if not src.exists():
        return {"error": f"File not found: {src}"}
    start, end = parse_time(start), parse_time(end)
    orig, sr = _read(src)
    duration = orig.shape[1] / sr
    if not 0 <= start < end <= duration + 0.01:
        return {"error": f"Range {start:.1f}-{end:.1f}s is outside the song (0-{duration:.1f}s)."}
    if duration > MAX_SECONDS:
        return {"error": f"Song is {duration:.0f}s; repaint supports up to {MAX_SECONDS}s."}
    out = Path(out_dir).resolve() if out_dir else src.parent / f"{src.stem}_repaint"
    work = out / f"raw_{int(start)}-{int(end)}"
    work.mkdir(parents=True, exist_ok=True)
    original_copy = out / f"original{src.suffix}"
    if not original_copy.exists():
        shutil.copy2(src, original_copy)  # keep the untouched source next to the takes
    args = ["--task", "repaint", "--model", MODEL, "--src", str(src), "--out-dir", str(work),
            "--caption", caption, "--lyrics", lyrics, "--duration", f"{duration:.2f}",
            "--repaint-start", f"{start:.3f}", "--repaint-end", f"{end:.3f}",
            "--seed", str(seed), "--steps", str(steps), "--takes", str(takes), "--offload", *low_vram_args()]
    if bpm:
        args += ["--bpm", str(int(bpm))]
    r = run_ace(args)
    if "error" in r:
        return r
    results = []
    for i, p in enumerate(r["paths"], 1):
        new, _ = _read(Path(p), sr)
        mixed = splice(orig, new, sr, start, end)
        files = save_mix(mixed, sr, out / f"take{i}_{int(start)}-{int(end)}s")
        results.append(files)
    return {"takes": results, "original": str(original_copy), "range": [start, end],
            "seconds": r.get("seconds"), "partial_errors": r.get("partial_errors"),
            "peak_memory_gb": r.get("peak_memory_gb"),
            "note": "Only the chosen range changed; the rest is your original audio. "
                    "Pick a take, then run again on it for the next part."}
