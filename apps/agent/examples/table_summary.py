"""本地无外部调用示例：读取自带测试 CSV，把实际行数返回执行端。"""

import csv
from pathlib import Path

from autojobs_agent.script_sdk import write_result


def main() -> None:
    with Path("sample.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    write_result("success", "本地示例表格读取完成", {"processed_rows": len(rows), "source": "sample.csv"})


if __name__ == "__main__":
    main()
