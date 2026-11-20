"""本机状态的只读投影；不创建账本，也不把本地事件冒充云端已接收。"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any

import psutil

from autojobs_agent.contracts import ProtocolError, read_json_file, require_plain_path
from autojobs_agent.journal import Journal


class StatusReader:
    def __init__(self, state_dir: Path) -> None:
        self.state_dir = require_plain_path(state_dir)

    def _worker(self) -> dict[str, Any]:
        marker = self.state_dir / "worker.json"
        offline = {"online": False, "last_seen_at": None, "pid": None}
        if not marker.exists():
            return offline
        state = read_json_file(marker, limit=4096)
        if not isinstance(state, dict):
            raise ProtocolError("INVALID_WORKER_STATE", "执行程序状态记录损坏。")
        last_seen = state.get("last_seen_at")
        pid = state.get("pid")
        if type(pid) is not int or pid <= 0 or not isinstance(last_seen, (int, float)) or isinstance(last_seen, bool):
            raise ProtocolError("INVALID_WORKER_STATE", "执行程序状态字段无效。")
        if not math.isfinite(last_seen):
            raise ProtocolError("INVALID_WORKER_STATE", "执行程序状态时间无效。")
        online = state.get("online") is True and 0 <= time.time() - last_seen < 5
        try:
            online = online and psutil.Process(pid).create_time() == state.get("created_at")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            online = False
        return {"online": online, "last_seen_at": last_seen, "pid": pid}

    @staticmethod
    def _summary(record: dict[str, Any]) -> dict[str, Any]:
        fields = ("run_id", "task_id", "state", "stop_requested", "enqueued_at", "deadline",
                  "started_at", "finished_at", "pid", "exit_code", "error_code", "message", "result")
        summary = {key: record.get(key) for key in fields}
        serialized = json.dumps(summary["result"], ensure_ascii=False)
        if len(serialized) > 16_384:
            summary["result"] = {"display_truncated": True, "preview": serialized[:16_384],
                                 "message": "此窗口仅展示摘要，完整结果保留在本机账本。"}
        return summary

    def get_status(self) -> dict[str, Any]:
        worker = self._worker()
        path = require_plain_path(self.state_dir / "journal.sqlite3")
        if not path.exists():
            if worker["online"]:
                raise ProtocolError("MISSING_JOURNAL", "执行程序在线，但本地账本缺失。")
            return {"mode": "local_validation", "worker": worker,
                    "active_run": None, "runs": [], "pending_event_count": 0}
        journal = Journal(path, read_only=True)
        active = journal.active_run()
        return {"mode": "local_validation", "worker": worker,
                "active_run": self._summary(active) if active else None,
                "runs": [self._summary(record) for record in journal.list_runs(limit=50)],
                "pending_event_count": journal.pending_event_count()}
