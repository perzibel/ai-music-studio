"""FastAPI app wiring songs/jobs/generate_job/previews/assist together, plus the static UI."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from studio.render import OUTPUT_DIR

from . import assist, generate_job, jobs, previews, songs

app = FastAPI()
job_manager = jobs.JobManager()


class NewNameRequest(BaseModel):
    title: str


class MakeRequest(BaseModel):
    caption: str
    lyrics: str
    takes: int
    duration: float = 120
    bpm: int | None = None
    key: str = ""


class AssistRequest(BaseModel):
    level: str
    idea_text: str
    current_lyrics: str


class OpenFolderRequest(BaseModel):
    name: str


@app.get("/api/songs")
def get_songs() -> list[dict]:
    return songs.list_songs()


@app.get("/api/songs/{name}")
def get_song(name: str):
    try:
        song = songs.load_song(name)
    except songs.SongNotFound:
        return JSONResponse({"error": f"Song not found: {name}"}, status_code=404)
    return {"song": song, "takes": songs.list_takes(name)}


@app.post("/api/songs/new-name")
def post_new_name(body: NewNameRequest) -> dict:
    return {"name": songs.new_song_name(body.title)}


@app.post("/api/songs/{name}/make")
def post_make(name: str, body: MakeRequest) -> dict:
    job_id = job_manager.submit(generate_job.make_song_job, name, body.caption, body.lyrics, body.takes,
                                 body.duration, body.bpm, body.key)
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    try:
        return job_manager.status(job_id)
    except jobs.JobNotFound:
        return JSONResponse({"error": f"Job not found: {job_id}"}, status_code=404)


@app.post("/api/assist/lyrics")
def post_assist_lyrics(body: AssistRequest):
    try:
        lyrics = assist.draft_lyrics(body.level, body.idea_text, body.current_lyrics)
    except assist.AssistUnavailable as exc:
        return JSONResponse({"error": str(exc)}, status_code=503)
    return {"lyrics": lyrics}


@app.get("/api/previews/{genre}")
def get_preview(genre: str):
    try:
        path = previews.get_preview_path(genre)
    except previews.UnknownGenre:
        return JSONResponse({"error": f"Unknown genre: {genre}"}, status_code=404)
    return FileResponse(path)


@app.get("/api/songs/{name}/takes/{index}")
def get_take_audio(name: str, index: int):
    takes = songs.list_takes(name)
    if index < 0 or index >= len(takes):
        return JSONResponse({"error": f"No take {index} for song {name}"}, status_code=404)
    return FileResponse(takes[index]["mp3"])


@app.post("/api/open-folder")
def post_open_folder(body: OpenFolderRequest) -> dict:
    os.startfile(OUTPUT_DIR / body.name)  # Windows-only, matching this project's platform
    return {"ok": True}


_STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="static")
