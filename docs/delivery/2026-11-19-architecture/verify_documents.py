"""复核本次技术文档的文件、链接、编号与快照一致性，不验证产品能力。"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit


def main() -> int:
    root = Path(__file__).resolve().parents[3]
    delivery = Path(__file__).resolve().parent
    architecture = root / "docs/architecture"
    files = [
        root / "README.md",
        root / "docs/README.md",
        architecture / "README.md",
        root / "docs/decisions/README.md",
        root / "docs/decisions/0001-control-platform-stack.md",
        architecture / "automation-control-platform-technical-design.md",
        *sorted((architecture / "research").glob("*.md")),
        *sorted((architecture / "research").glob("*.json")),
        delivery / "plan.md",
        delivery / "report.md",
        delivery / "review.md",
        delivery / "baseline.json",
    ]
    errors: list[str] = []
    counters = {"files": 0, "local_links": 0, "json_files": 0, "json_examples": 0,
                "repository_rows": 0, "unchanged_inputs": 0}
    texts: dict[Path, str] = {}

    def require(condition: bool, message: str) -> None:
        if not condition:
            errors.append(message)

    for path in files:
        require(path.is_file(), f"缺少文件：{path.relative_to(root)}")
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeError as exc:
            errors.append(f"UTF-8 错误：{path.relative_to(root)}：{exc}")
            continue
        texts[path] = text
        counters["files"] += 1
        require(text.endswith("\n"), f"缺少末尾换行：{path.relative_to(root)}")
        require(not any(line.rstrip() != line for line in text.splitlines()),
                f"存在行尾空白：{path.relative_to(root)}")
        if path.suffix == ".json":
            try:
                json.loads(text)
                counters["json_files"] += 1
            except ValueError as exc:
                errors.append(f"JSON 错误：{path.relative_to(root)}：{exc}")
        if path.suffix != ".md":
            continue
        prose = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", prose):
            target = target.strip("<>")
            if urlsplit(target).scheme or target.startswith("#"):
                continue
            destination = path.parent / unquote(target.split("#", 1)[0])
            counters["local_links"] += 1
            require(destination.exists(), f"本地链接不存在：{path.relative_to(root)} -> {target}")
        for example in re.findall(r"```json\s*\n(.*?)```", text, flags=re.DOTALL):
            try:
                parsed = json.loads(example)
                require(parsed.get("protocol_version") == "0.1", "结果示例协议版本不一致")
                require(parsed.get("status") in {"success", "failed"}, "结果示例状态不合法")
                require("run_id" in parsed and "result" in parsed, "结果示例缺必要字段")
                counters["json_examples"] += 1
            except (ValueError, AttributeError) as exc:
                errors.append(f"JSON 示例错误：{path.relative_to(root)}：{exc}")

    design = texts.get(architecture / "automation-control-platform-technical-design.md", "")
    for prefix, count in [("R", 18), ("AC", 20), ("Q", 12)]:
        for number in range(1, count + 1):
            require(re.search(rf"\b{prefix}{number:02d}\b", design) is not None,
                    f"方案缺少编号：{prefix}{number:02d}")

    research = architecture / "research"
    components = json.loads((research / "components-github-snapshot.json").read_text(encoding="utf-8"))
    orchestration = json.loads((research / "orchestrators-github-snapshot.json").read_text(encoding="utf-8"))
    windows = json.loads((research / "windows-github-snapshot.json").read_text(encoding="utf-8"))
    groups = [
        ("components-2026-11-19.md", [(row["url"], row["stars"]) for row in components]),
        ("orchestrators-2026-11-19.md", [
            *[(row["html_url"], row["stargazers_count"]) for row in orchestration["web_api_repositories"]],
            *[(row["resolved_url"], row["stargazers_count"]) for row in orchestration["html_fallback"]
              if row["requested_repository"] != "xxl-job/xxl-job"],
        ]),
        ("windows-agent-2026-11-19.md", [(row["html_url"], row["stargazers_count"])
                                       for row in windows["repositories"]]),
    ]
    for document, rows in groups:
        content = texts.get(research / document, "")
        for url, stars in rows:
            require(isinstance(stars, int) and stars > 0, f"Star 数无效：{url}")
            matching_rows = [line for line in content.splitlines() if line.startswith("|") and url in line]
            require(any(f"{stars:,}" in line for line in matching_rows), f"表格与快照不一致：{url}")
            counters["repository_rows"] += 1

    baseline = json.loads((delivery / "baseline.json").read_text(encoding="utf-8"))
    unchanged = {"AGENTS.md", "project.config.json", "docs/product/automation-control-platform-prd.md",
                 "docs/standards/script-integration.md"}
    for record in baseline:
        if record["path"] in unchanged:
            current_hash = hashlib.sha256((root / record["path"]).read_bytes()).hexdigest()
            require(current_hash == record["sha256"], f"范围外输入被修改：{record['path']}")
            counters["unchanged_inputs"] += 1

    result = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version.split()[0],
        "scope": "技术文档静态检查；不是产品功能测试",
        "counts": counters,
        "errors": errors,
        "exit_code": 1 if errors else 0,
    }
    (delivery / "verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
