"""Print the words in a recording (auto-detects the language), as lyric lines with timestamps.

Usage: .venv\Scripts\python.exe tools\transcribe_recording.py <audio file> [model]
"""
import os
import sys

import numpy as np
from faster_whisper import WhisperModel
from scipy.signal import resample_poly

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from studio.enhance import load_audio  # noqa: E402

audio, sr = load_audio(sys.argv[1])  # faster-whisper's own decoder breaks on this PyAV version
mono = audio.mean(axis=0) if audio.ndim == 2 else audio
g = np.gcd(sr, 16000)
mono = resample_poly(mono, 16000 // g, sr // g).astype(np.float32)
model = WhisperModel(sys.argv[2] if len(sys.argv) > 2 else "medium", device="cpu", compute_type="int8")
segments, info = model.transcribe(mono, beam_size=5, vad_filter=True)
print(f"language: {info.language} ({info.language_probability:.0%})")
for s in segments:
    print(f"{s.start:6.1f}-{s.end:6.1f}  {s.text.strip()}")
