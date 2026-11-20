"""安全初始化当前模板副本，仅使用 Python 标准库。"""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from project_support import ProjectError, load_config, require_regular_file, validate_config


def initialize(root: Path, name: str | None, description: str | None) -> list[str]:
    """预检全部输入，保护已有 .env，以原子替换更新项目配置。"""
    config_path = root / "project.config.json"
    config = load_config(config_path)
    original = json.dumps(config, ensure_ascii=False, indent=2) + "\n"
    if name is not None:
        config["project"]["name"] = name
    if description is not None:
        config["project"]["description"] = description
    validate_config(config)
    rendered = json.dumps(config, ensure_ascii=False, indent=2) + "\n"

    example_path = root / ".env.example"
    env_path = root / ".env"
    require_regular_file(example_path)
    example_bytes = example_path.read_bytes()
    if env_path.is_symlink():
        raise ProjectError(".env 不能是符号链接；未修改任何配置。")
    if env_path.exists():
        require_regular_file(env_path)

    staged_path = None
    created_env = False
    messages = []
    try:
        if rendered != original:
            # 临时文件与目标同目录，避免跨文件系统替换；旧配置在替换成功前保持完整。
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", newline="\n", dir=root,
                prefix=".project-config-", suffix=".tmp", delete=False,
            ) as staged:
                staged_path = Path(staged.name)
                staged.write(rendered)
        try:
            # 独占创建，即使预检后文件刚被创建，也不覆盖用户内容。
            with env_path.open("xb") as env_file:
                created_env = True
                env_file.write(example_bytes)
            messages.append("已创建 .env（来源：.env.example）。")
        except FileExistsError:
            require_regular_file(env_path)
            messages.append("已保留现有 .env。")
        if staged_path is not None:
            os.replace(staged_path, config_path)
            messages.append("已更新 project.config.json。")
        else:
            messages.append("项目元数据未变化。")
    except OSError:
        # 配置写入失败时撤销本次新建的环境文件；不删除原有文件。
        if created_env:
            env_path.unlink()
        raise
    finally:
        if staged_path is not None:
            staged_path.unlink(missing_ok=True)
    return messages


def main() -> int:
    parser = argparse.ArgumentParser(description="初始化脚本所在的项目；不安装依赖或执行 Git 操作。")
    parser.add_argument("--name", help="项目名称，如 my-project；省略时保留现值")
    parser.add_argument("--description", help="项目描述，最长 500 字符；省略时保留现值")
    args = parser.parse_args()
    if sys.version_info < (3, 11):
        print("需要 Python 3.11 或以上版本。", file=sys.stderr)
        return 1
    try:
        for message in initialize(Path(__file__).resolve().parent.parent, args.name, args.description):
            print(message)
    except ProjectError as exc:
        print(f"初始化失败：{exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"初始化失败：文件访问错误（{type(exc).__name__}），请检查权限和占用。", file=sys.stderr)
        return 1
    print("初始化完成。下一步：python scripts/check_project.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
