"""Song storage for the local studio app: each song is a folder under OUTPUT_DIR,
the same convention studio/generate.py and the MCP tools already use. This module
only reads/organizes that convention; it never calls ACE-Step itself.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from studio.render import OUTPUT_DIR  # bare module attribute: tests monkeypatch songs.OUTPUT_DIR

__all__ = ["OUTPUT_DIR", "SongNotFound", "list_songs", "load_song", "list_takes",
           "new_song_name", "archive_current_takes"]


class SongNotFound(Exception):
    pass


def _slug(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40].strip("-")
    return slug or "untitled"


def new_song_name(title: str) -> str:
    base = _slug(title)
    name = base
    n = 2
    while (OUTPUT_DIR / name).exists():
        name = f"{base}-{n}"
        n += 1
    return name


def list_songs() -> list[dict]:
    if not OUTPUT_DIR.exists():
        return []
    out = []
    for d in sorted(OUTPUT_DIR.iterdir()):
        song_json = d / "song.json"
        if not d.is_dir() or not song_json.exists():
            continue
        title = json.loads(song_json.read_text(encoding="utf-8")).get("title", d.name)
        take_count = len(list(d.glob("mix*.mp3")))
        out.append({"name": d.name, "title": title, "take_count": take_count})
    return out


def load_song(name: str) -> dict:
    song_json = OUTPUT_DIR / name / "song.json"
    if not song_json.exists():
        raise SongNotFound(name)
    return json.loads(song_json.read_text(encoding="utf-8"))


def list_takes(name: str) -> list[dict]:
    d = OUTPUT_DIR / name
    takes = [{"id": p.stem, "mp3": str(p), "version": 0} for p in sorted(d.glob("mix*.mp3"))]
    takes_dir = d / "takes"
    if takes_dir.exists():
        for version_dir in sorted(takes_dir.iterdir()):
            if not version_dir.is_dir() or not version_dir.name.startswith("v"):
                continue
            try:
                version = int(version_dir.name[1:])
            except ValueError:
                continue
            for p in sorted(version_dir.glob("mix*.mp3")):
                takes.append({"id": f"{version_dir.name}/{p.stem}", "mp3": str(p), "version": version})
    # version 0 (current) is the newest take; among archived takes, the highest version
    # number was archived most recently, so it sorts right after the current take.
    takes.sort(key=lambda t: (t["version"] != 0, -t["version"], t["id"]))
    return takes


def archive_current_takes(name: str) -> int:
    d = OUTPUT_DIR / name
    current = list(d.glob("mix*.wav")) + list(d.glob("mix*.mp3"))
    if not current:
        return 0
    takes_dir = d / "takes"
    existing_versions = [int(p.name[1:]) for p in takes_dir.glob("v*") if p.is_dir() and p.name[1:].isdigit()] \
        if takes_dir.exists() else []
    version = max(existing_versions, default=0) + 1
    version_dir = takes_dir / f"v{version}"
    version_dir.mkdir(parents=True)
    for p in current:
        shutil.move(str(p), str(version_dir / p.name))
    return version
