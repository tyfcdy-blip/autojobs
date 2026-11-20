"""整台电脑的执行器互斥；不同状态目录也不能同时运行。"""

from __future__ import annotations

import sys
import threading
from types import TracebackType

from ._handles import NativeHandle

if sys.platform == "win32":
    import pywintypes
    import win32api
    import win32event
    import winerror


class AgentAlreadyRunning(RuntimeError):
    """另一执行器已持有机器锁。"""


class MachineMutex:
    def __init__(self, name: str = r"Global\AutojobsAgentWorker-v1") -> None:
        if not name or "\x00" in name:
            raise ValueError("机器锁名称无效。")
        self.name = name
        self._handle: NativeHandle | None = None
        self._owner_thread: int | None = None
        self.abandoned = False

    def acquire(self) -> None:
        if sys.platform != "win32":
            raise OSError("执行端机器锁仅支持 Windows。")
        if self._handle is not None:
            raise RuntimeError("同一机器锁实例不能重复获取。")
        # 不接管其他用户的锁；访问被拒绝时直接失败，不以另一个名称绕过。
        handle = win32event.CreateMutex(pywintypes.SECURITY_ATTRIBUTES(), False, self.name)
        already_exists = win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS
        try:
            outcome = win32event.WaitForSingleObject(int(handle), 0)
            if outcome == win32event.WAIT_TIMEOUT:
                raise AgentAlreadyRunning("本机已有执行端运行。")
            if outcome not in (win32event.WAIT_OBJECT_0, win32event.WAIT_ABANDONED):
                raise OSError(f"机器锁等待结果异常：{outcome}")
            if already_exists and outcome == win32event.WAIT_OBJECT_0:
                # Win32 mutex 允许同线程递归拥有；另一个 wrapper 不能借此绕过单实例。
                # 对仅剩观察句柄的未占用旧对象也保守拒绝，关闭旧句柄后可重新启动。
                win32event.ReleaseMutex(int(handle))
                raise AgentAlreadyRunning("本机执行端锁已存在，请核对原执行端是否退出。")
            self._handle = handle
            self._owner_thread = threading.get_ident()
            self.abandoned = outcome == win32event.WAIT_ABANDONED
        except BaseException:
            handle.Close()
            raise

    def release(self) -> None:
        if self._handle is None:
            return
        if self._owner_thread != threading.get_ident():
            raise RuntimeError("机器锁必须由获取它的线程释放。")
        win32event.ReleaseMutex(int(self._handle))
        self._handle.Close()
        self._handle = None
        self._owner_thread = None

    def __enter__(self) -> MachineMutex:
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.release()
