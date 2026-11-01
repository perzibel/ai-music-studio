import pytest

from webapp import generate_job


def test_make_song_job_passes_offload_true_to_generate(monkeypatch, tmp_path):
    monkeypatch.setattr(generate_job.songs, "OUTPUT_DIR", tmp_path)
    (tmp_path / "s").mkdir()
    captured = {}

    def fake_generate(**kwargs):
        captured.update(kwargs)
        return {"name": "s", "takes": [], "seconds": 1.0}

    monkeypatch.setattr(generate_job, "generate", fake_generate)
    generate_job.make_song_job("s", "a happy pop song", "la la la", takes=2)
    assert captured["offload"] is True
    assert captured["name"] == "s"
    assert captured["prompt"] == "a happy pop song"
    assert captured["lyrics"] == "la la la"
    assert captured["takes"] == 2


def test_make_song_job_archives_existing_takes_before_generating(monkeypatch, tmp_path):
    monkeypatch.setattr(generate_job.songs, "OUTPUT_DIR", tmp_path)
    d = tmp_path / "s"
    d.mkdir()
    (d / "mix.mp3").write_bytes(b"old")
    calls = []
    monkeypatch.setattr(generate_job, "generate",
                         lambda **kw: calls.append("generated") or {"name": "s", "takes": []})
    generate_job.make_song_job("s", "idea", "", takes=1)
    assert (d / "takes" / "v1" / "mix.mp3").exists()
    assert calls == ["generated"]


def test_make_song_job_raises_runtime_error_on_generate_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(generate_job.songs, "OUTPUT_DIR", tmp_path)
    (tmp_path / "s").mkdir()
    monkeypatch.setattr(generate_job, "generate", lambda **kw: {"error": "GPU exploded"})
    with pytest.raises(RuntimeError, match="GPU exploded"):
        generate_job.make_song_job("s", "idea", "", takes=1)
