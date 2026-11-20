from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import psutil
import pytest

from autojobs_agent.contracts import load_request
from autojobs_agent.environment import inspect_environment
from autojobs_agent.journal import Journal
from autojobs_agent.runtime import Worker, run_directory
from autojobs_agent.status import StatusReader
from autojobs_agent.windows.process import WindowsJobProcess

pytestmark = [pytest.mark.windows, pytest.mark.integration]


def submit(
    tmp_path: Path, body: str, *, run_id: str = "run-1", timeout: float = 10,
    queue_timeout: float = 60, requirements: list[str] | None = None,
) -> tuple[Path, Journal]:
    task_dir = tmp_path / f"任务 with spaces {run_id}"
    task_dir.mkdir()
    (task_dir / "task.py").write_text(body, encoding="utf-8")
    manifest = task_dir / "task.json"
    manifest.write_text(json.dumps({
        "task_id": "local-test", "python": sys.executable, "entrypoint": "task.py",
        "queue_timeout_seconds": queue_timeout, "timeout_seconds": timeout,
        "stop_grace_seconds": 0.1, "requirements": requirements or [],
    }), encoding="utf-8")
    request = load_request(manifest, run_id)
    state = tmp_path / "state"
    journal = Journal(state / "journal.sqlite3")
    journal.enqueue(run_id=run_id, task_id=request.manifest.task_id, request=request.model_dump(),
                    queue_timeout_seconds=request.manifest.queue_timeout_seconds)
    return state, journal


def wait_for(predicate: object, seconds: float = 10) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():  # type: ignore[operator]
            return
        time.sleep(0.025)
    raise AssertionError("状态未在测试时限内达到")


@pytest.mark.parametrize("body,expected,error_code", [
    ("from autojobs_agent.script_sdk import write_result\nwrite_result('success','完成',{'rows':3})\n", "succeeded", None),
    ("from autojobs_agent.script_sdk import write_result\nwrite_result('failed','业务失败',False)\n", "failed", "BUSINESS_FAILED"),
    ("from autojobs_agent.script_sdk import write_result\nwrite_result('success','完成')\nraise SystemExit(3)\n", "failed", "RESULT_EXIT_CONFLICT"),
    ("print('没有报错也没有业务结果')\n", "failed", "FILE_MISSING"),
    ("import os\nfrom pathlib import Path\nPath(os.environ['AUTOJOBS_RESULT_PATH']).write_text('invalid')\n", "failed", "INVALID_JSON"),
])
def test_real_execution_outcomes(tmp_path: Path, body: str, expected: str, error_code: str | None) -> None:
    state, journal = submit(tmp_path, body)
    Worker(state).serve(once=True)
    record = journal.get("run-1")
    assert record["state"] == expected
    assert record["error_code"] == error_code
    assert journal.active_run() is None
    assert record["pid"] is not None
    assert record["finished_at"] >= record["started_at"]
    assert journal.pending_event_count() == 4


def test_timeout_waits_for_owned_child_and_preserves_result(tmp_path: Path) -> None:
    body = """import subprocess, sys
from autojobs_agent.script_sdk import write_result
subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
write_result('success', '入口完成，但自有子进程仍运行')
"""
    state, journal = submit(tmp_path, body, timeout=0.4)
    Worker(state, poll_seconds=0.02).serve(once=True)
    record = journal.get("run-1")
    assert record["state"] == "timed_out"
    assert record["result"]["status"] == "success"
    assert journal.active_run() is None


def test_manual_stop_and_sequential_next_run(tmp_path: Path) -> None:
    state, journal = submit(tmp_path, "import time\ntime.sleep(30)\n")
    submit(tmp_path, "from autojobs_agent.script_sdk import write_result\nwrite_result('success','下一轮完成')\n", run_id="run-2")
    stop = threading.Event()
    thread = threading.Thread(target=lambda: Worker(state).serve(stop_event=stop))
    thread.start()
    try:
        wait_for(lambda: journal.get("run-1")["state"] == "running")
        assert journal.get("run-2")["state"] == "queued"
        journal.request_stop("run-1")
        wait_for(lambda: journal.get("run-2")["state"] == "succeeded")
        assert journal.get("run-1")["state"] == "stopped"
        assert journal.get("run-2")["started_at"] >= journal.get("run-1")["finished_at"]
    finally:
        stop.set()
        thread.join(timeout=10)
        assert not thread.is_alive()


def test_duplicate_submission_does_not_repeat_business(tmp_path: Path) -> None:
    body = """from pathlib import Path
from autojobs_agent.script_sdk import write_result
marker=Path('executions.txt')
with marker.open('a') as stream: stream.write('executed\\n')
write_result('success','完成')
"""
    state, journal = submit(tmp_path, body)
    original = journal.get("run-1")
    Worker(state).serve(once=True)
    journal.enqueue(run_id="run-1", task_id="local-test", request=original["request"], queue_timeout_seconds=60)
    Worker(state).serve(once=True)
    assert (tmp_path / "任务 with spaces run-1" / "executions.txt").read_text() == "executed\n"


def test_expired_and_cancelled_requests_never_start(tmp_path: Path) -> None:
    state, journal = submit(tmp_path, "raise AssertionError('不得执行')\n", queue_timeout=0.01)
    submit(tmp_path, "raise AssertionError('不得执行')\n", run_id="run-2")
    journal.request_stop("run-2")
    time.sleep(0.03)
    Worker(state).serve(once=True)
    assert journal.get("run-1")["state"] == "queue_expired"
    assert journal.get("run-2")["state"] == "cancelled"
    assert journal.get("run-1")["pid"] is None


def test_queue_expires_while_another_run_is_busy(tmp_path: Path) -> None:
    state, journal = submit(tmp_path, "import time\ntime.sleep(30)\n")
    stop = threading.Event()
    thread = threading.Thread(target=lambda: Worker(state).serve(stop_event=stop))
    thread.start()
    try:
        wait_for(lambda: journal.get("run-1")["state"] == "running")
        submit(tmp_path, "raise AssertionError('过期任务不能执行')\n", run_id="run-2", queue_timeout=0.15)
        wait_for(lambda: journal.get("run-2")["state"] == "queue_expired", seconds=3)
        assert journal.get("run-1")["state"] == "running"
        assert journal.get("run-2")["pid"] is None
        assert any(event["run_id"] == "run-2" and event["state"] == "queue_expired" for event in journal.pending_events())
    finally:
        stop.set()
        thread.join(timeout=10)
        assert not thread.is_alive()


def test_environment_check_reports_missing_without_installing(tmp_path: Path) -> None:
    state, journal = submit(tmp_path, "raise AssertionError('缺环境不可执行')\n",
                            requirements=["autojobs-missing-fixture-package==1.0"])
    request = load_request(tmp_path / "任务 with spaces run-1" / "task.json", "check-1")
    inspection = inspect_environment(request)
    assert inspection["ready"] is False
    assert inspection["installation_performed"] is False
    assert inspection["python"]["executable"].lower() == sys.executable.lower()
    assert any(check["component"].startswith("package:") and not check["ready"] for check in inspection["checks"])
    Worker(state).serve(once=True)
    assert journal.get("run-1")["error_code"] == "ENVIRONMENT_NOT_READY"
    assert journal.get("run-1")["pid"] is None


def test_restarted_worker_retains_unknown_slot(tmp_path: Path) -> None:
    state, journal = submit(tmp_path, "raise AssertionError('不可自动重跑')\n")
    journal.claim_next()
    submit(tmp_path, "raise AssertionError('占用未知不可执行下一轮')\n", run_id="run-2")
    Worker(state).serve(once=True)
    assert journal.get("run-1")["state"] == "reconciling"
    assert journal.get("run-2")["state"] == "queued"
    assert StatusReader(state).get_status()["worker"]["online"] is False


def test_log_output_is_bounded_and_marked(tmp_path: Path) -> None:
    body = """import sys
from autojobs_agent.script_sdk import write_result
sys.stdout.write('x' * 2000000)
write_result('success','完成')
"""
    state, journal = submit(tmp_path, body)
    Worker(state).serve(once=True)
    assert journal.get("run-1")["state"] == "succeeded"
    assert "截断" in journal.get("run-1")["message"]
    assert (run_directory(state, "run-1") / "stdout.log").stat().st_size <= 1024 * 1024


def test_real_worker_crash_cleans_owned_process_and_recovers_unknown(tmp_path: Path) -> None:
    state, journal = submit(tmp_path, "import time\ntime.sleep(30)\n")
    launcher = subprocess.Popen([sys.executable, "-m", "autojobs_agent.cli", "--state-dir", str(state), "serve"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    actual_worker: psutil.Process | None = None
    try:
        wait_for(lambda: journal.get("run-1")["state"] == "running")
        heartbeat = json.loads((state / "worker.json").read_text(encoding="utf-8"))
        actual_worker = psutil.Process(heartbeat["pid"])
        descendants = actual_worker.children(recursive=True)
        assert descendants
        actual_worker.kill()
        actual_worker.wait(timeout=5)
        _, alive = psutil.wait_procs(descendants, timeout=5)
        assert not alive
        Worker(state).serve(once=True)
        assert journal.get("run-1")["state"] == "reconciling"
    finally:
        if actual_worker is not None and actual_worker.is_running():
            actual_worker.kill()
            actual_worker.wait(timeout=5)
        if launcher.poll() is None:
            launcher.terminate()
        launcher.wait(timeout=5)


def test_worker_does_not_inherit_unrelated_credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTOJOBS_TEST_SECRET", "synthetic-only-do-not-inherit")
    state, journal = submit(tmp_path, "import os\nfrom autojobs_agent.script_sdk import write_result\nwrite_result('success','环境隔离',os.environ.get('AUTOJOBS_TEST_SECRET'))\n")
    Worker(state).serve(once=True)
    assert journal.get("run-1")["result"]["result"] is None


def test_slow_probe_keeps_heartbeat_and_expires_other_requests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import autojobs_agent.environment as environment

    state, journal = submit(tmp_path, "raise AssertionError('检查后已取消，不应启动业务')\n")
    original_probe = Path(environment.__file__).with_name("environment_probe.py")
    slow_probe = tmp_path / "slow_probe.py"
    slow_probe.write_text(f"import runpy,time\ntime.sleep(6)\nrunpy.run_path({str(original_probe)!r}, run_name='__main__')\n", encoding="utf-8")
    original_spawn = WindowsJobProcess.spawn

    def delayed_spawn(**kwargs: object) -> WindowsJobProcess:
        if kwargs["entrypoint"] == original_probe:
            kwargs["entrypoint"] = slow_probe
        return original_spawn(**kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(WindowsJobProcess, "spawn", delayed_spawn)
    stop = threading.Event()
    thread = threading.Thread(target=lambda: Worker(state).serve(stop_event=stop))
    thread.start()
    try:
        wait_for(lambda: journal.get("run-1")["state"] == "starting")
        submit(tmp_path, "raise AssertionError('排队已超时')\n", run_id="run-2", queue_timeout=0.15)
        wait_for(lambda: journal.get("run-2")["state"] == "queue_expired", seconds=2)
        time.sleep(5.1)
        assert journal.get("run-1")["state"] == "starting"
        assert StatusReader(state).get_status()["worker"]["online"] is True
    finally:
        stop.set()
        thread.join(timeout=10)
        assert not thread.is_alive()
    assert journal.get("run-1")["state"] == "cancelled"


def test_isolated_edge_browser_task(tmp_path: Path) -> None:
    candidates = [Path(os.environ.get(variable, "C:/missing")) / "Microsoft/Edge/Application/msedge.exe"
                  for variable in ("PROGRAMFILES(X86)", "PROGRAMFILES")]
    browser = next((candidate for candidate in candidates if candidate.is_file()), None)
    if browser is None:
        pytest.skip("本机未安装 Edge，真实浏览器验证需另行执行")
    body = f"""import subprocess, tempfile
from pathlib import Path
from autojobs_agent.script_sdk import write_result
with tempfile.TemporaryDirectory(prefix='autojobs-browser-') as directory:
    root = Path(directory)
    html = root / 'local.html'
    html.write_text('<h1>autojobs-isolated-browser-proof</h1>', encoding='utf-8')
    completed = subprocess.run([{str(browser)!r}, '--headless', '--disable-gpu', '--no-first-run',
        '--no-default-browser-check', '--disable-background-networking', '--disable-sync',
        '--host-resolver-rules=MAP * ~NOTFOUND', '--user-data-dir=' + str(root / 'profile'),
        '--dump-dom', html.as_uri()], capture_output=True, timeout=20)
    found = b'autojobs-isolated-browser-proof' in completed.stdout
    write_result('success' if found else 'failed', '隔离浏览器本地页面校验',
                 {{'marker_found': found, 'browser_exit_code': completed.returncode}})
"""
    state, journal = submit(tmp_path, body, timeout=30)
    Worker(state, poll_seconds=0.05).serve(once=True)
    record = journal.get("run-1")
    assert record["state"] == "succeeded", record["message"]
    assert record["result"]["result"]["marker_found"] is True
