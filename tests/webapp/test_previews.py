import threading
import time

import pytest

from webapp import previews


def test_get_preview_path_generates_on_first_call(monkeypatch, tmp_path):
    monkeypatch.setattr(previews, "PREVIEW_DIR", tmp_path)
    calls = []

    def fake_generate(**kw):
        calls.append(kw["name"])
        p = tmp_path / "pop.mp3"
        p.write_bytes(b"x")
        return {"name": "_preview_pop", "takes": [{"mp3": str(p)}]}

    monkeypatch.setattr(previews, "generate", fake_generate)
    path = previews.get_preview_path("pop")
    assert path.exists()
    assert calls == ["_preview_pop"]


def test_get_preview_path_reuses_cache_on_second_call(monkeypatch, tmp_path):
    monkeypatch.setattr(previews, "PREVIEW_DIR", tmp_path)
    (tmp_path / "pop.mp3").write_bytes(b"cached")
    monkeypatch.setattr(previews, "generate",
                         lambda **kw: (_ for _ in ()).throw(AssertionError("should not generate")))
    assert previews.get_preview_path("pop").read_bytes() == b"cached"


def test_unknown_genre_raises():
    with pytest.raises(previews.UnknownGenre):
        previews.get_preview_path("dubstep")


def test_concurrent_requests_generate_only_once(monkeypatch, tmp_path):
    monkeypatch.setattr(previews, "PREVIEW_DIR", tmp_path)
    call_count = {"n": 0}

    def fake_generate(**kw):
        call_count["n"] += 1
        time.sleep(0.2)
        p = tmp_path / "pop.mp3"
        p.write_bytes(b"x")
        return {"name": kw["name"], "takes": [{"mp3": str(p)}]}

    monkeypatch.setattr(previews, "generate", fake_generate)
    threads = [threading.Thread(target=previews.get_preview_path, args=("pop",)) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert call_count["n"] == 1
