from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

import pytest

import autojobs_agent.runtime as runtime
from autojobs_agent.contracts import load_request
from autojobs_agent.journal import Journal
from autojobs_agent.runtime import Worker, run_directory
from autojobs_agent.windows.process import ProcessCleanupError, WindowsJobProcess


def prepare(tmp_path: Path, run_id: str = "failure-run") -> tuple[Worker, Journal, dict]:
    (tmp_path / "task.py").write_text("pass\n", encoding="utf-8")
    manifest = tmp_path / "task.json"
    manifest.write_text(json.dumps({"task_id": "failure-task", "python": sys.executable,
                                   "entrypoint": "task.py", "queue_timeout_seconds": 60}), encoding="utf-8")
    request = load_request(manifest, run_id)
    worker = Worker(tmp_path / "state")
    journal = worker.journal
    journal.enqueue(run_id=run_id, task_id=request.manifest.task_id, request=request.model_dump(), queue_timeout_seconds=60)
    record = journal.claim_next()
    assert record is not None
    return worker, journal, record


@pytest.mark.parametrize("boundary", ["probe", "spawn"])
def test_cleanup_uncertainty_keeps_slot_before_process_return(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, boundary: str,
) -> None:
    worker, journal, record = prepare(tmp_path)

    def uncertain(*args: object, **kwargs: object) -> None:
        raise ProcessCleanupError("注入：清理未确认")

    if boundary == "probe":
        monkeypatch.setattr(runtime, "inspect_environment", uncertain)
    else:
        monkeypatch.setattr(runtime, "inspect_environment", lambda _, **kwargs: {"ready": True})
        monkeypatch.setattr(WindowsJobProcess, "spawn", uncertain)
    with pytest.raises(ProcessCleanupError):
        worker._execute(record, threading.Event())
    assert journal.get(record["run_id"])["state"] == "reconciling"
    assert journal.active_run() is not None
    assert journal.claim_next() is None


@pytest.mark.parametrize("status,exit_code,logs_truncated", [("success", 0, True), ("failed", 0, False)])
def test_maximum_message_keeps_original_result(
    tmp_path: Path, status: str, exit_code: int, logs_truncated: bool,
) -> None:
    worker, journal, record = prepare(tmp_path)
    journal.set_running(record["run_id"], 123, time.time())
    directory = run_directory(worker.state_dir, record["run_id"])
    directory.mkdir(parents=True)
    original = "测" * 4096
    (directory / "result.json").write_text(json.dumps({"protocol_version": "0.1", "run_id": record["run_id"],
                                                       "status": status, "message": original, "result": {"rows": 3}}), encoding="utf-8")
    worker._record_completion(record["run_id"], directory, exit_code, None, logs_truncated)
    result = journal.get(record["run_id"])
    assert result["state"] == ("succeeded" if status == "success" else "failed")
    assert result["result"]["message"] == original
    assert len(result["message"]) <= 4096
    assert "摘要已截断" in result["message"]
    if logs_truncated:
        assert "日志超过限额" in result["message"]
