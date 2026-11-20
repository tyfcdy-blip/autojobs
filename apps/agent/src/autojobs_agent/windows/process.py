"""本轮自有 Windows 进程树和有界日志，不操作任何既有应用。"""

from __future__ import annotations

import os
import sys
import threading
import time
from collections.abc import Callable
from contextlib import ExitStack
from pathlib import Path
from types import TracebackType
from typing import Literal, cast

from ._handles import NativeHandle

if sys.platform == "win32":
    import msvcrt

    import win32api
    import win32con
    import win32event
    import win32job
    import win32process

    from ._creation import create_suspended


class ProcessCleanupError(RuntimeError):
    """自有进程或日志尚未确认清理；调用方不得据此释放执行位置。"""


class _SpawnResources(ExitStack):
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        try:
            super().__exit__(exc_type, exc, traceback)
            # 此资源栈不得吞掉启动失败，即使未来某个上下文管理器请求抑制异常。
            return False
        except BaseException as cleanup_error:
            # 成功退出资源栈才允许传播原启动异常；清理异常必须有独立语义。
            raise ProcessCleanupError("启动阶段的资源清理未能确认完成。") from cleanup_error


def _stop_and_confirm(job: int, process: int, *, assigned: bool) -> None:
    """句柄关闭前确认两个内核证据；一个 API 失败也继续尝试其余安全清理。"""
    failures: list[BaseException] = []
    try:
        win32job.TerminateJobObject(job, 1)
    except BaseException as exc:
        failures.append(exc)
    if not assigned:
        try:
            # 分配失败也可能已经产生副作用，因此 Job 和入口进程均需处理。
            if win32event.WaitForSingleObject(process, 0) != win32event.WAIT_OBJECT_0:
                win32process.TerminateProcess(process, 1)
        except BaseException as exc:
            failures.append(exc)
    try:
        deadline = time.monotonic() + 5
        while int(
            win32job.QueryInformationJobObject(job, win32job.JobObjectBasicAccountingInformation)[
                "ActiveProcesses"
            ]
        ):
            if time.monotonic() >= deadline:
                raise ProcessCleanupError("终止后仍有本轮进程，无法确认已停止。")
            time.sleep(0.01)
    except BaseException as exc:
        failures.append(exc)
    try:
        # Job 统计与入口进程信号可短暂不同步，二者都确认后才能结束本轮。
        if win32event.WaitForSingleObject(process, 5000) != win32event.WAIT_OBJECT_0:
            raise ProcessCleanupError("入口进程尚未确认退出。")
    except BaseException as exc:
        failures.append(exc)
    if failures:
        cause = (
            failures[0]
            if len(failures) == 1
            else BaseExceptionGroup("本轮停止或核对失败", failures)
        )
        raise ProcessCleanupError("本轮进程清理未能确认完成。") from cause


class _Capture:
    def __init__(self, read_fd: int, path: Path, limit: int) -> None:
        self._reader = os.fdopen(read_fd, "rb", buffering=0)
        try:
            self._output = path.open("xb", buffering=0)
        except BaseException:
            self._reader.close()
            raise
        self._limit = limit
        self.truncated = False
        self._error: OSError | None = None
        self._thread = threading.Thread(target=self._drain, name="autojobs-log", daemon=True)
        self._started = False

    def start(self) -> None:
        self._thread.start()
        self._started = True

    def _drain(self) -> None:
        written = 0
        try:
            while chunk := self._reader.read(16384):
                retained = chunk[: max(0, self._limit - written)]
                if retained:
                    pending = memoryview(retained)
                    while pending:
                        count = self._output.write(pending)
                        if count is None or count <= 0:
                            raise OSError("日志文件未能写入数据。")
                        written += count
                        pending = pending[count:]
                if len(retained) < len(chunk):
                    self.truncated = True
                # 达到限额后仍排空管道，避免被日志阻塞的任务永远不能退出。
        except OSError as exc:
            self._error = exc
        finally:
            self._reader.close()
            self._output.close()

    def finish(self) -> None:
        if not self._started:
            self._reader.close()
            self._output.close()
            return
        self._thread.join(timeout=5)
        if self._thread.is_alive():
            raise ProcessCleanupError("日志管道仍被占用，不能确认本轮资源已结束。")
        if self._error is not None:
            raise ProcessCleanupError("本轮日志写入或读取失败。") from self._error


class WindowsJobProcess:
    def __init__(
        self,
        process_handle: int,
        job_handle: NativeHandle,
        pid: int,
        created_at: float,
        captures: list[_Capture],
        resources: ExitStack,
    ) -> None:
        self._process = process_handle
        self._job = job_handle
        self.pid = pid
        self.created_at = created_at
        self._captures = captures
        self._resources = resources
        self._closed = False
        self._exit_code: int | None = None
        self._cleanup_error: BaseException | None = None

    @classmethod
    def spawn(
        cls,
        *,
        python: Path,
        entrypoint: Path,
        cwd: Path,
        env: dict[str, str],
        stdout_path: Path,
        stderr_path: Path,
        log_limit_bytes: int = 1048576,
    ) -> WindowsJobProcess:
        if sys.platform != "win32":
            raise OSError("受控任务执行仅支持 Windows。")
        if type(log_limit_bytes) is not int or not 1 <= log_limit_bytes <= 64 * 1024 * 1024:
            raise ValueError("单条日志流限额须为 1 字节至 64 MiB。")
        if not python.is_absolute() or not python.is_file():
            raise ValueError("Python 必须是存在的绝对文件路径。")
        if not entrypoint.is_absolute() or not entrypoint.is_file():
            raise ValueError("入口必须是存在的绝对文件路径。")
        if not cwd.is_absolute() or not cwd.is_dir():
            raise ValueError("工作目录必须是存在的绝对目录。")
        if stdout_path.resolve() == stderr_path.resolve():
            raise ValueError("stdout 和 stderr 必须使用不同的文件。")
        folded_keys: set[str] = set()
        for key, value in env.items():
            if not key or "=" in key or "\x00" in key or "\x00" in value:
                raise ValueError("环境变量含非法名称或空字符。")
            if key.casefold() in folded_keys:
                raise ValueError("环境变量名称大小写冲突。")
            folded_keys.add(key.casefold())

        with _SpawnResources() as resources:
            captures: list[_Capture] = []
            writers = []
            for path in (stdout_path, stderr_path):
                read_fd, write_fd = os.pipe()
                writer = resources.enter_context(os.fdopen(write_fd, "wb", buffering=0))
                capture = _Capture(read_fd, path, log_limit_bytes)
                resources.callback(capture.finish)
                captures.append(capture)
                writers.append(writer)
            null_input = resources.enter_context(open(os.devnull, "rb", buffering=0))
            inherited_handles = [
                msvcrt.get_osfhandle(stream.fileno()) for stream in [null_input, *writers]
            ]
            for handle in inherited_handles:
                os.set_handle_inheritable(handle, True)

            # types-pywin32 312 错把该函数标为返回 None；真实调用返回可关闭 PyHANDLE。
            create_job = cast(Callable[[None, str], NativeHandle], win32job.CreateJobObject)
            job = create_job(None, "")
            resources.callback(job.Close)
            win32api.SetHandleInformation(int(job), win32con.HANDLE_FLAG_INHERIT, 0)
            limits = win32job.QueryInformationJobObject(
                int(job), win32job.JobObjectExtendedLimitInformation
            )
            limits["BasicLimitInformation"]["LimitFlags"] |= (
                win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            )
            win32job.SetInformationJobObject(
                int(job), win32job.JobObjectExtendedLimitInformation, limits
            )
            process, thread, pid = create_suspended(
                python, entrypoint, cwd, env, *inherited_handles
            )
            resources.callback(win32api.CloseHandle, process)
            thread_open = True

            def close_thread() -> None:
                nonlocal thread_open
                if thread_open:
                    win32api.CloseHandle(thread)
                    thread_open = False

            resources.callback(close_thread)
            assigned = False
            startup_complete = False

            def cleanup_failed_start() -> None:
                if not startup_complete:
                    _stop_and_confirm(int(job), int(process), assigned=assigned)

            # 回调最后登记、最先执行，保证核对时进程和 Job 句柄仍有效。
            resources.callback(cleanup_failed_start)
            win32job.AssignProcessToJobObject(int(job), int(process))
            assigned = True
            created_at = win32process.GetProcessTimes(int(process))["CreationTime"].timestamp()
            for writer in writers:
                writer.close()
            null_input.close()
            for capture in captures:
                capture.start()
            win32process.ResumeThread(int(thread))
            close_thread()
            instance = cls(process, job, pid, created_at, captures, resources)
            startup_complete = True
            instance._resources = resources.pop_all()
            return instance

    @property
    def logs_truncated(self) -> bool:
        return any(capture.truncated for capture in self._captures)

    def poll(self) -> int | None:
        if self._closed:
            return self._exit_code
        outcome = win32event.WaitForSingleObject(int(self._process), 0)
        if outcome == win32event.WAIT_TIMEOUT:
            return None
        if outcome != win32event.WAIT_OBJECT_0:
            raise ProcessCleanupError("无法确认入口进程的退出状态。")
        self._exit_code = int(win32process.GetExitCodeProcess(int(self._process)))
        return self._exit_code

    def active_process_count(self) -> int:
        if self._closed:
            raise RuntimeError("Job 已关闭，不能继续核对进程数。")
        accounting = win32job.QueryInformationJobObject(
            int(self._job), win32job.JobObjectBasicAccountingInformation
        )
        return int(accounting["ActiveProcesses"])

    def terminate(self, exit_code: int = 1) -> None:
        if self._closed:
            raise RuntimeError("Job 已关闭，不能再次终止。")
        win32job.TerminateJobObject(int(self._job), exit_code)

    def close(self) -> None:
        if self._closed:
            if self._cleanup_error is not None:
                raise ProcessCleanupError("上次资源清理未能确认完成。") from self._cleanup_error
            return
        try:
            try:
                _stop_and_confirm(int(self._job), int(self._process), assigned=True)
                self.poll()
            finally:
                self._closed = True
                # Job 句柄先关闭，再等待日志管道排空，不能把仍有写端视为清理成功。
                self._resources.close()
        except BaseException as exc:
            self._cleanup_error = exc
            raise ProcessCleanupError("本轮资源清理未能确认完成。") from exc

    def __enter__(self) -> WindowsJobProcess:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
