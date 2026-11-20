"""检查模板完整性和项目配置，不执行业务命令，不读取 .env。"""

import sys
from pathlib import Path

from project_support import ProjectError, load_config


REQUIRED_FILES = (
    "AGENTS.md", "README.md", "project.config.json", ".editorconfig",
    ".gitattributes", ".gitignore", ".env.example",
    "scripts/init_project.py", "scripts/init.ps1", "scripts/project_support.py", "scripts/check_project.py",
    "scripts/README.md", "tests/unit/test_project_tools.py",
    "apps/backend/README.md", "apps/frontend/README.md", "apps/jobs/README.md",
    "packages/README.md", "config/README.md", "tests/README.md",
    "docs/README.md", "docs/architecture/README.md",
    "docs/standards/engineering.md", "docs/standards/testing.md",
    "docs/standards/security.md", "docs/standards/git-workflow.md",
    "docs/runbooks/local-development.md", "docs/runbooks/release-rollback.md",
    "docs/decisions/README.md", "docs/decisions/0000-template.md",
    "docs/templates/task.md", "docs/templates/test-plan.md",
    "docs/templates/test-report.md", "docs/templates/review.md",
    "docs/templates/change-plan.md", ".github/workflows/template-check.yml",
    ".github/PULL_REQUEST_TEMPLATE.md", ".github/ISSUE_TEMPLATE/bug_report.md",
    ".github/ISSUE_TEMPLATE/feature_request.md",
)
REQUIRED_DIRS = (
    "apps/backend", "apps/frontend", "apps/jobs", "packages", "config", "scripts",
    "tests/unit", "tests/integration", "tests/e2e", "docs/delivery",
    "data/samples", "data/tmp", "logs",
)


def check(root: Path) -> list[str]:
    errors = []
    for relative in REQUIRED_FILES:
        path = root / relative
        if not path.is_file():
            errors.append(f"缺少必要文件：{relative}")
        elif path.stat().st_size == 0:
            errors.append(f"必要文件为空：{relative}")
    for relative in REQUIRED_DIRS:
        if not (root / relative).is_dir():
            errors.append(f"缺少必要目录：{relative}")
    try:
        load_config(root / "project.config.json")
    except ProjectError as exc:
        errors.append(str(exc))
    return errors


def main() -> int:
    if sys.version_info < (3, 11):
        print("需要 Python 3.11 或以上版本。", file=sys.stderr)
        return 1
    root = Path(__file__).resolve().parent.parent
    try:
        errors = check(root)
        if errors:
            for error in errors:
                print(f"失败：{error}", file=sys.stderr)
            return 1
        config = load_config(root / "project.config.json")
    except OSError as exc:
        print(f"检查失败：文件访问错误（{type(exc).__name__}）。", file=sys.stderr)
        return 1
    print(f"模板检查通过：{len(REQUIRED_FILES)} 个必要文件，{len(REQUIRED_DIRS)} 个目录，配置格式有效。")
    configured = [name for name, commands in config["verification"].items() if commands]
    print("已登记业务验证类型：" + ("、".join(configured) if configured else "无（尚未配置）"))
    print("本检查不执行业务命令，不代表构建、业务测试、CI 或发布审批通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
