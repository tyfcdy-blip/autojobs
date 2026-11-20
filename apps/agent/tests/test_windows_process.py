"""只在临时目录创建自有进程，验证真实 Job 边界。"""

from __future__ import annotations

import gc
import os
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import psutil
import pytest

from autojobs_agent.windows.process import ProcessCleanupError, WindowsJobProcess

pytestmark = [
    pytest.mark.windows,
    pytest.mark.integration,
    pytest.mark.skipif(sys.platform != "win32", reason="需要真实 Windows Job"),
]


def wait_for(condition: Callable[[], bool], timeout: float = 10) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() >= deadline:
            pytest.fail("自有测试进程未在时限内达到预期状态")
        time.sleep(0.02)


def spawn_script(tmp_path: Path, source: str, *, limit: int = 1048576) -> WindowsJobProcess:
    script = tmp_path / "执行入口 含空格.py"
    script.write_text(source, encoding="utf-8")
    environment = dict(os.environ, PYTHONIOENCODING="utf-8")
    return WindowsJobProcess.spawn(
        python=Path(sys.executable),
        entrypoint=script,
        cwd=tmp_path,
        env=environment,
        stdout_path=tmp_path / "stdout.log",
        stderr_path=tmp_path / "stderr.log",
        log_limit_bytes=limit,
    )


def test_unicode_paths_exit_code_and_logs(tmp_path: Path) -> None:
    with spawn_script(
        tmp_path,
        'import sys,time\nprint("中文结果")\nprint("错误说明",file=sys.stderr)\ntime.sleep(.2)',
    ) as run:
        assert abs(run.created_at - psutil.Process(run.pid).create_time()) < 0.01
        wait_for(lambda: run.poll() is not None)
        assert run.poll() == 0
        assert run.active_process_count() == 0
    assert (tmp_path / "stdout.log").read_text(encoding="utf-8").strip() == "中文结果"
    assert (tmp_path / "stderr.log").read_text(encoding="utf-8").strip() == "错误说明"
    assert run.poll() == 0
    assert not run.logs_truncated


def test_nonzero_exit_code(tmp_path: Path) -> None:
    with spawn_script(tmp_path, "raise SystemExit(17)") as run:
        wait_for(lambda: run.poll() is not None)
        assert run.poll() == 17


def test_parent_exits_while_child_is_still_in_job(tmp_path: Path) -> None:
    source = (
        "import subprocess,sys\n"
        'subprocess.Popen([sys.executable,"-c","import time;time.sleep(60)"])\n'
    )
    with spawn_script(tmp_path, source) as run:
        wait_for(lambda: run.poll() is not None)
        assert run.poll() == 0
        # 虚拟环境 python.exe 可能额外派生启动器，不能用源码层数猜 OS 进程数。
        assert run.active_process_count() >= 1
        run.terminate(23)
        wait_for(lambda: run.active_process_count() == 0)


def test_terminate_cleans_grandchildren_and_preserves_unrelated_process(tmp_path: Path) -> None:
    grandchild = tmp_path / "grandchild.py"
    grandchild.write_text(
        "import time\nfrom pathlib import Path\nPath('grandchild-ready').write_text('ready')\ntime.sleep(60)\n",
        encoding="utf-8",
    )
    child = tmp_path / "child.py"
    child.write_text(
        "import subprocess,sys,time\n"
        "subprocess.Popen([sys.executable,'grandchild.py'])\ntime.sleep(60)\n",
        encoding="utf-8",
    )
    unrelated = subprocess.Popen(
        [sys._base_executable, "-c", "import time;time.sleep(60)"],
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    try:
        with spawn_script(
            tmp_path,
            "import subprocess,sys,time\nsubprocess.Popen([sys.executable,'child.py'])\ntime.sleep(60)",
        ) as run:
            wait_for(lambda: (tmp_path / "grandchild-ready").exists())
            assert run.active_process_count() >= 3
            children = psutil.Process(run.pid).children(recursive=True)
            run.terminate(19)
            wait_for(lambda: run.active_process_count() == 0)
            wait_for(lambda: run.poll() is not None)
            assert run.poll() == 19
            assert all(not process.is_running() for process in children)
            assert unrelated.poll() is None
    finally:
        unrelated.terminate()
        unrelated.wait(timeout=5)


def test_close_cleans_active_job_and_is_idempotent(tmp_path: Path) -> None:
    run = spawn_script(tmp_path, "import time\ntime.sleep(60)")
    process = psutil.Process(run.pid)
    run.close()
    assert not process.is_running()
    run.close()
    with pytest.raises(RuntimeError, match="已关闭"):
        run.active_process_count()


def test_both_log_streams_are_bounded_and_do_not_block(tmp_path: Path) -> None:
    source = (
        "import os\n"
        "for iteration in range(512):\n"
        '    os.write(1,b"O"*16384)\n'
        '    os.write(2,b"E"*16384)\n'
    )
    with spawn_script(tmp_path, source, limit=1024) as run:
        wait_for(lambda: run.poll() is not None, timeout=15)
        assert run.poll() == 0
    assert run.logs_truncated
    assert (tmp_path / "stdout.log").read_bytes() == b"O" * 1024
    assert (tmp_path / "stderr.log").read_bytes() == b"E" * 1024


def test_supervisor_crash_closes_job_without_inherited_job_handle(tmp_path: Path) -> None:
    script = tmp_path / "task.py"
    script.write_text("import time\ntime.sleep(60)", encoding="utf-8")
    supervisor = tmp_path / "supervisor.py"
    supervisor.write_text(
        "import os,sys,time\nfrom pathlib import Path\n"
        "from autojobs_agent.windows.process import WindowsJobProcess\n"
        "root=Path(__file__).parent\n"
        "run=WindowsJobProcess.spawn(python=Path(sys.executable),entrypoint=root/'task.py',"
        "cwd=root,env=dict(os.environ),stdout_path=root/'out',stderr_path=root/'err')\n"
        "(root/'pid').write_text(str(run.pid))\ntime.sleep(60)\n",
        encoding="utf-8",
    )
    controller = subprocess.Popen(
        [sys.executable, str(supervisor)], creationflags=subprocess.CREATE_NO_WINDOW
    )
    owned_process: psutil.Process | None = None
    try:
        wait_for(lambda: (tmp_path / "pid").exists())
        owned_process = psutil.Process(int((tmp_path / "pid").read_text()))
        controller.terminate()
        controller.wait(timeout=5)
        wait_for(lambda: not owned_process.is_running())
    finally:
        if controller.poll() is None:
            controller.terminate()
            controller.wait(timeout=5)
        if owned_process is not None and owned_process.is_running():
            owned_process.kill()
            owned_process.wait(timeout=5)


def test_assignment_failure_never_runs_user_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import autojobs_agent.windows.process as module

    captured: list[psutil.Process] = []

    def fail_assignment(job: Any, handle: Any) -> None:
        captured.append(psutil.Process(module.win32process.GetProcessId(handle)))
        raise OSError("测试注入的 Job 分配失败")

    monkeypatch.setattr(module.win32job, "AssignProcessToJobObject", fail_assignment)
    with pytest.raises(OSError, match="测试注入"):
        spawn_script(tmp_path, "from pathlib import Path\nPath('must-not-run').write_text('bad')")
    assert len(captured) == 1
    assert not captured[0].is_running()
    assert not (tmp_path / "must-not-run").exists()


def test_spawn_cleanup_does_not_accumulate_handles(tmp_path: Path) -> None:
    current = psutil.Process()
    gc.collect()
    before = current.num_handles()
    for index in range(10):
        folder = tmp_path / str(index)
        folder.mkdir()
        with spawn_script(folder, "raise SystemExit(0)") as run:
            wait_for(lambda: run.poll() is not None)
    gc.collect()
    assert current.num_handles() <= before + 2


@pytest.mark.parametrize("invalid", [0, -1, True, 67108865])
def test_invalid_log_limit_rejected(tmp_path: Path, invalid: int) -> None:
    with pytest.raises(ValueError, match="日志流限额"):
        spawn_script(tmp_path, "raise SystemExit(0)", limit=invalid)


def test_existing_log_is_not_overwritten(tmp_path: Path) -> None:
    (tmp_path / "stdout.log").write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError):
        spawn_script(tmp_path, "raise SystemExit(0)")
    assert (tmp_path / "stdout.log").read_text() == "keep"


def test_resume_failure_cleans_suspended_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import autojobs_agent.windows.process as module

    captured: list[psutil.Process] = []
    original_create = module.create_suspended

    def capture_creation(*args: Any) -> tuple[int, int, int]:
        result = original_create(*args)
        captured.append(psutil.Process(result[2]))
        return result

    def fail_resume(handle: int) -> None:
        raise OSError("测试注入的线程恢复失败")

    monkeypatch.setattr(module, "create_suspended", capture_creation)
    monkeypatch.setattr(module.win32process, "ResumeThread", fail_resume)
    with pytest.raises(OSError, match="测试注入"):
        spawn_script(tmp_path, "from pathlib import Path\nPath('must-not-run').write_text('bad')")
    assert len(captured) == 1
    wait_for(lambda: not captured[0].is_running())
    assert not (tmp_path / "must-not-run").exists()


def test_native_create_failure_cleans_pipe_handles(tmp_path: Path) -> None:
    executable = tmp_path / "not-python.exe"
    executable.write_bytes(b"not an executable")
    script = tmp_path / "never-run.py"
    script.write_text("raise SystemExit(0)", encoding="utf-8")
    gc.collect()
    before = psutil.Process().num_handles()
    with pytest.raises(OSError):
        WindowsJobProcess.spawn(
            python=executable,
            entrypoint=script,
            cwd=tmp_path,
            env=dict(os.environ),
            stdout_path=tmp_path / "out",
            stderr_path=tmp_path / "err",
        )
    gc.collect()
    assert psutil.Process().num_handles() <= before + 2


@pytest.mark.parametrize("stage", ["creation_time", "capture_start", "resume"])
def test_assigned_spawn_failure_requires_job_and_process_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    import autojobs_agent.windows.process as module

    startup_error = OSError(f"测试注入的 {stage} 启动失败")
    confirmed: list[str] = []
    created: list[psutil.Process] = []
    original_create = module.create_suspended
    original_query = module.win32job.QueryInformationJobObject
    original_wait = module.win32event.WaitForSingleObject
    original_capture_start = module._Capture.start

    def capture_creation(*args: Any) -> tuple[int, int, int]:
        result = original_create(*args)
        created.append(psutil.Process(result[2]))
        return result

    def query_job(handle: int, information: int) -> Any:
        result = original_query(handle, information)
        if information == module.win32job.JobObjectBasicAccountingInformation:
            if result["ActiveProcesses"] == 0:
                confirmed.append("job_empty")
        return result

    def wait_process(handle: int, timeout: int) -> int:
        result = original_wait(handle, timeout)
        if timeout == 5000 and result == module.win32event.WAIT_OBJECT_0:
            confirmed.append("process_signaled")
        return result

    def fail_native(handle: int) -> None:
        raise startup_error

    def fail_capture(capture: Any) -> None:
        original_capture_start(capture)
        raise startup_error

    monkeypatch.setattr(module, "create_suspended", capture_creation)
    monkeypatch.setattr(module.win32job, "QueryInformationJobObject", query_job)
    monkeypatch.setattr(module.win32event, "WaitForSingleObject", wait_process)
    if stage == "creation_time":
        monkeypatch.setattr(module.win32process, "GetProcessTimes", fail_native)
    elif stage == "capture_start":
        monkeypatch.setattr(module._Capture, "start", fail_capture)
    else:
        monkeypatch.setattr(module.win32process, "ResumeThread", fail_native)

    with pytest.raises(OSError) as raised:
        spawn_script(tmp_path, "from pathlib import Path\nPath('must-not-run').write_text('bad')")
    assert raised.value is startup_error
    assert confirmed == ["job_empty", "process_signaled"]
    assert len(created) == 1
    assert not created[0].is_running()
    assert not (tmp_path / "must-not-run").exists()


@pytest.mark.parametrize("cleanup_stage", ["terminate_job", "query_job", "wait_process"])
def test_assigned_spawn_cleanup_uncertain_is_distinct_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cleanup_stage: str
) -> None:
    import autojobs_agent.windows.process as module

    original_terminate = module.win32job.TerminateJobObject
    original_query = module.win32job.QueryInformationJobObject
    original_wait = module.win32event.WaitForSingleObject
    original_create = module.create_suspended
    created: list[psutil.Process] = []
    cleanup_error = OSError("测试注入的清理证据失败")

    def capture_creation(*args: Any) -> tuple[int, int, int]:
        result = original_create(*args)
        created.append(psutil.Process(result[2]))
        return result

    def fail_start(handle: int) -> None:
        raise OSError("测试注入的启动失败")

    def terminate_job(handle: int, code: int) -> None:
        original_terminate(handle, code)
        if cleanup_stage == "terminate_job":
            raise cleanup_error

    def query_job(handle: int, information: int) -> Any:
        if (
            cleanup_stage == "query_job"
            and information == module.win32job.JobObjectBasicAccountingInformation
        ):
            raise cleanup_error
        return original_query(handle, information)

    def wait_process(handle: int, timeout: int) -> int:
        result = original_wait(handle, timeout)
        if cleanup_stage == "wait_process" and timeout == 5000:
            # 本轮已真实停止，只注入“调用方无法得到确认”的外部边界。
            return module.win32event.WAIT_TIMEOUT
        return result

    monkeypatch.setattr(module, "create_suspended", capture_creation)
    monkeypatch.setattr(module.win32process, "GetProcessTimes", fail_start)
    monkeypatch.setattr(module.win32job, "TerminateJobObject", terminate_job)
    monkeypatch.setattr(module.win32job, "QueryInformationJobObject", query_job)
    monkeypatch.setattr(module.win32event, "WaitForSingleObject", wait_process)
    with pytest.raises(ProcessCleanupError) as raised:
        spawn_script(tmp_path, "raise SystemExit(0)")
    assert raised.value.__cause__ is not None
    assert len(created) == 1
    assert not created[0].is_running()


def test_unassigned_terminate_error_is_cleanup_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import autojobs_agent.windows.process as module

    original_terminate = module.win32process.TerminateProcess
    created: list[psutil.Process] = []

    def fail_assignment(job: int, handle: int) -> None:
        created.append(psutil.Process(module.win32process.GetProcessId(handle)))
        raise OSError("测试注入的分配失败")

    def terminate_then_fail(handle: int, code: int) -> None:
        original_terminate(handle, code)
        raise OSError("测试注入的 TerminateProcess 错误")

    monkeypatch.setattr(module.win32job, "AssignProcessToJobObject", fail_assignment)
    monkeypatch.setattr(module.win32process, "TerminateProcess", terminate_then_fail)
    with pytest.raises(ProcessCleanupError) as raised:
        spawn_script(tmp_path, "raise SystemExit(0)")
    cause = raised.value.__cause__
    assert isinstance(cause, ProcessCleanupError)
    assert isinstance(cause.__cause__, OSError)
    assert "TerminateProcess" in str(cause.__cause__)
    assert len(created) == 1
    assert not created[0].is_running()


def test_close_wraps_resource_error_and_repeated_close_stays_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import autojobs_agent.windows.process as module

    run = spawn_script(tmp_path, "import time\ntime.sleep(60)")
    created = psutil.Process(run.pid)
    original_close = module._SpawnResources.close
    cleanup_error = OSError("测试注入的句柄关闭错误")

    def close_then_fail(resources: Any) -> None:
        original_close(resources)
        raise cleanup_error

    monkeypatch.setattr(module._SpawnResources, "close", close_then_fail)
    with pytest.raises(ProcessCleanupError) as first:
        run.close()
    assert first.value.__cause__ is cleanup_error
    assert not created.is_running()
    with pytest.raises(ProcessCleanupError, match="上次") as second:
        run.close()
    assert second.value.__cause__ is cleanup_error
