"""Prompt -> finished song with ACE-Step 1.5 text2music (local GPU): style prompt + optional lyrics in,
mastered WAV/MP3 out. The fastest route to a realistic-sounding full song (vocals included); use the JSON
composer (render_song) instead when every note must be editable.

Output: output/<name>/mix.wav/.mp3 (best take) + mix_take<N>.* for extra takes, and song.json describing
the request so get_song / play_song / enhance_song work on it like on any other song.
"""
from __future__ import annotations

import json
import re

from .enhance import MAX_SECONDS, load_audio, low_vram_args, run_ace, save_mix

MODEL = "acestep-v15-turbo"  # best text2music quality of the 2B models (8 steps)
LM = "acestep-5Hz-lm-1.7B"  # plans structure/melody before rendering; noticeably more coherent songs
QUALITY = {"draft": {"steps": 8, "lm": False}, "high": {"steps": 8, "lm": True}}


def _slug(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", text).strip("_").lower()[:40] or "untitled"


def generate(prompt: str, lyrics: str = "", name: str | None = None, duration: float = 120,
             bpm: int | None = None, key: str = "", language: str = "en", takes: int = 1, seed: int = -1,
             quality: str = "high", loudness: str = "streaming") -> dict:
    from . import render
    from .mix import master
    if quality not in QUALITY:
        return {"error": f"quality must be one of {sorted(QUALITY)}"}
    if not 10 <= duration <= MAX_SECONDS:
        return {"error": f"duration must be 10-{MAX_SECONDS} seconds"}
    preset = QUALITY[quality]
    d = render.OUTPUT_DIR / (name or _slug(prompt))
    work = d / "generated"
    work.mkdir(parents=True, exist_ok=True)
    for old in list(work.glob("*.*")) + list(d.glob("mix*.*")):
        old.unlink()

    lyrics = lyrics.strip()
    paths, seconds, errors = [], 0.0, []
    for t in range(max(1, takes)):  # one process per take: GPU memory is fully released between takes
        args = ["--task", "text2music", "--model", MODEL, "--out-dir", str(work), "--caption", prompt,
                "--lyrics", lyrics, "--language", language if lyrics else "unknown",
                "--duration", str(duration), "--seed", str(seed + t if seed >= 0 else -1),
                "--steps", str(preset["steps"]), *low_vram_args()]
        if bpm:
            args += ["--bpm", str(int(bpm))]
        if key:
            args += ["--keyscale", key]
        if preset["lm"]:
            args += ["--lm", LM]
        r = run_ace(args)
        if "error" in r:
            errors.append(r["error"])
            continue
        paths += r["paths"]
        seconds += r.get("seconds") or 0
    if not paths:
        return {"error": "; ".join(errors) or "no audio was generated"}

    results = []
    for path in paths:
        audio, sr = load_audio(path)
        check = _score(audio, sr, lyrics, language) if lyrics else None
        results.append((audio, sr, check))
    # Best take first: ranked by how accurately the lyrics can be heard.
    results.sort(key=lambda r: -(r[2] or {}).get("lyric_accuracy", 0))
    outputs = []
    for i, (audio, sr, check) in enumerate(results):
        mastered, loud = master(audio, sr, {"loudness": loudness, "master_effects": []}, bpm or 120)
        stem = "mix" if i == 0 else f"mix_take{i + 1}"
        entry = {**save_mix(mastered, sr, d / stem), "take": i + 1, "loudness": loud}
        if check:
            entry["lyric_check"] = {k: check[k] for k in ("lyric_accuracy", "first_word_at_s")}
        outputs.append(entry)

    spec = {"title": prompt[:60], "bpm": bpm, "loudness": loudness, "tracks": [],
            "generated": {"prompt": prompt, "lyrics": lyrics, "duration": duration, "key": key,
                          "language": language, "quality": quality, "seed": seed}}
    (d / "song.json").write_text(json.dumps(spec, indent=2), encoding="utf-8")
    return {"name": d.name, "takes": outputs, "seconds": round(seconds, 1), "failed_takes": errors or None,
            "note": "Play with play_song(name) (extra takes: version='take2', ...). Regenerate with another "
                    "seed for a different performance, or refine the prompt (genre, era, instruments, "
                    "vocal type, mood, production words like 'polished studio mix')."}


def _score(audio, sr: int, lyrics: str, language: str) -> dict | None:
    """Speech-recognition lyric check (skipped if faster-whisper is missing)."""
    try:
        from .lyrics_check import check_take
        return check_take(audio, sr, lyrics, language)
    except Exception:  # scoring is a bonus; never fail the song because of it
        return None
