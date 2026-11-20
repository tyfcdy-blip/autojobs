# autojobs 自动化脚本控制中台

项目目标是建设企业内部的自动化脚本控制中台，集中管理任务上传、定时执行、电脑状态、环境准备、运行结果及钉钉告警。当前已完成通用工程模板、产品/技术文档，以及 **M0 本机执行端基础**：受控运行、机器互斥、持久记录、环境检查和独立 Vue 状态窗口。云端中台、集中定时、脚本上传、自动安装和钉钉尚未实现。

## 运行当前版本

入口为 [Windows 执行端使用说明](apps/agent/README.md)，含安装、无外部调用示例、常驻程序、状态窗口和验证命令。代码位于 `apps/agent/`；目前只在 Windows 11 开发机验证，两台 Windows 10 的现场兼容性仍待验证，不能直接用于生产。

开发与验证范围见 [M0 交付记录](docs/delivery/2026-11-19-agent-m0/report.md)。关闭状态窗口不会停止独立 worker；M0 尚无托盘、开机启动或云端连接，不应把本机验证模式当成完整中台。

## 产品设计入口

- [产品需求文档](docs/product/automation-control-platform-prd.md)：背景、已确认需求、首期范围、页面和流程建议、验收用例、待决事项。
- [主要页面视觉原型](docs/product/prototypes/v0.1/README.md)：四张中台页面效果图，以及执行电脑上的本地执行端窗口。
- [脚本接入与编写规范](docs/standards/script-integration.md)：单次入口、依赖声明、结果约定、停止与恢复边界；具体协议仍为草案。
- [技术路线与架构方案](docs/architecture/automation-control-platform-technical-design.md)：推荐 Python + Vue 中台和独立 Windows 执行端，含高 Star 项目比较、状态与协议设计、部署和分阶段验收。
- [技术路线调研交付记录](docs/delivery/2026-11-19-architecture/report.md)：本轮官方来源、文档检查和独立复核范围。
- [本次文档交付记录](docs/delivery/2026-11-19-product/report.md)：文档检查与评审证据，不代表产品功能已实现。

目标部署为阿里云 Linux Docker 中台和专用 Windows 10 执行电脑。用户选择以 Python、Vue 为主；本机执行端已初始化，其 Python/Vue 依赖已锁定。云端 FastAPI、PostgreSQL 尚未初始化或部署。以下命令用于已有模板工具。

## 立即开始

需要 Python **3.11 或以上版本**。在项目根目录运行，适用于 Windows、macOS 和 Linux：

```text
python scripts/init_project.py --name autojobs --description "我的长期开发项目"
python scripts/check_project.py
python -m unittest discover -s tests/unit -v
```

Windows 使用 PowerShell **7.3 或以上版本**时，也可使用以下入口（旧版直接使用 Python 命令）：

```powershell
./scripts/init.ps1 -Name autojobs -Description '我的长期开发项目'
```

初始化仅更新 `project.config.json` 中的名称和描述，并在 `.env` 不存在时从 `.env.example` 创建它；不会覆盖已有 `.env`，不会安装依赖、创建业务代码或执行 Git 操作。可重复运行。名称使用小写英文字母开头、数字及单个连字符，最长 63 字符，如 `my-project`；省略参数则保留现有元数据。项目名称以配置文件为准，README 标题可手动修改。

本项目现已初始化 Git，主分支为 `main`，远程仓库为 [tyfcdy-blip/autojobs](https://github.com/tyfcdy-blip/autojobs)。首次导入保留 GitHub 已有初始提交；历史交付记录中“尚无 Git”描述的是当时状态。初始化脚本仍不自动执行 Git 操作。如果 PowerShell 策略限制脚本运行，直接使用 Python 入口，不必更改系统策略。

## 目录地图

```text
autojobs/
├── AGENTS.md                 Codex 的执行规则与门禁
├── README.md                 项目入口
├── project.config.json       项目元数据、技术栈和业务验证命令登记
├── .editorconfig             基础编辑格式
├── .gitattributes            文本与换行约定
├── .gitignore                配置、凭据、构建产物与缓存排除
├── .env.example              无凭据的本地环境示例
├── .github/                  PR/Issue 模板、模板工具 CI
├── apps/
│   ├── backend/              后端应用预留（推荐 Python，未初始化）
│   ├── frontend/             前端应用预留（推荐 Vue，未初始化）
│   ├── jobs/                 独立批处理预留，当前未启用
│   └── agent/                M0 Windows执行端、只读窗口、测试与锁文件
├── packages/                 有真实多调用方时才提取共享能力
├── config/                   可提交的非敏感配置说明
├── scripts/                  初始化和检查工具
├── tests/
│   ├── unit/                 当前模板工具的自动化测试
│   ├── integration/          跨模块测试预留
│   └── e2e/                  完整用户流程测试预留
├── docs/
│   ├── product/              产品需求、验收设计与待决事项
│   ├── architecture/         架构、模块边界和待决事项
│   ├── standards/            工程、测试、安全、Git 规范
│   ├── runbooks/             开发、发布和回滚操作说明
│   ├── decisions/            架构决策记录（ADR）
│   ├── templates/            任务、测试、审查和变更计划模板
│   └── delivery/             每次任务的实际计划、证据和交付记录
├── data/
│   ├── samples/              可提交的脱敏样本说明
│   └── tmp/                  忽略的本地临时数据
└── logs/                     忽略的本地日志
```

预留目录的 README 或 `.gitkeep` 使目录可被 Git 保留，并不表示模块已经实现。没有复用需求时保持 `packages/` 为空，不创建通用工具大杂烩。

## 开始第一个开发任务

1. 阅读 [AGENTS.md](AGENTS.md) 和 [文档导航](docs/README.md)，确认真实目标、范围和验收证据。
2. 从 [任务模板](docs/templates/task.md) 与 [测试计划](docs/templates/test-plan.md) 建立本次 `docs/delivery/<日期>-<任务>/` 记录；小任务可合并为一个文件。
3. 确定技术栈、目录和环境，在 [架构文档](docs/architecture/README.md) 及 `project.config.json` 中登记；有权衡的决定写入 [ADR](docs/decisions/README.md)。
4. 在相应应用目录初始化真实项目，使用该技术栈的正式依赖清单和锁文件，登记可执行的构建、检查和测试命令。
5. 执行实际测试、记录退出码和结果；修改公共行为或数据前按 AGENTS 的门禁确认。完成后填写 [测试报告](docs/templates/test-report.md) 和 [审查记录](docs/templates/review.md)。

`project.config.json` 的 `verification` 是**业务命令登记表**，检查脚本仅校验格式并显示登记状态，不执行其中的命令。空数组表示未配置，不代表无须测试；不要登记尚不存在的命令。模板自身的验证入口如下。

## 验证边界

```text
python scripts/check_project.py
python -m unittest discover -s tests/unit -v
python -m compileall -q scripts tests
```

检查包括模板必要文件、目录和元数据；测试覆盖模板脚本的成功/失败行为、幂等和已有文件保护。模板检查通过不代表执行端、云端 API、UI、安全或性能验证通过。执行端的实际构建和测试命令见其 README；云端应用尚未初始化。

`.github/workflows/template-check.yml` 在推送、PR 或手动触发时运行模板检查和测试；它仅在托管到 GitHub 并启用 Actions 后生效。此模板不包含部署动作，不代表远程 CI 已执行。第三方 Action 的来源和固定版本见 [来源记录](docs/delivery/third-party.md)。

## 配置、数据与授权

`.env`、本地日志和临时数据不纳入版本管理。示例配置只提供无敏感信息的键，不自动向进程注入环境变量。不要把真实用户数据放进 `data/samples/`；详见 [安全规范](docs/standards/security.md)。

未预设项目许可证、维护人账号、远程仓库或生产环境。对外分发前由所有者决定许可证与维护方式。Codex 自检通过不等于开发自测确认、人工代码评审、CI 验证或发布审批通过。
