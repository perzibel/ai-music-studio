"""Renders a song spec to audio.

instruments (SFZ libraries / SoundFont / synths / VST3) -> amp sim -> effects -> auto EQ -> automation
-> mix + reverb bus -> mastering (LUFS) -> WAV / MP3 / MIDI / stems
"""
from __future__ import annotations

import difflib
import json
import os
import re
from functools import lru_cache
from pathlib import Path

import mido
import numpy as np
import tinysoundfont as tsf

from . import effects as fx
from . import library, mix
from .song import (Note, SongError, automation_curve, bar_beats, cc_events, pitch_curve, track_events,
                   track_notes_beats, validate)
from .synths import SYNTH_TYPES, render_synth
from .theory import ALIAS_LOOKUP, GM_LOOKUP, GM_NAMES, _norm, note_to_midi

ROOT = Path(__file__).resolve().parent.parent
SOUNDFONT_DIR = Path(os.environ.get("AI_MUSIC_SOUNDFONTS", ROOT / "soundfonts"))
OUTPUT_DIR = Path(os.environ.get("AI_MUSIC_OUTPUT", ROOT / "output"))
SR = 44100
DRUM_BANK = 128
SF_BEND_RANGE = 12.0  # SoundFont engine: we set the synth's bend range, so wide slides work
SFZ_BEND_RANGE = 2.0  # SFZ libraries define their own range; 2 semitones is the SFZ default


# ----------------------------------------------------------------------------- soundfonts

def default_soundfont() -> Path:
    env = os.environ.get("AI_MUSIC_SOUNDFONT")
    if env:
        return Path(env)
    preferred = SOUNDFONT_DIR / "GeneralUser-GS.sf2"
    if preferred.exists():
        return preferred
    found = sorted(SOUNDFONT_DIR.glob("*.sf2"))
    if not found:
        raise SongError(f"No .sf2 SoundFont found in {SOUNDFONT_DIR}. Run setup.ps1 to download one.")
    return found[0]


def resolve_soundfont(name: str | None) -> Path:
    if not name:
        return default_soundfont()
    p = Path(name)
    for cand in (p, SOUNDFONT_DIR / name, SOUNDFONT_DIR / f"{name}.sf2"):
        if cand.exists():
            return cand.resolve()
    raise SongError(f"SoundFont {name!r} not found. Available: {[f.name for f in SOUNDFONT_DIR.glob('*.sf2')]}")


@lru_cache(maxsize=8)
def preset_table(sf_path: str) -> dict[tuple[int, int], str]:
    synth = tsf.Synth(samplerate=SR)
    sfid = synth.sfload(sf_path)
    table = {}
    for bank in range(129):
        for prog in range(128):
            try:
                name = synth.sfpreset_name(sfid, bank, prog)
            except Exception:
                name = None
            if name:
                table[(bank, prog)] = name.strip()
    return table


def list_presets(search: str | None = None, soundfont: str | None = None) -> list[dict]:
    """High-quality SFZ instruments first, then the General MIDI SoundFont presets."""
    out = []
    words = search.lower().split() if search else []
    for name, spec in library.INSTRUMENTS.items():
        text = f"{name} {spec.get('desc', '')} {'drum kit' if spec.get('drums') else ''} sfz".lower().replace("_", " ")
        if all(w in text for w in words):
            installed = spec.get("generated") or library.is_installed(spec["lib"])
            out.append({"instrument": f"sfz:{name}", "quality": "high", "desc": spec.get("desc"),
                        "range": spec.get("range"), "kind": "drum kit" if spec.get("drums") else "instrument",
                        "default_amp": spec.get("amp"), "installed": bool(installed)})
    sf = resolve_soundfont(soundfont)
    for (bank, prog), name in sorted(preset_table(str(sf)).items()):
        gm = GM_NAMES[prog] if bank == 0 else None
        kind = "drum kit" if bank == DRUM_BANK else "instrument"
        text = f"{name} {gm or ''} {kind} gm soundfont".lower()
        if words and not all(w in text for w in words):
            continue
        out.append({"instrument": gm or name, "quality": "basic (GM SoundFont)", "bank": bank, "program": prog,
                    "name": name, "kind": kind})
    return out


def _fuzzy(query: str, options: dict[str, tuple[int, int]]) -> tuple[tuple[int, int] | None, bool]:
    """Returns (bank/program, exact_match)."""
    q = _norm(query)
    if q in options:
        return options[q], True
    subs = [n for n in options if q in n.split() or q in n]
    if subs:
        return options[min(subs, key=len)], False
    close = difflib.get_close_matches(q, list(options), n=1, cutoff=0.6)
    return (options[close[0]] if close else None), False


def _resolve_gm(track: dict, inst, is_drums: bool) -> dict:
    sf = resolve_soundfont(track.get("soundfont"))
    table = preset_table(str(sf))
    exact = True
    if "bank" in track and "program" in track:
        bank, prog = int(track["bank"]), int(track["program"])
    elif is_drums:
        kits = {_norm(n): bp for bp, n in table.items() if bp[0] == DRUM_BANK}
        kit = track.get("kit", 0)
        if isinstance(kit, int):
            bank, prog = DRUM_BANK, kit
        else:
            found, _ = _fuzzy(str(kit), kits)
            if not found:
                raise SongError(f"Track {track['name']!r}: drum kit {kit!r} not found. "
                                f"Kits: {sorted(table[bp] for bp in kits.values())}")
            bank, prog = found
    elif isinstance(inst, int):
        bank, prog = 0, inst
    elif isinstance(inst, str):
        key = _norm(inst)
        if key in ALIAS_LOOKUP:
            bank, prog = 0, ALIAS_LOOKUP[key]
        elif key in GM_LOOKUP:
            bank, prog = 0, GM_LOOKUP[key]
        else:
            options = {_norm(n): bp for bp, n in table.items() if bp[0] != DRUM_BANK}
            options.update({k: (0, v) for k, v in GM_LOOKUP.items()})
            options.update({k: (0, v) for k, v in ALIAS_LOOKUP.items()})
            found, exact = _fuzzy(inst, options)
            if not found:
                raise SongError(f"Track {track['name']!r}: instrument {inst!r} not found. "
                                f"Use list_instruments to search.")
            bank, prog = found
    else:
        raise SongError(f"Track {track['name']!r}: set 'instrument' (e.g. 'sfz:grand_piano', a GM name, "
                        f"'drums' or 'synth:<type>')")
    if (bank, prog) not in table:
        raise SongError(f"Track {track['name']!r}: preset bank {bank} program {prog} not in {sf.name}")
    info = {"kind": "sf", "soundfont": str(sf), "bank": bank, "program": prog, "drums": bank == DRUM_BANK,
            "label": f"{table[(bank, prog)]} (GM SoundFont, bank {bank} prog {prog})"}
    if not exact:
        info["warning"] = (f"Track {track['name']!r}: no instrument named {inst!r}; using closest match "
                           f"{table[(bank, prog)]!r}. Check list_instruments if that is wrong.")
    return info


def resolve_instrument(track: dict) -> dict:
    """Figures out what makes the sound for a track."""
    inst = track.get("instrument")
    if track.get("vst3"):
        return {"kind": "vst3", "path": track["vst3"], "label": f"VST3 {Path(track['vst3']).name}"}
    if isinstance(inst, str) and inst.lower().startswith("synth:"):
        kind = inst.split(":", 1)[1].strip().lower()
        if kind not in SYNTH_TYPES:
            raise SongError(f"Track {track['name']!r}: unknown synth {kind!r}. Available: {sorted(SYNTH_TYPES)}")
        return {"kind": "synth", "synth": kind, "label": f"synth:{kind}"}
    if isinstance(inst, str) and inst.lower().startswith("sfz:"):
        name = inst.split(":", 1)[1].strip()
        try:
            spec = library.resolve(name)
        except ValueError as e:
            raise SongError(f"Track {track['name']!r}: {e}") from e
        if spec.get("missing"):
            lib = spec["missing"]
            fb = dict(track)
            if spec.get("drums"):
                fb["kit"] = spec.get("fallback_kit", 0)
            info = _resolve_gm(fb, spec.get("fallback", 0), bool(spec.get("drums")))
            info["warning"] = (f"Track {track['name']!r}: library {lib!r} is not installed, using basic GM sound. "
                               f"Install with: python -m studio.library {lib}")
            info["amp"] = spec.get("amp")
            return info
        info = {"kind": "sfz", **spec}
        info["gain_db"] = library.calibration_gain_db(name, spec) if name in library.INSTRUMENTS else 0.0
        return info
    is_drums = inst in ("drums", "drum", "kit", "percussion") or "kit" in track
    return _resolve_gm(track, inst, is_drums)


# ----------------------------------------------------------------------------- events

def _bend_events(notes: list[Note], bend_range: float, length: int) -> tuple[list[tuple], list[str]]:
    """Pitch-wheel events for expressive notes. The wheel is per track (like a real MIDI channel)."""
    events, warnings = [], []
    starts = sorted(n.start for n in notes)
    for n in notes:
        if not n.expressive:
            continue
        end = n.start + n.dur
        t = np.arange(n.start, end, 0.005)
        semis = pitch_curve(n, t)
        if np.max(np.abs(semis)) > bend_range + 1e-6:
            warnings.append(f"bend of {np.max(np.abs(semis)):.1f} semitones exceeds this instrument's "
                            f"±{bend_range:g} range; clipped")
        wheel = np.clip(np.round(semis / bend_range * 8191), -8192, 8191).astype(int)
        last = None
        for ti, w in zip(t, wheel):
            if w != last:
                events.append((min(length - 1, int(ti * SR)), "bend", int(w), 0))
                last = w
        nxt = next((s for s in starts if s > n.start + 1e-4), None)
        reset = min(end + 0.25, nxt if nxt is not None else end + 0.25)
        events.append((min(length - 1, int(reset * SR)), "bend", 0, 0))
    return events, warnings


def _note_events(notes: list[Note], drum_map: dict | None = None) -> list[tuple]:
    ev = []
    for n in notes:
        p = (drum_map or {}).get(n.pitch, n.pitch)
        on = int(n.start * SR)
        ev.append((on, "on", p, n.vel))
        ev.append((max(on + 1, int((n.start + n.dur) * SR)), "off", p, 0))
    return ev


def _render_soundfont(info: dict, notes: list[Note], length: int, track: dict, song: dict, warn: list) -> np.ndarray:
    synth = tsf.Synth(gain=float(track.get("gain_db", 0.0)), samplerate=SR)
    sfid = synth.sfload(info["soundfont"])
    ch = 9 if info["drums"] else 0
    synth.program_select(ch, sfid, info["bank"], info["program"], is_drums=info["drums"])
    synth.pitchbend_range(ch, SF_BEND_RANGE)
    events = _note_events(notes)
    bends, w = _bend_events(notes, SF_BEND_RANGE, length)
    events += bends
    events += [(int(t * SR), "cc", c, v) for t, c, v in cc_events(track, song)]
    warn += [f"Track {track['name']!r}: {x}" for x in dict.fromkeys(w)]
    order = {"off": 0, "cc": 1, "bend": 1, "on": 2}
    events.sort(key=lambda e: (e[0], order[e[1]]))
    out = np.zeros((length, 2), dtype=np.float32)
    pos = 0
    for when, kind, a, b in events:
        when = min(when, length)
        if when > pos:
            out[pos:when] = np.frombuffer(synth.generate(when - pos), dtype=np.float32).reshape(-1, 2)
            pos = when
        if kind == "on":
            synth.noteon(ch, a, b)
        elif kind == "off":
            synth.noteoff(ch, a)
        elif kind == "cc":
            synth.control_change(ch, a, b)
        else:
            synth.pitchbend(ch, 8192 + a)
    if pos < length:
        out[pos:] = np.frombuffer(synth.generate(length - pos), dtype=np.float32).reshape(-1, 2)
    return out.T.copy()


def _render_sfz(info: dict, notes: list[Note], length: int, track: dict, song: dict, warn: list) -> np.ndarray:
    from .sfz import render_sfz
    bend_range = float(track.get("bend_range", SFZ_BEND_RANGE))
    events = _note_events(notes, info.get("drum_map"))
    bends, w = _bend_events(notes, bend_range, length)
    events += bends
    events += [(int(t * SR), "cc", c, v) for t, c, v in cc_events(track, song)]
    warn += [f"Track {track['name']!r}: {x}" for x in dict.fromkeys(w)]
    audio = render_sfz(info["sfz"], events, length, SR)
    gain = float(info.get("gain_db", 0.0)) + float(track.get("gain_db", 0.0))
    return audio * np.float32(10 ** (gain / 20))


def _render_vst3(track: dict, notes: list[Note], length: int) -> np.ndarray:
    import pedalboard as pb
    plugin = pb.load_plugin(track["vst3"])
    if track.get("vst3_preset"):
        plugin.load_preset(track["vst3_preset"])
    for k, v in (track.get("vst3_params") or {}).items():
        setattr(plugin, k, v)
    msgs = []
    for n in notes:
        msgs.append((mido.Message("note_on", note=n.pitch, velocity=n.vel).bytes(), n.start))
        msgs.append((mido.Message("note_off", note=n.pitch, velocity=0).bytes(), n.start + n.dur))
    msgs.sort(key=lambda m: m[1])
    audio = plugin(msgs, duration=length / SR, sample_rate=SR, num_channels=2)
    audio = np.asarray(audio, dtype=np.float32)
    if audio.shape[1] < length:
        audio = np.pad(audio, ((0, 0), (0, length - audio.shape[1])))
    return audio[:, :length]


def _pan(audio: np.ndarray, pan) -> np.ndarray:
    pan = np.clip(pan, -1.0, 1.0)
    angle = (pan + 1) * np.pi / 4
    return np.stack([audio[0] * np.cos(angle) * np.sqrt(2), audio[1] * np.sin(angle) * np.sqrt(2)])


def _duck_envelope(duck: dict, song: dict, events_by_track: dict, length: int) -> np.ndarray:
    src = duck.get("source") or duck.get("on_track")
    if src not in events_by_track:
        raise SongError(f"duck source track {src!r} not found")
    wanted = {note_to_midi(p) for p in duck.get("notes", ["kick"])}
    depth = float(duck.get("depth", 0.7))
    release = float(duck.get("release_beats", 0.5)) * 60.0 / float(song["bpm"])
    rel_n = max(1, int(release * SR))
    curve = 1.0 - depth * (1.0 - np.linspace(0, 1, rel_n)) ** 2
    env = np.ones(length, dtype=np.float32)
    for n in events_by_track[src]:
        if n.pitch in wanted:
            s = int(n.start * SR)
            e = min(length, s + rel_n)
            if s < length:
                env[s:e] = np.minimum(env[s:e], curve[: e - s])
    return env


def _filter_sweep(audio: np.ndarray, points: list, song: dict) -> np.ndarray:
    """Automated low-pass filter (EDM build-ups, intros)."""
    import pedalboard as pb
    cutoff = automation_curve(points, song, audio.shape[1], SR, 20000.0)
    lp = pb.LowpassFilter(cutoff_frequency_hz=float(cutoff[0]))
    out = np.empty_like(audio)
    block = 256
    for s in range(0, audio.shape[1], block):
        lp.cutoff_frequency_hz = float(np.clip(cutoff[s], 20, 20000))
        out[:, s:s + block] = lp(audio[:, s:s + block], SR, reset=False)
    return out


def _render_track(track: dict, song: dict, info: dict, notes: list[Note], length: int, seed: int,
                  warn: list) -> np.ndarray:
    if info["kind"] == "synth":
        audio = render_synth(info["synth"], notes, track.get("synth_params", {}), SR, length, seed)
    elif info["kind"] == "vst3":
        audio = _render_vst3(track, notes, length)
    elif info["kind"] == "sfz":
        audio = _render_sfz(info, notes, length, track, song, warn)
    else:
        audio = _render_soundfont(info, notes, length, track, song, warn)
    rig = track.get("amp", info.get("amp"))
    if rig:  # recorded-DI guitars/basses (or anything) through a real amp capture + cabinet
        from .amp import apply_rig, resolve_rig
        rig = resolve_rig(rig)
        if info.get("palm_mute") and "pre_lowpass_hz" not in rig:
            rig["pre_lowpass_hz"] = 1800
        audio = apply_rig(audio, SR, rig)
    return audio


def _events_for(track: dict, song: dict, info: dict, seed: int) -> list[Note]:
    t = dict(track)
    if track.get("double_track") and not t.get("humanize"):
        t["humanize"] = {"timing_ms": 12, "velocity": 6}
    events = track_events(t, song, seed=seed)
    if info.get("drums"):
        # Let drum samples ring out; a new hit on the same drum still cuts the previous one.
        by_pitch: dict[int, list[Note]] = {}
        for n in events:
            by_pitch.setdefault(n.pitch, []).append(n)
        for group in by_pitch.values():
            for a, b in zip(group, group[1:] + [None]):
                a.dur = max(a.dur, 2.5) if b is None else max(a.dur, min(2.5, b.start - a.start))
    return events


def render_song(song: dict, name: str | None = None, export_stems: bool = True, formats=("wav", "mp3", "mid")) -> dict:
    warnings = validate(song)
    title = name or song.get("title") or "untitled"
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", title).strip("_").lower() or "untitled"
    out_dir = OUTPUT_DIR / slug
    (out_dir / "stems").mkdir(parents=True, exist_ok=True)
    bpm = float(song["bpm"])

    tracks = song["tracks"]
    soloed = [t for t in tracks if t.get("solo")]
    active = [t for t in (soloed or tracks) if not t.get("mute")]

    infos = {t["name"]: resolve_instrument(t) for t in tracks}
    warnings += [i["warning"] for i in infos.values() if "warning" in i]
    events = {t["name"]: _events_for(t, song, infos[t["name"]], 1) for t in tracks}
    end = max((n.start + n.dur for evs in events.values() for n in evs), default=0.0)
    if "length_bars" in song:
        end = max(end, float(song["length_bars"]) * bar_beats(song) * 60.0 / bpm)
    length = int((end + float(song.get("tail_seconds", 3.0))) * SR)

    bus_spec = song.get("reverb")
    auto_sends = bool(bus_spec) and (not isinstance(bus_spec, dict) or bus_spec.get("auto", True))
    send_bus = np.zeros((2, length), dtype=np.float32)
    roles = {}

    stems: dict[str, np.ndarray] = {}
    for i, t in enumerate(active):
        tn = t["name"]
        info = infos[tn]
        if t.get("double_track"):
            width = float(t.get("double_width", 0.85))
            left = _render_track(t, song, info, events[tn], length, 10 + i, warnings)
            right = _render_track(t, song, info, _events_for(t, song, info, 2), length, 20 + i, warnings)
            audio = _pan(left, -width) * 0.75 + _pan(right, width) * 0.75
        else:
            audio = _render_track(t, song, info, events[tn], length, 10 + i, warnings)
        if t.get("effects"):
            audio = fx.build_chain(t["effects"], bpm)(audio.astype(np.float32), SR)
        role = roles[tn] = mix.infer_role(t, info)
        if song.get("auto_eq", True) and t.get("auto_eq", True):
            lowest = min((n.pitch for n in events[tn]), default=None)
            lowest_hz = 440.0 * 2 ** ((lowest - 69) / 12) if lowest is not None and not info.get("drums") else None
            audio = mix.auto_eq(audio.astype(np.float32), SR, role, lowest_hz)
        auto = t.get("automation") or {}
        if auto.get("filter"):
            audio = _filter_sweep(audio.astype(np.float32), auto["filter"], song)
        if auto.get("volume"):
            audio = audio * automation_curve(auto["volume"], song, length, SR, 1.0)
        if t.get("duck"):
            audio = audio * _duck_envelope(t["duck"], song, events, length)
        audio = audio * float(t.get("volume", 0.8))
        if not t.get("double_track"):
            pan = automation_curve(auto["pan"], song, length, SR, 0.0) if auto.get("pan") else float(t.get("pan", 0.0))
            audio = _pan(audio, pan)
        stems[tn] = audio.astype(np.float32)
        send = t.get("reverb_send", mix.ROLE_SETTINGS.get(role, (0, 0.1))[1] if auto_sends else 0.0)
        if bus_spec and send:
            send_bus += stems[tn] * float(send)

    dry = np.sum(list(stems.values()), axis=0) if stems else np.zeros((2, length), np.float32)
    if bus_spec and np.any(send_bus):
        wet = mix.reverb_bus(send_bus, SR, bus_spec)
        dry = dry + wet
        stems["_reverb_bus"] = wet.astype(np.float32)
    pre = 10 ** (-6 / 20) / (float(np.max(np.abs(dry))) or 1.0)  # stem export level
    mastered, loud = mix.master(dry, SR, song, bpm)
    fade = min(int(float(song.get("fade_out_seconds", 0.05)) * SR), mastered.shape[1])
    if fade:
        mastered[:, -fade:] *= np.linspace(1, 0, fade)

    from pedalboard.io import AudioFile
    files = {}
    if "wav" in formats:
        files["wav"] = str(out_dir / "mix.wav")
        with AudioFile(files["wav"], "w", SR, 2, bit_depth=24) as f:
            f.write(mastered)
    if "mp3" in formats:
        files["mp3"] = str(out_dir / "mix.mp3")
        try:
            with AudioFile(files["mp3"], "w", SR, 2, quality=320) as f:
                f.write(mastered)
        except Exception as e:  # pragma: no cover - depends on platform codecs
            warnings.append(f"MP3 export failed ({e}); WAV is available")
            files.pop("mp3")
    if export_stems:
        for old in (out_dir / "stems").glob("*.wav"):
            old.unlink()
        for tname, audio in stems.items():
            p = out_dir / "stems" / f"{re.sub(r'[^a-zA-Z0-9_-]+', '_', tname)}.wav"
            with AudioFile(str(p), "w", SR, 2, bit_depth=24) as f:
                f.write(np.clip(audio * pre, -1, 1).astype(np.float32))
        files["stems"] = str(out_dir / "stems")
    if "mid" in formats:
        files["mid"] = str(out_dir / "song.mid")
        export_midi(song, infos, events, files["mid"])
    (out_dir / "song.json").write_text(json.dumps(song, indent=2), encoding="utf-8")
    files["song_json"] = str(out_dir / "song.json")

    return {
        "name": slug,
        "duration_seconds": round(length / SR, 2),
        "bars": round(end * bpm / 60.0 / bar_beats(song), 2),
        "files": files,
        "tracks": {t["name"]: {"sound": infos[t["name"]]["label"], "notes": len(events[t["name"]]),
                               "role": roles.get(t["name"]), "muted": t not in active} for t in tracks},
        "loudness": loud,
        "warnings": list(dict.fromkeys(warnings)),
    }


# ----------------------------------------------------------------------------- MIDI export

def export_midi(song: dict, infos: dict, events: dict, path: str) -> None:
    ppq = 480
    bpm = float(song["bpm"])
    mid = mido.MidiFile(type=1, ticks_per_beat=ppq)
    meta = mido.MidiTrack()
    meta.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm)))
    num, den = song.get("time_signature", [4, 4])
    meta.append(mido.MetaMessage("time_signature", numerator=num, denominator=den))
    mid.tracks.append(meta)
    channel = 0
    for t in song["tracks"]:
        info = infos[t["name"]]
        drums = bool(info.get("drums"))
        if drums:
            ch = 9
        else:
            ch = channel
            channel += 1
            if channel == 9:
                channel += 1
            ch %= 16
        tr = mido.MidiTrack()
        tr.append(mido.MetaMessage("track_name", name=t["name"]))
        program = info.get("program", info.get("fallback"))
        if not drums and isinstance(program, int):
            tr.append(mido.Message("program_change", channel=ch, program=program))
        msgs = []
        for n in events[t["name"]]:
            on = round(n.start * bpm / 60.0 * ppq)
            off = max(on + 1, round((n.start + n.dur) * bpm / 60.0 * ppq))
            msgs.append((on, 1, mido.Message("note_on", channel=ch, note=n.pitch, velocity=n.vel)))
            msgs.append((off, 0, mido.Message("note_off", channel=ch, note=n.pitch, velocity=0)))
        msgs.sort(key=lambda m: (m[0], m[1]))
        now = 0
        for tick, _, msg in msgs:
            tr.append(msg.copy(time=tick - now))
            now = tick
        mid.tracks.append(tr)
    mid.save(path)


def open_file(path: str) -> None:
    if hasattr(os, "startfile"):
        os.startfile(path)  # type: ignore[attr-defined]
    else:
        import subprocess
        import sys
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", path])
