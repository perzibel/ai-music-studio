"""AI singer: generates a sung vocal track over a rendered instrumental with ACE-Step 1.5 ("lego" task).

Song JSON:
  "vocals": {"lyrics": "[verse]\\n...\\n[chorus]\\n...", "style": "male classic rock vocalist, raspy",
             "language": "en", "volume": 1.0, "takes": 2, "seed": -1}
Output: output/<song>/mix_vocals.wav/.mp3 (take 1) and mix_vocals_take<N>.* for extra takes.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pedalboard as pb

from .enhance import MAX_SECONDS, audio_seconds, load_audio, low_vram_args, run_ace, save_mix

VOCAL_MODEL = "acestep-v15-base"  # lego (add a track to existing audio) needs the base model
INSTRUCTION = "Generate the vocals track based on the audio context:"


def _resample(x: np.ndarray, sr_from: int, sr_to: int) -> np.ndarray:
    if sr_from == sr_to:
        return x
    from scipy.signal import resample_poly
    g = np.gcd(sr_from, sr_to)
    return resample_poly(x, sr_to // g, sr_from // g, axis=1).astype(np.float32)


def _fit(x: np.ndarray, n: int) -> np.ndarray:
    return x[:, :n] if x.shape[1] >= n else np.pad(x, ((0, 0), (0, n - x.shape[1])))


def _instrumental_premaster(song_dir: Path) -> tuple[np.ndarray, int]:
    """Sum of the exported stems = the mix before mastering (so we can re-master with the vocal in it)."""
    total, sr = None, 44100
    for f in sorted((song_dir / "stems").glob("*.wav")):
        x, sr = load_audio(str(f))
        total = x if total is None else _fit(total, x.shape[1]) + _fit(x, total.shape[1])
    if total is None:
        total, sr = load_audio(str(song_dir / "mix.wav"))
    return total, sr


def _active_rms(x: np.ndarray, block: int = 4410) -> float:
    m = x.mean(axis=0)
    n = len(m) // block * block
    r = np.sqrt(np.mean(m[:n].reshape(-1, block) ** 2, axis=1)) if n else np.array([np.sqrt(np.mean(m ** 2))])
    active = r[r > r.max() * 0.1]
    return float(np.sqrt(np.mean(active ** 2))) if len(active) else 1e-9


def vocal_chain(vocal: np.ndarray, sr: int, bpm: float) -> np.ndarray:
    """Classic vocal treatment: clean lows, even out dynamics, presence, slapback + plate."""
    dry = pb.Pedalboard([
        pb.HighpassFilter(cutoff_frequency_hz=90),
        pb.Compressor(threshold_db=-20, ratio=3.5, attack_ms=5, release_ms=80),
        pb.PeakFilter(cutoff_frequency_hz=3000, gain_db=2.5, q=0.8),
        pb.HighShelfFilter(cutoff_frequency_hz=9000, gain_db=-2.0),  # tame harsh "s" sounds
    ])(vocal, sr)
    wet = pb.Pedalboard([
        pb.Delay(delay_seconds=60.0 / bpm * 0.75, feedback=0.2, mix=1.0),
        pb.Reverb(room_size=0.6, damping=0.3, wet_level=1.0, dry_level=0.0, width=1.0),
        pb.HighpassFilter(cutoff_frequency_hz=300),
    ])(dry, sr)
    return dry + wet * 0.18


def add_vocals(song_dir: Path, song: dict, takes: int | None = None, seed: int | None = None,
               steps: int = 32) -> dict:
    spec = dict(song.get("vocals") or {})
    lyrics = (spec.get("lyrics") or "").strip()
    if not lyrics:
        return {"error": "Song has no \"vocals\": {\"lyrics\": ...} section. Add lyrics with [verse]/[chorus] tags."}
    src = song_dir / "mix.wav"
    if not src.exists():
        return {"error": "Render the song first (render_song), then add vocals."}
    duration = audio_seconds(src)
    if duration > MAX_SECONDS:
        return {"error": f"Song is {duration:.0f}s; vocals support up to {MAX_SECONDS}s."}
    takes = int(takes or spec.get("takes", 1))
    seed = int(seed if seed is not None else spec.get("seed", -1))
    style = spec.get("style") or "expressive lead vocalist"
    work = song_dir / "vocals"
    work.mkdir(exist_ok=True)
    for old in work.glob("*.*"):  # raw takes from previous runs
        old.unlink()
    paths, seconds, errors = [], 0.0, []
    for t in range(takes):  # one process per take: GPU memory is fully released between takes
        take_seed = seed + t if seed >= 0 else -1
        args = ["--task", "lego", "--model", VOCAL_MODEL, "--instruction", INSTRUCTION, "--src", str(src),
                "--out-dir", str(work), "--caption", style, "--lyrics", lyrics,
                "--language", spec.get("language", "en"), "--duration", f"{duration:.2f}",
                "--bpm", str(int(song.get("bpm", 120))), "--seed", str(take_seed), "--steps", str(steps),
                *low_vram_args()]
        r = run_ace(args)
        if "error" in r:
            errors.append(r["error"])
            continue
        paths += r["paths"]
        seconds += r.get("seconds") or 0
    if not paths:
        return {"error": "; ".join(errors) or "no vocal takes were generated"}
    result = {"paths": paths, "seconds": round(seconds, 1)}

    from .mix import master
    inst, sr = _instrumental_premaster(song_dir)
    bpm = float(song.get("bpm", 120))
    gens = []
    for path in result["paths"]:
        gen, gsr = load_audio(path)
        gens.append((_fit(_resample(gen, gsr, sr), inst.shape[1]), _score(gen, gsr, lyrics, spec)))
    # Best take first: ranked by how accurately the lyrics can be heard.
    gens.sort(key=lambda g: -(g[1] or {}).get("lyric_accuracy", 0))
    for f in list(song_dir.glob("mix_vocals*.*")) + list((song_dir / "stems").glob("_vocals_take*.wav")):
        f.unlink()
    outputs = []
    for i, (gen, check) in enumerate(gens):
        # Does the model return the vocal alone, or the whole song with the vocal in it?
        a, b = inst.mean(axis=0), gen.mean(axis=0)
        corr = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))
        if corr > 0.5:  # full mix returned: use it as-is
            mixed, kind = gen, "full mix from model"
        else:
            vocal = vocal_chain(gen, sr, bpm)
            vocal *= _active_rms(inst) / _active_rms(vocal) * float(spec.get("volume", 1.0)) * 0.9
            mixed, kind = inst + vocal, "vocal stem mixed over the instrumental"
            vpath = song_dir / "stems" / f"_vocals_take{i + 1}.wav"
            save_mix(vocal, sr, vpath.with_suffix(""))
            vpath.with_suffix(".mp3").unlink(missing_ok=True)
        mastered, loud = master(mixed.astype(np.float32), sr,
                                {"loudness": song.get("loudness", "streaming"), "master_effects": ["glue"]}, bpm)
        name = "mix_vocals" if i == 0 else f"mix_vocals_take{i + 1}"
        entry = {**save_mix(mastered, sr, song_dir / name), "take": i + 1, "type": kind, "loudness": loud}
        if check:
            entry["lyric_check"] = {k: check[k] for k in ("lyric_accuracy", "first_word_at_s")}
            entry["heard"] = [f"{s['start']:.1f}s {s['text']}" for s in check["heard"]]
        outputs.append(entry)
    return {"takes": outputs, "seconds": result.get("seconds"), "failed_takes": errors or None,
            "note": "Takes are ranked by lyric accuracy (speech recognition). Compare 'heard' with the lyrics: "
                    "if lines are wrong or missing, re-run with another seed or simplify those lines."}


def _score(gen: np.ndarray, sr: int, lyrics: str, spec: dict) -> dict | None:
    """Transcribe the raw vocal and score it against the lyrics (skipped if faster-whisper is missing)."""
    try:
        from .lyrics_check import check_take
    except ImportError:
        return None
    try:
        return check_take(gen, sr, lyrics, spec.get("language", "en"))
    except Exception:  # scoring is a bonus; never fail the vocal because of it
        return None
