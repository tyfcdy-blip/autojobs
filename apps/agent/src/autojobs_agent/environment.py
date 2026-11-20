"""只读检查声明环境；检查过程不创建 venv、不下载或安装业务依赖。"""

from __future__ import annotations

import json
import os
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from packaging.requirements import Requirement

from autojobs_agent.contracts import ProtocolError, RunRequest, parse_json, require_plain_path
from autojobs_agent.windows.process import ProcessCleanupError, WindowsJobProcess


def child_environment() -> dict[str, str]:
    # 不把宿主的 API 密钥、代理认证和其他无关变量继承给业务进程。
    allowed = {
        "SYSTEMROOT", "WINDIR", "COMSPEC", "PATH", "TEMP", "TMP", "USERPROFILE",
        "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "PROGRAMFILES", "PROGRAMFILES(X86)",
        "ALLUSERSPROFILE", "OS", "PROCESSOR_ARCHITECTURE", "NUMBER_OF_PROCESSORS",
    }
    environment = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    environment.update(PYTHONIOENCODING="utf-8", PYTHONUTF8="1", PYTHONNOUSERSITE="1")
    return environment


def _probe_python(
    python: Path, requirements: list[Requirement], on_poll: Callable[[], None] | None = None,
) -> dict[str, Any]:
    environment = child_environment()
    environment["AUTOJOBS_PROBE_PACKAGES"] = json.dumps([req.name for req in requirements])
    with tempfile.TemporaryDirectory(prefix="autojobs-probe-") as directory:
        temporary = Path(directory)
        stdout = temporary / "stdout.log"
        process = WindowsJobProcess.spawn(
            python=python, entrypoint=Path(__file__).with_name("environment_probe.py"),
            cwd=temporary, env=environment, stdout_path=stdout,
            stderr_path=temporary / "stderr.log", log_limit_bytes=65_536,
        )
        try:
            deadline = time.monotonic() + 10
            while process.poll() is None or process.active_process_count() > 0:
                if on_poll is not None:
                    on_poll()
                if time.monotonic() >= deadline:
                    process.terminate()
                    raise ProtocolError("PYTHON_PROBE_TIMEOUT", "指定 Python 的环境检查超时。")
                time.sleep(0.02)
            if process.poll() != 0:
                raise ProtocolError("PYTHON_PROBE_FAILED", "指定 Python 无法完成环境检查。")
        finally:
            try:
                process.close()
            except Exception as exc:
                raise ProcessCleanupError("环境检查进程资源尚未确认清理。") from exc
        response = parse_json(stdout.read_bytes(), limit=65_536)
        if not isinstance(response, dict) or not isinstance(response.get("packages"), dict):
            raise ProtocolError("PYTHON_PROBE_FAILED", "指定程序未返回有效的 Python 环境信息。")
        return response


def inspect_environment(
    request: RunRequest, *, on_poll: Callable[[], None] | None = None,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    python = require_plain_path(Path(request.manifest.python))
    python_metadata: dict[str, Any] | None = None
    checks.append({"component": "entrypoint", "ready": request.entrypoint_path().is_file(),
                   "message": "任务入口存在。"})
    if not python.is_file() or python.suffix.lower() != ".exe":
        checks.append({"component": "python", "ready": False, "message": "指定 Python 可执行文件不存在。"})
    else:
        requirements = [Requirement(value) for value in request.manifest.requirements]
        try:
            python_metadata = _probe_python(python, requirements, on_poll)
            checks.append({"component": "python", "ready": True,
                           "message": f"Python {python_metadata['version']} ({python_metadata['architecture']})"})
            for requirement in requirements:
                if requirement.marker and not requirement.marker.evaluate(python_metadata["markers"]):
                    continue
                installed = python_metadata["packages"].get(requirement.name)
                ready = bool(installed is not None and requirement.specifier.contains(installed))
                checks.append({"component": f"package:{requirement.name}", "ready": ready,
                               "message": f"要求 {requirement}；实际 {installed or '未安装'}。"})
        except (ProtocolError, OSError) as exc:
            checks.append({"component": "python", "ready": False,
                           "message": str(exc) if isinstance(exc, ProtocolError) else "Python 检查无法启动。"})
    for filename in request.manifest.required_files:
        declared = Path(filename)
        path = require_plain_path(declared if declared.is_absolute() else Path(request.task_root) / declared)
        checks.append({"component": "file", "ready": path.is_file(),
                       "message": f"固定文件{'存在' if path.is_file() else '缺失'}：{filename}"})
    if request.manifest.browser_executable:
        browser = require_plain_path(Path(request.manifest.browser_executable))
        checks.append({"component": "browser", "ready": browser.is_file(),
                       "message": "仅检查浏览器路径；版本匹配、登录状态和桌面会话未验证。"})
    return {"ready": all(check["ready"] for check in checks), "python": python_metadata,
            "checks": checks, "installation_performed": False,
            "unverified": ["浏览器与驱动版本匹配", "网站登录状态", "锁屏/注销/远程桌面行为"]}
