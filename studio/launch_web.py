"""Start the studio web UI and open it in the browser.  Usage: python -m studio.launch_web [--port 8765]"""
from __future__ import annotations

import argparse
import threading
import time
import urllib.request
import webbrowser


def _open_when_ready(url: str) -> None:
    for _ in range(100):
        try:
            urllib.request.urlopen(url, timeout=0.5)
            break
        except OSError:
            time.sleep(0.2)
    webbrowser.open(url)


def main() -> None:
    import uvicorn

    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--no-browser", action="store_true")
    a = p.parse_args()
    url = f"http://127.0.0.1:{a.port}"
    if not a.no_browser:
        threading.Thread(target=_open_when_ready, args=(url,), daemon=True).start()
    print(f"Studio running at {url}  (close this window to stop it)", flush=True)
    uvicorn.run("webapp.app:app", host="127.0.0.1", port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
