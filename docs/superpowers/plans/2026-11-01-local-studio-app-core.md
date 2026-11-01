# Local AI Music Studio — Core App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a local web app that makes a finished song from a typed idea, with free-text Lyrics (AI-assisted on a four-level dial) and free-text Instructions (picker-assisted), shows every past take for that song, and runs entirely offline on this machine's 8 GB GPU.

**Architecture:** A small FastAPI server (`webapp/`) sits beside the existing `studio/` package and reuses it directly (`studio.generate`, `studio.render.OUTPUT_DIR`, `studio.lyrics_check`) rather than duplicating it. The server serves a static single-page UI and a small JSON API; a single-worker background job queue runs ACE-Step generations so HTTP requests never block on GPU work. Ollama (already installed, local) backs the Lyrics-assist dial. Implement on a new branch off `main` (not `docs/local-studio-app-design`, which only carries the design doc).

**Tech Stack:** Python 3.12, FastAPI + Uvicorn, pytest, Playwright (already installed) for one UI smoke test, plain HTML/CSS/JS for the frontend (no build step), Ollama HTTP API for lyrics assist.

**Spec:** `docs/superpowers/specs/2026-11-01-local-ai-music-studio-app-design.md`

This plan implements only the parts of that spec provable with the one generation path already confirmed stable on this GPU (`text2music`, via `studio.generate.generate`). The voice-memo/reference-track/continue-a-song paths, the Cubase stems+MIDI export, and the piano-roll note editor each need their own spike (per the spec's "What's left to the builder") and are deferred to separate plans.

## Global Constraints

- ACE-Step generation must run with `--offload` from the first attempt on this 8 GB GPU, not only as a fallback after an out-of-memory error — a bare attempt without it was observed to hang 30+ minutes with no error and no feedback (spec anti-goals).
- No paid or cloud services. Ollama, `faster-whisper`, yt-dlp, and ffmpeg (all already installed locally) are the only AI helpers this plan may call.
- Every screen shows every control for making a song at once; no multi-step wizard, no Back/Next flow (spec anti-goals).
- Lyrics and Instructions are free text. Picker tiles only ever write into that text; they never set a hidden parameter the text box doesn't reflect (spec, "Instructions" section).
- A generation job must never leave the UI with no feedback on failure or while queued; the server must survive longer than any single browser request (spec anti-goals, constraints).

## Review Focus

- A second "Make" request arrives while one is already running (only one GPU) — must queue visibly, not silently overlap or get rejected with no explanation.
- A generation job fails or the ACE-Step subprocess errors out — the failure must surface to the UI, not hang with no feedback (the exact anti-goal this project already hit once).
- Ollama isn't running, or the model isn't pulled, when the Lyrics-assist dial is used above "Complete manual" — must degrade with a clear error, not crash the request or silently return nothing.
- The existing `studio.generate.generate()` deletes every previous `mix*.*` file in a song's folder on each call — directly conflicts with the spec goal "keep every generated take"; must be handled before any take is lost.
- A song title with spaces, punctuation, or the same name as an existing song is used to start a new song — must produce a valid, unique folder name, not a crash or an overwrite of an unrelated song.

---

## File Structure

```
webapp/
  __init__.py
  songs.py          # song storage: list/load songs, list takes, archive takes, new unique song name
  jobs.py           # single-worker background job queue + status polling
  generate_job.py   # wraps studio.generate.generate as a background job, handles take archiving
  previews.py        # cached 10-second genre preview clips (Pop/Rock/Power Metal/Chill House/Hip-Hop/Acoustic)
  assist.py          # Ollama-backed Lyrics-assist dial (manual/helps/extra/all)
  app.py             # FastAPI app: static UI + JSON API wiring the above together
  static/
    index.html
    app.js
    style.css
tests/webapp/
  test_songs.py
  test_jobs.py
  test_generate_job.py
  test_previews.py
  test_assist.py
  test_app_api.py
  test_ui_smoke.py
studio/generate.py   # modified: generate() gains an offload parameter
```

---

### Task 1: Song storage (`webapp/songs.py`)

**Files:**
- Create: `webapp/__init__.py`, `webapp/songs.py`
- Test: `tests/webapp/test_songs.py`

**Interfaces:**
- Consumes: `studio.render.OUTPUT_DIR` (existing `Path`, reads `os.environ["AI_MUSIC_OUTPUT"]` or defaults to `<repo>/output`).
- Produces:
  - `songs.SongNotFound(Exception)`
  - `songs.list_songs() -> list[dict]` — each `{"name": str, "title": str, "take_count": int}`
  - `songs.load_song(name: str) -> dict` — raw `song.json` contents; raises `SongNotFound` if the folder or `song.json` is missing
  - `songs.list_takes(name: str) -> list[dict]` — each `{"id": str, "mp3": str, "version": int}`; `version=0` for the song's current `mix*.mp3` files, `version=N` for anything archived under `takes/vN/`; sorted newest version first, then by filename
  - `songs.new_song_name(title: str) -> str` — slug of `title` (lowercase, `[a-z0-9]+` joined by `-`, max 40 chars, `"untitled"` if empty after slugifying), suffixed `-2`, `-3`, ... if a folder with that name already exists under `OUTPUT_DIR`. No side effects (does not create the folder).
  - `songs.archive_current_takes(name: str) -> int` — moves every `mix*.wav`/`mix*.mp3` currently directly under `OUTPUT_DIR/name` into a new `OUTPUT_DIR/name/takes/v{n}/` folder (`n` = one more than the highest existing `takes/v*` folder, starting at 1). Returns `n`, or `0` if there were no `mix*.*` files to move. Leaves `song.json` where it is.

- [ ] **Step 1: Write the failing tests**

```python
def test_new_song_name_slugifies_title(monkeypatch, tmp_path):
    monkeypatch.setattr(songs, "OUTPUT_DIR", tmp_path)
    assert songs.new_song_name("Winter in LA!") == "winter-in-la"

def test_new_song_name_appends_suffix_on_collision(monkeypatch, tmp_path):
    monkeypatch.setattr(songs, "OUTPUT_DIR", tmp_path)
    (tmp_path / "winter-in-la").mkdir()
    assert songs.new_song_name("Winter in LA") == "winter-in-la-2"

def test_list_songs_reads_title_and_take_count(monkeypatch, tmp_path):
    monkeypatch.setattr(songs, "OUTPUT_DIR", tmp_path)
    d = tmp_path / "my-song"; d.mkdir()
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
    d = tmp_path / "s"; d.mkdir()
    (d / "mix.mp3").write_bytes(b"x")
    (d / "takes" / "v1").mkdir(parents=True)
    (d / "takes" / "v1" / "mix.mp3").write_bytes(b"x")
    takes = songs.list_takes("s")
    assert [t["version"] for t in takes] == [0, 1]

def test_archive_current_takes_moves_files_and_returns_1(monkeypatch, tmp_path):
    monkeypatch.setattr(songs, "OUTPUT_DIR", tmp_path)
    d = tmp_path / "s"; d.mkdir()
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
    d = tmp_path / "s"; d.mkdir()
    (d / "mix.mp3").write_bytes(b"x")
    songs.archive_current_takes("s")
    (d / "mix.mp3").write_bytes(b"y")
    assert songs.archive_current_takes("s") == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/webapp/test_songs.py -v`
Expected: FAIL (module `webapp.songs` not defined)

- [ ] **Step 3: Implement `webapp/songs.py`** with the functions in the Interfaces block above, importing `OUTPUT_DIR` as a bare module attribute (`from studio.render import OUTPUT_DIR`) so tests can monkeypatch it directly on the `songs` module.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/webapp/test_songs.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add webapp/__init__.py webapp/songs.py tests/webapp/test_songs.py
git commit -m "feat: add song storage layer for the local studio app"
```

---

### Task 2: Background job queue (`webapp/jobs.py`)

**Files:**
- Create: `webapp/jobs.py`
- Test: `tests/webapp/test_jobs.py`

**Interfaces:**
- Produces:
  - `jobs.JobNotFound(Exception)`
  - `jobs.JobManager(max_workers: int = 1)`
    - `.submit(fn, *args, **kwargs) -> str` — returns a job id (UUID4 string)
    - `.status(job_id: str) -> dict` — `{"state": "queued" | "running" | "done" | "error", "result": Any | None, "error": str | None}`; raises `JobNotFound` for an unknown id

- [ ] **Step 1: Write the failing tests**

```python
def test_submit_runs_function_and_reports_done():
    mgr = jobs.JobManager()
    job_id = mgr.submit(lambda: 42)
    for _ in range(50):
        if mgr.status(job_id)["state"] == "done":
            break
        time.sleep(0.05)
    assert mgr.status(job_id) == {"state": "done", "result": 42, "error": None}

def test_status_for_unknown_job_raises_job_not_found():
    mgr = jobs.JobManager()
    with pytest.raises(jobs.JobNotFound):
        mgr.status("no-such-id")

def test_failing_job_reports_error_state_with_message():
    mgr = jobs.JobManager()
    def boom(): raise ValueError("boom")
    job_id = mgr.submit(boom)
    for _ in range(50):
        if mgr.status(job_id)["state"] in ("done", "error"):
            break
        time.sleep(0.05)
    status = mgr.status(job_id)
    assert status["state"] == "error"
    assert "boom" in status["error"]

def test_second_submit_while_first_running_is_queued_not_rejected():
    mgr = jobs.JobManager(max_workers=1)
    release = threading.Event()
    first = mgr.submit(lambda: release.wait(timeout=5))
    time.sleep(0.1)  # let the worker pick up the first job
    second = mgr.submit(lambda: "second-result")
    assert mgr.status(second)["state"] == "queued"
    release.set()
    for _ in range(50):
        if mgr.status(second)["state"] == "done":
            break
        time.sleep(0.05)
    assert mgr.status(second)["result"] == "second-result"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/webapp/test_jobs.py -v`
Expected: FAIL (module `webapp.jobs` not defined)

- [ ] **Step 3: Implement `webapp/jobs.py`.** Use `concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)` to run jobs and a `threading.Lock`-guarded dict keyed by job id to track state, since the executor itself doesn't distinguish "queued" from "running". Set state to `"queued"` at submit time, flip it to `"running"` from inside the submitted wrapper just before calling `fn`, and to `"done"`/`"error"` after it returns or raises.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/webapp/test_jobs.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add webapp/jobs.py tests/webapp/test_jobs.py
git commit -m "feat: add single-worker background job queue"
```

---

### Task 3: Generation job (`webapp/generate_job.py` + `studio/generate.py` offload fix)

**Files:**
- Modify: `studio/generate.py` (the `generate()` function)
- Create: `webapp/generate_job.py`
- Test: `tests/webapp/test_generate_job.py`

**Interfaces:**
- Consumes: `songs.archive_current_takes(name: str) -> int` (Task 1); `studio.generate.generate(...)` (modified below)
- Produces: `generate_job.make_song_job(song_name: str, caption: str, lyrics: str, takes: int = 2, duration: float = 120, bpm: int | None = None, key: str = "") -> dict` — archives any existing takes for `song_name`, then calls `studio.generate.generate(prompt=caption, lyrics=lyrics, name=song_name, takes=takes, duration=duration, bpm=bpm, key=key, offload=True)` (the "More options" length/tempo/key fields from the spec, already accepted by `generate()` today); if the result contains `"error"`, raises `RuntimeError(result["error"])`; otherwise returns the result dict unchanged (`{"name", "takes", "seconds", ...}`, per `studio/generate.py`'s existing return contract).

- [ ] **Step 1: Modify `studio/generate.py`'s `generate()` signature** to add `offload: bool = True`, and pass `(["--offload"] if offload else [])` into each take's `args` list alongside the existing `*low_vram_args()` — this must happen on the *first* attempt, not only inside `run_ace`'s own OOM-retry (which was observed to hang rather than cleanly report OOM, so relying on that retry is not safe on this GPU).

- [ ] **Step 2: Write the failing tests for `generate_job`**

```python
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
    d = tmp_path / "s"; d.mkdir()
    (d / "mix.mp3").write_bytes(b"old")
    calls = []
    monkeypatch.setattr(generate_job, "generate", lambda **kw: calls.append("generated") or {"name": "s", "takes": []})
    generate_job.make_song_job("s", "idea", "", takes=1)
    assert (d / "takes" / "v1" / "mix.mp3").exists()
    assert calls == ["generated"]

def test_make_song_job_raises_runtime_error_on_generate_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(generate_job.songs, "OUTPUT_DIR", tmp_path)
    (tmp_path / "s").mkdir()
    monkeypatch.setattr(generate_job, "generate", lambda **kw: {"error": "GPU exploded"})
    with pytest.raises(RuntimeError, match="GPU exploded"):
        generate_job.make_song_job("s", "idea", "", takes=1)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/webapp/test_generate_job.py -v`
Expected: FAIL (module `webapp.generate_job` not defined)

- [ ] **Step 4: Implement `webapp/generate_job.py`** importing `songs` and `generate` as bare module references (`from . import songs`; `from studio.generate import generate`, then referenced as `generate_job.generate` so tests can monkeypatch it) per the Interfaces block.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/webapp/test_generate_job.py -v tests/webapp/test_songs.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add studio/generate.py webapp/generate_job.py tests/webapp/test_generate_job.py
git commit -m "feat: generate songs with offload from the first attempt, archiving prior takes"
```

---

### Task 4: Genre preview cache (`webapp/previews.py`)

**Files:**
- Create: `webapp/previews.py`
- Test: `tests/webapp/test_previews.py`

**Interfaces:**
- Consumes: `studio.generate.generate(...)` (Task 3's modified signature)
- Produces:
  - `previews.UnknownGenre(Exception)`
  - `previews.GENRES: dict[str, str]` — exactly `{"pop": "polished pop, bright production, catchy hook", "rock": "modern alternative rock, driving distorted electric guitars, punchy live drums", "power-metal": "power metal, soaring vocals, double-kick drums, epic guitar harmonies", "chill-house": "chill deep house, laid-back groove, heavy hip-hop 808 sub bass, warm pads", "hip-hop": "boom-bap hip-hop, punchy drums, deep 808 bass, confident vocals", "acoustic": "acoustic singer-songwriter, warm guitar, intimate vocals"}` (the six tiles from the approved mockup)
  - `previews.get_preview_path(genre: str) -> Path` — returns `webapp/previews/<genre>.mp3`, generating a cached 10-second clip via `generate()` on first request for that genre (`duration=10, takes=1, offload=True, name=f"_preview_{genre}"`); raises `UnknownGenre` for any key not in `GENRES`; concurrent requests for the same genre must not trigger a second generation (one render per genre, ever, unless the cache file is deleted).

- [ ] **Step 1: Write the failing tests**

```python
def test_get_preview_path_generates_on_first_call(monkeypatch, tmp_path):
    monkeypatch.setattr(previews, "PREVIEW_DIR", tmp_path)
    calls = []
    def fake_generate(**kw):
        calls.append(kw["name"])
        p = tmp_path / "pop.mp3"; p.write_bytes(b"x")
        return {"name": "_preview_pop", "takes": [{"mp3": str(p)}]}
    monkeypatch.setattr(previews, "generate", fake_generate)
    path = previews.get_preview_path("pop")
    assert path.exists()
    assert calls == ["_preview_pop"]

def test_get_preview_path_reuses_cache_on_second_call(monkeypatch, tmp_path):
    monkeypatch.setattr(previews, "PREVIEW_DIR", tmp_path)
    (tmp_path / "pop.mp3").write_bytes(b"cached")
    monkeypatch.setattr(previews, "generate", lambda **kw: (_ for _ in ()).throw(AssertionError("should not generate")))
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
        p = tmp_path / "pop.mp3"; p.write_bytes(b"x")
        return {"name": kw["name"], "takes": [{"mp3": str(p)}]}
    monkeypatch.setattr(previews, "generate", fake_generate)
    threads = [threading.Thread(target=previews.get_preview_path, args=("pop",)) for _ in range(5)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert call_count["n"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/webapp/test_previews.py -v`
Expected: FAIL (module `webapp.previews` not defined)

- [ ] **Step 3: Implement `webapp/previews.py`.** Use one `threading.Lock` per genre (a `dict[str, threading.Lock]` built from `GENRES`) around the check-cache-then-generate-then-cache sequence, so concurrent requests for the same genre serialize instead of double-rendering.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/webapp/test_previews.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add webapp/previews.py tests/webapp/test_previews.py
git commit -m "feat: cache 10-second genre preview clips"
```

---

### Task 5: Lyrics assist (`webapp/assist.py`)

**Files:**
- Create: `webapp/assist.py`
- Test: `tests/webapp/test_assist.py`

**Interfaces:**
- Produces:
  - `assist.AssistUnavailable(Exception)`
  - `assist.OLLAMA_MODEL = "qwen3:8b"`
  - `assist.draft_lyrics(level: str, idea_text: str, current_lyrics: str) -> str` — `level` is one of `"manual"`, `"helps"`, `"extra"`, `"all"` (the four stops of the effort bar); raises `ValueError` for any other value. `"manual"` returns `current_lyrics` unchanged with no network call. The other three levels build a level-specific prompt including `idea_text` and (for `"helps"`/`"extra"`) `current_lyrics`, call `_call_ollama`, and return its output.
  - `assist._call_ollama(prompt: str) -> str` — `POST`s `{"model": OLLAMA_MODEL, "prompt": prompt, "stream": False}` to `http://localhost:11434/api/generate`, returns the `"response"` field; raises `AssistUnavailable(str(original_exception))` on any `requests` exception or non-200 response.

- [ ] **Step 1: Write the failing tests**

```python
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
    def fake_post(*a, **kw): raise requests.ConnectionError("refused")
    monkeypatch.setattr(assist.requests, "post", fake_post)
    with pytest.raises(assist.AssistUnavailable):
        assist._call_ollama("prompt")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/webapp/test_assist.py -v`
Expected: FAIL (module `webapp.assist` not defined)

- [ ] **Step 3: Implement `webapp/assist.py`** per the Interfaces block, using the `requests` library.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/webapp/test_assist.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add webapp/assist.py tests/webapp/test_assist.py
git commit -m "feat: add Ollama-backed lyrics assist dial"
```

---

### Task 6: FastAPI app and API routes (`webapp/app.py`)

**Files:**
- Create: `webapp/app.py`
- Test: `tests/webapp/test_app_api.py`

**Interfaces:**
- Consumes: `songs.list_songs/load_song/list_takes/new_song_name` (Task 1), `jobs.JobManager` (Task 2), `generate_job.make_song_job` (Task 3), `previews.get_preview_path/UnknownGenre` (Task 4), `assist.draft_lyrics/AssistUnavailable` (Task 5)
- Produces: `app.app` — a FastAPI instance, importable for `TestClient(app.app)` and for Uvicorn, with routes:
  - `GET /api/songs` -> `songs.list_songs()`
  - `GET /api/songs/{name}` -> `{"song": songs.load_song(name), "takes": songs.list_takes(name)}`; 404 with `{"error": str}` on `SongNotFound`
  - `POST /api/songs/new-name {"title": str}` -> `{"name": songs.new_song_name(title)}`
  - `POST /api/songs/{name}/make {"caption": str, "lyrics": str, "takes": int, "duration": float = 120, "bpm": int | None = None, "key": str = ""}` -> `{"job_id": job_manager.submit(generate_job.make_song_job, name, caption, lyrics, takes, duration, bpm, key)}`
  - `GET /api/jobs/{job_id}` -> `job_manager.status(job_id)`; 404 with `{"error": str}` on `JobNotFound`
  - `POST /api/assist/lyrics {"level": str, "idea_text": str, "current_lyrics": str}` -> `{"lyrics": assist.draft_lyrics(...)}`; 503 with `{"error": str}` on `AssistUnavailable`
  - `GET /api/previews/{genre}` -> `FileResponse(previews.get_preview_path(genre))`; 404 with `{"error": str}` on `UnknownGenre`
  - `POST /api/open-folder {"name": str}` -> calls `os.startfile(studio.render.OUTPUT_DIR / name)`, returns `{"ok": True}`
  - `app.mount("/", StaticFiles(directory="webapp/static", html=True))` serving `index.html` at `/`

- [ ] **Step 1: Write the failing tests**

```python
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
    first = client.post("/api/songs/s/make", json={"caption": "c", "lyrics": "", "takes": 1})
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
    monkeypatch.setattr(app.assist, "draft_lyrics", lambda *a, **kw: (_ for _ in ()).throw(app.assist.AssistUnavailable("down")))
    resp = client.post("/api/assist/lyrics", json={"level": "all", "idea_text": "x", "current_lyrics": ""})
    assert resp.status_code == 503

def test_get_preview_404_for_unknown_genre(monkeypatch):
    monkeypatch.setattr(app.previews, "get_preview_path", lambda g: (_ for _ in ()).throw(app.previews.UnknownGenre(g)))
    resp = client.get("/api/previews/dubstep")
    assert resp.status_code == 404

def test_post_open_folder_calls_os_startfile(monkeypatch):
    calls = []
    monkeypatch.setattr(app.os, "startfile", lambda p: calls.append(p))
    client.post("/api/open-folder", json={"name": "s"})
    assert calls
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/webapp/test_app_api.py -v`
Expected: FAIL (module `webapp.app` not defined)

- [ ] **Step 3: Implement `webapp/app.py`** per the Interfaces block, importing `songs`, `jobs`, `generate_job`, `previews`, and `assist` as bare module references (not `from x import y`) so tests can monkeypatch functions on them through `app.songs.*`, `app.jobs.*`, etc.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/webapp/test_app_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add webapp/app.py tests/webapp/test_app_api.py
git commit -m "feat: add FastAPI app wiring songs, jobs, previews, and assist"
```

---

### Task 7: Studio UI (`webapp/static/`)

**Files:**
- Create: `webapp/static/index.html`, `webapp/static/app.js`, `webapp/static/style.css`
- Test: `tests/webapp/test_ui_smoke.py`

**Interfaces:**
- Consumes: every route in Task 6's Interfaces block.
- Produces: a single-page UI matching the approved mockup at `.superpowers/brainstorm/2095-1793519839/content/studio-v3.html` (dark studio look, one warm-amber accent, every section visible without scrolling past anything required), adapted to call the real API instead of showing static example data:
  - Song header with a "My Songs" list (type-to-filter) backed by `GET /api/songs`, and "new song" entry point using `POST /api/songs/new-name`.
  - Lyrics section: free-text box plus the four-stop effort bar, calling `POST /api/assist/lyrics` when a stop above "Complete manual" is picked, and writing the response into the Lyrics box.
  - Instructions section: free-text box plus Sound/Voice/Feel picker tiles; tapping a tile with a ▶ plays `GET /api/previews/{genre}` and appends its phrase into the Instructions text (toggling it back out if tapped again while selected).
  - Output row: takes stepper, a collapsed "More options" disclosure for length (duration), tempo (BPM), and key, and the "Make the song" button, posting all of it to `POST /api/songs/{name}/make`, then polling `GET /api/jobs/{job_id}` until `done`/`error` and showing the result or the error inline (never a silent hang, per Global Constraints).
  - "Already made for this song" row listing `GET /api/songs/{name}`'s `takes`, each with a native `<audio>` player.
  - "Open this song's folder" button posting to `POST /api/open-folder`.
  - The Cubase-stems checkbox and the memo/reference/continue "Start from" tiles are visible but disabled with a "coming soon" label — their engine work is deferred to later plans (spec, "What's left to the builder").

- [ ] **Step 1: Write the failing smoke test**

```python
# tests/webapp/test_ui_smoke.py — spins up the real app with uvicorn in a background thread,
# points Playwright's sync API at it.
def test_make_song_flow(studio_server_url, page):
    page.goto(studio_server_url)
    page.get_by_test_id("instructions-text").fill("")
    page.get_by_test_id("sound-pill-chill-house").click()
    assert "chill house" in page.get_by_test_id("instructions-text").input_value()
    page.get_by_test_id("make-button").click()
    assert page.get_by_test_id("job-status").is_visible()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/webapp/test_ui_smoke.py -v`
Expected: FAIL (no `index.html` / no matching `data-testid` elements yet)

- [ ] **Step 3: Implement the UI.** Follow the mockup's visual direction and this task's Interfaces block for behavior; add `data-testid` attributes matching the smoke test (`instructions-text`, `sound-pill-chill-house` and one per other genre slug from `previews.GENRES`, `make-button`, `job-status`, plus `lyrics-text` and `song-list`). No build step: plain `<script>`/`<link>` tags, `fetch()` for API calls.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/webapp/test_ui_smoke.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add webapp/static/ tests/webapp/test_ui_smoke.py
git commit -m "feat: add studio UI wired to the local API"
```

---

### Task 8: Desktop launcher

**Files:**
- Create: `C:\Users\User\Desktop\AI Music Studio App.cmd`

**Interfaces:**
- Consumes: `webapp.app:app` (Task 6/7).

- [ ] **Step 1: Write the launcher**, following the existing `AI Music Studio.cmd` pattern (activate the project's `.venv`, `cd` into the repo), running `uvicorn webapp.app:app --port 7861` and then opening `http://127.0.0.1:7861` in the default browser once the port responds.

- [ ] **Step 2: Manual verification.** Double-click the `.cmd` file; confirm the page loads at `http://127.0.0.1:7861`, "Make the song" with a typed idea produces a playable take within the file's "Already made for this song" list, and closing the window stops the Uvicorn process.

- [ ] **Step 3: Commit** (the `.cmd` file lives on the Desktop, outside the repo, so this step applies to any repo-side notes only — e.g. mentioning the launcher in `README.md` if the project's README already documents the existing `AI Music Studio.cmd`).

```bash
git add README.md  # only if it was edited to mention the new launcher
git commit -m "docs: note the local studio app launcher"
```
