from __future__ import annotations

import json
import os
import time
from pathlib import Path

import psutil

from autojobs_agent.journal import Journal
from autojobs_agent.status import StatusReader


def test_status_does_not_create_state(tmp_path: Path) -> None:
    state = tmp_path / "absent"
    snapshot = StatusReader(state).get_status()
    assert snapshot["worker"]["online"] is False
    assert snapshot["runs"] == []
    assert not state.exists()


def test_status_keeps_unknown_occupancy_and_pending_events(tmp_path: Path) -> None:
    journal = Journal(tmp_path / "journal.sqlite3")
    journal.enqueue(run_id="run-1", task_id="task-1", request={}, queue_timeout_seconds=60)
    journal.claim_next()
    journal.mark_interrupted()
    snapshot = StatusReader(tmp_path).get_status()
    assert snapshot["active_run"]["state"] == "reconciling"
    assert snapshot["worker"]["online"] is False
    assert snapshot["pending_event_count"] == 3
    assert "request" not in snapshot["runs"][0]


def test_status_rejects_stale_or_reused_pid(tmp_path: Path) -> None:
    marker = tmp_path / "worker.json"
    contents = {"online": True, "pid": os.getpid(), "created_at": psutil.Process().create_time(),
                "last_seen_at": time.time() - 60}
    marker.write_text(json.dumps(contents), encoding="utf-8")
    assert StatusReader(tmp_path).get_status()["worker"]["online"] is False
    contents.update(last_seen_at=time.time(), created_at=0)
    marker.write_text(json.dumps(contents), encoding="utf-8")
    assert StatusReader(tmp_path).get_status()["worker"]["online"] is False
