from webapp import generate_job


def test_make_song_flow(studio_server_url, page, monkeypatch, tmp_path):
    # studio_server_url runs the real app in-process (a background thread, not a subprocess), so this
    # monkeypatch reaches the live server: the UI flow is exercised end to end, but Make never actually
    # calls ACE-Step (slow, GPU-bound, and the exact thing that hung this project for 30+ minutes once).
    monkeypatch.setattr(generate_job.songs, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(generate_job, "generate",
                         lambda **kw: {"name": kw["name"], "takes": [], "seconds": 1.0})

    page.goto(studio_server_url)
    page.get_by_test_id("instructions-text").fill("")
    page.get_by_test_id("sound-pill-chill-house").click()
    assert "chill house" in page.get_by_test_id("instructions-text").input_value()
    page.get_by_test_id("make-button").click()
    assert page.get_by_test_id("job-status").is_visible()
