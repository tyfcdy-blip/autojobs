from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from autojobs_agent.contracts import (
    MAX_RESULT_BYTES,
    ProtocolError,
    load_request,
    load_result,
    parse_json,
    require_plain_path,
)
from autojobs_agent.script_sdk import cancellation_requested, write_result


def test_manifest_uses_explicit_interpreter_and_default_runtime(tmp_path: Path) -> None:
    (tmp_path / "入口.py").write_text("pass\n", encoding="utf-8")
    manifest = tmp_path / "task.json"
    manifest.write_text(json.dumps({"task_id": "report", "python": sys.executable,
                                   "entrypoint": "入口.py", "queue_timeout_seconds": 60}), encoding="utf-8")
    request = load_request(manifest, "run-001")
    assert request.manifest.timeout_seconds == 86_400
    assert request.manifest.python == sys.executable
    assert request.entrypoint_path() == tmp_path / "入口.py"


@pytest.mark.parametrize("payload", [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}',
                                     b'{"a":1e999}', b'{"a":', b'"\xff"', b'"\\ud800"'])
def test_invalid_json_is_rejected(payload: bytes) -> None:
    with pytest.raises(ProtocolError, match="JSON"):
        parse_json(payload, limit=100)


@pytest.mark.parametrize("field,value", [("entrypoint", "../outside.py"),
                                         ("python", "python.exe"),
                                         ("queue_timeout_seconds", 0),
                                         ("timeout_seconds", True),
                                         ("requirements", ["package @ https://example.invalid/a.whl"])])
def test_unsafe_manifest_rejected(tmp_path: Path, field: str, value: object) -> None:
    contents = {"task_id": "test", "python": sys.executable, "entrypoint": "run.py",
                "queue_timeout_seconds": 5}
    contents[field] = value  # type: ignore[assignment]
    path = tmp_path / "task.json"
    path.write_text(json.dumps(contents), encoding="utf-8")
    with pytest.raises(ProtocolError):
        load_request(path, "run-001")


def test_sdk_result_roundtrip_and_cancel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "result.json"
    cancel = tmp_path / "cancel.flag"
    monkeypatch.setenv("AUTOJOBS_RUN_ID", "run-001")
    monkeypatch.setenv("AUTOJOBS_RESULT_PATH", str(target))
    monkeypatch.setenv("AUTOJOBS_CANCEL_PATH", str(cancel))
    assert not cancellation_requested()
    cancel.touch()
    assert cancellation_requested()
    write_result("failed", "登录失效", {"partial": 1}, error={"code": "LOGIN_REQUIRED"})
    response = load_result(target, "run-001")
    assert response.result == {"partial": 1}
    assert response.status == "failed"
    assert not list(tmp_path.glob(".result-*"))
    with pytest.raises(ProtocolError, match="标识"):
        load_result(target, "another-run")


@pytest.mark.parametrize("value", [None, [], "完成", 7, False, {"result": [1, None]}])
def test_result_supports_any_json_value(tmp_path: Path, value: object) -> None:
    target = tmp_path / "result.json"
    target.write_text(json.dumps({"protocol_version": "0.1", "run_id": "run-1", "status": "success",
                                  "message": "完成", "result": value}), encoding="utf-8")
    assert load_result(target, "run-1").result == value


def test_result_size_is_bounded(tmp_path: Path) -> None:
    target = tmp_path / "result.json"
    target.write_bytes(b" " * (MAX_RESULT_BYTES + 1))
    with pytest.raises(ProtocolError) as caught:
        load_result(target, "run-1")
    assert caught.value.code == "PAYLOAD_TOO_LARGE"


@pytest.mark.windows
def test_dangling_junction_parent_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "target"
    junction = tmp_path / "junction"
    target.mkdir()
    subprocess.run(["cmd", "/d", "/c", "mklink", "/J", str(junction), str(target)],
                   check=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    target.rmdir()
    try:
        assert not junction.exists() and junction.is_junction()
        with pytest.raises(ProtocolError) as caught:
            require_plain_path(junction / "new-state")
        assert caught.value.code == "UNSAFE_PATH"
        assert not target.exists()
    finally:
        junction.rmdir()
