"""Command line: works for any agent/shell, no MCP needed.

  python -m studio render examples/metal.json [--name my_song] [--play] [--no-stems]
  python -m studio enhance <song_name> "style description" [--faithfulness 0.65] [--play]
  python -m studio vocals <song_name> [--takes 2] [--seed 7] [--play]
  python -m studio instruments [search words]
  python -m studio library [names...]      (list or download sample libraries)
  python -m studio guide
  python -m studio serve                   (run the MCP server over stdio)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser(prog="studio")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render", help="render a song JSON file")
    r.add_argument("file")
    r.add_argument("--name")
    r.add_argument("--no-stems", action="store_true")
    r.add_argument("--play", action="store_true")
    e = sub.add_parser("enhance", help="AI realism pass on a rendered song (ACE-Step)")
    e.add_argument("name")
    e.add_argument("style")
    e.add_argument("--faithfulness", type=float, default=0.65)
    e.add_argument("--seed", type=int, default=-1)
    e.add_argument("--play", action="store_true")
    v = sub.add_parser("vocals", help="add an AI singer to a rendered song (uses its \"vocals\" lyrics)")
    v.add_argument("name")
    v.add_argument("--takes", type=int, default=1)
    v.add_argument("--seed", type=int, default=-1)
    v.add_argument("--play", action="store_true")
    i = sub.add_parser("instruments", help="search available instruments")
    i.add_argument("search", nargs="*")
    lb = sub.add_parser("library", help="list or download sample libraries")
    lb.add_argument("names", nargs="*")
    sub.add_parser("guide", help="print the composition guide")
    sub.add_parser("serve", help="run the MCP server (stdio)")
    args = ap.parse_args()

    if args.cmd == "serve":
        from .server import main as serve
        serve()
        return

    # Native engines log to stdout; keep our JSON output clean by moving their output to stderr.
    out = os.fdopen(os.dup(1), "w", encoding="utf-8", buffering=1)
    os.dup2(2, 1)

    from . import library, render
    if args.cmd == "render":
        song = json.loads(Path(args.file).read_text(encoding="utf-8"))
        try:
            result = render.render_song(song, name=args.name, export_stems=not args.no_stems)
        except (ValueError, KeyError, TypeError) as err:
            print(f"ERROR: {type(err).__name__}: {err}", file=sys.stderr)
            sys.exit(1)
        print(json.dumps(result, indent=2), file=out)
        if args.play:
            render.open_file(result["files"].get("mp3") or result["files"]["wav"])
    elif args.cmd == "enhance":
        from .enhance import enhance
        d = render.OUTPUT_DIR / args.name
        song = json.loads((d / "song.json").read_text(encoding="utf-8"))
        result = enhance(d, args.style, strength=args.faithfulness, seed=args.seed, bpm=song.get("bpm"),
                         loudness=song.get("loudness", "streaming"))
        print(json.dumps(result, indent=2), file=out)
        if args.play and "mp3" in result:
            render.open_file(result["mp3"])
    elif args.cmd == "vocals":
        from .vocals import add_vocals
        d = render.OUTPUT_DIR / args.name
        song = json.loads((d / "song.json").read_text(encoding="utf-8"))
        result = add_vocals(d, song, takes=args.takes, seed=args.seed)
        print(json.dumps(result, indent=2), file=out)
        if args.play and result.get("takes"):
            render.open_file(result["takes"][0]["mp3"])
    elif args.cmd == "instruments":
        for p in render.list_presets(" ".join(args.search) or None):
            if p["quality"] == "high":
                flag = "" if p["installed"] else "  [not installed]"
                print(f"{p['instrument']:28s} {p['kind']:10s} {p.get('range') or '':8s} {p['desc']}{flag}", file=out)
            else:
                print(f"{p['instrument']:28s} (GM bank {p['bank']} prog {p['program']}: {p['name']})", file=out)
    elif args.cmd == "library":
        if args.names:
            for n in args.names:
                library.download(n, log=lambda m: print(m, file=out))
        else:
            for n, s in library.status().items():
                print(f"{n:22s} {'installed' if s['installed'] else 'missing  '} {s['size_mb']:>5} MB  {s['desc']}",
                      file=out)
    elif args.cmd == "guide":
        print((Path(__file__).resolve().parent.parent / "GUIDE.md").read_text(encoding="utf-8"), file=out)


if __name__ == "__main__":
    main()
