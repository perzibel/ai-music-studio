"""The studio owner's name, asked once on first launch so the app can call itself "<Name> Music Studio"."""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROFILE_PATH = Path(os.environ.get("AI_MUSIC_PROFILE", ROOT / "studio_profile.json"))
MAX_NAME_LEN = 40
DEFAULT_TITLE = "AI Music Studio"


def clean_name(raw: str) -> str:
    """Collapse whitespace and drop control characters; an empty result means 'no name'."""
    text = "".join(ch for ch in raw if ch.isprintable())
    return " ".join(text.split())[:MAX_NAME_LEN].strip()


def studio_title(name: str) -> str:
    return f"{name} Music Studio" if name else DEFAULT_TITLE


def load_profile() -> dict:
    try:
        name = clean_name(str(json.loads(PROFILE_PATH.read_text(encoding="utf-8")).get("name", "")))
    except (OSError, ValueError, AttributeError):
        name = ""
    return {"name": name, "title": studio_title(name), "needs_name": not name}


def save_name(raw: str) -> dict:
    name = clean_name(raw)
    if not name:
        raise ValueError("Please type a name.")
    PROFILE_PATH.write_text(json.dumps({"name": name}, ensure_ascii=False), encoding="utf-8")
    return load_profile()
