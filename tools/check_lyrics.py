"""Transcribe raw ACE-Step vocal takes of a song and score them against its lyrics.

Usage: .venv\\Scripts\\python.exe tools\\check_lyrics.py <song_name>
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from studio import render  # noqa: E402
from studio.enhance import load_audio  # noqa: E402
from studio.lyrics_check import check_take  # noqa: E402

d = render.OUTPUT_DIR / sys.argv[1]
song = json.loads((d / "song.json").read_text(encoding="utf-8"))
lyrics = song["vocals"]["lyrics"]
for f in sorted(glob.glob(str(d / "vocals" / "*.flac"))):
    audio, sr = load_audio(f)
    r = check_take(audio, sr, lyrics)
    print(f"== {os.path.basename(f)}: accuracy {r['lyric_accuracy']:.0%} "
          f"({r['words_heard']}/{r['words_expected']} words), first word at {r['first_word_at_s']}s")
    for s in r["heard"]:
        print(f"   {s['start']:6.1f}-{s['end']:6.1f}  {s['text']}")
