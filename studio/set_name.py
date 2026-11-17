"""First launch: ask for the owner's name, then title the ACE-Step web app "<Name> Music Studio".

Runs before the app starts (see start_studio.cmd). Idempotent: every launch re-applies the saved name,
so it also survives re-applying tools/ace_patches/p3rzible-studio.patch (which hardcodes a title).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from webapp import profile  # noqa: E402

I18N = ROOT / "engines" / "ACE-Step-1.5" / "acestep" / "ui" / "gradio" / "i18n"
TITLE_RE = re.compile(r'("title":\s*")[^"]*Music Studio(")')


def ask_name() -> str:
    print("\nWelcome! Let's name your studio.")
    while True:
        try:
            raw = input("What's your name? ")
        except EOFError:
            return ""
        try:
            data = profile.save_name(raw)
        except ValueError:
            print("Please type a name.")
            continue
        print(f"Your studio is now: {data['title']}\n")
        return data["name"]


def apply_title(name: str) -> None:
    title = profile.studio_title(name)
    for path in I18N.glob("*.json"):
        text = path.read_text(encoding="utf-8")
        new = TITLE_RE.sub(lambda m: f"{m.group(1)}\U0001F39B️ {title}{m.group(2)}", text)
        if new != text:
            path.write_text(new, encoding="utf-8")


def main() -> None:
    state = profile.load_profile()
    name = state["name"] or ask_name()
    if name:
        apply_title(name)


if __name__ == "__main__":
    main()
