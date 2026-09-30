"""Registry + downloader for free high-quality sample libraries (SFZ) and amp models (NAM)."""
from __future__ import annotations

import io
import os
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIB_DIR = Path(os.environ.get("AI_MUSIC_LIBRARIES", ROOT / "libraries"))

# Downloadable libraries (all free: CC0 / CC-BY).
LIBRARIES = {
    "salamander_piano": {"repo": "sfzinstruments/SalamanderGrandPiano", "mb": 714,
                         "license": "CC-BY 3.0, Alexander Holm", "desc": "Yamaha C5 grand piano, 16 velocity layers"},
    "jrhodes": {"repo": "sfzinstruments/jlearman.jRhodes3c", "mb": 17,
                "license": "see library readme, Jeff Learman", "desc": "1977 Rhodes Mark I electric piano"},
    "virtuosity_drums": {"repo": "sfzinstruments/virtuosity_drums", "mb": 1169,
                         "license": "CC0, Versilian Studios & Karoryfer", "desc": "Acoustic drum kit, multi-mic, round robins"},
    # Release zip: the repo's .gitattributes forces CRLF conversion, which corrupts WAVs in source archives.
    "black_green_guitars": {"repo": "sfzinstruments/karoryfer.black-and-green-guitars", "mb": 460,
                            "url": "https://github.com/sfzinstruments/karoryfer.black-and-green-guitars/releases/"
                                   "download/v1.000/Karoryfer_Black_And_Green_Guitars_1000.zip",
                            "license": "CC0, Karoryfer Samples", "desc": "Electric guitars recorded DI (for amp models)"},
    "black_blue_basses": {"repo": "sfzinstruments/karoryfer.black-and-blue-basses", "mb": 962,
                          "license": "CC0, Karoryfer Samples", "desc": "Electric basses recorded DI"},
    "vsco2": {"repo": "sgossner/VSCO-2-CE", "mb": 2280,
              "license": "CC0, Versilian Studios", "desc": "Orchestra: strings, brass, woodwinds, percussion"},
}


def _vsco(folder, short=False, release=None, desc="", rng=""):
    return {"lib": "vsco2", "auto": [folder], "short": short, "release": release, "desc": desc, "range": rng}


# GM number -> key in the Virtuosity kit (it has 2 toms and no china/clap)
VIRTUOSITY_MAP = {50: 48, 48: 48, 47: 50, 45: 41, 43: 43, 41: 41, 52: 55, 39: 40}

# Instruments the AI can use as "instrument": "sfz:<name>".
INSTRUMENTS = {
    # --- keys
    "grand_piano": {"lib": "salamander_piano", "sfz": "Salamander Grand Piano V3.sfz", "fallback": 0,
                    "desc": "Yamaha C5 concert grand, 16 velocity layers", "range": "A0-C8"},
    "rhodes": {"lib": "jrhodes", "sfz": "jRhodes3c-looped-flac-sfz/_jRhodes-stereo-looped.sfz", "fallback": 4,
               "desc": "1977 Rhodes Mark I electric piano (neo-soul, lo-fi, hip-hop)", "range": "E1-G7"},
    "upright_piano": {**_vsco("Keys/Upright Nr1", desc="Upright piano, intimate/lo-fi", rng="C1-C8"), "fallback": 0},
    # --- drums (use drum names/patterns like the GM kits)
    "acoustic_drums": {"lib": "virtuosity_drums", "sfz": "Programs/01-basic-kit.sfz", "drums": True,
                       "drum_map": VIRTUOSITY_MAP, "fallback_kit": "Room",
                       "desc": "Real acoustic kit (rock, metal, pop, jazz): 2 toms, crash, ride, hats"},
    "acoustic_drums_full": {"lib": "virtuosity_drums", "sfz": "Programs/02-full-kit.sfz", "drums": True,
                            "drum_map": VIRTUOSITY_MAP, "fallback_kit": "Room",
                            "desc": "Same kit, all microphones (bigger, roomier)"},
    "808_kit": {"generated": True, "drums": True, "fallback_kit": "808/909", "desc": "Roland TR-808 style (hip-hop, trap, R&B)"},
    "909_kit": {"generated": True, "drums": True, "fallback_kit": "808/909", "desc": "Roland TR-909 style (house, techno, EDM)"},
    "trap_kit": {"generated": True, "drums": True, "fallback_kit": "808/909", "desc": "Trap: boomy kick, clap-snare, tight hats"},
    # --- electric guitars: recorded DI, played through an amp model ("amp")
    "electric_guitar": {"lib": "black_green_guitars", "sfz": "Programs/04-green_twang.sfz", "amp": "rock", "fallback": 27,
                        "desc": "Gretsch electric, DI + amp model. Sustained notes/chords", "range": "E2-E6"},
    "electric_guitar_2": {"lib": "black_green_guitars", "sfz": "Programs/07-black_twang.sfz", "amp": "rock", "fallback": 27,
                          "desc": "Hofner Club electric (darker), DI + amp model", "range": "E2-E6"},
    "electric_guitar_mute": {"lib": "black_green_guitars", "sfz": "Programs/05-green_staccato.sfz", "amp": "metal",
                             "palm_mute": True, "fallback": 28,
                             "desc": "Short/palm-muted picking for chugs and riffs", "range": "E2-E6"},
    # --- basses
    "bass_guitar": {"lib": "black_blue_basses", "sfz": "Programs/05-darkblack_pluck.sfz", "amp": "bass_clean", "fallback": 33,
                    "desc": "Electric bass, fingerstyle DI", "range": "E1-G4"},
    "bass_guitar_warm": {"lib": "black_blue_basses", "sfz": "Programs/06-darkblack_pluck_warm.sfz", "amp": "bass_clean",
                         "fallback": 33, "desc": "Electric bass, warmer tone", "range": "E1-G4"},
    "bass_guitar_mute": {"lib": "black_blue_basses", "sfz": "Programs/09-darkblack_stac.sfz", "amp": "bass_grit",
                         "fallback": 34, "desc": "Short/staccato bass for tight riffs", "range": "E1-G4"},
    # --- orchestra (VSCO 2)
    "violins": _vsco("Strings/Violin Section/susVib", desc="Violin section, sustained vibrato", rng="G3-A7"),
    "violins_pizz": _vsco("Strings/Violin Section/Pizz", True, desc="Violin section pizzicato", rng="G3-A7"),
    "violins_spic": _vsco("Strings/Violin Section/Spic", True, desc="Violin section spiccato (short)", rng="G3-A7"),
    "violins_trem": _vsco("Strings/Violin Section/Trem", desc="Violin section tremolo", rng="G3-A7"),
    "violin_solo": _vsco("Strings/Solo Violin/Arco Vib", desc="Solo violin, expressive", rng="G3-C7"),
    "violas": _vsco("Strings/Viola Section/susvib", desc="Viola section, sustained", rng="C3-E6"),
    "violas_pizz": _vsco("Strings/Viola Section/pizz", True, desc="Viola pizzicato", rng="C3-E6"),
    "violas_spic": _vsco("Strings/Viola Section/spic", True, desc="Viola spiccato", rng="C3-E6"),
    "violas_trem": _vsco("Strings/Viola Section/trem", desc="Viola tremolo", rng="C3-E6"),
    "cellos": _vsco("Strings/Cello Section/susvib", desc="Cello section, sustained", rng="C2-A5"),
    "cellos_pizz": _vsco("Strings/Cello Section/pizzT", True, desc="Cello pizzicato", rng="C2-A5"),
    "cellos_spic": _vsco("Strings/Cello Section/spic", True, desc="Cello spiccato", rng="C2-A5"),
    "cellos_trem": _vsco("Strings/Cello Section/trem", desc="Cello tremolo", rng="C2-A5"),
    "contrabass": _vsco("Strings/Solo Contrabass/SusVib", desc="Double bass, sustained", rng="E1-G3"),
    "contrabass_pizz": _vsco("Strings/Solo Contrabass/Pizz", True, desc="Double bass pizzicato", rng="E1-G3"),
    "contrabass_spic": _vsco("Strings/Solo Contrabass/Spic", True, desc="Double bass spiccato", rng="E1-G3"),
    "harp": _vsco("Strings/Harp", True, 1.2, desc="Concert harp", rng="C1-G7"),
    "french_horn": _vsco("Brass/F Horn/sus", desc="French horn, sustained", rng="B1-F5"),
    "french_horn_stac": _vsco("Brass/F Horn/stac", True, desc="French horn staccato", rng="B1-F5"),
    "french_horn_mute": _vsco("Brass/F Horn/mute", desc="Muted French horn", rng="B1-F5"),
    "trumpet": _vsco("Brass/Trumpet/sus", desc="Trumpet, sustained", rng="F#3-D6"),
    "trumpet_vib": _vsco("Brass/Trumpet/susvib", desc="Trumpet with vibrato", rng="F#3-D6"),
    "trumpet_stac": _vsco("Brass/Trumpet/stac", True, desc="Trumpet staccato", rng="F#3-D6"),
    "trombone": _vsco("Brass/Tenor Trombone/sus", desc="Tenor trombone, sustained", rng="E2-F5"),
    "trombone_stac": _vsco("Brass/Tenor Trombone/stac", True, desc="Trombone staccato", rng="E2-F5"),
    "tuba": _vsco("Brass/Tuba/sus", desc="Tuba, sustained", rng="D1-F4"),
    "tuba_stac": _vsco("Brass/Tuba/stac", True, desc="Tuba staccato", rng="D1-F4"),
    "flute": _vsco("Woodwinds/Flute/susvib", desc="Flute with vibrato", rng="C4-C7"),
    "flute_stac": _vsco("Woodwinds/Flute/stac", True, desc="Flute staccato", rng="C4-C7"),
    "oboe": _vsco("Woodwinds/Oboe/Vib", desc="Oboe", rng="Bb3-A6"),
    "oboe_stac": _vsco("Woodwinds/Oboe/Stacc", True, desc="Oboe staccato", rng="Bb3-A6"),
    "clarinet": _vsco("Woodwinds/Clarinet/susLong", desc="Clarinet", rng="D3-Bb6"),
    "clarinet_stac": _vsco("Woodwinds/Clarinet/stac", True, desc="Clarinet staccato", rng="D3-Bb6"),
    "bassoon": _vsco("Woodwinds/Bassoon/sus", desc="Bassoon", rng="Bb1-E5"),
    "bassoon_stac": _vsco("Woodwinds/Bassoon/stac", True, desc="Bassoon staccato", rng="Bb1-E5"),
    "piccolo": _vsco("Woodwinds/Piccolo/Sus", desc="Piccolo", rng="D5-C8"),
    "glockenspiel": _vsco("Percussion/Glock", True, 1.5, desc="Glockenspiel", rng="G5-C8"),
    "marimba": _vsco("Percussion/Marimba", True, 0.8, desc="Marimba", rng="C2-C7"),
    "xylophone": _vsco("Percussion/Xylo", True, 0.6, desc="Xylophone", rng="F3-C8"),
}
# GM fallbacks for orchestra instruments if VSCO isn't installed
_ORCH_FALLBACK = {"violin": 40, "viola": 41, "cello": 42, "contrabass": 43, "harp": 46, "french_horn": 60,
                  "trumpet": 56, "trombone": 57, "tuba": 58, "flute": 73, "oboe": 68, "clarinet": 71, "bassoon": 70,
                  "piccolo": 72, "glockenspiel": 9, "marimba": 12, "xylophone": 13}
for _n, _i in INSTRUMENTS.items():
    if "fallback" not in _i and "fallback_kit" not in _i:
        _i["fallback"] = next((v for k, v in _ORCH_FALLBACK.items() if _n.startswith(k)), 48)
        if _n.endswith("_pizz"):
            _i["fallback"] = 45


def resolve(name: str) -> dict:
    """Instrument name (or path to a .sfz file) -> render info. Falls back to GM if a library is missing."""
    from . import automap, drumsynth
    if name not in INSTRUMENTS:
        p = Path(name)
        if p.suffix.lower() == ".sfz" and p.exists():
            return {"sfz": str(p.resolve()), "label": f"SFZ {p.name}"}
        raise ValueError(f"Unknown sfz instrument {name!r}. Available: {sorted(INSTRUMENTS)} (or a path to a .sfz)")
    info = dict(INSTRUMENTS[name])
    info["label"] = f"{name} ({info.get('desc', '')})"
    if info.get("generated"):
        info["sfz"] = str(drumsynth.ensure_kits()[name])
        return info
    lib = info["lib"]
    if not is_installed(lib):
        info["missing"] = lib
        return info
    root = lib_path(lib)
    if "auto" in info:
        sfz = root / f"_auto_{name}.sfz"
        if not sfz.exists():
            sfz.write_text(automap.build_sfz([root / f for f in info["auto"]], root, short=info.get("short", False),
                                             release=info.get("release")), encoding="utf-8")
        info["sfz"] = str(sfz)
    else:
        info["sfz"] = str(root / info["sfz"])
    return info


def lib_path(name: str) -> Path:
    return LIB_DIR / name


def is_installed(name: str) -> bool:
    return (lib_path(name) / ".installed").exists()


def download(name: str, log=print) -> Path:
    info = LIBRARIES[name]
    dest = lib_path(name)
    if is_installed(name):
        log(f"{name}: already installed")
        return dest
    url = info.get("url") or f"https://github.com/{info['repo']}/archive/HEAD.zip"
    LIB_DIR.mkdir(parents=True, exist_ok=True)
    tmp = LIB_DIR / f"{name}.zip.part"
    log(f"{name}: downloading ~{info['mb']} MB from {url}")
    with urllib.request.urlopen(url) as resp, open(tmp, "wb") as f:
        done = 0
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if done % (100 << 20) < (1 << 20):
                log(f"{name}: {done >> 20} MB")
    log(f"{name}: extracting")
    if dest.exists():
        shutil.rmtree(dest)
    staging = LIB_DIR / f"{name}.extract"
    with zipfile.ZipFile(tmp) as z:
        z.extractall(staging)
    entries = list(staging.iterdir())
    # Source archives wrap everything in one top folder; release zips may not.
    src = entries[0] if len(entries) == 1 and entries[0].is_dir() else staging
    shutil.move(str(src), str(dest))
    shutil.rmtree(staging, ignore_errors=True)
    tmp.unlink()
    (dest / ".installed").write_text(info["repo"], encoding="utf-8")
    log(f"{name}: installed at {dest}")
    return dest


CALIBRATION_FILE = LIB_DIR / "calibration.json"
TARGET_RMS_DB = -28.0


def calibration_gain_db(name: str, info: dict) -> float:
    """Gain that brings an instrument to a common reference loudness (measured once, cached)."""
    import json

    import numpy as np

    from .sfz import render_sfz
    from .theory import note_to_midi

    key = f"{name}|{info['sfz']}"
    cache = json.loads(CALIBRATION_FILE.read_text(encoding="utf-8")) if CALIBRATION_FILE.exists() else {}
    if key in cache:
        return cache[key]
    sr = 44100
    if info.get("drums"):
        keys = [36, 38, 42, 42, 36, 38, 46, 42]
    else:
        lo, hi = (note_to_midi(x) for x in info.get("range", "C3-C6").split("-"))
        mid = (lo + hi) // 2
        keys = [max(lo, mid - 12), mid - 5, mid, min(hi, mid + 4)]
    ev = []
    for i, k in enumerate(keys):
        k = (info.get("drum_map") or {}).get(k, k)
        ev += [(int(i * 0.5 * sr), "on", k, 100), (int((i * 0.5 + 0.45) * sr), "off", k, 0)]
    audio = render_sfz(info["sfz"], ev, int(sr * (len(keys) * 0.5 + 0.5)), sr)
    rms_db = 20 * np.log10(float(np.sqrt(np.mean(audio ** 2))) + 1e-9)
    gain = round(max(-12.0, min(30.0, TARGET_RMS_DB - rms_db)), 1)
    cache[key] = gain
    CALIBRATION_FILE.parent.mkdir(parents=True, exist_ok=True)
    CALIBRATION_FILE.write_text(json.dumps(cache, indent=1), encoding="utf-8")
    return gain


NAM_REPO = "https://raw.githubusercontent.com/pelennor2170/NAM_models/main/"
IR_REPO = "https://media.githubusercontent.com/media/fnpngn/IR/master/"
IR_SOURCES = {
    "mesa_4x12_v30.wav": "0Miscellaneous/ML Sound Lab's BEST IR IN THE WORLD.wav",
    "v30_sm57.wav": "0Miscellaneous/SMG_UK_V30 57_dc.wav",
    "marshall_1960a.wav": "1960a/1960a Audix i5/4x12-i5-1in-1.5c.wav",
    "modern_metal_chugslayer.wav": "Free Impulse Responses_Modern Metal Songwriter/IR's/Chugslayer.wav",
    "bass_ampeg_svt_810.wav": "Bass IR Shiftline/07_Ampeg_SVT-810E_by_Shift_Line.wav",
    "bass_balanced.wav": "FREE BASS IR Pack - Modern Music Solutions/BALANCED.wav",
}
SFIZZ_URL = "https://github.com/sfztools/sfizz/releases/download/1.2.3/sfizz-1.2.3-win64.zip"


def download_amps(log=print) -> None:
    """Neural Amp Modeler captures (community, free) + cabinet impulse responses (free packs)."""
    import urllib.parse
    from .amp import AMPS, IR_DIR, NAM_DIR
    NAM_DIR.mkdir(parents=True, exist_ok=True)
    IR_DIR.mkdir(parents=True, exist_ok=True)
    for file, _ in AMPS.values():
        if not (NAM_DIR / file).exists():
            log(f"amp model: {file}")
            urllib.request.urlretrieve(NAM_REPO + urllib.parse.quote(file), NAM_DIR / file)
    for file, src in IR_SOURCES.items():
        if not (IR_DIR / file).exists():
            log(f"cabinet IR: {file}")
            urllib.request.urlretrieve(IR_REPO + urllib.parse.quote(src), IR_DIR / file)


def download_sfizz(log=print) -> None:
    from .sfz import DLL_PATH
    if DLL_PATH.exists():
        return
    engines = ROOT / "engines"
    engines.mkdir(exist_ok=True)
    log("sfizz: downloading")
    with urllib.request.urlopen(SFIZZ_URL) as resp:
        data = resp.read()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        z.extractall(engines / "sfizz")


def status() -> dict:
    return {n: {"installed": is_installed(n), "size_mb": i["mb"], "license": i["license"], "desc": i["desc"]}
            for n, i in LIBRARIES.items()}


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or "engines" in args:
        download_sfizz()
        download_amps()
    for n in [a for a in args if a != "engines"] or ([] if args else list(LIBRARIES)):
        download(n)
