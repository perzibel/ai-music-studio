import pytest
import requests

from webapp import assist


def test_manual_level_returns_lyrics_unchanged_without_calling_ollama(monkeypatch):
    monkeypatch.setattr(assist, "_call_ollama", lambda p: (_ for _ in ()).throw(AssertionError("called")))
    assert assist.draft_lyrics("manual", "an idea", "my words") == "my words"


def test_all_level_returns_ollama_output(monkeypatch):
    monkeypatch.setattr(assist, "_call_ollama", lambda p: "AI-written lyrics")
    assert assist.draft_lyrics("all", "a happy day", "") == "AI-written lyrics"


def test_helps_level_includes_current_lyrics_in_prompt(monkeypatch):
    captured = {}
    monkeypatch.setattr(assist, "_call_ollama", lambda p: captured.setdefault("prompt", p) or "polished")
    assist.draft_lyrics("helps", "a happy day", "my rough verse")
    assert "my rough verse" in captured["prompt"]


def test_unknown_level_raises_value_error():
    with pytest.raises(ValueError):
        assist.draft_lyrics("bogus", "idea", "")


def test_call_ollama_wraps_connection_error(monkeypatch):
    def fake_post(*a, **kw):
        raise requests.ConnectionError("refused")

    monkeypatch.setattr(assist.requests, "post", fake_post)
    with pytest.raises(assist.AssistUnavailable):
        assist._call_ollama("prompt")
