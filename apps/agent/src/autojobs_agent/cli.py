"""本机验证命令；没有远程终端、云端连接或生产任务的隐式启动。"""

from __future__ import annotations

import argparse
import io
import json
import signal
import sqlite3
import sys
import threading
import uuid
from pathlib import Path
from typing import Any

from autojobs_agent.contracts import ProtocolError, load_request, require_plain_path
from autojobs_agent.journal import Journal, JournalError
from autojobs_agent.status import StatusReader


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="autojobs 本地执行验证；尚未连接云端中台。")
    parser.add_argument("--state-dir", type=Path, required=True, help="本地运行账本和输出目录")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="启动本机常驻执行程序")
    serve.add_argument("--once", action="store_true", help="只尝试执行一轮后退出")
    submit = commands.add_parser("submit", help="提交已信任的本地任务声明")
    submit.add_argument("manifest", type=Path)
    submit.add_argument("--run-id", default=None)
    inspect = commands.add_parser("check", help="只读检查指定任务环境，不安装")
    inspect.add_argument("manifest", type=Path)
    stop = commands.add_parser("stop", help="取消排队或请求停止指定轮次")
    stop.add_argument("run_id")
    show = commands.add_parser("show", help="查看一轮的完整记录")
    show.add_argument("run_id")
    commands.add_parser("status", help="读取本机状态，不创建账本")
    commands.add_parser("window", help="打开独立只读窗口，关闭不影响 worker")
    events = commands.add_parser("events", help="查看待回传事件；不伪装云端已接收")
    events.add_argument("--limit", type=int, default=100)
    return parser


def _print(contents: Any) -> None:
    print(json.dumps(contents, ensure_ascii=False, indent=2, allow_nan=False))


def _serve(state_dir: Path, once: bool) -> None:
    from autojobs_agent.runtime import Worker

    stopped = threading.Event()

    def stop_handler(signum: int, frame: Any) -> None:
        stopped.set()

    previous = signal.signal(signal.SIGINT, stop_handler)
    try:
        Worker(state_dir).serve(once=once, stop_event=stopped)
    finally:
        signal.signal(signal.SIGINT, previous)


def main(argv: list[str] | None = None) -> int:
    # Windows 重定向管道默认可能使用本地代码页；CLI 与协议始终输出 UTF-8。
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")
    options = _parser().parse_args(argv)
    try:
        state_dir = require_plain_path(options.state_dir)
        if options.command == "status":
            _print(StatusReader(state_dir).get_status())
        elif options.command == "window":
            from autojobs_agent.desktop import open_window

            open_window(state_dir)
        elif options.command == "serve":
            _serve(state_dir, options.once)
        elif options.command == "check":
            from autojobs_agent.environment import inspect_environment

            result = inspect_environment(load_request(options.manifest, "environment-check"))
            _print(result)
            return 0 if result["ready"] else 2
        else:
            readonly = options.command in {"show", "events"}
            journal = Journal(require_plain_path(state_dir / "journal.sqlite3"), read_only=readonly)
            if options.command == "submit":
                request = load_request(options.manifest, options.run_id or str(uuid.uuid4()))
                record = journal.enqueue(run_id=request.run_id, task_id=request.manifest.task_id,
                                         request=request.model_dump(),
                                         queue_timeout_seconds=request.manifest.queue_timeout_seconds)
                _print(record)
            elif options.command == "stop":
                _print(journal.request_stop(options.run_id))
            elif options.command == "show":
                _print(journal.get(options.run_id))
            elif options.command == "events":
                _print(journal.pending_events(options.limit))
        return 0
    except (ProtocolError, JournalError, OSError, RuntimeError, sqlite3.Error) as exc:
        message = str(exc) if isinstance(exc, (ProtocolError, JournalError, RuntimeError)) else f"本地操作失败（{type(exc).__name__}）。"
        print(json.dumps({"error": type(exc).__name__, "message": message}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
