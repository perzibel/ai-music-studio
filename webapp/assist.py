"""Lyrics-assist dial, backed by the local Ollama install: four stops from "do nothing" to
"write it all". Degrades with a clear error if Ollama isn't running, rather than crashing the
request that asked for it.
"""
from __future__ import annotations

import requests

OLLAMA_MODEL = "qwen3:8b"
OLLAMA_URL = "http://localhost:11434/api/generate"

LEVELS = ("manual", "helps", "extra", "all")

__all__ = ["AssistUnavailable", "OLLAMA_MODEL", "draft_lyrics"]


class AssistUnavailable(Exception):
    pass


def draft_lyrics(level: str, idea_text: str, current_lyrics: str) -> str:
    if level not in LEVELS:
        raise ValueError(f"level must be one of {LEVELS}, got {level!r}")
    if level == "manual":
        return current_lyrics
    if level == "all":
        prompt = f"Write complete song lyrics for this idea: {idea_text}"
    elif level == "helps":
        prompt = (f"Polish and fix these song lyrics, keeping them mostly as written. "
                   f"Idea: {idea_text}\n\nLyrics:\n{current_lyrics}")
    else:  # "extra"
        prompt = (f"These song lyrics are incomplete. Add what's missing (e.g. a missing verse or "
                   f"chorus) around what's already there, keeping the existing lines unchanged. "
                   f"Idea: {idea_text}\n\nLyrics so far:\n{current_lyrics}")
    return _call_ollama(prompt)


def _call_ollama(prompt: str) -> str:
    try:
        resp = requests.post(OLLAMA_URL, json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False})
    except requests.RequestException as exc:
        raise AssistUnavailable(str(exc)) from exc
    if resp.status_code != 200:
        raise AssistUnavailable(f"Ollama returned HTTP {resp.status_code}: {resp.text[:200]}")
    return resp.json()["response"]
