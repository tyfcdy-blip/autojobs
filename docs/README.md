# 项目文档导航

本目录服务于需求澄清、实现、测试、审查和长期维护。项目已形成产品与技术方案，并开始 M0 本机执行端开发；Python、Vue 方向已确认，云端中台尚未实现。目标部署仍为阿里云 Linux Docker 中台与两台 Windows 10 执行电脑。文档中的未来验收清单不是已完成的产品测试证据。

阅读顺序：仓库根 [README](../README.md) → [AGENTS.md](../AGENTS.md) → 本次任务涉及的标准与运行手册。任务冲突、权限和停止条件以根目录协作规则及当前用户授权为准。

## 按用途查找

| 用途 | 文档 |
| --- | --- |
| 了解自动化中台首期需求及待决事项 | [产品需求文档](product/automation-control-platform-prd.md) |
| 查看主要页面布局与操作入口 | [视觉原型 v0.1](product/prototypes/v0.1/README.md) |
| 为脚本接入统一结果和执行约定 | [脚本接入与编写规范草案](standards/script-integration.md) |
| 查看推荐技术栈、架构、协议和实施顺序 | [技术路线与架构方案](architecture/automation-control-platform-technical-design.md) |
| 比较高 Star 编排平台 | [平台调研与官方来源](architecture/research/orchestrators-2026-11-19.md) |
| 查看 Windows、浏览器、停止和环境准备限制 | [Windows 执行端专项调研](architecture/research/windows-agent-2026-11-19.md) |
| 查看技术文档检查与独立复核 | [技术路线交付记录](delivery/2026-11-19-architecture/report.md) |
| 运行当前本机执行端与窗口 | [执行端使用说明](../apps/agent/README.md) |
| 查看首阶段实现、测试和未验证门禁 | [M0 开发交付记录](delivery/2026-11-19-agent-m0/report.md) |
| 安排两台执行机的隔离兼容验证 | [Windows 10 现场验收](runbooks/windows-agent-m0-acceptance.md) |
| 复制测试包并逐台记录现场结果 | [Windows 10 测试包说明](delivery/2026-11-20-win10-validation/README.md) |
| 查看本次产品文档检查结果 | [文档交付记录](delivery/2026-11-19-product/report.md) |
| 明确模块归属与选型状态 | [架构与目录边界](architecture/README.md) |
| 编码、分层、兼容、依赖管理 | [工程规范](standards/engineering.md) |
| 风险分级、测试计划、用例和门禁 | [测试规范](standards/testing.md) |
| 配置、凭据、数据和安全边界 | [安全规范](standards/security.md) |
| 分支、变更范围、提交与审查 | [Git 协作规范](standards/git-workflow.md) |
| 首次使用和本地检查 | [本地开发手册](runbooks/local-development.md) |
| 准备发布与验证回滚 | [发布与回滚手册](runbooks/release-rollback.md) |
| 记录影响长期维护的决定 | [架构决策记录](decisions/README.md) |
| 记录需求和验收条件 | [任务模板](templates/task.md) |
| 设计测试和追踪覆盖 | [测试计划模板](templates/test-plan.md) |
| 保存实际执行结果 | [测试报告模板](templates/test-report.md) |
| 独立审查与问题追踪 | [审查模板](templates/review.md) |
| 跨阶段实施、兼容与回滚 | [变更计划模板](templates/change-plan.md) |

## 文档存放约定

- `docs/delivery/<任务编号>/`：已填写的任务、计划、测试报告、审查记录与脱敏证据。编号由项目自行约定，首次任务可以使用 `TASK-001`。
- `docs/decisions/`：已编号的架构决策，不用它替代普通任务记录。
- `docs/architecture/`：实际架构、模块关系、接口边界和数据流说明。确定设计后及时更新，保持与代码一致。
- `docs/product/`：产品需求、范围、验收设计与待决事项；已确认需求和建议设计明确区分。
- `docs/runbooks/`：可重复执行的操作步骤，包含前置条件、预期结果、失败处置及适用环境。
- `docs/templates/`：空白写作模板。复制后填写实际记录，不把原模板状态改成“通过”。

L1 小任务允许将任务、精简测试矩阵、结果和自检合并为一份交付记录；L2/L3 需要保留完整追踪关系。无需为每次修改机械复制全部模板。

## 维护规则

1. 修改业务行为、接口、配置或验证命令时，同步更新受影响文档。
2. 所有“通过”需要对应命令、输出或人工证据；没有证据填写“未验证”。
3. 链接优先使用仓库内相对路径，避免绑定某位开发者的本机位置。
4. 不提交凭据、真实个人信息、生产数据、未脱敏日志或来源不明附件。
5. 历史记录保留当时事实；后续修复通过追加记录或明确修订关联，不改写失败历史。
