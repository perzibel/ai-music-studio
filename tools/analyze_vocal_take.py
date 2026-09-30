"""Inspect an ACE-Step output against the instrumental: is it a vocal stem or a full mix, and when does it sing?

Usage: .venv\\Scripts\\python.exe tools\\analyze_vocal_take.py <song_name>
"""
import glob
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from studio import render  # noqa: E402
from studio.vocals import _fit, _resample  # noqa: E402
from studio.enhance import load_audio  # noqa: E402

d = render.OUTPUT_DIR / sys.argv[1]
inst, sr = load_audio(str(d / "mix.wav"))
for f in sorted(glob.glob(str(d / "vocals" / "*.flac"))):
    gen, gsr = load_audio(f)
    gen = _fit(_resample(gen, gsr, sr), inst.shape[1])
    a, b = inst.mean(0), gen.mean(0)
    corr = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))
    # loudness per 2-second window, to see where the generated audio is active
    win = 2 * sr
    lv = [20 * np.log10(np.sqrt(np.mean(b[i:i + win] ** 2)) + 1e-9) for i in range(0, len(b) - win, win)]
    spec = np.abs(np.fft.rfft(b)) ** 2
    fr = np.fft.rfftfreq(len(b), 1 / sr)
    band = lambda lo, hi: spec[(fr >= lo) & (fr < hi)].sum() / spec.sum()
    print(os.path.basename(f), f"sr={gsr} corr_with_instrumental={corr:.2f}")
    print("  energy <150Hz {:.0%}  150-1k {:.0%}  1k-4k {:.0%}  >4k {:.0%}".format(
        band(0, 150), band(150, 1000), band(1000, 4000), band(4000, 24000)))
    print("  level per 2s:", " ".join(f"{x:.0f}" for x in lv))
