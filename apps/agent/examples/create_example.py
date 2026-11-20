"""为本机演示生成明确标注的测试任务；拒绝覆盖已有目录。"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="创建无网络访问的本地表格示例")
    parser.add_argument("destination", type=Path)
    options = parser.parse_args()
    destination = options.destination.absolute()
    if destination.exists() or destination.is_symlink():
        parser.error("目标已存在；请指定新的示例目录，不覆盖已有文件。")
    for parent in destination.parents:
        if parent.is_symlink() or parent.is_junction():
            parser.error("目标目录不能经过符号链接或重解析目录。")
    destination.mkdir(parents=True)
    shutil.copyfile(Path(__file__).with_name("table_summary.py"), destination / "task.py")
    (destination / "sample.csv").write_text("sample_id,label\nsample-01,本地测试一\nsample-02,本地测试二\n", encoding="utf-8")
    (destination / "task.json").write_text(json.dumps({
        "protocol_version": "0.1", "task_id": "local-table-example", "python": sys.executable,
        "entrypoint": "task.py", "queue_timeout_seconds": 600, "timeout_seconds": 60,
        "stop_grace_seconds": 2, "required_files": ["sample.csv"],
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(destination / "task.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
