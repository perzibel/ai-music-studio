"""Turn a song link (YouTube, etc.) into a style caption, without keeping the audio.

Downloads the audio with yt-dlp, runs it through ACE-Step's own song-understanding
model (the same "Analyze" feature in the Playground's Custom mode) to get a caption
describing the style, then deletes the downloaded file. Nothing about the song is
reproduced verbatim: by design, this only prints the caption and short metadata
(tempo, key, language), never the transcribed lyrics, to avoid copying anyone's
actual words.

Must run inside ACE-Step's own Python environment (it needs the `acestep` package):
    engines\\ACE-Step-1.5\\.venv\\Scripts\\python.exe tools\\reference_caption.py <url>

Requires yt-dlp on PATH (already installed on this machine) and the Playground's
models already downloaded (acestep-v15-turbo, acestep-5Hz-lm-0.6B by default).
Loads its own copy of the model, so avoid running this at the same time as a
heavy generation in the Playground on an 8 GB GPU.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ACE_ROOT = Path(__file__).resolve().parent.parent / "engines" / "ACE-Step-1.5"
sys.path.insert(0, str(ACE_ROOT))


def download_audio(url: str, out_dir: Path) -> Path:
    """Download the best available audio for `url` into `out_dir`; returns its path."""
    out_template = str(out_dir / "reference.%(ext)s")
    cmd = ["yt-dlp", "-f", "bestaudio", "-x", "--audio-format", "mp3", "-o", out_template, url]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"yt-dlp failed: {proc.stderr[-1500:]}")
    found = list(out_dir.glob("reference.*"))
    if not found:
        raise RuntimeError(f"yt-dlp reported success but no file was found in {out_dir}")
    return found[0]


def describe_audio(audio_path: Path, model: str = "acestep-v15-turbo",
                    lm_model: str = "acestep-5Hz-lm-0.6B", offload: bool = True) -> dict:
    """Run ACE-Step's own analyze pipeline on `audio_path`; returns the caption and metadata."""
    from acestep.handler import AceStepHandler
    from acestep.llm_inference import LLMHandler
    from acestep.inference import understand_music

    dit_handler = AceStepHandler()
    status, ok = dit_handler.initialize_service(project_root=str(ACE_ROOT), config_path=model, device="auto",
                                                 offload_to_cpu=offload)
    if not ok:
        raise RuntimeError(f"ACE-Step init failed: {status}")

    llm_handler = LLMHandler()
    status, ok = llm_handler.initialize(checkpoint_dir=str(ACE_ROOT / "checkpoints"), lm_model_path=lm_model,
                                         backend="pt", device="auto", offload_to_cpu=offload)
    if not ok:
        raise RuntimeError(f"ACE-Step LM init failed: {status}")

    codes = dit_handler.convert_src_audio_to_codes(str(audio_path))
    if not codes:
        raise RuntimeError("Could not turn the audio into codes (file may be silent or unsupported).")

    result = understand_music(llm_handler=llm_handler, audio_codes=codes, use_constrained_decoding=True)
    if not result.success:
        raise RuntimeError(f"Analysis failed: {result.status_message}")

    return {"caption": result.caption, "bpm": result.bpm, "key": result.keyscale,
            "language": result.language, "timesignature": result.timesignature}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("url", help="A song link, e.g. a YouTube URL")
    args = ap.parse_args()

    work_dir = Path(tempfile.mkdtemp(prefix="reference_caption_"))
    try:
        print(f"Downloading audio from {args.url} ...")
        audio_path = download_audio(args.url, work_dir)
        print("Analyzing style ...")
        info = describe_audio(audio_path)
        print("\nCaption:", info["caption"])
        if info["bpm"]:
            print("Tempo (BPM):", info["bpm"])
        if info["key"]:
            print("Key:", info["key"])
        if info["language"]:
            print("Language:", info["language"])
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
        print(f"\nDeleted the downloaded audio ({work_dir}).")


if __name__ == "__main__":
    main()
