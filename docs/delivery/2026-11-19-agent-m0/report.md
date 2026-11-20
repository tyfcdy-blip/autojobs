# M0 本机执行端开发交付记录

日期：2026-11-19，Asia/Shanghai。结论：**M0 本机开发交付有条件通过；完整 M0 尚未验收，不允许生产发布。** 已完成可运行的 Windows 本机执行链路与独立状态窗口，未把它标记为完整控制中台。

## 一、任务闭环

### 模式、等级与基准

全过程开发，L3：涉及本地 SQLite 状态、并发互斥和 Windows 自有进程控制。用户已确认技术方案并明确授权开始开发。本轮按方案优先验证最难的执行与停止边界；未操作两台真实执行机、生产数据、既有脚本或真实账号。

开发前已完成只读检查。仓库没有 `.git`，无分支、提交号或可用 Git diff；未初始化 Git、commit、push、部署。原业务目录为预留目录，新增实现位于 `apps/agent/`。见 [开工计划](plan.md)、[原始文件摘要](baseline.json)、[基线对比](baseline-comparison.json)。其中模板工具 `scripts/project_support.py`、`scripts/check_project.py` 的字节摘要未变。

### 本次实现

- **执行与控制**：指定 Python 绝对路径；固定机器级互斥；本地持久队列；单次执行；手动停止；默认一天运行时限；排队到期不启动；Windows Job 管理本轮进程树，清理未确认时保持待核实占用。
- **记录与结果**：SQLite WAL、短事务及单活动槽约束；同 run_id 请求幂等；状态与事件同事务；严格 JSON 结果协议、退出码冲突处理；崩溃后不自动重跑。待回传事件只落本地，尚无真实云端确认。
- **环境检查**：在指定解释器中读取版本和包元数据；检查依赖约束、固定文件和浏览器路径；检查不安装。慢检查期间仍维护心跳和到期队列。
- **本机窗口**：Vue 页面通过只读 pywebview 桥读取真实账本；在线与占用分别展示；运行详情、最近记录、待回传数量；窗口关闭不终止独立 worker；加载、空状态、错误、过期快照明确标识。
- **可用入口**：CLI、标准库结果 SDK、可重复生成的合成 CSV 示例、uv/pnpm 锁文件、wheel/sdist、离线页面资源和第三方许可文本。

明确未实现：云端 API/认证/集中调度、中台页面、上传分发、自动准备业务环境、钉钉机器人维护与通知、托盘/开机启动/安装器、生产恢复放行、全局磁盘配额和长期留存策略。完整中台能力继续按后续里程碑开发。

### 需求—工作包—实现—用例—结果

当前里程碑是 M0 的本机部分。技术方案的两台 Windows 10 现场兼容门禁未完成，因此不宣布完整 M0 通过，也不越过门禁部署或接入生产。

| 用例 / 工作包 | 实现位置（相对 `apps/agent/`） | 验证位置与实际结果 | 状态 |
| --- | --- | --- | --- |
| M0-01 / WP03 结果契约 | `contracts.py`、`script_sdk.py`（均在 `src/autojobs_agent/`） | `test_contracts.py`：版本、轮次、重复键、非有限数、UTF-8、大小与路径边界 | 本机通过 |
| M0-02 / WP03 环境 | `environment.py`、`environment_probe.py` | `test_runtime.py` 缺包不安装；Windows 路径/中文/空格；慢 probe 心跳 | 本机子集通过；浏览器登录未验证 |
| M0-03/04 / WP01 进程树 | `windows/process.py`、`_creation.py` | 真正创建父/子/孙进程、入口先退出、supervisor 崩溃；保留另一个无关测试进程 | 本机通过 |
| M0-05 / WP01 机器互斥 | `windows/mutex.py` | `test_windows_mutex.py` 6 项，包括不同进程、不同对象、弃用锁与目录无关 | 本机通过 |
| M0-06/07 / WP02+03 幂等与排队 | `journal.py`、`runtime.py` | 实际 SQLite 多线程/多进程领取、取消竞争、忙时到期、重复提交不重跑 | 本机通过 |
| M0-08/09 / WP03 完成与停止 | `runtime.py` | 成功/失败与退出码组合、无/坏结果、手动停止、超时、残留自有子进程、结果保留 | 本机通过 |
| M0-10/11 / WP02+03 恢复与事件 | `journal.py`、`runtime.py` | 实际 worker 崩溃后恢复为待核实；事件持久/幂等确认；事务失败回滚 | 本机通过；非网络补传验收 |
| M0-12 / WP01+03 输入与日志 | `contracts.py`、`windows/process.py` | 断链 junction 实测、越界输入、结果上限、两路海量日志有界且不阻塞 | 本机通过；非恶意代码沙箱验收 |
| M0-13 / WP03 窗口 | `status.py`、`desktop.py`、`desktop-ui/` | 16 项组件测试；真实 WebView2/Vue/SQLite/worker 集成，关闭窗口后任务继续 | 本机通过 |
| M0-14 / 现场 | [现场验收手册](../../runbooks/windows-agent-m0-acceptance.md) | 两台 Win10、锁屏、RDP、注销/重启、既有浏览器与登录态 | 未验证 |
| M0-15 / WP03+04 构建回归 | 锁文件、包配置、测试、根命令登记 | 139 项 agent、16 项 Vue、模板 24 通过/3 跳过；独立安装 wheel 运行实际示例 | 本机通过；发布与生产回滚未验证 |

本表的测试文件均位于 `apps/agent/tests/`，Vue 用例位于 `desktop-ui/tests/`。各自动化用例中的测试名称、fixture、输入、动作、断言与 JUnit 逐项对应；[计划矩阵](plan.md) 保留编码前的预期，[JUnit](agent-junit.xml) 保存最终实际结果。

### 变更范围

新增 `apps/agent/` 下 Python/Vue 源码、对应测试、示例、锁文件、离线资源；新增本交付目录及现场验收手册。更新根 `AGENTS.md` 的项目现状说明、README、`project.config.json`、文档导航、架构现状、技术方案状态、ADR 状态和脚本规范的实际实现边界。没有降低 AGENTS 门禁。

模板测试仅修正一个用例的数据准备：明确构造“未登记命令”的输入，避免复制当前项目已登记命令后仍断言“尚未配置”。原断言保留，模板业务代码未改。历史产品/架构交付记录保留当时事实，没有改成后来已实现。

## 二、测试证据

### 环境、数据及边界

Windows 11 build 26100，Python 3.12.7，Node 24.18.0，pnpm 11.9.0。Python 依赖在 `apps/agent/.venv`，独立安装验证另建 `data/tmp/agent-wheel-smoke-20261119`；未全局安装或改业务环境。

所有任务、CSV、SQLite 和进程都是本轮合成测试数据；实际浏览器测试使用 Edge 无头模式、独立临时 profile、本地 HTML。没有复用用户浏览器登录资料、调用生产接口或数仓。测试注入只用于清理 API 证据失败、错误边界及 UI 宿主替身；SQLite、机器互斥、进程树和最终窗口集成均使用真实组件。UI 的四张截图来自标识为测试的快照，不是生产运行证据。

### 最终命令和退出码

下表未特别说明时在 `D:\codex\autojobs` 执行。`uv run` 使用已锁定的应用依赖。

| 完整命令 / 操作 | 退出码 | 结果 |
| --- | --- | --- |
| `uv run --project apps/agent --frozen --extra desktop ruff check apps/agent/src apps/agent/tests apps/agent/examples` | 0 | 静态检查通过 |
| `uv run --project apps/agent --frozen --extra desktop mypy --config-file apps/agent/pyproject.toml apps/agent/src/autojobs_agent` | 0 | 15 个源文件通过 |
| 在 `apps/agent/`：`uv run --frozen --extra desktop pytest tests -q --junitxml=../../docs/delivery/2026-11-19-agent-m0/agent-junit.xml` | 0 | **139 通过 / 0 失败 / 0 跳过，37.12 秒** |
| `pnpm --dir apps/agent/desktop-ui typecheck` | 0 | Vue/TS 类型检查通过 |
| `pnpm --dir apps/agent/desktop-ui test` | 0 | **16 通过 / 0 失败 / 0 跳过** |
| `pnpm --dir apps/agent/desktop-ui build` | 0 | 类型检查 + Vite 构建；3 个离线页面资源及资源清单 |
| `uv build --project apps/agent` | 0 | sdist 与 wheel 构建通过；补入许可文本后已重新构建 |
| `uv pip check --python apps/agent/.venv/Scripts/python.exe` | 0 | 28 个已安装开发/运行包的依赖兼容检查通过 |
| `pnpm --dir apps/agent/desktop-ui audit --prod --json --registry=https://registry.npmjs.org` | 0 | 注册表报告前端生产依赖已知漏洞 0；非整体安全验收 |
| `python -X utf8 scripts/check_project.py` | 0 | 38 必要文件、13 目录和配置有效；本命令不执行业务测试 |
| `python -X utf8 -m unittest discover -s tests/unit -v` | 0 | **27 项：24 通过 / 0 失败 / 3 跳过，8.283 秒** |
| `python -X utf8 -m compileall -q scripts tests` | 0 | 模板脚本及测试编译通过 |
| 在 `apps/agent/desktop-ui/`：`python -B -X utf8 scripts/verify-browser.py` | 0 | UI 工作包执行：四种布局；无页面/控制台错误、横向溢出或外部资源请求 |

模板 3 项跳过为原有符号链接创建用例，本机无相应创建权限；未增加跳过或降低断言。agent 的真实 Windows junction 测试已执行通过。首次模板运行是 1 失败 / 3 跳过，修订 fixture 后才得到上表结果。

agent 的 139 项分布：CLI 2、契约 22、真实桌面集成 1、账本 60、运行集成 17、故障注入 4、状态读取 3、机器互斥 6、Windows 进程 24。JUnit suite 计时 36.878 秒，与 pytest 总摘要 37.12 秒的计时边界不同。

### 安装包独立验证

实际完成以下命令，最终均退出 0：

```text
# 前一条在 apps/agent/ 执行，其余在仓库根目录
uv export --frozen --no-dev --extra desktop --no-emit-project --output-file ../../data/tmp/agent-wheel-requirements.txt
uv venv --python apps/agent/.venv/Scripts/python.exe data/tmp/agent-wheel-smoke-20261119
uv pip sync --python data/tmp/agent-wheel-smoke-20261119/Scripts/python.exe --require-hashes --link-mode copy data/tmp/agent-wheel-requirements.txt
uv pip install --python data/tmp/agent-wheel-smoke-20261119/Scripts/python.exe --reinstall --no-deps --link-mode copy apps/agent/dist/autojobs_agent-0.1.0-py3-none-any.whl
```

在该隔离环境通过实际安装的 CLI 完成 `生成示例 → check → submit → serve --once → show`，确认导入位置不在源码目录，实际读取两行 CSV，返回 `succeeded` 和 `processed_rows: 2`。核对 wheel 的离线资源清单、SDK 和第三方许可文本，最终重建后再次执行真实示例。

完整子进程 argv、stdout、stderr、退出码与最终包摘要见 [packaging-smoke.json](packaging-smoke.json)。最终 wheel SHA-256：`44852a935173b5d45ad7ed15af98ac33ead843650365920adf18e31a9f3e84a8`。包在 `apps/agent/dist/`，属于本地忽略的构建产物，可由锁文件重建；本次未发布。

### 复核与失败记录

[独立 AI 复核](review.md) 已核对最终代码、对应回归设计及 139 项 JUnit。Windows/账本/UI 工作包局部验证后，主 agent 统一执行以上跨模块回归。没有把子 agent 的口头结论直接当作通过依据。

主 agent 另行只读检查由 UI worker 编写的状态轮询、输入结构校验、主页面与结果组件：确认同一时刻只有一次桥调用，卸载后不更新页面，失败快照有提示，结果使用文本插值，无任意执行入口。未发现新的阻断问题。最终文档检查覆盖 14 份文档、102 个本地链接，全部存在；模板检查和 Ruff 在文档收尾后再次退出 0。

开发中实际出现并处理的问题包括：pytest 的保留 fixture 名称冲突；Windows venv 额外启动进程导致固定进程数假设不成立；进程时间读取和退出信号竞争；CLI 中文编码；状态时间值类型收窄。修订实现或正确的测试前提后执行了定向复验与最终 139 项回归。

前端初次 TypeScript 7 与 vue-tsc 不兼容，锁定为 6.0.3 后类型/构建通过；组件测试等待时机与浏览器验证脚本语法也已修正，记录见 [UI 工作包报告](../../../apps/agent/desktop-ui/verification/report.md)。未关闭类型检查、删除断言或跳过失败用例。

打包验证脚本也记录了工具/验证前提修正：`uv pip sync` 不接受 `-r`，改用位置文件参数；首次资源数量断言漏算独立 manifest，改为逐项核对 manifest；许可文本一度按已换行转换的文本与原始字节比较，改为逐字节核对安装副本与 wheel。三项错误均发生在本次隔离工具验证中，最终安装和真实任务重跑通过，不是产品功能失败的掩盖。

## 三、问题、风险与回滚

### 已关闭缺陷

| 编号 | 等级 | 修复及复验 |
| --- | --- | --- |
| M0-R01 | P1 | 启动/probe 尚未返回进程对象时清理失败不得释放槽；Windows 任一清理证据失败统一保留不确定性。真实 API 边界故障用例 + runtime 回归通过 |
| M0-R02 | P2 | 运行期间维护到期排队；忙时过期用例通过 |
| M0-R03 | P2 | 合法最长消息追加说明不再丢失结果；仅裁摘要并保留平台诊断；成功/失败两个边界通过 |
| M0-R04 | P2 | 断链 junction 不能绕过路径检查；真实目录联接回归通过 |
| M0-R05 | P2 | 慢环境 probe 同时维护心跳和到期排队；真实 6 秒检查回归通过 |

没有已知未关闭 P0/P1。另有 P3：传递开发依赖 `ini@1.3.4` 被安装工具标记 deprecated，未为消除提示扩大升级范围。

### 未验证与非范围

- 两台 Windows 10 的实际版本、锁屏/RDP/注销/重启、现有浏览器登录态、连接已有应用、非 3.12 业务解释器组合、壁钟调整/休眠场景均未验证。[现场手册](../../runbooks/windows-agent-m0-acceptance.md) 给出记录与执行步骤。当前已验证的浏览器只限开发机独立 Edge 无头本地页面。
- 无 24 小时连续压力/磁盘满/停电实测，无生产容量或 SLA 结论；每轮日志限额已验证，但总队列、留存和总磁盘配额未实现，不适合长期无人值守生产部署。
- 账本事务回滚与崩溃保守恢复已验证；没有数据库备份恢复、旧版本迁移、生产降级和业务补偿演练。待核实轮次目前没有可用的人工恢复放行功能。
- 云端、HTTP API、跨网断连/补传、钉钉、认证/权限、CSRF、生产账号与敏感数据等对应实现尚未存在，未做相关 API/E2E/安全验收。金额、库存、历史业务数据迁移门禁不适用本机合成示例；不能据此豁免未来业务门禁。
- 本程序接收可信维护人员的脚本，路径检查和进程控制不构成恶意代码沙箱。只读本机窗口不等于完成生产 ACL、远程鉴权或完整安全审计。
- Python/前端全开发依赖漏洞审计、人工许可审查、无障碍专项均未完成；前端生产依赖 audit 0 已知漏洞仅是限定查询结果。

回退：本轮仅新增隔离运行目录和应用，没有业务库迁移。停止本项目 worker 并核实自有进程清理，关闭窗口；保留 SQLite、运行日志和未确认事件用于分析。不能删除未知记录、换状态目录绕过占用或重跑业务。当前没有发布，不声称生产回滚演练通过。

### 第三方来源与版本

实际版本以 [uv.lock](../../../apps/agent/uv.lock) 与 [pnpm-lock.yaml](../../../apps/agent/desktop-ui/pnpm-lock.yaml) 为准。Python 运行版本/来源/许可元数据见 [python-runtime-dependencies.json](python-runtime-dependencies.json)；前端生产依赖来源与许可证见 [frontend-runtime-licenses.json](frontend-runtime-licenses.json)。来源为锁定包及其实际安装元数据，没有复制未知来源业务代码。

直接运行组件：Pydantic 2.14.3、packaging 26.3、psutil 7.2.2、pywin32 312、pywebview 6.2.1；Vue 3.5.45。编译与测试版本见锁文件及 UI 报告。`clr-loader 0.3.1` 元数据未列 license expression，但实际 `dist-info/licenses/LICENSE` 内容为 MIT，已读取；不能将空元数据误记为无许可。

前端生产依赖树 24 个包的实际 LICENSE 文件保存在 `apps/agent/src/autojobs_agent/THIRD_PARTY_NOTICES.txt` 并纳入 wheel，包含经构建裁掉的包以保守保留来源。更新锁文件或重新打包依赖时应同步核对该许可快照。项目自身许可证仍由所有者决定；本记录不替代人工法律/发布审查。

## 四、质量状态

| 项目 | 实际状态 |
| --- | --- |
| Codex 开发完成 | 本轮 M0 本机范围完成；完整 M0 与整套中台未完成 |
| 测试计划/用例已生成 | 是，计划矩阵、Python/Vue 用例与现场手册已形成 |
| 自动化测试已执行 | 是，agent 139、Vue 16、模板 24 通过；模板 3 项明确跳过；构建与独立包示例通过 |
| 人工验证已执行 | 否；AI 界面检查不计人工验收 |
| 剩余未验证项 | Win10现场、生产会话/浏览器、长期运维、完整安全、恢复/发布等，见上节 |
| 独立复核通过 | 本机代码范围的独立 AI 复核通过，见 review.md；不是人工评审 |
| CI 通过 | 未执行；无远程仓库/CI 运行证据 |
| 开发最终确认 | 未取得维护人员最终确认 |
| 人工代码评审通过 | 未执行 |
| 允许发布 | 否 |

**AI 自检结论：有条件通过，仅限本机开发交付。** 下一门禁是两台 Windows 10 现场兼容与人工专项复核；该阶段完成前，完整 M0 保持未验收。使用入口为 [执行端 README](../../../apps/agent/README.md)。

**Codex 自检通过不等于开发自测确认、人工代码评审、CI 验证或发布审批通过。**
