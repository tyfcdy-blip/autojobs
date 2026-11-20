"""仅使用标准库的结果写入工具，可直接复制到业务脚本目录使用。"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Literal


def cancellation_requested() -> bool:
    """脚本自行检查取消标记，并在返回前清理其拥有的资源。"""
    marker = os.environ.get("AUTOJOBS_CANCEL_PATH")
    return bool(marker and Path(marker).is_file())


def write_result(
    status: Literal["success", "failed"],
    message: str,
    result: Any = None,
    *,
    error: dict[str, Any] | None = None,
) -> None:
    run_id = os.environ.get("AUTOJOBS_RUN_ID", "")
    target_text = os.environ.get("AUTOJOBS_RESULT_PATH", "")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", run_id):
        raise ValueError("缺少有效的本轮运行标识。")
    target = Path(target_text)
    if not target_text or not target.is_absolute() or not target.parent.is_dir():
        raise ValueError("缺少有效的本轮结果路径。")
    if status not in {"success", "failed"} or not isinstance(message, str) or not message.strip():
        raise ValueError("结果状态与说明无效。")
    if len(message) > 4096 or (error is not None and not isinstance(error, dict)):
        raise ValueError("结果说明或诊断格式无效。")
    payload = json.dumps(
        {"protocol_version": "0.1", "run_id": run_id, "status": status,
         "message": message, "result": result, "error": error},
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")
    if len(payload) > 1024 * 1024:
        raise ValueError("最终结果不能超过 1 MiB。")
    descriptor, temporary = tempfile.mkstemp(prefix=".result-", suffix=".tmp", dir=target.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, target)
    finally:
        temporary_path.unlink(missing_ok=True)
