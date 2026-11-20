"""本机验证 worker：持有机器锁后领取本地请求，监督并持久化真实执行结果。"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

import psutil

from autojobs_agent.contracts import (
    ProtocolError,
    RunRequest,
    load_result,
    require_plain_path,
)
from autojobs_agent.environment import child_environment, inspect_environment
from autojobs_agent.journal import Journal
from autojobs_agent.windows.mutex import MachineMutex
from autojobs_agent.windows.process import ProcessCleanupError, WindowsJobProcess


def run_directory(state_dir: Path, run_id: str) -> Path:
    # 运行标识只作关联；摘要目录规避 Windows 保留名、末尾点与路径歧义。
    return require_plain_path(state_dir / "runs" / hashlib.sha256(run_id.encode()).hexdigest())


def atomic_json(path: Path, contents: dict[str, Any]) -> None:
    target = require_plain_path(path)
    descriptor, name = tempfile.mkstemp(prefix=".state-", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(contents, stream, ensure_ascii=False, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, target)
    finally:
        Path(name).unlink(missing_ok=True)


class Worker:
    def __init__(self, state_dir: Path, *, poll_seconds: float = 0.1) -> None:
        self.state_dir = require_plain_path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.journal = Journal(require_plain_path(self.state_dir / "journal.sqlite3"))
        self.poll_seconds = poll_seconds
        self._pid = os.getpid()
        self._created_at = psutil.Process(self._pid).create_time()
        self._last_heartbeat = 0.0
        self._last_queue_sweep = 0.0

    def _heartbeat(self, *, online: bool = True, force: bool = False) -> None:
        current = time.monotonic()
        if not force and current - self._last_heartbeat < 1:
            return
        atomic_json(self.state_dir / "worker.json", {
            "online": online, "pid": self._pid, "created_at": self._created_at,
            "last_seen_at": time.time(), "mode": "local_validation",
        })
        self._last_heartbeat = current

    def _maintenance(self) -> None:
        self._heartbeat()
        now = time.monotonic()
        if now - self._last_queue_sweep >= self.poll_seconds:
            self.journal.expire_queued()
            self._last_queue_sweep = now

    def serve(self, *, once: bool = False, stop_event: threading.Event | None = None) -> None:
        stop = stop_event if stop_event is not None else threading.Event()
        with MachineMutex():
            # 获取全机锁之后才处理旧记录；第二个启动者不能改写正在执行的状态。
            self.journal.mark_interrupted()
            self._heartbeat(force=True)
            try:
                while not stop.is_set():
                    self._heartbeat()
                    record = self.journal.claim_next()
                    if record is not None:
                        self._execute(record, stop)
                    if once:
                        return
                    stop.wait(self.poll_seconds)
            finally:
                self._heartbeat(online=False, force=True)

    def _execute(self, record: dict[str, Any], stop: threading.Event) -> None:
        run_id = record["run_id"]
        process: WindowsJobProcess | None = None
        try:
            request = RunRequest.model_validate(record["request"])
            if request.run_id != run_id or request.manifest.task_id != record["task_id"]:
                raise ProtocolError("REQUEST_MISMATCH", "本地请求与账本标识不一致。")
            directory = run_directory(self.state_dir, run_id)
            # 同一 run 永不覆盖旧输出；旧目录意味着启动历史不完整，需要核实。
            if directory.exists():
                self.journal.mark_interrupted()
                return
            directory.mkdir(parents=True)
            inspection = inspect_environment(request, on_poll=self._maintenance)
            atomic_json(directory / "environment.json", inspection)
            if not inspection["ready"]:
                self._finish(run_id, "failed", error_code="ENVIRONMENT_NOT_READY",
                             message="运行环境缺项；查看本轮环境检查记录。")
                return
            current = self.journal.get(run_id)
            if current["stop_requested"] or stop.is_set():
                self._finish(run_id, "cancelled", message="在启动业务进程前已取消。")
                return
            if time.time() >= record["deadline"]:
                self._finish(run_id, "queue_expired", error_code="QUEUE_TIMEOUT",
                             message="等待及启动前检查已超过排队时限，本轮未启动。")
                return
            environment = child_environment()
            environment.update({
                "AUTOJOBS_RUN_ID": run_id,
                "AUTOJOBS_RESULT_PATH": str(directory / "result.json"),
                "AUTOJOBS_CANCEL_PATH": str(directory / "cancel.flag"),
                "PYTHONPATH": str(Path(__file__).resolve().parent.parent),
            })
            started = time.monotonic()
            process = WindowsJobProcess.spawn(
                python=Path(request.manifest.python), entrypoint=request.entrypoint_path(),
                cwd=Path(request.task_root), env=environment,
                stdout_path=directory / "stdout.log", stderr_path=directory / "stderr.log",
            )
            self.journal.set_running(run_id, process.pid, process.created_at)
            stop_reason = self._monitor(request, process, directory, started, stop)
            exit_code = process.poll()
            process.close()
            logs_truncated = process.logs_truncated
            process = None
            self._record_completion(run_id, directory, exit_code, stop_reason, logs_truncated)
        except Exception as exc:
            # 执行边界必须先清理、再记失败；无法确认清理则保持占用，不推进队列。
            if process is not None:
                try:
                    process.close()
                except Exception:
                    self.journal.mark_interrupted()
                    raise
            if isinstance(exc, ProcessCleanupError):
                # spawn/probe 也可能在返回进程对象之前失败，不能因此推断没有残留进程。
                self.journal.mark_interrupted()
                raise
            current = self.journal.get(run_id)
            if current["state"] in {"starting", "running", "stopping"}:
                code = exc.code if isinstance(exc, ProtocolError) else "EXECUTION_ERROR"
                message = str(exc) if isinstance(exc, ProtocolError) else f"执行端异常（{type(exc).__name__}），本轮自有进程已清理。"
                self._finish(run_id, "failed", error_code=code, message=message)
            else:
                raise

    def _monitor(
        self, request: RunRequest, process: WindowsJobProcess, directory: Path,
        started: float, stop: threading.Event,
    ) -> str | None:
        stop_reason: str | None = None
        stop_deadline: float | None = None
        forced = False
        while True:
            self._maintenance()
            if process.poll() is not None and process.active_process_count() == 0:
                return stop_reason
            current = self.journal.get(request.run_id)
            now = time.monotonic()
            if stop_reason is None:
                expired = now - started >= request.manifest.timeout_seconds
                # Windows 恢复休眠后，墙钟截止作为补充防线；时钟调整需现场验证。
                expired = expired or time.time() >= process.created_at + request.manifest.timeout_seconds
                if expired or current["stop_requested"] or stop.is_set():
                    stop_reason = "timed_out" if expired else "stopped"
                    self.journal.request_stop(request.run_id)
                    require_plain_path(directory / "cancel.flag").touch()
                    stop_deadline = now + request.manifest.stop_grace_seconds
            if stop_deadline is not None and now >= stop_deadline and not forced:
                process.terminate()
                forced = True
                stop_deadline = now + 5
            elif forced and stop_deadline is not None and now >= stop_deadline:
                raise RuntimeError("任务进程终止后仍无法确认已清理。")
            time.sleep(self.poll_seconds)

    def _record_completion(
        self, run_id: str, directory: Path, exit_code: int | None,
        stop_reason: str | None, logs_truncated: bool,
    ) -> None:
        result: dict[str, Any] | None = None
        result_error: ProtocolError | None = None
        diagnostics = ""
        try:
            result = load_result(directory / "result.json", run_id).model_dump()
        except ProtocolError as exc:
            result_error = exc
        if stop_reason:
            status = stop_reason
            code = "RUN_TIMEOUT" if status == "timed_out" else "STOP_REQUESTED"
            message = "达到最长运行时间，已确认本轮自有进程停止。" if status == "timed_out" else "已确认本轮自有进程停止。"
        elif result_error:
            status, code, message = "failed", result_error.code, str(result_error)
        elif result is not None and result["status"] == "success" and exit_code == 0:
            status, code, message = "succeeded", None, result["message"]
        elif result is not None and result["status"] == "failed":
            status, code, message = "failed", "BUSINESS_FAILED", result["message"]
            if exit_code == 0:
                diagnostics += "（业务失败，但脚本退出码为 0。）"
        else:
            status, code, message = "failed", "RESULT_EXIT_CONFLICT", "成功结果与进程退出码冲突。"
        if logs_truncated:
            diagnostics += "（日志超过限额，已截断。）"
        if len(message) + len(diagnostics) > 4096:
            # 只限制平台展示摘要，脚本完整 message 仍在结构化 result 中保留。
            suffix = diagnostics + "（摘要已截断，完整说明见业务结果。）"
            message = message[:4096 - len(suffix)] + suffix
        else:
            message += diagnostics
        self._finish(run_id, status, exit_code=exit_code, result=result, error_code=code, message=message)

    def _finish(
        self, run_id: str, status: str, *, exit_code: int | None = None,
        result: dict[str, Any] | None = None, error_code: str | None = None, message: str,
    ) -> None:
        self.journal.finish(run_id, status=status, exit_code=exit_code, result=result,
                            error_code=error_code, message=message)
