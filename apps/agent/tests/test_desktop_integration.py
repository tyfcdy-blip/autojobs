from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

import pytest

from autojobs_agent.contracts import load_request
from autojobs_agent.environment import child_environment
from autojobs_agent.journal import Journal
from autojobs_agent.runtime import Worker
from autojobs_agent.windows.process import WindowsJobProcess

pytestmark = [pytest.mark.windows, pytest.mark.integration]


def test_real_webview_bridge_and_window_close_does_not_stop_worker(tmp_path: Path) -> None:
    pytest.importorskip("webview", reason="该集成验证需要 desktop 可选依赖")
    import autojobs_agent.desktop as desktop

    index = Path(desktop.__file__).with_name("desktop_assets") / "index.html"
    assert index.is_file(), "必须先构建本地 Vue 窗口"
    task = tmp_path / "task.py"
    task.write_text("import time\ntime.sleep(50)\n", encoding="utf-8")
    manifest = tmp_path / "task.json"
    manifest.write_text(json.dumps({"task_id": "desktop-bridge-proof", "python": sys.executable,
                                   "entrypoint": "task.py", "queue_timeout_seconds": 60,
                                   "timeout_seconds": 60, "stop_grace_seconds": 0}), encoding="utf-8")
    request = load_request(manifest, "desktop-run-001")
    state = tmp_path / "state"
    journal = Journal(state / "journal.sqlite3")
    journal.enqueue(run_id=request.run_id, task_id=request.manifest.task_id,
                    request=request.model_dump(), queue_timeout_seconds=60)
    stop = threading.Event()
    worker_thread = threading.Thread(target=lambda: Worker(state).serve(stop_event=stop))
    worker_thread.start()
    host = tmp_path / "window_host.py"
    proof = tmp_path / "window-proof.json"
    host.write_text(f"""import json, time
from pathlib import Path
import webview
from autojobs_agent.desktop import StatusBridge
window = webview.create_window('autojobs UI test', url={str(index)!r},
    js_api=StatusBridge(Path({str(state)!r})), width=1120, height=780, hidden=True)
def inspect_window():
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            body = window.evaluate_js('document.body.innerText') or ''
            if 'desktop-bridge-proof' in body and '运行中' in body:
                Path({str(proof)!r}).write_text(json.dumps({{'rendered': True, 'real_bridge': True}}), encoding='utf-8')
                return
            time.sleep(0.2)
        Path({str(proof)!r}).write_text(json.dumps({{'rendered': False, 'body': body}}), encoding='utf-8')
    finally:
        window.destroy()
webview.start(inspect_window, gui='edgechromium', debug=False)
""", encoding="utf-8")
    process: WindowsJobProcess | None = None
    try:
        deadline = time.monotonic() + 10
        while journal.get(request.run_id)["state"] != "running" and time.monotonic() < deadline:
            time.sleep(0.05)
        assert journal.get(request.run_id)["state"] == "running"
        process = WindowsJobProcess.spawn(python=Path(sys.executable), entrypoint=host, cwd=tmp_path,
                                          env=child_environment(), stdout_path=tmp_path / "ui-out.log",
                                          stderr_path=tmp_path / "ui-error.log")
        deadline = time.monotonic() + 30
        while process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.1)
        assert process.poll() == 0, (tmp_path / "ui-error.log").read_text(encoding="utf-8")
        process.close()
        process = None
        assert json.loads(proof.read_text(encoding="utf-8"))["rendered"] is True
        assert worker_thread.is_alive()
        assert journal.get(request.run_id)["state"] == "running"
    finally:
        if process is not None:
            process.close()
        stop.set()
        worker_thread.join(timeout=10)
        assert not worker_thread.is_alive()
