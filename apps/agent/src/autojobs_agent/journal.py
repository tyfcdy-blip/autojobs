"""本地运行账本：事务内更新状态与待回传事件，不执行任何业务进程。"""

from __future__ import annotations

import json
import math
import re
import sqlite3
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

ACTIVE = ("starting", "running", "stopping", "reconciling")
FINISHED = ("succeeded", "failed", "stopped", "timed_out")
TERMINAL = (*FINISHED, "queue_expired", "cancelled")
_ACTIVE_SQL = "state IN ('starting','running','stopping','reconciling')"
_MAX_JSON_BYTES = 2 * 1024 * 1024


class JournalError(ValueError):
    """账本输入或状态不满足约束。"""


class JournalConflict(JournalError):
    """重复标识内容不同或状态转换冲突。"""


class NotFound(JournalError):
    """运行记录不存在。"""


class SchemaVersionError(JournalError):
    """账本版本不受支持，禁止覆盖或隐式迁移。"""


def _identifier(value: str) -> None:
    if (
        not isinstance(value, str)
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", value) is None
    ):
        raise JournalError("标识须为 1–128 个字母、数字、点、下划线或连字符。")


def _json(value: dict[str, Any]) -> str:
    if not isinstance(value, dict):
        raise JournalError("账本请求和结果必须为 JSON 对象。")
    try:
        encoded = json.dumps(
            value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
        )
        if len(encoded.encode("utf-8")) > _MAX_JSON_BYTES:
            raise JournalError("账本 JSON 超过 2 MiB 上限。")
        if json.loads(encoded) != value:
            raise JournalError("JSON 对象键必须是字符串，值必须是原生 JSON 类型。")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise JournalError("账本 JSON 不是有效且有界的 UTF-8 对象。") from exc
    return encoded


def _limit(limit: int) -> None:
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise JournalError("查询批量须为 1–1000。")


class Journal:
    """每个方法使用独立连接，支持 CLI 与 worker 并发访问同一账本。"""

    def __init__(
        self, path: Path, *, now: Callable[[], float] = time.time, read_only: bool = False
    ) -> None:
        self.path = Path(path).absolute()
        self._now = now
        self._read_only = read_only
        if not read_only:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.execute("BEGIN" if read_only else "BEGIN IMMEDIATE")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            tables = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
            if version not in (0, 1) or (version == 0 and (tables or read_only)):
                raise SchemaVersionError("账本版本不受支持，未更改已有表。")
            if version == 0:
                self._create_schema(connection)
                connection.execute("PRAGMA user_version=1")
            elif {row[0] for row in tables} != {"runs", "events"}:
                raise SchemaVersionError("账本结构不完整，拒绝继续运行。")
            connection.commit()
            if (
                not read_only
                and connection.execute("PRAGMA journal_mode=WAL").fetchone()[0] != "wal"
            ):
                raise JournalError("账本无法启用 WAL 模式。")

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        if self.path.is_symlink() or self.path.is_junction():
            raise JournalError("账本不能是符号链接或重解析目录。")
        target = self.path.as_uri() + "?mode=ro" if self._read_only else str(self.path)
        connection = sqlite3.connect(target, timeout=5, isolation_level=None, uri=self._read_only)
        connection.row_factory = sqlite3.Row
        try:
            if not self._read_only:
                connection.execute("PRAGMA foreign_keys=ON")
                connection.execute("PRAGMA synchronous=FULL")
            yield connection
        finally:
            connection.close()

    @contextmanager
    def _transaction(self, *, write: bool = True) -> Iterator[sqlite3.Connection]:
        if write and self._read_only:
            raise JournalError("只读账本不能修改运行状态。")
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            try:
                yield connection
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

    @staticmethod
    def _create_schema(connection: sqlite3.Connection) -> None:
        connection.execute("""CREATE TABLE runs (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL UNIQUE,
            task_id TEXT NOT NULL, request_json TEXT NOT NULL, queue_timeout REAL NOT NULL,
            state TEXT NOT NULL CHECK (state IN ('queued','starting','running','stopping',
                'reconciling','succeeded','failed','queue_expired','cancelled','stopped','timed_out')),
            stop_requested INTEGER NOT NULL DEFAULT 0 CHECK(stop_requested IN (0,1)),
            pid INTEGER, process_created_at REAL, enqueued_at REAL NOT NULL,
            deadline REAL NOT NULL, started_at REAL, finished_at REAL, exit_code INTEGER,
            result_json TEXT, error_code TEXT, message TEXT NOT NULL DEFAULT ''
        )""")
        connection.execute(f"CREATE UNIQUE INDEX one_active_run ON runs((1)) WHERE {_ACTIVE_SQL}")
        connection.execute("CREATE INDEX queued_runs ON runs(state,enqueued_at,sequence)")
        connection.execute("""CREATE TABLE events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL REFERENCES runs(run_id), state TEXT NOT NULL,
            occurred_at REAL NOT NULL, payload_json TEXT NOT NULL, acknowledged_at REAL
        )""")
        connection.execute(
            "CREATE INDEX pending_events ON events(event_id) WHERE acknowledged_at IS NULL"
        )

    def _timestamp(self) -> float:
        value = self._now()
        if (
            isinstance(value, bool)
            or not isinstance(value, (float, int))
            or not math.isfinite(value)
        ):
            raise JournalError("账本时钟必须返回有限 UTC 时间戳。")
        return float(value)

    @staticmethod
    def _decode(row: sqlite3.Row) -> dict[str, Any]:
        record = dict(row)
        record["request"] = json.loads(record.pop("request_json"))
        result = record.pop("result_json")
        record["result"] = json.loads(result) if result is not None else None
        record["stop_requested"] = bool(record["stop_requested"])
        return record

    def _get(self, connection: sqlite3.Connection, run_id: str) -> dict[str, Any]:
        _identifier(run_id)
        row = connection.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            raise NotFound("运行记录不存在。")
        return self._decode(row)

    def _event(self, connection: sqlite3.Connection, run_id: str) -> dict[str, Any]:
        record = self._get(connection, run_id)
        connection.execute(
            "INSERT INTO events(run_id,state,occurred_at,payload_json) VALUES(?,?,?,?)",
            (
                run_id,
                record["state"],
                self._timestamp(),
                json.dumps(record, ensure_ascii=False, allow_nan=False),
            ),
        )
        return record

    def _change(
        self, connection: sqlite3.Connection, run_id: str, state: str, **columns: Any
    ) -> dict[str, Any]:
        # 列名只由本模块固定调用点提供；外部值始终使用 SQL 参数。
        assignments = ",".join(f"{name}=?" for name in columns)
        suffix = f",{assignments}" if assignments else ""
        connection.execute(
            f"UPDATE runs SET state=?{suffix} WHERE run_id=?", (state, *columns.values(), run_id)
        )
        return self._event(connection, run_id)

    def enqueue(
        self, *, run_id: str, task_id: str, request: dict[str, Any], queue_timeout_seconds: float
    ) -> dict[str, Any]:
        _identifier(run_id)
        _identifier(task_id)
        encoded = _json(request)
        if (
            isinstance(queue_timeout_seconds, bool)
            or not isinstance(queue_timeout_seconds, (int, float))
            or not math.isfinite(queue_timeout_seconds)
            or queue_timeout_seconds <= 0
        ):
            raise JournalError("排队时限必须为正的有限秒数。")
        with self._transaction() as connection:
            existing = connection.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if existing is not None:
                if (
                    existing["task_id"] != task_id
                    or existing["request_json"] != encoded
                    or existing["queue_timeout"] != queue_timeout_seconds
                ):
                    raise JournalConflict("相同运行标识已用于不同的请求。")
                return self._decode(existing)
            now = self._timestamp()
            deadline = now + queue_timeout_seconds
            if not math.isfinite(deadline):
                raise JournalError("排队截止时间超出范围。")
            connection.execute(
                """INSERT INTO runs
                (run_id,task_id,request_json,queue_timeout,state,enqueued_at,deadline)
                VALUES(?,?,?,?,'queued',?,?)""",
                (run_id, task_id, encoded, queue_timeout_seconds, now, deadline),
            )
            return self._event(connection, run_id)

    def get(self, run_id: str) -> dict[str, Any]:
        with self._transaction(write=False) as connection:
            return self._get(connection, run_id)

    def list_runs(self, limit: int = 100) -> list[dict[str, Any]]:
        _limit(limit)
        with self._transaction(write=False) as connection:
            return [
                self._decode(row)
                for row in connection.execute(
                    "SELECT * FROM runs ORDER BY sequence DESC LIMIT ?", (limit,)
                )
            ]

    def active_run(self) -> dict[str, Any] | None:
        with self._transaction(write=False) as connection:
            row = connection.execute(f"SELECT * FROM runs WHERE {_ACTIVE_SQL}").fetchone()
            return self._decode(row) if row is not None else None

    def _expire(self, connection: sqlite3.Connection) -> int:
        now = self._timestamp()
        expired = connection.execute(
            "SELECT run_id FROM runs WHERE state='queued' AND deadline<=?", (now,)
        ).fetchall()
        for row in expired:
            self._change(
                connection,
                row["run_id"],
                "queue_expired",
                finished_at=now,
                error_code="QUEUE_EXPIRED",
                message="超过排队截止时间，本轮未启动。",
            )
        return len(expired)

    def expire_queued(self) -> int:
        with self._transaction() as connection:
            return self._expire(connection)

    def claim_next(self) -> dict[str, Any] | None:
        with self._transaction() as connection:
            self._expire(connection)
            if connection.execute(f"SELECT 1 FROM runs WHERE {_ACTIVE_SQL}").fetchone():
                return None
            candidate = connection.execute(
                "SELECT run_id FROM runs WHERE state='queued' ORDER BY enqueued_at,sequence LIMIT 1"
            ).fetchone()
            if candidate is None:
                return None
            # STARTING 先落盘；进程创建窗口崩溃后必须核对，不能重新派发。
            return self._change(connection, candidate["run_id"], "starting")

    def set_running(self, run_id: str, pid: int, created_at: float) -> dict[str, Any]:
        if (
            type(pid) is not int
            or pid <= 0
            or isinstance(created_at, bool)
            or not isinstance(created_at, (int, float))
            or not math.isfinite(created_at)
            or created_at <= 0
        ):
            raise JournalError("进程身份必须包含有效 PID 与创建时间。")
        with self._transaction() as connection:
            record = self._get(connection, run_id)
            if record["pid"] is not None:
                if (
                    record["state"] in ("running", "stopping")
                    and record["pid"] == pid
                    and record["process_created_at"] == created_at
                ):
                    return record
                raise JournalConflict("运行记录已绑定其他进程或已结束。")
            if record["state"] not in ("starting", "stopping"):
                raise JournalConflict("只有已领取的运行才能登记进程。")
            state = "stopping" if record["stop_requested"] else "running"
            return self._change(
                connection,
                run_id,
                state,
                pid=pid,
                process_created_at=created_at,
                started_at=created_at,
            )

    def request_stop(self, run_id: str) -> dict[str, Any]:
        with self._transaction() as connection:
            record = self._get(connection, run_id)
            if record["state"] in TERMINAL or record["stop_requested"]:
                return record
            if record["state"] == "queued":
                return self._change(
                    connection,
                    run_id,
                    "cancelled",
                    stop_requested=1,
                    finished_at=self._timestamp(),
                    message="排队已取消，未启动。",
                )
            # 待核实状态保留，停止请求不能凭空证明遗留进程已不存在。
            state = "reconciling" if record["state"] == "reconciling" else "stopping"
            return self._change(connection, run_id, state, stop_requested=1)

    def finish(
        self,
        run_id: str,
        *,
        status: str,
        exit_code: int | None,
        result: dict[str, Any] | None,
        error_code: str | None,
        message: str,
    ) -> dict[str, Any]:
        if status not in TERMINAL:
            raise JournalError("不支持的执行终态。")
        if exit_code is not None and type(exit_code) is not int:
            raise JournalError("退出码必须是整数或 null。")
        if not isinstance(message, str) or not message.strip() or len(message) > 4096:
            raise JournalError("结果说明必须非空且不超过 4096 字符。")
        try:
            message.encode("utf-8")
        except UnicodeError as exc:
            raise JournalError("结果说明不是有效 UTF-8 文本。") from exc
        if error_code is not None:
            _identifier(error_code)
        encoded = _json(result) if result is not None else None
        with self._transaction() as connection:
            record = self._get(connection, run_id)
            if record["state"] in TERMINAL:
                if (
                    record["state"] == status
                    and record["exit_code"] == exit_code
                    and (_json(record["result"]) if record["result"] is not None else None)
                    == encoded
                    and record["error_code"] == error_code
                    and record["message"] == message
                ):
                    return record
                raise JournalConflict("已确认终态不可被迟到结果覆盖。")
            if record["state"] not in ACTIVE:
                raise JournalConflict("尚未领取的任务不能提交执行终态。")
            if status in ("cancelled", "queue_expired") and (
                record["state"] not in ("starting", "stopping")
                or any(
                    record[field] is not None
                    for field in ("pid", "process_created_at", "started_at")
                )
            ):
                raise JournalConflict("无法证明本轮尚未启动，不能按排队取消或过期释放。")
            return self._change(
                connection,
                run_id,
                status,
                exit_code=exit_code,
                result_json=encoded,
                error_code=error_code,
                message=message,
                finished_at=self._timestamp(),
            )

    def mark_interrupted(self) -> int:
        with self._transaction() as connection:
            rows = connection.execute(
                "SELECT run_id FROM runs WHERE state IN ('starting','running','stopping')"
            ).fetchall()
            for row in rows:
                self._change(
                    connection,
                    row["run_id"],
                    "reconciling",
                    error_code="WORKER_INTERRUPTED",
                    message="上轮执行状态待核实，禁止重跑。",
                )
            return len(rows)

    def pending_events(self, limit: int = 100) -> list[dict[str, Any]]:
        _limit(limit)
        with self._transaction(write=False) as connection:
            records = []
            for row in connection.execute(
                """SELECT event_id,run_id,state,occurred_at,payload_json
                FROM events WHERE acknowledged_at IS NULL ORDER BY event_id LIMIT ?""",
                (limit,),
            ):
                record = dict(row)
                record["payload"] = json.loads(record.pop("payload_json"))
                records.append(record)
            return records

    def pending_event_count(self) -> int:
        with self._transaction(write=False) as connection:
            return int(
                connection.execute(
                    "SELECT count(*) FROM events WHERE acknowledged_at IS NULL"
                ).fetchone()[0]
            )

    def ack_events(self, ids: list[int]) -> int:
        if (
            not isinstance(ids, list)
            or len(ids) > 1000
            or any(type(event_id) is not int or event_id <= 0 for event_id in ids)
        ):
            raise JournalError("确认列表须包含最多 1000 个正整数事件标识。")
        with self._transaction() as connection:
            count = 0
            for event_id in set(ids):
                count += connection.execute(
                    """UPDATE events SET acknowledged_at=?
                    WHERE event_id=? AND acknowledged_at IS NULL""",
                    (self._timestamp(), event_id),
                ).rowcount
            return count
