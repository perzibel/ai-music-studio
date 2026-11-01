"""Single-worker background job queue: ACE-Step runs one job at a time (one GPU),
so HTTP requests submit work here instead of blocking on it directly.
"""
from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

__all__ = ["JobNotFound", "JobManager"]


class JobNotFound(Exception):
    pass


class JobManager:
    def __init__(self, max_workers: int = 1) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._lock = threading.Lock()
        self._jobs: dict[str, dict[str, Any]] = {}

    def submit(self, fn: Callable, *args: Any, **kwargs: Any) -> str:
        job_id = str(uuid.uuid4())
        with self._lock:
            self._jobs[job_id] = {"state": "queued", "result": None, "error": None}

        def run() -> None:
            with self._lock:
                self._jobs[job_id]["state"] = "running"
            try:
                result = fn(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001 - surfaced to the caller via status(), not raised here
                with self._lock:
                    self._jobs[job_id]["state"] = "error"
                    self._jobs[job_id]["error"] = str(exc)
                return
            with self._lock:
                self._jobs[job_id]["state"] = "done"
                self._jobs[job_id]["result"] = result

        self._executor.submit(run)
        return job_id

    def status(self, job_id: str) -> dict:
        with self._lock:
            if job_id not in self._jobs:
                raise JobNotFound(job_id)
            return dict(self._jobs[job_id])
