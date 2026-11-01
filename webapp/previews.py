"""Cached 10-second genre preview clips (the six tiles from the approved studio-v3 mockup):
rendered once per genre via studio.generate.generate, then served from webapp/previews/ forever
after. A per-genre lock keeps concurrent requests for the same genre from rendering twice.
"""
from __future__ import annotations

import shutil
import threading
from pathlib import Path

from studio.generate import generate  # bare name on this module so tests can monkeypatch it

PREVIEW_DIR = Path(__file__).resolve().parent / "previews"

GENRES: dict[str, str] = {
    "pop": "polished pop, bright production, catchy hook",
    "rock": "modern alternative rock, driving distorted electric guitars, punchy live drums",
    "power-metal": "power metal, soaring vocals, double-kick drums, epic guitar harmonies",
    "chill-house": "chill deep house, laid-back groove, heavy hip-hop 808 sub bass, warm pads",
    "hip-hop": "boom-bap hip-hop, punchy drums, deep 808 bass, confident vocals",
    "acoustic": "acoustic singer-songwriter, warm guitar, intimate vocals",
}

__all__ = ["UnknownGenre", "GENRES", "get_preview_path"]

_locks = {genre: threading.Lock() for genre in GENRES}


class UnknownGenre(Exception):
    pass


def get_preview_path(genre: str) -> Path:
    if genre not in GENRES:
        raise UnknownGenre(genre)
    cache_path = PREVIEW_DIR / f"{genre}.mp3"
    with _locks[genre]:
        if cache_path.exists():
            return cache_path
        PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
        result = generate(prompt=GENRES[genre], name=f"_preview_{genre}", duration=10, takes=1, offload=True)
        rendered_path = Path(result["takes"][0]["mp3"])
        if rendered_path != cache_path:
            shutil.copy2(rendered_path, cache_path)
        return cache_path
