from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_cli_outputs_utf8_json_and_does_not_create_status_directory(tmp_path: Path) -> None:
    state = tmp_path / "missing"
    completed = subprocess.run([sys.executable, "-m", "autojobs_agent.cli", "--state-dir", str(state), "status"],
                               capture_output=True, timeout=10)
    assert completed.returncode == 0
    result = json.loads(completed.stdout.decode("utf-8"))
    assert result["runs"] == []
    assert not state.exists()


def test_invalid_manifest_cli_error_is_valid_utf8(tmp_path: Path) -> None:
    manifest = tmp_path / "invalid.json"
    manifest.write_text('{"task_id":"invalid"}', encoding="utf-8")
    completed = subprocess.run([sys.executable, "-m", "autojobs_agent.cli", "--state-dir", str(tmp_path / "state"),
                                "submit", str(manifest)], capture_output=True, timeout=10)
    assert completed.returncode == 2
    error = json.loads(completed.stderr.decode("utf-8"))
    assert "字段无效" in error["message"]
