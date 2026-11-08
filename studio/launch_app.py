"""Desktop launcher for the P3rzible Music Studio web app (ACE-Step's Gradio UI on http://127.0.0.1:7860).

Replaces ACE-Step's start_gradio_ui.bat, which ran the app through `uv run`: that re-resolved packages
online at every launch (a GitHub 504 for flash-attn broke startup) and reported ANY crash, e.g. running
out of memory, as "Failed to start ACE-Step / check your internet". This launcher instead:
  * starts the already-installed app directly (no network, faster),
  * runs it inside a memory-capped Windows job (studio.memguard): a runaway can't freeze the PC, and
    closing this window always ends every AI process,
  * refuses to start next to another AI run that already holds the GPU,
  * on a crash prints what actually happened (with the memory peak) and restarts the app, and
  * keeps a log in output/logs/web_app.log.

Usage: python -m studio.launch_app [--limit-gb 40] [--backend pt|vllm] [--no-restart]
"""
from __future__ import annotations

import argparse
import datetime
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from .memguard import IS_WIN, GuardedJob, _CREATE_SUSPENDED, _resume

ROOT = Path(__file__).resolve().parent.parent
ACE_DIR = ROOT / "engines" / "ACE-Step-1.5"
APP_EXE = ACE_DIR / ".venv" / ("Scripts/acestep.exe" if IS_WIN else "bin/acestep")
LOG = ROOT / "output" / "logs" / "web_app.log"
PORT = 7860
MAX_RESTARTS = 3
RESTART_REQUESTED = 75  # exit code the web page's "Restart engine" button uses (p3_control.py)


def port_busy(port: int = PORT) -> bool:
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def other_ai_running() -> str | None:
    """Another ACE-Step process (a studio CLI/MCP run) would share the 8 GB GPU and RAM."""
    if not IS_WIN:
        return None
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command",
                              "(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\").CommandLine"],
                             capture_output=True, text=True, errors="replace", timeout=20).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    return "a studio AI job (ace_bridge.py) is running" if "ace_bridge.py" in out else None


def app_command(backend: str) -> list[str]:
    return [str(APP_EXE), "--port", str(PORT), "--server-name", "127.0.0.1", "--language", "en",
            "--config_path", "acestep-v15-turbo", "--lm_model_path", "acestep-5Hz-lm-0.6B",
            "--offload_to_cpu", "true", "--init_service", "true", "--backend", backend,
            # int8 quantization + CPU offload leaked ~3 GB of RAM per generation (weights re-copied
            # RAM<->GPU every run and never returned to Windows). With offload the GPU only needs ~4.6 GB
            # unquantized, so quantization buys nothing here.
            "--quantization", "none",
            # Keep the DiT (~4.5 GB) resident on the GPU. Moving it RAM<->GPU on every run left ~4 GB of
            # native RAM behind per generation (the leak that crashed the 2nd/3rd run); kept on the GPU,
            # RAM stays flat. The LM and other parts are still offloaded.
            "--offload_dit_to_cpu", "false"]


def explain(code: int, peak_gb: float | None, limit_gb: float) -> str:
    peak = f"{peak_gb:.1f} GB" if peak_gb else "unknown"
    if peak_gb and peak_gb >= limit_gb * 0.9:
        why = (f"it ran out of memory: it reached the {limit_gb:.0f} GB safety cap (peak {peak}). "
               "The cap stopped it so Windows would not freeze.")
    elif code in (0xC0000005, -1073741819, 3221225477):
        why = f"it crashed inside the AI engine (access violation; memory peak {peak})."
    else:
        why = f"it exited with code {code} (memory peak {peak})."
    return f"The music app stopped: {why}"


def run_once(cmd: list[str], limit_gb: float, log) -> tuple[int, float | None]:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "CHECK_UPDATE": "false"}
    job = GuardedJob(limit_gb)
    proc = subprocess.Popen(cmd, cwd=str(ACE_DIR), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            creationflags=_CREATE_SUSPENDED if IS_WIN else 0)
    job.add(proc)
    if IS_WIN:
        _resume(proc)
    try:
        for raw in proc.stdout:  # mirror the app's output to this window and the log
            line = raw.decode("utf-8", "replace")
            sys.stdout.write(line)
            sys.stdout.flush()
            log.write(line)
            log.flush()
        code = proc.wait()
        return code, job.peak_gb()
    finally:
        job.close()  # kills anything the app left behind and frees its RAM/VRAM


def main() -> None:
    ap = argparse.ArgumentParser(prog="launch_app")
    ap.add_argument("--limit-gb", type=float, default=40)
    ap.add_argument("--backend", default="pt", choices=["pt", "vllm"])
    ap.add_argument("--no-restart", action="store_true")
    a = ap.parse_args()
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if not APP_EXE.exists():
        sys.exit(f"ACE-Step is not installed at {ACE_DIR} (missing {APP_EXE.name}). Run setup.ps1 -WithAceStep.")
    if port_busy():
        sys.exit("The music app is already running: open http://127.0.0.1:7860 (or close its window first).")
    busy = other_ai_running()
    if busy:
        sys.exit(f"Not starting: {busy}. Wait for it to finish so the two don't run out of memory together.")
    LOG.parent.mkdir(parents=True, exist_ok=True)
    print(f"P3rzible Music Studio: memory cap {a.limit_gb:.0f} GB, LM backend {a.backend}. "
          f"Log: {LOG}\nClosing this window stops the app and frees all its memory.\n", flush=True)
    restarts = 0
    with LOG.open("a", encoding="utf-8") as log:
        while True:
            log.write(f"\n===== start {datetime.datetime.now():%Y-%m-%d %H:%M:%S} =====\n")
            started = time.time()
            try:
                code, peak = run_once(app_command(a.backend), a.limit_gb, log)
            except KeyboardInterrupt:
                print("\nStopped.")
                return
            if code == 0:
                return
            if code == RESTART_REQUESTED:  # the page's "Restart engine" button: not a failure
                print("\n" + "=" * 70 + "\nRestarting the engine as requested: all its memory has been "
                      "freed. Reload the browser page in about a minute.\n" + "=" * 70, flush=True)
                log.write("restart requested from the page\n")
                continue
            msg = explain(code, peak, a.limit_gb)
            print("\n" + "=" * 70 + f"\n{msg}\nAll of its memory has been freed.", flush=True)
            log.write(msg + "\n")
            if time.time() - started > 600:
                restarts = 0  # it ran fine for a while: count this as a fresh failure
            restarts += 1
            if a.no_restart or restarts > MAX_RESTARTS:
                print(f"Not restarting again ({restarts - 1} restarts). Details in {LOG}", flush=True)
                input("Press Enter to close...")
                sys.exit(1)
            print(f"Restarting the app (attempt {restarts}/{MAX_RESTARTS})... "
                  "reload the browser page in about a minute.\n" + "=" * 70, flush=True)
            time.sleep(3)


if __name__ == "__main__":
    main()
