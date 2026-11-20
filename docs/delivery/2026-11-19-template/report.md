# 通用项目模板交付记录

日期：2026-11-19（Asia/Shanghai）。模式：全过程开发。等级：L1；新增通用目录、规范和本地模板工具，没有业务系统、数据库、公开接口或生产操作。

## 结果与基准

- 用户明确选择“通用模板，不预装框架”。初始目录为空，无 `.git`、分支、提交或既有变更；不存在可比较的 Git 基准。
- 已建立根 AGENTS、README、项目元数据、编辑/换行/忽略配置、无凭据环境示例、应用和测试目录、15 份规范/文档模板，以及 PR/Issue/CI 模板。
- 已实现一个 Python 初始化入口、一个 PowerShell 转发入口、共享配置校验和只读结构检查器。没有引入第三方运行时包或业务框架。
- 已在实际项目无参数运行初始化：仅创建 `.env`，保留 `autojobs` 元数据；未建立 Git 仓库，未提交/推送/部署。
- 本记录是本次模板交付的历史证据，不表示后续项目仍为空或继续采用当前工具版本。

## 需求—实现—验证追踪

一个工作包一次集成交付。编码前计划见 [plan.md](plan.md)。

| 用例 | 实现与验证范围 | 实际结果 |
| --- | --- | --- |
| T01 | 根配置、目录、AGENTS、README、docs、GitHub 模板；`check_project.py` | 38 个必要文件、13 个目录及配置校验通过 |
| T02 | `init_project.py` 正常名称/中文描述；新建 .env | 临时副本测试通过；实际根目录初始化通过 |
| T03 | 无参数、重复运行、自定义 .env；已有配置字节与时间戳 | 通过；已有 .env 不覆盖，未变化元数据不重写 |
| T04 | 名称空/非法/路径/超长及 1/63 字符边界；描述空/500/501 字符 | 通过；非法输入未写目标文件 |
| T05 | JSON/UTF-8 异常、BOM、字段/版本/类型、空命令、孤立 Unicode 代理字符；不执行登记命令 | 通过；失败非零退出、不打印配置原文或异常堆栈 |
| T06 | 缺示例、.env 为目录、替换失败回滚与保留旧 .env | 已执行部分通过；3 项真实符号链接创建因系统权限受限跳过 |
| T07 | 缺文件、空文件、缺目录 | 通过；非零退出并指出缺项 |
| T08 | 从其他工作目录运行，中文和含空格路径 | 通过；仅写脚本所属项目 |
| T09 | `init.ps1` 中文/空格/双引号参数、成功与失败退出码、旧版拒绝 | PowerShell 7.6.9 通过；Windows PowerShell 5.1 在写入前拒绝，提示使用 Python |
| T10 | Python 编译、PowerShell 解析、文档链接/格式、Git 忽略规则 | 通过；无 Git 基准，Git diff 检查不适用 |

最终自动化共发现 **27 个测试：24 通过、0 失败、3 跳过**。首轮为 25 个测试、22 通过、3 跳过；独立复核后增加边界用例并完成全套回归。名称与输入边界的 subTest 包含多个场景，不额外算作独立测试。数据均为临时目录中的模板副本和人工测试字符串，不读取真实 `.env`、业务数据或生产服务；临时目录在用例结束后清理。

文件替换故障用 `unittest.mock` 注入 `PermissionError`，只替代操作系统替换边界；真实解析、校验、写入、清理和保留逻辑均执行。没有业务 API、UI、数据库或外部服务，因此对应业务集成、性能、权限及生产恢复测试不适用。

## 执行证据

工作目录：`D:\codex\autojobs`。环境：Windows、Python 3.12.7、PowerShell 7.6.9。`-X utf8` 用于让本次采集的中文终端输出按 UTF-8 解码，不改变工具功能。

| 实际命令/检查 | 退出码 | 结果 |
| --- | --- | --- |
| `python scripts/check_project.py` | 0 | 38 必要文件、13 目录、配置有效 |
| `python -m unittest discover -s tests/unit -v` | 0 | Ran 25 tests；OK (skipped=3)，22 通过、0 失败 |
| `python -X utf8 -m unittest discover -s tests/unit -v` | 0 | 修复后最终回归 Ran 27 tests；OK (skipped=3)，24 通过、0 失败 |
| `python -m compileall -q scripts tests` | 0 | 编译检查通过；非业务制品构建 |
| PowerShell Parser.ParseFile，完整命令见下文 | 0 | PowerShell syntax: OK |
| UTF-8/换行/空白/本地 Markdown 链接审计，见下文 | 0 | 当时 45 文件、35 本地链接、0 错误 |
| 文档完成后的同一审计命令 | 0 | 47 文件、37 本地链接、0 错误 |
| 临时 Git 仓库中的忽略规则检查，见下文 | 0 | 12 项通过，临时仓库已清理 |
| `python -X utf8 scripts/init_project.py` | 0 | 实际根目录创建 .env，元数据未变化 |
| `python -X utf8 scripts/check_project.py` | 0 | 实际初始化后检查通过 |
| AI 独立复验，完整命令见下文 | 0 | Ran 3 tests in 3.169s；OK，3 通过、0 失败、0 跳过 |

开工及结束的 `git status --short --branch` 返回“not a git repository”，用于确认没有仓库，不能记成 Git 检查通过。根目录没有运行 `git init`；忽略规则测试只在工具创建的隔离临时目录内运行 Git 初始化，不设置远程或产生提交。全部文件均为本任务新增；已检查文件内容和本地链接，无已有修改被覆盖。

## 缺陷、复核与限制

- 自检发现 CI 中 `git diff --check` 对干净检出不能验证已提交内容，已移除此无效步骤，避免形成表面门禁；有效的结构、自动化用例和编译步骤保留。未出现测试失败，未删测、降断言或扩大跳过。
- AI 独立只读复核发现 2 项 P2，主 agent 已核验并修复：Windows PowerShell 5.1 原有参数转义会丢失双引号，入口现要求 7.3+ 并设置脚本局部标准传参，旧版明确拒绝且不写入；JSON 孤立代理字符原会触发编码堆栈，现于统一配置校验阶段拒绝。相关新用例和全套回归通过；独立 AI 复验对应 3 项测试，3 通过、0 失败、0 跳过、退出码 0，两项问题均关闭，无未关闭 P0/P1/P2。这是 AI 复核，不是人工评审。
- 3 项真实符号链接测试未验证：当前 Windows 不能创建该类型链接。补验时在允许创建符号链接的隔离开发环境运行同一 unittest 命令，预期三项执行且通过；不得为测试擅改系统全局策略。
- 本机实测 Python 3.12.7、PowerShell 7.6.9，另验证了 Windows PowerShell 5.1 的拒绝路径。Python 3.11、Linux、macOS、PowerShell 7.3 最低版本未实测；CI 配置包含 Ubuntu/Windows 与 Python 3.11/3.12，但尚无远程运行记录。
- 初始化不保证并发运行或断电后的跨文件事务恢复；已在工具说明披露。单进程本地使用可重复执行，普通替换失败回滚路径已测试。
- 未建立业务应用，所以业务构建/集成/UI/性能/生产回滚不适用；不能用模板通过状态替代后续业务验收。

回滚范围：本次新增的本地模板文件，不涉及数据迁移或外部副作用。若不采用模板，先保存已有 `.env` 和后续用户修改，再由所有者决定移除哪些新增文件；不执行整目录清理。

## 质量状态

| 项目 | 当前状态 |
| --- | --- |
| Codex 开发完成 | 完成 |
| 测试计划/用例生成 | 完成 |
| 自动化测试执行 | 已执行，24 通过、0 失败、3 跳过 |
| 人工验证 | 未执行；实际根目录功能验证由 Codex 执行 |
| 剩余未验证项 | 符号链接、其他运行环境、远程 CI |
| AI 独立复核 | 通过；两项 P2 已修复并独立复验关闭 |
| CI 通过 | 未执行 |
| 开发最终确认 | 等待项目所有者确认 |
| 人工代码评审 | 未执行 |
| 允许发布 | 不适用；本任务为本地模板交付，未授权部署 |

AI 自检结论：**有条件通过**。本地关键行为、静态检查和回归通过，没有未关闭 P0/P1；条件为已披露的非阻断符号链接及跨环境验证缺口。下一门禁为项目所有者确认模板使用方式；接入 GitHub 后执行真实 CI。首次业务开发前按真实目标确认技术栈和验收标准。

**Codex 自检通过不等于开发自测确认、人工代码评审、CI 验证或发布审批通过。**

## 附：补充检查的完整命令

修复后的独立 AI 复验（主 agent 已用完整 27 项回归核验相同用例）：

```powershell
@'
import sys, unittest
sys.path.insert(0, 'tests/unit')
from test_project_tools import ProjectToolsTests
names = (
    'test_unpaired_unicode_surrogates_fail_before_writes',
    'test_powershell_wrapper_forwards_arguments_and_failure',
    'test_legacy_powershell_is_rejected_before_writes',
)
result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(ProjectToolsTests(name) for name in names))
raise SystemExit(not result.wasSuccessful())
'@ | python -X utf8 -
```

PowerShell 语法检查及再次编译：

```powershell
$tokens = $null
$parseErrors = $null
[System.Management.Automation.Language.Parser]::ParseFile((Join-Path (Get-Location) 'scripts\init.ps1'), [ref]$tokens, [ref]$parseErrors) | Out-Null
if ($parseErrors.Count -gt 0) { $parseErrors | Format-List; exit 1 }
Write-Output 'PowerShell syntax: OK'
python -X utf8 -m compileall -q scripts tests
```

文本与链接检查（此记录增加后，文件与链接数量会随之增加）：

```powershell
@'
from pathlib import Path
import re
root = Path.cwd()
files = [p for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts]
errors = []
links = 0
for path in files:
    if path.name == '.gitkeep':
        continue
    try:
        content = path.read_text(encoding='utf-8')
    except UnicodeError:
        errors.append(f'not UTF-8: {path.relative_to(root)}')
        continue
    if not content.endswith('\n'):
        errors.append(f'missing final newline: {path.relative_to(root)}')
    for number, line in enumerate(content.splitlines(), 1):
        if line.rstrip() != line:
            errors.append(f'trailing whitespace: {path.relative_to(root)}:{number}')
    if path.suffix == '.md':
        for target in re.findall(r'\]\(([^)]+)\)', content):
            if '://' in target or target.startswith('#'):
                continue
            links += 1
            if not (path.parent / target.split('#')[0]).exists():
                errors.append(f'broken link: {path.relative_to(root)} -> {target}')
print(f'Files={len(files)}, local Markdown links={links}, errors={len(errors)}')
for error in errors:
    print(error)
raise SystemExit(bool(errors))
'@ | python -X utf8 -
```

忽略规则验证：

```powershell
@'
from pathlib import Path
import shutil
import subprocess
import tempfile
root = Path.cwd()
with tempfile.TemporaryDirectory(prefix='template-ignore-test-') as temporary:
    repo = Path(temporary)
    shutil.copy2(root / '.gitignore', repo / '.gitignore')
    subprocess.run(['git', 'init', '--quiet', str(repo)], check=True, capture_output=True)
    cases = {'.env': True, '.env.production': True, '.env.example': False, '.env.test.example': False, 'logs/run.log': True, 'logs/.gitkeep': False, 'data/tmp/export.csv': True, 'data/tmp/.gitkeep': False, 'apps/frontend/package-lock.json': False, 'apps/backend/pom.xml': False, 'apps/jobs/uv.lock': False, 'docs/delivery/report.md': False}
    for relative, expected in cases.items():
        result = subprocess.run(['git', '-C', str(repo), 'check-ignore', '--quiet', relative], check=False)
        assert result.returncode in (0, 1), (relative, result.returncode)
        assert (result.returncode == 0) == expected, relative
    print(f'Git ignore checks: {len(cases)} passed; temporary repository cleaned on exit.')
'@ | python -X utf8 -
```
