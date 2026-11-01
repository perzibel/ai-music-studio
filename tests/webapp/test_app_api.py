import threading
import time

from fastapi.testclient import TestClient

from webapp import app

client = TestClient(app.app)


def test_get_songs_returns_list_from_songs_module(monkeypatch):
    monkeypatch.setattr(app.songs, "list_songs", lambda: [{"name": "a", "title": "A", "take_count": 1}])
    resp = client.get("/api/songs")
    assert resp.status_code == 200
    assert resp.json() == [{"name": "a", "title": "A", "take_count": 1}]


def test_get_song_404_when_not_found(monkeypatch):
    monkeypatch.setattr(app.songs, "load_song", lambda n: (_ for _ in ()).throw(app.songs.SongNotFound(n)))
    resp = client.get("/api/songs/nope")
    assert resp.status_code == 404


def test_post_make_returns_job_id(monkeypatch):
    monkeypatch.setattr(app.job_manager, "submit", lambda fn, *a, **kw: "job-123")
    resp = client.post("/api/songs/s/make", json={"caption": "c", "lyrics": "", "takes": 2})
    assert resp.json() == {"job_id": "job-123"}


def test_post_make_while_job_running_still_returns_a_job_id(monkeypatch):
    # app.job_manager is a real JobManager(max_workers=1); only make_song_job is stubbed, so the
    # first request genuinely occupies the one worker while the second is submitted.
    release = threading.Event()
    monkeypatch.setattr(app.generate_job, "make_song_job", lambda *a, **kw: release.wait(timeout=5))
    client.post("/api/songs/s/make", json={"caption": "c", "lyrics": "", "takes": 1})
    time.sleep(0.1)  # let the worker pick up the first job
    second = client.post("/api/songs/s/make", json={"caption": "c2", "lyrics": "", "takes": 1})
    assert second.status_code == 200
    assert "job_id" in second.json()
    release.set()


def test_get_job_status_404_when_not_found(monkeypatch):
    monkeypatch.setattr(app.job_manager, "status", lambda j: (_ for _ in ()).throw(app.jobs.JobNotFound(j)))
    resp = client.get("/api/jobs/nope")
    assert resp.status_code == 404


def test_post_assist_lyrics_503_when_ollama_unavailable(monkeypatch):
    monkeypatch.setattr(app.assist, "draft_lyrics",
                         lambda *a, **kw: (_ for _ in ()).throw(app.assist.AssistUnavailable("down")))
    resp = client.post("/api/assist/lyrics", json={"level": "all", "idea_text": "x", "current_lyrics": ""})
    assert resp.status_code == 503


def test_get_preview_404_for_unknown_genre(monkeypatch):
    monkeypatch.setattr(app.previews, "get_preview_path",
                         lambda g: (_ for _ in ()).throw(app.previews.UnknownGenre(g)))
    resp = client.get("/api/previews/dubstep")
    assert resp.status_code == 404


def test_post_open_folder_calls_os_startfile(monkeypatch):
    calls = []
    monkeypatch.setattr(app.os, "startfile", lambda p: calls.append(p))
    client.post("/api/open-folder", json={"name": "s"})
    assert calls


def test_get_take_audio_serves_file_by_index(monkeypatch, tmp_path):
    take_file = tmp_path / "mix.mp3"
    take_file.write_bytes(b"audio-bytes")
    monkeypatch.setattr(app.songs, "list_takes", lambda n: [{"id": "mix", "mp3": str(take_file), "version": 0}])
    resp = client.get("/api/songs/s/takes/0")
    assert resp.status_code == 200
    assert resp.content == b"audio-bytes"


def test_get_take_audio_404_for_out_of_range_index(monkeypatch):
    monkeypatch.setattr(app.songs, "list_takes", lambda n: [])
    resp = client.get("/api/songs/s/takes/0")
    assert resp.status_code == 404
