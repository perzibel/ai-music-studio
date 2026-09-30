"""Render the example songs and print sounds, roles, loudness and warnings.

Usage: .venv\\Scripts\\python.exe tools\\render_examples.py [hiphop trap metal rock classical edm]
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(sys.path[0])
from studio import render  # noqa: E402

names = sys.argv[1:] or ["hiphop", "trap", "metal", "rock", "classical", "edm"]
for s in names:
    t0 = time.time()
    song = json.load(open(f"examples/{s}.json", encoding="utf-8"))
    r = render.render_song(song)
    print(f"== {s}: {time.time() - t0:.1f}s  {r['duration_seconds']}s  loudness={r['loudness']}")
    for tn, ti in r["tracks"].items():
        print(f"   {tn:16s} {ti['role']:10s} {ti['sound'][:70]}")
    for w in r["warnings"]:
        print("   WARN", w)
