import pytest
from fastapi.testclient import TestClient

from webapp import app, profile


@pytest.fixture(autouse=True)
def _tmp_profile(tmp_path, monkeypatch):
    monkeypatch.setattr(profile, "PROFILE_PATH", tmp_path / "profile.json")


client = TestClient(app.app)


def test_first_launch_needs_a_name():
    data = client.get("/api/profile").json()
    assert data == {"name": "", "title": "AI Music Studio", "needs_name": True}


def test_saving_a_name_titles_the_studio_and_persists():
    resp = client.post("/api/profile", json={"name": "  P3rzibel  "})
    assert resp.json() == {"name": "P3rzibel", "title": "P3rzibel Music Studio", "needs_name": False}
    assert client.get("/api/profile").json()["title"] == "P3rzibel Music Studio"


def test_blank_name_is_rejected():
    assert client.post("/api/profile", json={"name": "   "}).status_code == 400
    assert client.get("/api/profile").json()["needs_name"] is True


def test_corrupt_profile_file_counts_as_first_launch():
    profile.PROFILE_PATH.write_text("{not json", encoding="utf-8")
    assert client.get("/api/profile").json()["needs_name"] is True
