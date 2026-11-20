"""执行请求与结果边界；业务成功必须来自本轮合法结果。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any, Literal

from packaging.requirements import InvalidRequirement, Requirement
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

MAX_RESULT_BYTES = 1024 * 1024
MAX_MANIFEST_BYTES = 64 * 1024
Identifier = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")]


class ProtocolError(ValueError):
    """不含输入原文的可展示错误。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, value in pairs:
        if name in result:
            raise ProtocolError("INVALID_JSON", "JSON 不允许重复字段。")
        result[name] = value
    return result


def _reject_constant(value: str) -> None:
    raise ProtocolError("INVALID_JSON", "JSON 不允许 NaN 或 Infinity。")


def parse_json(payload: bytes, *, limit: int) -> Any:
    if len(payload) > limit:
        raise ProtocolError("PAYLOAD_TOO_LARGE", "内容超过允许大小。")
    try:
        decoded = json.loads(
            payload.decode("utf-8"), object_pairs_hook=_unique_object, parse_constant=_reject_constant
        )
        # 1e999 会被标准解析器转为 Infinity，序列化复检同时约束深度与编码。
        json.dumps(decoded, allow_nan=False, ensure_ascii=False).encode("utf-8")
        return decoded
    except (UnicodeError, ValueError, RecursionError) as exc:
        if isinstance(exc, ProtocolError):
            raise
        raise ProtocolError("INVALID_JSON", "内容不是受支持的 UTF-8 JSON。") from exc


def require_plain_path(path: Path) -> Path:
    """拒绝路径上的链接和重解析点，避免状态/入口被重定向至其他位置。"""
    absolute = path.absolute()
    for component in [absolute, *absolute.parents]:
        if component.is_symlink() or component.is_junction():
            raise ProtocolError("UNSAFE_PATH", "路径不能包含符号链接或重解析目录。")
        try:
            metadata = component.lstat()
        except FileNotFoundError:
            continue
        if getattr(metadata, "st_file_attributes", 0) & 0x400:
            raise ProtocolError("UNSAFE_PATH", "路径不能包含 Windows 重解析点。")
    return absolute.resolve()


def read_json_file(path: Path, *, limit: int) -> Any:
    source = require_plain_path(path)
    if not source.is_file():
        raise ProtocolError("FILE_MISSING", "指定文件不存在或不是普通文件。")
    with source.open("rb") as stream:
        payload = stream.read(limit + 1)
    return parse_json(payload, limit=limit)


class TaskManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    protocol_version: Literal["0.1"] = "0.1"
    task_id: Identifier
    python: str = Field(min_length=1, max_length=2048)
    entrypoint: str = Field(min_length=1, max_length=512)
    queue_timeout_seconds: float = Field(gt=0, le=31_536_000, allow_inf_nan=False)
    timeout_seconds: float = Field(default=86_400, gt=0, le=31_536_000, allow_inf_nan=False)
    stop_grace_seconds: float = Field(default=10, ge=0, le=300, allow_inf_nan=False)
    requirements: list[str] = Field(default_factory=list, max_length=256)
    required_files: list[str] = Field(default_factory=list, max_length=256)
    browser_executable: str | None = Field(default=None, max_length=2048)

    @field_validator("entrypoint")
    @classmethod
    def validate_entrypoint(cls, value: str) -> str:
        path = Path(value)
        if path.is_absolute() or path.drive or ".." in path.parts or ":" in value:
            raise ValueError("入口必须是任务目录内的相对 Python 文件。")
        if path.suffix.lower() != ".py":
            raise ValueError("入口必须是 Python 文件。")
        return value

    @field_validator("python", "browser_executable")
    @classmethod
    def validate_executable_path(cls, value: str | None) -> str | None:
        if value is not None and not Path(value).is_absolute():
            raise ValueError("解释器和浏览器必须使用绝对路径。")
        return value

    @field_validator("requirements")
    @classmethod
    def validate_requirements(cls, values: list[str]) -> list[str]:
        for value in values:
            try:
                requirement = Requirement(value)
            except InvalidRequirement as exc:
                raise ValueError("依赖声明必须符合 PEP 508。") from exc
            if requirement.url or requirement.extras:
                raise ValueError("当前只读检查不接受 URL 或 extras 依赖声明。")
        return values

    @field_validator("required_files")
    @classmethod
    def validate_files(cls, values: list[str]) -> list[str]:
        if any(not value.strip() or len(value) > 2048 or "\x00" in value for value in values):
            raise ValueError("固定文件路径无效。")
        return values


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    run_id: Identifier
    task_root: str
    manifest: TaskManifest

    @field_validator("task_root")
    @classmethod
    def validate_task_root(cls, value: str) -> str:
        if not Path(value).is_absolute():
            raise ValueError("任务目录必须是绝对路径。")
        return value

    def entrypoint_path(self) -> Path:
        root = require_plain_path(Path(self.task_root))
        entry = require_plain_path(root / self.manifest.entrypoint)
        if not entry.is_relative_to(root) or not entry.is_file():
            raise ProtocolError("INVALID_ENTRYPOINT", "入口不存在或超出任务目录。")
        return entry


class ScriptResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    protocol_version: Literal["0.1"]
    run_id: Identifier
    status: Literal["success", "failed"]
    message: str = Field(min_length=1, max_length=4096)
    result: Any
    error: dict[str, Any] | None = None

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("结果说明不能为空。")
        return value


def load_request(manifest_path: Path, run_id: str) -> RunRequest:
    source = require_plain_path(manifest_path)
    payload = read_json_file(source, limit=MAX_MANIFEST_BYTES)
    try:
        manifest = TaskManifest.model_validate(payload)
        request = RunRequest(run_id=run_id, task_root=str(source.parent), manifest=manifest)
        request.entrypoint_path()
        return request
    except ValidationError as exc:
        fields = ", ".join(sorted({str(error["loc"][0]) for error in exc.errors() if error["loc"]}))
        raise ProtocolError("INVALID_MANIFEST", f"任务声明字段无效：{fields}。") from exc


def load_result(path: Path, run_id: str) -> ScriptResult:
    try:
        result = ScriptResult.model_validate(read_json_file(path, limit=MAX_RESULT_BYTES))
    except ValidationError as exc:
        raise ProtocolError("INVALID_RESULT", "最终结果字段不符合 0.1 协议。") from exc
    if result.run_id != run_id:
        raise ProtocolError("RUN_ID_MISMATCH", "结果与本轮运行标识不一致。")
    return result
