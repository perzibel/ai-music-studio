import threading
import time

import pytest

from webapp import jobs


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

    def boom():
        raise ValueError("boom")

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
