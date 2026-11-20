"""M0-06/07/10/11/15：用真实 SQLite 验证串行、幂等、恢复与原子事件。"""

from __future__ import annotations

import hashlib
import sqlite3
import threading
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

from autojobs_agent.journal import (
    Journal,
    JournalConflict,
    JournalError,
    NotFound,
    SchemaVersionError,
)


class Clock:
    def __init__(self) -> None:
        self.value = 1_000.0

    def __call__(self) -> float:
        return self.value


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def journal(tmp_path: Path, clock: Clock) -> Journal:
    return Journal(tmp_path / "journal.sqlite3", now=clock)


def enqueue(journal: Journal, run_id: str = "run-1", timeout: float = 60) -> dict[str, Any]:
    return journal.enqueue(
        run_id=run_id,
        task_id="task-1",
        request={"entrypoint": "作业.py"},
        queue_timeout_seconds=timeout,
    )


def finish(journal: Journal, run_id: str = "run-1", status: str = "succeeded") -> dict[str, Any]:
    return journal.finish(
        run_id,
        status=status,
        exit_code=0,
        result={"status": "success", "result": None},
        error_code=None,
        message="测试任务完成",
    )


def _claim_from_process(path: str) -> str | None:
    claimed = Journal(Path(path)).claim_next()
    return claimed["run_id"] if claimed else None


def test_complete_run_events_are_persistent_and_ack_is_idempotent(journal: Journal) -> None:
    enqueue(journal)
    assert journal.claim_next()["state"] == "starting"
    journal.set_running("run-1", 4321, 1_001)
    completed = finish(journal)
    restored = Journal(journal.path)
    assert restored.get("run-1") == completed
    events = restored.pending_events()
    assert [event["state"] for event in events] == ["queued", "starting", "running", "succeeded"]
    assert events[0]["payload"]["state"] == "queued"
    assert restored.pending_event_count() == 4
    ids = [event["event_id"] for event in events]
    assert restored.ack_events(ids + [ids[0]]) == 4
    assert restored.ack_events(ids) == 0
    assert restored.pending_event_count() == 0
    assert restored.get("run-1")["state"] == "succeeded"


def test_enqueue_duplicate_is_canonical_and_does_not_extend_deadline(
    journal: Journal,
    clock: Clock,
) -> None:
    original = journal.enqueue(
        run_id="run-1", task_id="task-1", request={"a": 1, "b": 2}, queue_timeout_seconds=60
    )
    clock.value += 50
    duplicate = journal.enqueue(
        run_id="run-1", task_id="task-1", request={"b": 2, "a": 1}, queue_timeout_seconds=60
    )
    assert duplicate == original
    assert journal.pending_event_count() == 1
    for changed in ({"task_id": "task-2"}, {"request": {"a": 2}}, {"queue_timeout_seconds": 61}):
        request = {
            "run_id": "run-1",
            "task_id": "task-1",
            "request": {"a": 1, "b": 2},
            "queue_timeout_seconds": 60,
        }
        request.update(changed)
        with pytest.raises(JournalConflict):
            journal.enqueue(**request)


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf"), True, "60"])
def test_invalid_wait_limits_are_rejected(journal: Journal, timeout: Any) -> None:
    with pytest.raises(JournalError):
        enqueue(journal, timeout=timeout)
    assert journal.list_runs() == []


@pytest.mark.parametrize("run_id", ["", "../run", "name;DELETE", "r" * 129, 123])
def test_invalid_identity_rejected_before_sql(journal: Journal, run_id: Any) -> None:
    with pytest.raises(JournalError):
        enqueue(journal, run_id=run_id)


@pytest.mark.parametrize(
    "payload",
    [
        {"bad": float("nan")},
        {"bad": object()},
        [],
        {1: "numeric key"},
        {"nested": {1: "numeric key"}},
        {"tuple": (1, 2)},
        {"surrogate": "\ud800"},
        {"large": "a" * (2 * 1024 * 1024)},
    ],
)
def test_invalid_or_oversized_request_is_rejected(journal: Journal, payload: Any) -> None:
    with pytest.raises(JournalError):
        journal.enqueue(run_id="run-1", task_id="task-1", request=payload, queue_timeout_seconds=60)
    assert journal.pending_event_count() == 0


def test_fifo_order_and_single_active_slot(journal: Journal) -> None:
    for name in ["run-z", "run-a", "run-b"]:
        enqueue(journal, name)
    assert journal.claim_next()["run_id"] == "run-z"
    assert journal.claim_next() is None
    assert journal.active_run()["run_id"] == "run-z"
    finish(journal, "run-z", "failed")
    assert journal.claim_next()["run_id"] == "run-a"


def test_exact_deadline_expires_only_queued(journal: Journal, clock: Clock) -> None:
    enqueue(journal, "active", timeout=1)
    enqueue(journal, "waiting", timeout=1)
    assert journal.claim_next()["run_id"] == "active"
    clock.value += 1
    assert journal.claim_next() is None
    assert journal.get("waiting")["state"] == "queue_expired"
    assert journal.get("active")["state"] == "starting"
    assert journal.expire_queued() == 0


def test_cancel_queued_prevents_claim(journal: Journal) -> None:
    enqueue(journal)
    cancelled = journal.request_stop("run-1")
    assert cancelled["state"] == "cancelled"
    assert cancelled["pid"] is None
    assert journal.claim_next() is None
    assert journal.request_stop("run-1") == cancelled
    assert journal.pending_event_count() == 2


def test_stop_before_pid_is_recorded_does_not_get_overwritten(journal: Journal) -> None:
    enqueue(journal)
    journal.claim_next()
    journal.request_stop("run-1")
    running = journal.set_running("run-1", 4321, 1_001)
    assert running["state"] == "stopping"
    assert running["stop_requested"] is True
    assert journal.set_running("run-1", 4321, 1_001) == running
    assert journal.pending_event_count() == 4
    with pytest.raises(JournalConflict):
        journal.set_running("run-1", 9876, 1_002)


@pytest.mark.parametrize("old_state", ["starting", "running", "stopping"])
def test_restart_requires_reconciliation_and_never_reclaims(
    journal: Journal,
    old_state: str,
) -> None:
    enqueue(journal, "interrupted")
    enqueue(journal, "next")
    journal.claim_next()
    if old_state == "running":
        journal.set_running("interrupted", 4321, 1_001)
    if old_state == "stopping":
        journal.request_stop("interrupted")
    restored = Journal(journal.path)
    assert restored.mark_interrupted() == 1
    assert restored.mark_interrupted() == 0
    assert restored.claim_next() is None
    record = restored.get("interrupted")
    assert record["state"] == "reconciling"
    assert restored.request_stop("interrupted")["state"] == "reconciling"
    assert restored.active_run()["run_id"] == "interrupted"


def test_finish_replay_is_idempotent_but_late_conflicts_cannot_overwrite(journal: Journal) -> None:
    enqueue(journal)
    journal.claim_next()
    first = finish(journal)
    count = journal.pending_event_count()
    assert finish(journal) == first
    assert journal.pending_event_count() == count
    with pytest.raises(JournalConflict):
        finish(journal, status="failed")
    with pytest.raises(JournalConflict):
        journal.set_running("run-1", 4321, 1_001)
    assert journal.request_stop("run-1") == first


def test_unclaimed_run_cannot_finish(journal: Journal) -> None:
    enqueue(journal)
    with pytest.raises(JournalConflict):
        finish(journal)
    assert journal.get("run-1")["state"] == "queued"


def test_invalid_message_rejected_without_losing_active_run(journal: Journal) -> None:
    enqueue(journal)
    journal.claim_next()
    with pytest.raises(JournalError):
        journal.finish(
            "run-1", status="failed", exit_code=1, result=None, error_code=None, message="\ud800"
        )
    assert journal.active_run()["state"] == "starting"


def test_terminal_replay_does_not_coerce_boolean_to_number(journal: Journal) -> None:
    enqueue(journal)
    journal.claim_next()
    journal.finish(
        "run-1",
        status="failed",
        exit_code=1,
        result={"result": True},
        error_code=None,
        message="业务失败",
    )
    with pytest.raises(JournalConflict):
        journal.finish(
            "run-1",
            status="failed",
            exit_code=1,
            result={"result": 1},
            error_code=None,
            message="业务失败",
        )


@pytest.mark.parametrize("status", ["cancelled", "queue_expired"])
@pytest.mark.parametrize("stop_requested", [False, True])
def test_claimed_but_never_started_can_cancel_or_expire(
    journal: Journal,
    status: str,
    stop_requested: bool,
) -> None:
    enqueue(journal)
    journal.claim_next()
    if stop_requested:
        journal.request_stop("run-1")
    record = journal.finish(
        "run-1",
        status=status,
        exit_code=None,
        result=None,
        error_code=None,
        message="已确认本轮未创建进程",
    )
    assert record["state"] == status
    assert journal.active_run() is None


@pytest.mark.parametrize("status", ["cancelled", "queue_expired"])
@pytest.mark.parametrize("recorded_process", [False, True])
def test_unknown_or_started_run_cannot_use_queue_terminal_state(
    journal: Journal,
    status: str,
    recorded_process: bool,
) -> None:
    enqueue(journal)
    journal.claim_next()
    if recorded_process:
        journal.set_running("run-1", 4321, 1_001)
        journal.request_stop("run-1")
    else:
        journal.mark_interrupted()
    with pytest.raises(JournalConflict):
        journal.finish(
            "run-1",
            status=status,
            exit_code=None,
            result=None,
            error_code=None,
            message="不能证明未启动",
        )
    assert journal.active_run()["run_id"] == "run-1"


@pytest.mark.parametrize("method", ["get", "request_stop"])
def test_unknown_run_is_explicit(journal: Journal, method: str) -> None:
    with pytest.raises(NotFound):
        getattr(journal, method)("missing")


@pytest.mark.parametrize("limit", [0, -1, 1001, True, 1.5])
def test_query_and_event_batch_limits(journal: Journal, limit: Any) -> None:
    for method in [journal.list_runs, journal.pending_events]:
        with pytest.raises(JournalError):
            method(limit=limit)


@pytest.mark.parametrize("event_ids", [[True], [0], [-1], [1] * 1001, "1"])
def test_event_ack_limits(journal: Journal, event_ids: Any) -> None:
    with pytest.raises(JournalError):
        journal.ack_events(event_ids)
    assert journal.ack_events([]) == 0
    assert journal.ack_events([9999]) == 0


def test_unknown_schema_refused_without_changing_database(tmp_path: Path) -> None:
    path = tmp_path / "future.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA user_version=2")
        connection.execute("CREATE TABLE future_version(secret TEXT)")
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(SchemaVersionError):
        Journal(path)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_unversioned_existing_database_refused(tmp_path: Path) -> None:
    path = tmp_path / "unrelated.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE unrelated(value TEXT)")
    with pytest.raises(SchemaVersionError):
        Journal(path)
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 0


def test_read_only_mode_does_not_initialize_and_rejects_writes(
    journal: Journal,
    tmp_path: Path,
) -> None:
    enqueue(journal)
    readonly = Journal(journal.path, read_only=True)
    assert readonly.get("run-1") == journal.get("run-1")
    assert readonly.pending_event_count() == 1
    with pytest.raises(JournalError, match="只读"):
        readonly.request_stop("run-1")
    with pytest.raises(JournalError, match="只读"):
        readonly.claim_next()
    missing = tmp_path / "not-created" / "missing.sqlite3"
    with pytest.raises(sqlite3.OperationalError):
        Journal(missing, read_only=True)
    assert not missing.parent.exists()


def test_event_write_failure_rolls_back_state(
    journal: Journal, monkeypatch: pytest.MonkeyPatch
) -> None:
    enqueue(journal)
    before = journal.get("run-1")

    def fail_event(*args: Any) -> dict[str, Any]:
        raise sqlite3.OperationalError("injected test storage failure")

    monkeypatch.setattr(journal, "_event", fail_event)
    with pytest.raises(sqlite3.OperationalError):
        journal.claim_next()
    assert journal.get("run-1") == before
    assert journal.pending_event_count() == 1


def test_database_constraint_itself_blocks_a_second_active_run(journal: Journal) -> None:
    enqueue(journal, "first")
    enqueue(journal, "second")
    journal.claim_next()
    with sqlite3.connect(journal.path) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("UPDATE runs SET state='starting' WHERE run_id='second'")
    assert journal.get("second")["state"] == "queued"


@pytest.mark.integration
def test_parallel_threads_claim_exactly_one_real_sqlite_run(tmp_path: Path) -> None:
    journal = Journal(tmp_path / "thread.sqlite3")
    for index in range(12):
        enqueue(journal, f"run-{index}")
    barrier = threading.Barrier(8)

    def claim() -> dict[str, Any] | None:
        separate_connection = Journal(journal.path)
        barrier.wait(timeout=10)
        return separate_connection.claim_next()

    with ThreadPoolExecutor(max_workers=8) as executor:
        claims = list(executor.map(lambda _: claim(), range(8)))
    assert sum(record is not None for record in claims) == 1
    assert len([record for record in journal.list_runs() if record["state"] == "starting"]) == 1


@pytest.mark.integration
def test_parallel_processes_claim_exactly_one_real_sqlite_run(tmp_path: Path) -> None:
    journal = Journal(tmp_path / "process.sqlite3")
    for index in range(8):
        enqueue(journal, f"run-{index}")
    with ProcessPoolExecutor(max_workers=4) as executor:
        claims = list(executor.map(_claim_from_process, [str(journal.path)] * 8))
    assert sum(claim is not None for claim in claims) == 1


@pytest.mark.integration
def test_cancel_and_claim_race_preserves_unambiguous_state(journal: Journal) -> None:
    enqueue(journal)
    barrier = threading.Barrier(2)

    def claim() -> dict[str, Any] | None:
        barrier.wait(timeout=10)
        return journal.claim_next()

    def cancel() -> dict[str, Any]:
        barrier.wait(timeout=10)
        return journal.request_stop("run-1")

    with ThreadPoolExecutor(max_workers=2) as executor:
        claimed = executor.submit(claim)
        cancelled = executor.submit(cancel)
        claimed_record, _ = claimed.result(), cancelled.result()
    record = journal.get("run-1")
    if claimed_record is None:
        assert record["state"] == "cancelled"
        assert journal.active_run() is None
    else:
        assert record["state"] == "stopping"
        assert journal.active_run()["run_id"] == "run-1"
