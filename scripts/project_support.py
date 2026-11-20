"""模板工具共享的配置校验；不执行配置中登记的命令。"""

import json
import re
from pathlib import Path
from typing import Any


class ProjectError(ValueError):
    """可以直接向用户展示、不包含配置原文的错误。"""


def validate_config(config: Any) -> None:
    """校验版本 1 的完整配置，避免无效元数据被写回。"""
    if not isinstance(config, dict):
        raise ProjectError("项目配置必须是 JSON 对象。")
    expected = {"format_version", "project", "stack", "verification"}
    if set(config) != expected:
        raise ProjectError("项目配置字段必须为 format_version、project、stack、verification。")
    if type(config["format_version"]) is not int or config["format_version"] != 1:
        raise ProjectError("format_version 必须为整数 1。")
    project = config["project"]
    if not isinstance(project, dict) or set(project) != {"name", "description"}:
        raise ProjectError("project 必须包含且仅包含 name、description。")
    name = project["name"]
    if (
        not isinstance(name, str)
        or not 1 <= len(name) <= 63
        or re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", name) is None
    ):
        raise ProjectError("项目名称须为 1~63 字符，以小写字母开头，仅含小写字母、数字和单个连字符。")
    description = project["description"]
    if not isinstance(description, str) or len(description) > 500:
        raise ProjectError("项目描述必须为不超过 500 字符的字符串。")
    stack = config["stack"]
    if not isinstance(stack, dict) or set(stack) != {"backend", "frontend", "jobs"}:
        raise ProjectError("stack 必须包含且仅包含 backend、frontend、jobs。")
    for value in stack.values():
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ProjectError("技术栈取值必须为 null 或非空字符串。")
    verification = config["verification"]
    checks = {"build", "lint", "typecheck", "unit", "integration", "e2e"}
    if not isinstance(verification, dict) or set(verification) != checks:
        raise ProjectError("verification 必须包含 build、lint、typecheck、unit、integration、e2e。")
    for commands in verification.values():
        if not isinstance(commands, list) or any(
            not isinstance(command, str) or not command.strip() for command in commands
        ):
            raise ProjectError("每类验证命令必须为非空字符串组成的数组；尚未配置请使用空数组。")
    try:
        # JSON 转义可包含孤立代理字符，必须在任何写入前确认文本可编码。
        json.dumps(config, ensure_ascii=False).encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ProjectError("配置文本包含无法编码为 UTF-8 的字符。") from exc


def require_regular_file(path: Path) -> None:
    """配置输入和写入目标不接受符号链接，避免越出项目范围。"""
    if path.is_symlink() or not path.is_file():
        raise ProjectError(f"需要普通文件且不能是符号链接：{path.name}")


def load_config(path: Path) -> dict[str, Any]:
    require_regular_file(path)
    try:
        config = json.loads(path.read_text(encoding="utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ProjectError("项目配置不是有效的 UTF-8 JSON；请检查格式。") from exc
    validate_config(config)
    return config
