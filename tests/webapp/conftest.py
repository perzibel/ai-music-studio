"""Shared fixtures for webapp tests: a real Uvicorn instance for Playwright-driven UI smoke tests."""
import socket
import threading
import time

import pytest
import requests
import uvicorn

from webapp.app import app


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def studio_server_url():
    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            if requests.get(url, timeout=0.5).status_code < 500:
                break
        except requests.RequestException:
            pass
        time.sleep(0.1)
    else:
        raise RuntimeError(f"Studio server did not come up at {url}")
    yield url
    server.should_exit = True
    thread.join(timeout=5)
