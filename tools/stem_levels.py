"""Print the loudness of each stem of rendered songs, to check the mix balance.

Usage: .venv\\Scripts\\python.exe tools\\stem_levels.py <song_name> [...]
"""
import os
import sys

import numpy as np
from pedalboard.io import AudioFile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from studio import render  # noqa: E402

for s in sys.argv[1:]:
    print("==", s)
    for f in sorted((render.OUTPUT_DIR / s / "stems").glob("*.wav")):
        with AudioFile(str(f)) as a:
            x = a.read(a.frames)
        # RMS over the parts where the track actually plays (so short parts aren't under-reported)
        blk = x.mean(0)[: len(x[0]) // 4410 * 4410].reshape(-1, 4410)
        r = np.sqrt((blk ** 2).mean(1))
        active = r[r > r.max() * 0.05] if r.max() > 0 else r
        print(f"  {f.stem:15s} active rms {20 * np.log10(np.sqrt((active ** 2).mean()) + 1e-9):6.1f} dB")
