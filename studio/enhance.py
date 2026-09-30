"""ACE-Step 1.5 integration (local, GPU): the AI realism pass ("enhance") and a shared runner used by vocals.

ACE-Step lives in its own environment (engines/ACE-Step-1.5); we call studio/ace_bridge.py inside it.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ACE_DIR = ROOT / "engines" / "ACE-Step-1.5"
ACE_PY = ACE_DIR / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
BRIDGE = ROOT / "studio" / "ace_bridge.py"  # runs inside ACE-Step's own environment
MAX_SECONDS = 240  # ACE-Step 1.5 handles longer songs, but 8 GB GPUs get tight


def available() -> bool:
    return ACE_PY.exists() and BRIDGE.exists()


def audio_seconds(path: Path) -> float:
    from pedalboard.io import AudioFile
    with AudioFile(str(path)) as f:
        return f.frames / f.samplerate


def gpu_vram_gb() -> float | None:
    """Total VRAM of the first NVIDIA GPU, via nvidia-smi (None if unknown)."""
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=10).stdout
        return float(out.split()[0]) / 1024
    except Exception:
        return None


def low_vram_args() -> list[str]:
    """INT8 weights halve the DiT's memory; needed for the bigger base model on <12 GB GPUs."""
    vram = gpu_vram_gb()
    return ["--quant", "int8_weight_only"] if vram is not None and vram < 12 else []


def run_ace(args: list[str], timeout: int = 3600) -> dict:
    """Run the bridge with the given arguments; retries with CPU offload if the GPU runs out of memory."""
    if not available():
        return {"error": f"ACE-Step is not installed at {ACE_DIR}. Run setup.ps1 -WithAceStep."}
    for offload in (False, True):
        cmd = [str(ACE_PY), "-u", str(BRIDGE), *args] + (["--offload"] if offload else [])
        env = {**os.environ, "PYTHONIOENCODING": "utf-8",
               "ACESTEP_GENERATION_TIMEOUT": str(timeout)}  # ACE-Step's own limit is 10 minutes
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=timeout, env=env, cwd=str(ACE_DIR))
        m = re.search(r"^ACE_RESULT (.*)$", proc.stdout, re.M)
        if not m:
            return {"error": f"ACE-Step failed (exit {proc.returncode}): {(proc.stdout + proc.stderr)[-1500:]}"}
        result = json.loads(m.group(1))
        err = str(result.get("error", "")).lower()
        if result.get("ok") or not ("out of memory" in err or "insufficient free vram" in err):
            break
    if not result.get("ok") or not result.get("paths"):
        return {"error": result.get("error") or "ACE-Step produced no audio", "detail": result.get("trace")}
    # Success: callers treat an "error" key as failure, so keep partial problems separately.
    return {"paths": result["paths"], "seconds": result.get("seconds"), "partial_errors": result.get("error")}


def load_audio(path: str):
    from pedalboard.io import AudioFile
    with AudioFile(path) as f:
        return f.read(f.frames).astype("float32"), int(f.samplerate)


def save_mix(audio, sr: int, stem: Path) -> dict:
    """Write <stem>.wav + <stem>.mp3."""
    from pedalboard.io import AudioFile
    wav, mp3 = stem.with_suffix(".wav"), stem.with_suffix(".mp3")
    with AudioFile(str(wav), "w", sr, audio.shape[0], bit_depth=24) as f:
        f.write(audio)
    with AudioFile(str(mp3), "w", sr, audio.shape[0], quality=320) as f:
        f.write(audio)
    return {"wav": str(wav), "mp3": str(mp3)}


def enhance(song_dir: Path, caption: str, strength: float = 0.65, seed: int = -1, steps: int = 8,
            bpm: int | None = None, loudness="streaming") -> dict:
    src = song_dir / "mix.wav"
    if not src.exists():
        return {"error": f"No mix.wav in {song_dir}; render the song first."}
    duration = audio_seconds(src)
    if duration > MAX_SECONDS:
        return {"error": f"Song is {duration:.0f}s; the enhance pass supports up to {MAX_SECONDS}s."}
    work = song_dir / "enhanced"
    work.mkdir(exist_ok=True)
    args = ["--src", str(src), "--out-dir", str(work), "--caption", caption, "--strength", str(strength),
            "--duration", f"{duration:.2f}", "--seed", str(seed), "--steps", str(steps)]
    if bpm:
        args += ["--bpm", str(int(bpm))]
    result = run_ace(args)
    if "error" in result:
        return result
    audio, sr = load_audio(result["paths"][0])
    # Master to the same loudness target as the original so the A/B comparison is fair.
    from .mix import master
    audio, _ = master(audio, sr, {"loudness": loudness, "master_effects": []}, bpm or 120)
    files = save_mix(audio, sr, song_dir / "mix_enhanced")
    return {**files, "original": str(src), "seconds": result.get("seconds"),
            "note": "AI re-synthesis: compare with the original. Lower faithfulness = more creative, "
                    "higher = closer to the original."}
