"""Background-job wrapper around studio.generate.generate: archives a song's existing takes
first (generate() deletes them otherwise, which would fight the "keep every take" goal), then
generates with --offload from the first attempt (see studio/generate.py; the Global Constraint
this plan exists to satisfy).
"""
from __future__ import annotations

from studio.generate import generate  # bare name on this module so tests can monkeypatch it

from . import songs

__all__ = ["make_song_job"]


def make_song_job(song_name: str, caption: str, lyrics: str, takes: int = 2, duration: float = 120,
                   bpm: int | None = None, key: str = "") -> dict:
    songs.archive_current_takes(song_name)
    result = generate(prompt=caption, lyrics=lyrics, name=song_name, takes=takes, duration=duration,
                       bpm=bpm, key=key, offload=True)
    if "error" in result:
        raise RuntimeError(result["error"])
    return result
