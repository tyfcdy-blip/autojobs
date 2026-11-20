"""独立状态窗口；窗口没有运行、停止或任意文件访问能力。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from autojobs_agent.status import StatusReader


class StatusBridge:
    def __init__(self, state_dir: Path) -> None:
        self._reader = StatusReader(state_dir)

    def get_status(self) -> dict[str, Any]:
        return self._reader.get_status()


def open_window(state_dir: Path) -> None:
    try:
        import webview
    except ImportError as exc:
        raise RuntimeError("未安装本机窗口组件，请安装 desktop 可选依赖。") from exc
    index = Path(__file__).with_name("desktop_assets") / "index.html"
    if not index.is_file():
        raise RuntimeError("本机页面尚未构建，请先构建 desktop-ui。")
    webview.create_window(
        "autojobs · 本机执行端", url=str(index), js_api=StatusBridge(state_dir),
        width=1120, height=780, min_size=(720, 560),
    )
    webview.start(gui="edgechromium", debug=False)
