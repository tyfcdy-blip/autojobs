"""两个真实进程争抢同一个系统锁，验证跨进程互斥。"""

from __future__ import annotations

import subprocess
import sys
import threading
import uuid
from typing import Any

import pytest

from autojobs_agent.windows.mutex import AgentAlreadyRunning, MachineMutex

pytestmark = [
    pytest.mark.windows,
    pytest.mark.integration,
    pytest.mark.skipif(sys.platform != "win32", reason="需要 Windows 命名互斥"),
]


def try_from_other_process(name: str) -> str:
    source = (
        "import sys\nfrom autojobs_agent.windows.mutex import MachineMutex,AgentAlreadyRunning\n"
        "try:\n"
        "    with MachineMutex(sys.argv[1]): print('acquired')\n"
        "except AgentAlreadyRunning: print('blocked')\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", source, name],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    return completed.stdout.strip()


def test_cross_process_lock_and_release() -> None:
    name = rf"Global\autojobs-test-{uuid.uuid4()}"
    with MachineMutex(name):
        assert try_from_other_process(name) == "blocked"
    assert try_from_other_process(name) == "acquired"


def test_same_object_reacquire_is_rejected() -> None:
    with MachineMutex(rf"Local\autojobs-test-{uuid.uuid4()}") as mutex:
        with pytest.raises(RuntimeError, match="重复获取"):
            mutex.acquire()


def test_separate_objects_cannot_reenter_same_thread_lock() -> None:
    name = rf"Global\autojobs-test-{uuid.uuid4()}"
    with MachineMutex(name):
        with pytest.raises(AgentAlreadyRunning):
            MachineMutex(name).acquire()
        assert try_from_other_process(name) == "blocked"


def test_other_thread_cannot_release_owner_lock() -> None:
    errors: list[BaseException] = []
    with MachineMutex(rf"Global\autojobs-test-{uuid.uuid4()}") as mutex:

        def release_from_thread() -> None:
            try:
                mutex.release()
            except RuntimeError as exc:
                errors.append(exc)

        thread = threading.Thread(target=release_from_thread)
        thread.start()
        thread.join(timeout=5)
        assert not thread.is_alive()
        assert len(errors) == 1
        assert try_from_other_process(mutex.name) == "blocked"


def test_default_machine_lock_is_not_directory_scoped() -> None:
    assert MachineMutex().name == r"Global\AutojobsAgentWorker-v1"
    assert issubclass(AgentAlreadyRunning, RuntimeError)


def test_abandoned_mutex_is_reported_for_recovery() -> None:
    import pywintypes
    import win32event

    name = rf"Global\autojobs-test-{uuid.uuid4()}"
    handles: list[Any] = []

    def abandoned_owner() -> None:
        handle = win32event.CreateMutex(pywintypes.SECURITY_ATTRIBUTES(), False, name)
        assert win32event.WaitForSingleObject(int(handle), 0) == win32event.WAIT_OBJECT_0
        handles.append(handle)
        # 测试故意让拥有线程结束而不 Release，保留观察句柄以检查内核 abandoned 状态。

    thread = threading.Thread(target=abandoned_owner)
    thread.start()
    thread.join(timeout=5)
    assert not thread.is_alive()
    try:
        with MachineMutex(name) as mutex:
            assert mutex.abandoned
    finally:
        for handle in handles:
            handle.Close()
