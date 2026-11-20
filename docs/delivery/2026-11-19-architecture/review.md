# 自动化中台技术方案独立评审记录

日期：2026-11-19（Asia/Shanghai）。模式：独立审查。等级：L1，范围为技术方案及证据文档，未实现或运行调度、权限、数据库、执行端与外部通知功能。本次为 AI 独立评审，不是人工评审。

## 1 范围与依据

审查 [技术方案](../../architecture/automation-control-platform-technical-design.md)，对照 [PRD](../../product/automation-control-platform-prd.md)、[脚本规范](../../standards/script-integration.md)、[原型说明](../../product/prototypes/v0.1/README.md)、[本机窗口说明](../../product/prototypes/v0.1/local-runner.md)，以及架构研究目录的三份调研和三份 GitHub 快照。

重点为确认事实与技术建议的边界、R01–R18/AC01–AC20/Q01–Q12 的追踪、机器级串行、启动授权和取消竞态、截止时间、失联不释放、重启/备份恢复、Windows 会话及进程归属、结果判定与通知边界。仓库未初始化 Git，无可用分支或提交基准。本评审未改主方案、代码或配置；仅新建本记录。主 agent 独立处理下述发现并反馈，评审 agent 已重新读取相关位置核验。

## 2 发现及关闭情况

| 编号 / 等级 | 初次发现与影响 | 修订及独立复核 | 状态 |
| --- | --- | --- | --- |
| AR-01 / P2 | 技术方案第 9.2 节规定环境准备占用整机维护槽，但最初未定义安装/下载卡住、准备中取消、worker 重启时如何监督与释放该操作。业务 run 的 24 小时上限不能自动覆盖 environment_operation。可能出现维护槽长期占用，或实施时为恢复服务错误地释放仍有安装进程的电脑。此为设计缺口推演，未发生实际故障。 | 现第 9.2 节第 275 行新增独立 operation_id，复用命令去重、本地账本、受控进程与重启核对；规定独立总时限及取消宽限、确认安装/构建子进程结束后释放、失败环境隔离和旧环境保留。M3 加入安装卡住、准备取消/重启的验证，Q01 明确相关参数待定。已只读核验这些条款。 | 文档缺口已关闭；运行验证待实现 |
| AR-02 / P3 | 首选技术表下“PostgreSQL 支持版本”链接原指向 explicit-locking 页面，该页面不能支持版本生命周期判断。 | 现第 24 行改为官方 Versioning Policy 页面；独立打开官方页面确认其包含受支持版本表，17 列为受支持版本。候选版本仍未宣称已锁定或兼容通过。 | 已关闭 |

未发现已证实的 P0/P1；本轮两项发现已关闭，不代表方案全部风险已在实际系统中验证。

## 3 需求与设计一致性结论

- 18 项需求均能关联技术章节及验收用例，20 个产品验收编号、12 个待决项均在技术方案中出现。编号齐全仅证明追踪入口完整，不能代替测试覆盖验证。
- 固定电脑、同机串行、排队超时取消并通知、运行默认 24 小时超时停止、四项人工控制、成功通知默认关闭、失败结果值可追溯、步骤可选等核心规则与访谈/PRD 一致。
- 云端原子占用和本机互斥分别承担不同边界；STARTING 回执丢失不直接回收占用，失联与终态分离，取消和授权由事务先后裁决。未将租约过期误写成远端进程已结束。
- 启动崩溃窗口、重连核对、旧代数拒绝、旧备份恢复暂停派发和 epoch 轮换已有设计要求；未承诺端到端业务恰好一次或自动回滚业务写入。
- Windows 用户会话 worker 与本机状态窗口分进程，UI 关闭不直接停止任务；Session 0、锁屏/RDP/注销、既有应用所有权和 Win10 兼容性均列出边界与 POC 门禁。
- 成功需要合法结果、正常退出及自有进程清理；缺结果、冲突、错误 run_id 不判成功。失败返回值与平台异常分开保存；通知事件去重与外部 Webhook 重发风险有明确区分。
- Python/浏览器自动准备先检查、后由人触发；准备范围、版本锁定、权限、时区、等待和告警阈值等仍标为建议或待冻结。原型中的展示值未当作产品默认值。

## 4 官方来源抽查

本次独立打开官方来源核验以下事实，未只依据搜索摘要。各事实只支持对应的技术边界，不证明现场兼容性。

| 官方来源 | 抽查结论 |
| --- | --- |
| [Playwright Python 安装要求](https://playwright.dev/python/docs/intro#system-requirements) | 当前页面列 Windows 11+、Windows Server 2019+、WSL；未列 Windows 10。方案将 Win10 列为兼容验证门槛有依据。 |
| [Microsoft Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects) | Job 可管理关联进程，但子进程归属存在 breakaway、创建方式及嵌套限制；不能从使用 Job 推断所有外部应用都被纳管。 |
| [Microsoft Interactive Services](https://learn.microsoft.com/en-us/windows/win32/services/interactive-services) | 服务与交互用户会话存在隔离；不能将系统服务直接等同为可操控用户桌面。 |
| [uv Python 选择与下载](https://docs.astral.sh/uv/concepts/python-versions/) | 支持明确解释器路径，缺失时默认可自动下载；官方提供关闭自动下载的配置/标志。检查阶段限制下载的设计有依据。 |
| [Prefect Windows 官方指南](https://www.prefect.io/docs/v3/how-to-guides/self-hosted/server-windows) | 官方描述原生 Windows process worker 支持，作为成品平台备选有依据；这不证明本项目进程树、桌面和恢复规则已满足。 |
| [APScheduler 版本历史](https://apscheduler.readthedocs.io/en/master/versionhistory.html) | 页面列 4.0 alpha 历史并保留预发布生产使用警示；采用已验证 3.x 触发计算的建议未被本次核验推翻。 |
| [PostgreSQL Versioning Policy](https://www.postgresql.org/support/versioning/) | 页面包含版本维护策略与支持表，17 当前列为受支持；用于修正 AR-02 的来源。 |

其余项目 Star、全部许可证/企业版限制、维护时间及所有传递依赖没有在本次重复逐项在线核验；仅核对已有调研与快照格式，不把这些未抽查字段表述为本次全部独立证实。钉钉真实接入、Windows 具体版本及开源候选的现场适配仍待后续验证。

## 5 实际检查证据

工作目录为 `D:\codex\autojobs`。文件读取和定向复核命令退出码均为 0；未运行产品、模板单元测试、Docker 或安装操作。

执行了以下只读解析命令，退出码 0：

```powershell
@'
from pathlib import Path
import json, re
root=Path.cwd()
tech=root/'docs/architecture/automation-control-platform-technical-design.md'
body=tech.read_text(encoding='utf-8')
for prefix,count in [('R',18),('AC',20),('Q',12)]:
    seen={int(x) for x in re.findall(r'\b'+prefix+r'(\d{2})\b',body)}
    missing=set(range(1,count+1))-seen
    print(f'{prefix}: explicit={len(seen)}, missing={sorted(missing)}')
paths=list((root/'docs/architecture/research').glob('*snapshot.json'))
for path in paths:
    contents=json.loads(path.read_text(encoding='utf-8'))
    print(path.name, 'valid JSON', type(contents).__name__)
print('No product or template unit tests executed.')
'@ | python -B -X utf8 -
```

实际输出为 R 18/AC 20/Q 12，均无缺失编号；三份快照均成功解析（组件为 list、编排和 Windows 为 dict）。这不是业务用例的通过数。

修订定向复核使用 `rg -n -C 2` 检查主方案中的 PostgreSQL 支持链接、operation_id、维护槽、M3 与 Q01 条款，退出码 0。主方案内容已与 AR-01/AR-02 的修订说明逐项比对。

## 6 质量状态和下一门禁

**AI 独立文档评审结论：通过。** 仅表示本次可定位的文档问题已修订、核心要求及可靠性边界有明确设计，不表示技术路线已完成工程验证。

Windows Job/会话兼容、真实机器互斥、授权/取消竞态、网络中断、运行与环境准备超时、SQLite/数据库恢复、通知送达、安全和性能测试均未执行。下一门禁为相关 Q 项冻结及 M0 Windows POC；通过后才能按阶段实施并取得真实证据。

Codex 自检通过不等于开发自测确认、人工代码评审、CI 验证或发布审批通过。
