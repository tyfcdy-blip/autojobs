# ADR-0001：Python 与 Vue 中台及独立 Windows 执行端

- 状态：路线已获用户同意并授权开发（2026-11-19，用户回复“好没有问题，那么你开始开发吧”）。不代表运行兼容、人工专项评审或发布审批通过；M0 已开始落地，具体云端协议仍按阶段冻结。
- 日期与时区：2026-11-19，Asia/Shanghai。
- 关联任务：[技术路线任务计划](../delivery/2026-11-19-architecture/plan.md)。
- 决策依据：用户访谈、现有 PRD 与五张视觉原型、官方仓库和文档；[技术方案](../architecture/automation-control-platform-technical-design.md) 为完整设计。
- 替代/被替代记录：无。

## 问题与上下文

两台专用 Windows 10 电脑运行十几个 Python 自动化脚本，需要固定电脑串行、集中定时、上传分发、环境识别/准备、结果和异常通知。脚本有浏览器登录态、既有应用连接与多个解释器环境。云端为 Linux Docker，团队主要使用 Python 和 Vue。

硬约束是整机互斥、未知运行不自动重跑、环境检查与安装分开、24 小时默认运行时限和可确认的停止。未知项包括具体 OS/脚本版本、会话兼容、账号权限、补跑口径、日志保留及安装范围。

## 候选方案

| 方案 | 收益 | 代价 / 放弃或采用理由 |
| --- | --- | --- |
| FastAPI + Vue + PostgreSQL + 独立 Python agent | 技术与维护方向一致；产品状态、窗口、环境和故障规则可直接表达 | 需自行实现与充分验证可靠派发、账本、恢复、权限和进程管理；推荐首期路线 |
| Prefect 自托管 + Windows process worker | 已有 Python 编排、调度与运行记录，官方支持原生 Windows worker | 仍需本机 UI、环境与设备协议适配；作为成品路线首选验证对象，不先 fork 核心 |
| Windmill 企业版 | 脚本管理与 Windows/HTTP Agent 较接近场景 | 对应能力有商业版本边界；预算与许可确认后可对比整套使用 |
| Airflow/Kestra/Dagster/XXL-JOB/n8n 深度二开 | 可借成熟编排、执行器、集成和日志模型 | 本场景的 Windows 桌面边界仍需适配，部分增加语言/运行组件或许可限制；当前不优先 |

对照证据见 [平台调研](../architecture/research/orchestrators-2026-11-19.md)。Star 只用于参考生态关注度，不单独决定路线。

## 推荐决定

1. 管理端 Vue 3 + TypeScript + Element Plus，后端 FastAPI + Pydantic + SQLAlchemy，PostgreSQL 保存配置与运行事实。
2. 后端采用模块化单体、独立 API/control 进程，不引入微服务、独立消息队列或第二套调度状态库。APScheduler 3.x 只承担时点计算。
3. Windows Python agent 主动通过 HTTPS 与云端连接；本机有 SQLite 账本与单机锁；pywebview 状态窗口独立于 worker。
4. 任务使用明确 Python 路径；uv 负责受控准备；Windows Job Objects 负责本轮拥有的进程；浏览器和登录资料按实际脚本管理。
5. Linux 使用 Docker Compose。初期无高可用承诺；备份恢复必须先核对执行端状态，再恢复派发。

## 影响、迁移与回滚

技术路线编制阶段只新增文档。用户随后授权开发，M0 已在 `apps/agent/` 落地本机执行链路、锁定依赖，并在 `project.config.json` 登记实际技术及验证命令；云端接口、数据库及部署仍未实施。

旧脚本迁移需停用内部常驻定时、改为受控单次执行、遵循结果规范并验证业务效果。只在旧任务已结束且中台试跑通过后启用新计划；回退先停中台再恢复旧调度，避免双跑。

程序回滚不能撤销业务写入。数据库恢复和 agent 降级不能依靠丢弃未知状态解决；须核对本地账本、版本和派发代数。第三方许可证按实际引入版本及文件审查，当前未复制第三方代码。

## 验证与再评估条件

首先执行技术方案 M0 与 Windows 专项 W01–W13。当前最新版 Playwright 官方支持列表不含 Windows 10，服务 Session 0 不等于用户桌面；存量兼容需实机验证，不能从文档推断通过。

如果无法可靠停止或区分未知运行，先收窄支持范围或对比 Prefect，不允许用“自动重试”掩盖状态不确定。若后续增加复杂 DAG、数据资产治理、很多执行机或商业运维预算，另建 ADR 重评，保持一套运行事实来源。

技术路线编制阶段的验证仅覆盖资料、设计推演和文档质量，历史证据见 [路线交付记录](../delivery/2026-11-19-architecture/report.md)。随后开展的本机实现与实测见 [M0 交付记录](../delivery/2026-11-19-agent-m0/report.md)。两台 Windows 10 现场验证、人工评审、CI 及发布审批仍未完成。
