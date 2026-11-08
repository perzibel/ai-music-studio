"""MCP server exposing the music studio to AI agents (Claude Code, Codex, ...)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer

from . import library, render
from .effects import EFFECTS, PRESETS
from .song import SongError
from .synths import SYNTH_TYPES

GUIDE = (Path(__file__).resolve().parent.parent / "GUIDE.md").read_text(encoding="utf-8")

mcp = MCPServer(
    name="ai-music-studio",
    instructions=(
        "Local music production studio. Compose songs as JSON specs and render them to real audio using "
        "high-quality sampled instruments (sfz:*), real guitar amp captures, built-in synths (808, supersaw...), "
        "studio effects and automatic mastering. "
        "ALWAYS call get_composition_guide once before writing your first song. "
        "Workflow: get_composition_guide -> write song JSON -> render_song -> play_song -> iterate "
        "(get_song, edit, render_song again with the same name). Songs with a \"vocals\" section (lyrics) get "
        "an AI singer via add_vocals after rendering. Optional: enhance_song for an AI realism pass. "
        "Two other routes: generate_song makes a finished, realistic song (vocals included) straight from a "
        "text prompt with the local AI model (best when the user wants a polished result, not editable notes); "
        "enhance_recording cleans up and masters the user's own recorded audio file (noise, hum, dull or thin "
        "sound, low volume), optionally followed by an AI re-performance."
    ),
)


def _load(song: Any) -> dict:
    if isinstance(song, str):
        p = Path(song)
        if p.suffix == ".json" and p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
        return json.loads(song)
    return song


@mcp.tool()
def get_composition_guide() -> str:
    """The song JSON format, instruments, amps, expression, mixing, and genre recipes
    (hip-hop, trap, metal, rock, classical, EDM). Read this before composing."""
    return GUIDE


@mcp.tool()
def list_instruments(search: str | None = None) -> list[dict]:
    """Search instruments. High-quality 'sfz:*' sampled instruments are listed first, then basic GM sounds.
    Example searches: 'guitar', 'piano', 'drum kit', 'violin', 'bass', 'brass'. Omit to list everything."""
    return render.list_presets(search)


@mcp.tool()
def list_sound_sources() -> dict:
    """List sample libraries (installed or not), amp rigs, synth types, effect types and presets."""
    from .amp import AMPS, CABS, RIGS
    return {
        "sample_libraries": library.status(),
        "amp_rigs": RIGS,
        "amps": {k: v[1] for k, v in AMPS.items()},
        "cabinets": {k: v[1] for k, v in CABS.items()},
        "synths": SYNTH_TYPES,
        "effect_types": sorted(EFFECTS) + ["vst3"],
        "effect_presets": PRESETS,
    }


@mcp.tool()
def render_song(song: dict | str, name: str | None = None, export_stems: bool = True) -> dict:
    """Render a song spec (see get_composition_guide) to a mastered WAV + MP3 + MIDI (+ per-track stems).
    `song` is the song JSON object (or a path to a .json file). Re-rendering with the same name
    overwrites the previous version. Returns file paths, duration, loudness, and warnings."""
    try:
        return render.render_song(_load(song), name=name, export_stems=export_stems)
    except (SongError, ValueError, KeyError, TypeError) as e:
        return {"error": f"{type(e).__name__}: {e}"}


@mcp.tool()
def enhance_song(name: str, style: str, faithfulness: float = 0.65, seed: int = -1) -> dict:
    """Optional AI realism pass (ACE-Step 1.5, runs locally on the GPU, takes ~1-3 minutes).
    Re-synthesizes a rendered song so it sounds more like a real recording, keeping its structure/melody.
    style: describe the sound, e.g. "heavy metal, crushing distorted guitars, live drums, polished mix".
    faithfulness 0-1: higher stays closer to the original (0.5-0.8 recommended). It may change details,
    so the original mix is kept; the result is saved as mix_enhanced.wav/.mp3."""
    from .enhance import enhance
    d = render.OUTPUT_DIR / name
    song = json.loads((d / "song.json").read_text(encoding="utf-8")) if (d / "song.json").exists() else {}
    return enhance(d, style, strength=faithfulness, seed=seed, bpm=song.get("bpm"),
                   loudness=song.get("loudness", "streaming"))


@mcp.tool()
def generate_song(prompt: str, lyrics: str = "", name: str | None = None, duration: float = 120,
                  bpm: int | None = None, key: str = "", language: str = "en", takes: int = 1,
                  quality: str = "high", seed: int = -1, loudness: str = "streaming") -> dict:
    """Generate a complete, realistic-sounding song from a text prompt (ACE-Step 1.5, local GPU,
    ~1-4 minutes per take). Unlike render_song, the AI model performs everything itself, vocals included.
    prompt: genre, era, instruments, vocal type, mood, tempo feel and production, comma-separated, e.g.
      "90s alternative rock, distorted guitars, live drums, raspy male vocals, anthemic, polished studio mix".
    lyrics: optional; use section tags: "[verse]\\n...\\n[chorus]\\n...\\n[bridge]\\n...". Empty = instrumental.
    duration: seconds (10-240). bpm / key ("E minor"): optional; the AI picks them if omitted.
    takes: generate several and rank them (by lyric accuracy when there are lyrics); offer the user 2-3.
    quality: "high" (an LM plans the song first: better structure, slower) or "draft" (fast).
    Writes output/<name>/mix.mp3 (best take) and mix_take2.mp3 ...; play with play_song."""
    from .generate import generate
    return generate(prompt, lyrics=lyrics, name=name, duration=duration, bpm=bpm, key=key, language=language,
                    takes=takes, seed=seed, quality=quality, loudness=loudness)


@mcp.tool()
def enhance_recording(path: str, name: str | None = None, denoise: float = 0.5, eq: float = 0.6,
                      brighten: float = 0.6, stereo: bool = True, loudness: str = "streaming",
                      ai_style: str = "", faithfulness: float = 0.75, seed: int = -1) -> dict:
    """Improve the sound of the user's own recording (WAV/MP3/FLAC/M4A/OGG; phone, laptop mic, old demo).
    Restoration keeps their performance: removes rumble and mains hum, reduces background noise/hiss,
    rebalances the tone toward a commercial mix, restores missing top end, compresses gently, widens mono
    recordings (mono-compatible) and masters to a loudness target ("streaming" -14 LUFS, "loud", "dynamic"...).
    denoise / eq / brighten: 0-1 strengths (0 disables that step). Each step is skipped if not needed.
    ai_style: optional; if set, also runs the AI re-performance (ACE-Step, local GPU, max 240 s audio) on the
      restored audio, e.g. "acoustic pop ballad, female vocals, warm studio recording". It sounds more
      produced but may change details; faithfulness 0-1 (higher = closer to the recording).
    Outputs mix (restored), original, and enhanced (AI) versions; compare them with play_song."""
    from .restore import enhance_recording as run
    return run(path, name=name, denoise=denoise, eq=eq, brighten=brighten, stereo=stereo, loudness=loudness,
               ai_style=ai_style, faithfulness=faithfulness, seed=seed)


@mcp.tool()
def repaint_section(path: str, start: str, end: str, style: str, lyrics: str = "", takes: int = 2,
                    seed: int = -1, bpm: int | None = None, instrumental: bool = False,
                    out_dir: str | None = None) -> dict:
    """Redo ONE part of a finished song audio file and keep the rest exactly as it is (ACE-Step repaint,
    local GPU, max 240 s songs). start/end: "1:12" or seconds. style: the song's style description, plus what
    this part should sound like. lyrics: the WHOLE song's lyrics, with new lines for this part if the words
    should change (required unless instrumental=True; without them the singer would be dropped).
    The new part is spliced into the original audio, so untouched sections stay bit-identical.
    To fix several parts, call once per part, each time on the take the user picked."""
    from .repaint import repaint
    return repaint(path, start, end, style, lyrics=lyrics, out_dir=out_dir, takes=takes, seed=seed, bpm=bpm,
                   instrumental=instrumental)


@mcp.tool()
def add_vocals(name: str, takes: int = 1, seed: int = -1) -> dict:
    """Add an AI singer (ACE-Step 1.5, local GPU, several minutes per take) to a rendered song.
    Uses the song's "vocals" section: {"lyrics": "[verse]...[chorus]...", "style": "...", "language": "en"}.
    Put the lyric sections in the same order as the song's music sections. Writes mix_vocals.mp3 (and
    mix_vocals_take2.mp3 ... for extra takes). Results vary per take/seed; offer the user a few."""
    from .vocals import add_vocals as run
    d = render.OUTPUT_DIR / name
    if not (d / "song.json").exists():
        return {"error": f"No song named {name!r}. Render it first."}
    song = json.loads((d / "song.json").read_text(encoding="utf-8"))
    return run(d, song, takes=takes, seed=seed)


@mcp.tool()
def install_library(name: str) -> str:
    """Download a free sample library (see list_sound_sources -> sample_libraries). Large downloads."""
    if name not in library.LIBRARIES:
        return f"Unknown library {name!r}. Available: {sorted(library.LIBRARIES)}"
    log = []
    library.download(name, log=log.append)
    return "\n".join(log)


@mcp.tool()
def list_songs() -> list[dict]:
    """List previously rendered songs."""
    out = []
    for d in sorted(render.OUTPUT_DIR.glob("*/song.json")):
        song = json.loads(d.read_text(encoding="utf-8"))
        out.append({"name": d.parent.name, "title": song.get("title"), "bpm": song.get("bpm"),
                    "tracks": [t.get("name") for t in song.get("tracks", [])],
                    "mp3": str(d.parent / "mix.mp3"),
                    "vocals": (d.parent / "mix_vocals.mp3").exists(),
                    "enhanced": (d.parent / "mix_enhanced.mp3").exists()})
    return out


@mcp.tool()
def get_song(name: str) -> dict:
    """Get the JSON spec of a previously rendered song so you can edit and re-render it."""
    p = render.OUTPUT_DIR / name / "song.json"
    if not p.exists():
        return {"error": f"No song named {name!r}. Use list_songs."}
    return json.loads(p.read_text(encoding="utf-8"))


@mcp.tool()
def play_song(name: str, version: str = "mix") -> str:
    """Open a rendered song in the user's default audio player so they can listen.
    version: "mix" (instrumental / restored recording / generated song), "vocals" (with the AI singer),
    "vocals_take2", ..., "take2", ... (extra generate_song takes), "enhanced", or "original" (the
    untouched input of enhance_recording)."""
    d = render.OUTPUT_DIR / name
    stem = version if version in ("mix", "original") else f"mix_{version}"
    names = (f"{stem}.mp3", f"{stem}.wav")
    for f in names:
        if (d / f).exists():
            render.open_file(str(d / f))
            return f"Playing {d / f}"
    return f"No {version!r} audio for {name!r}" + ("" if version == "mix" else " (run add_vocals / enhance_song first)")


def _protect_stdout() -> None:
    """MCP talks JSON-RPC over stdout. Native libraries (sfizz) print to the C-level stdout, which would
    corrupt the protocol, so point file descriptor 1 at stderr and give Python a private copy for MCP."""
    mcp_fd = os.dup(1)
    os.dup2(2, 1)
    sys.stdout = os.fdopen(mcp_fd, "w", encoding="utf-8", buffering=1)


def main() -> None:
    _protect_stdout()
    mcp.run("stdio")


if __name__ == "__main__":
    main()
