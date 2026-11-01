import json

import pytest

from webapp import songs


def test_new_song_name_slugifies_title(monkeypatch, tmp_path):
    monkeypatch.setattr(songs, "OUTPUT_DIR", tmp_path)
    assert songs.new_song_name("Winter in LA!") == "winter-in-la"


def test_new_song_name_appends_suffix_on_collision(monkeypatch, tmp_path):
    monkeypatch.setattr(songs, "OUTPUT_DIR", tmp_path)
    (tmp_path / "winter-in-la").mkdir()
    assert songs.new_song_name("Winter in LA") == "winter-in-la-2"


def test_list_songs_reads_title_and_take_count(monkeypatch, tmp_path):
    monkeypatch.setattr(songs, "OUTPUT_DIR", tmp_path)
    d = tmp_path / "my-song"
    d.mkdir()
    (d / "song.json").write_text(json.dumps({"title": "My Song"}))
    (d / "mix.mp3").write_bytes(b"x")
    (d / "mix_take2.mp3").write_bytes(b"x")
    songs_list = songs.list_songs()
    assert songs_list == [{"name": "my-song", "title": "My Song", "take_count": 2}]


def test_load_song_raises_song_not_found(monkeypatch, tmp_path):
    monkeypatch.setattr(songs, "OUTPUT_DIR", tmp_path)
    with pytest.raises(songs.SongNotFound):
        songs.load_song("nope")


def test_list_takes_includes_current_and_archived(monkeypatch, tmp_path):
    monkeypatch.setattr(songs, "OUTPUT_DIR", tmp_path)
    d = tmp_path / "s"
    d.mkdir()
    (d / "mix.mp3").write_bytes(b"x")
    (d / "takes" / "v1").mkdir(parents=True)
    (d / "takes" / "v1" / "mix.mp3").write_bytes(b"x")
    takes = songs.list_takes("s")
    assert [t["version"] for t in takes] == [0, 1]


def test_archive_current_takes_moves_files_and_returns_1(monkeypatch, tmp_path):
    monkeypatch.setattr(songs, "OUTPUT_DIR", tmp_path)
    d = tmp_path / "s"
    d.mkdir()
    (d / "mix.mp3").write_bytes(b"x")
    assert songs.archive_current_takes("s") == 1
    assert (d / "takes" / "v1" / "mix.mp3").exists()
    assert not (d / "mix.mp3").exists()


def test_archive_current_takes_returns_0_when_nothing_to_archive(monkeypatch, tmp_path):
    monkeypatch.setattr(songs, "OUTPUT_DIR", tmp_path)
    (tmp_path / "s").mkdir()
    assert songs.archive_current_takes("s") == 0


def test_archive_current_takes_increments_version(monkeypatch, tmp_path):
    monkeypatch.setattr(songs, "OUTPUT_DIR", tmp_path)
    d = tmp_path / "s"
    d.mkdir()
    (d / "mix.mp3").write_bytes(b"x")
    songs.archive_current_takes("s")
    (d / "mix.mp3").write_bytes(b"y")
    assert songs.archive_current_takes("s") == 2
