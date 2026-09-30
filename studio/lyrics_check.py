"""Checks AI vocal takes by transcribing them (faster-whisper, local) and comparing with the intended lyrics.

Gives the AI composer "ears": a lyric-accuracy score per take and where each line was actually sung.
"""
from __future__ import annotations

import difflib
import re
from functools import lru_cache

import numpy as np

MODEL = "small.en"  # ~460 MB, good accuracy on singing; downloads once


def _words(text: str) -> list[str]:
    text = re.sub(r"\[[^\]]*\]", " ", text)  # drop [verse]/[chorus] tags
    return re.findall(r"[a-z0-9']+", text.lower())


@lru_cache(maxsize=1)
def _model(name: str):
    from faster_whisper import WhisperModel
    return WhisperModel(name, device="cpu", compute_type="int8")


def transcribe(audio: np.ndarray, sr: int, language: str = "en") -> list[dict]:
    from scipy.signal import resample_poly
    mono = audio.mean(axis=0) if audio.ndim == 2 else audio
    if sr != 16000:
        g = np.gcd(sr, 16000)
        mono = resample_poly(mono, 16000 // g, sr // g)
    mono = (mono / (np.max(np.abs(mono)) + 1e-9) * 0.9).astype(np.float32)
    model = _model(MODEL if language == "en" else "small")
    segments, _ = model.transcribe(mono, language=language, beam_size=5, vad_filter=True,
                                   condition_on_previous_text=False)
    return [{"start": round(s.start, 1), "end": round(s.end, 1), "text": s.text.strip()} for s in segments]


def score(lyrics: str, heard: list[dict]) -> dict:
    """Word-level similarity between intended lyrics and what the recognizer heard (0-1)."""
    want = _words(lyrics)
    got = _words(" ".join(s["text"] for s in heard))
    sm = difflib.SequenceMatcher(a=want, b=got, autojunk=False)
    matched = sum(b.size for b in sm.get_matching_blocks())
    return {"lyric_accuracy": round(matched / max(1, len(want)), 2),
            "words_expected": len(want), "words_heard": len(got)}


def check_take(vocal: np.ndarray, sr: int, lyrics: str, language: str = "en") -> dict:
    """Transcribe one raw vocal take; returns accuracy, first sung word time and the timed transcript."""
    heard = transcribe(vocal, sr, language)
    return {**score(lyrics, heard), "first_word_at_s": heard[0]["start"] if heard else None,
            "heard": heard}
