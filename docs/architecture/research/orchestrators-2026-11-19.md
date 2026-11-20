# 自动化脚本中台：编排与调度平台调研

调研标签日期：2026-11-19（Asia/Shanghai）。模式：开发后自检；等级：L1，仅文档与公开资料快照，无依赖安装、代码引入或部署。本文为选型证据，不是已经验证的产品能力。Git 未初始化，无法提供 Git 基线或差异。

## 1. 从本项目约束得出的判断

本项目当前只有两台固定 Windows 10 执行电脑、十几个现有 Python 脚本。决定方案适配性的关键是：机器级串行、原生浏览器及已有登录态、进程树终止、失联后的执行状态核对、多个 Python 环境、脚本包分发，以及本地状态窗口。调度表达式和流程画布只是其中一部分。

**建议采用轻量自有中台与 Windows 执行端，复用成熟基础组件；不要以高 Star 为理由直接深度改造大型编排平台。** 这是基于功能边界与当前规模的工程推断，尚无实施成本实测。若希望优先验证“直接采用现成平台”，应先做 **Prefect process worker** 小型验证；若可接受商业授权，**Windmill 企业版原生 Windows/HTTP Agent** 是值得比较的候选。现成平台不能仅凭“支持 Windows”就判定已解决桌面会话和断网防重复执行。

## 2. GitHub 热度与许可证事实

精确查询记录见 [GitHub 快照](orchestrators-github-snapshot.json)。本地 GitHub REST API 首轮 8 次请求均 HTTP 403 限流，已保留失败；随后通过浏览工具读取官方 API 得到 4 个仓库，另外 3 个采用 GitHub 官方 HTML 内的 `stargazerCount`。API 缺失字段保持“未验证”，没有用页面最后提交时间冒充 `pushed_at`。

API 内容经浏览工具读取，缓存提示为当天或前一天；工具没有提供原始 HTTP Date，快照的 `web_api_observed_at_utc=2026-11-19T09:39:40.481973+00:00` 是观察记录时间。HTML 在 `2026-11-19T09:38:46Z` 左右请求，响应 Date 为 09:38:48–49 GMT。Stars 会继续变化。

| 项目与官方仓库 | 精确 Stars | `archived` / `pushed_at`（UTC） | GitHub API SPDX 与许可证边界 |
| --- | ---: | --- | --- |
| [Prefect](https://github.com/PrefectHQ/prefect) | 24,185 | false / 2026-11-19T08:11:53Z | API：Apache-2.0 |
| [Apache Airflow](https://github.com/apache/airflow) | 47,536 | false / 2026-11-19T04:09:17Z | API：Apache-2.0 |
| [Windmill](https://github.com/windmill-labs/windmill) | 18,640 | 未验证 / 未验证 | API 未取到；源码混合 AGPLv3、Apache-2.0 与专有授权，见下文 |
| [Kestra](https://github.com/kestra-io/kestra) | 30,265 | false / 2026-11-18T03:33:53Z | API：Apache-2.0；企业版功能另计 |
| [n8n](https://github.com/n8n-io/n8n) | 211,184 | false / 2026-11-19T04:52:55Z | API：NOASSERTION；Sustainable Use License 与企业授权，源代码可用，不能等同宽松开源 |
| [Dagster](https://github.com/dagster-io/dagster) | 16,444 | 未验证 / 未验证 | API 未取到；[根 LICENSE](https://raw.githubusercontent.com/dagster-io/dagster/master/LICENSE) 为 Apache License 2.0 |
| [XXL-JOB](https://github.com/xuxueli/xxl-job) | 30,673 | 未验证 / 未验证 | API 未取到；[当前根 LICENSE](https://raw.githubusercontent.com/xuxueli/xxl-job/master/LICENSE) 为 GPLv3 |

四个 API 来源分别是 [Prefect API](https://api.github.com/repos/PrefectHQ/prefect)、[Airflow API](https://api.github.com/repos/apache/airflow)、[Kestra API](https://api.github.com/repos/kestra-io/kestra)、[n8n API](https://api.github.com/repos/n8n-io/n8n)。API SPDX 只是仓库级检测值，不能代替具体引入文件及版本的许可证核对。

仓库名称核对：`https://github.com/xxl-job/xxl-job` 实际重定向到 `xxl-job/xxl-job-admin`，仅 20 Stars，不是本次比较的高 Star 主仓库；[XXL-JOB 官方站](https://www.xuxueli.com/xxl-job/) 的 GitHub 链接指向 `xuxueli/xxl-job`。

## 3. 适配比较

以下复杂度是相对本项目规模的判断，不是性能测试或费用报价。“借鉴”表示参考公开设计；不表示复制源代码或已引入依赖。

| 候选 | 已核实能力与部署形态 | 本场景缺口 | 建议 |
| --- | --- | --- | --- |
| Prefect | 原生 Windows process worker；Python flow、调度、运行记录。官方 Compose 示例含 PostgreSQL、Redis、API、后台服务和 worker | 仍需对脚本做 flow/子进程适配；本地状态窗口、预检与准备环境、机器级锁、会话与浏览器进程归属需补齐 | **现成平台验证第一候选**；优先通过 API/扩展集成，暂不 fork 核心 |
| Airflow | Python DAG、成熟调度与执行记录；官方生产部署支持 Linux | 官方不支持原生 Windows 生产部署；WSL/Linux 容器不能直接视为对既有 Windows 桌面任务的支持 | 当前不作底座；可参考调度与执行记录分离 |
| Windmill | 脚本、依赖解析、运行结果、UI；服务端可 Compose 部署；原生 Windows worker 与仅 HTTP 连接的 Agent 已有 | Windows worker 明确为 Self-Hosted Enterprise；HTTP Agent 为 Cloud/Self-hosted Enterprise。不是免费社区版直接满足；桌面会话仍待实测 | **有商业预算时验证整套使用**；无预算则参考产品结构，避免混用许可证 |
| Kestra | YAML 流程、脚本插件、Docker/Process runner；Windows 可运行独立 JAR；服务端 Compose + PostgreSQL | Process runner 支持 Windows，但固定到指定机器通常需要核对 Worker Groups；官方将 Worker Groups 标为 Enterprise。多维护一层 JVM/插件 | 若未来发展为跨系统多语言流程再比较；当前不优先二开 |
| n8n | 可视化集成流程、Webhook、Python/JS Code node；生产推荐外部 task runner，常用 sidecar 容器 | Code node runner 不等于具备本项目全部能力的 Windows 桌面执行端；仍需自建固定主机路由、环境管理、运行协议；有 SUL/EE 边界 | 可作为未来集成/通知外围；不建议作为执行主控 |
| Dagster | Python 数据资产/任务编排；安装指南含 Windows；典型 Compose 包含 webserver、daemon、code locations、数据库，并按运行启动容器 | 数据资产、血缘模型超出当前“管电脑和脚本”的主要需求；安装支持不证明桌面 Agent 生命周期已解决 | 数据链路治理成为主需求时再评估；当前参考运行元数据 |
| XXL-JOB | Java 调度中心与执行器、GLUE Python/PowerShell、命令行任务、阻塞策略、日志、失败告警扩展 | 当前代码按 `jobId` 维护执行线程，“单机串行”不能直接当成整台电脑所有不同任务互斥；Java 执行器网络连接及 Windows 桌面清理需验证 | 参考中心/执行器分离与日志告警；不建议为了十几个 Python 脚本深度 fork |

核验来源：

- Prefect：[Windows 原生执行](https://www.prefect.io/docs/v3/how-to-guides/self-hosted/server-windows)、[Process worker API](https://reference.prefect.io/prefect/workers/process/)、[Docker Compose 结构](https://www.prefect.io/docs/v3/how-to-guides/self-hosted/docker-compose)。
- Airflow：[官方支持平台与安全模型](https://airflow.apache.org/docs/apache-airflow/stable/security/security_model.html)。
- Windmill：[Windows workers](https://www.windmill.dev/docs/misc/windows_workers)、[HTTP Agent workers](https://www.windmill.dev/docs/core_concepts/agent_workers)、[部署说明](https://www.windmill.dev/docs/advanced/self_host)。
- Kestra：[Windows 安装](https://kestra.io/docs/installation/windows)、[Process runner](https://kestra.io/docs/task-runners/types/process-task-runner)、[Worker Groups 企业版边界](https://kestra.io/docs/task-runners/task-runners-vs-worker-groups)、[Compose 部署](https://kestra.io/docs/installation/docker-compose)。
- n8n：[task runner 定位和外部运行模式](https://docs.n8n.io/deploy/host-n8n/configure-n8n/set-up-task-runners.md)。
- Dagster：[Windows 安装步骤](https://dagster.io/docs/getting-started/installation)、[Compose 结构](https://dagster.io/docs/deployment/oss/deployment-options/docker)。
- XXL-JOB：[官方 README](https://github.com/xuxueli/xxl-job)、[按 jobId 维护线程的官方源码](https://raw.githubusercontent.com/xuxueli/xxl-job/master/xxl-job-core/src/main/java/com/xxl/job/core/executor/XxlJobExecutor.java)。

## 4. 两个容易误判的授权边界

**Windmill 的源码构建与官方 Community Edition 分发物要分开看。** 根 LICENSE 写明：通常源码为 AGPLv3；部分 client/OpenAPI 为 Apache-2.0；企业代码为专有授权。官方 Community Docker/binary 还包含非开源部分，其原样内部使用/API 使用与修改、包装、转售等情形的授权条件不同。因此不能只写“Windmill = AGPL，随便改造”。实际引入前应固定版本、文件清单和使用方式再复核。[Windmill LICENSE](https://raw.githubusercontent.com/windmill-labs/windmill/main/LICENSE)

**n8n 是源代码可用候选，不与 Apache-2.0 项目混称。** 主分支普通部分采用 Sustainable Use License，文件名/目录名带 `.ee` 的企业部分另有授权。SUL 包含内部业务、非商业用途及分发限制。内部自动化可以列为候选，不代表允许把整套产品任意包装后对外销售。本次没有做法律合规审批。[n8n LICENSE](https://raw.githubusercontent.com/n8n-io/n8n/master/LICENSE.md)

## 5. 可借鉴能力及验证顺序

1. **借鉴 Prefect 的控制面/执行面分离。** 中台只产生运行实例，执行端领取并报告。现有脚本与中台协议通过一层薄适配连接，业务脚本不用承担网络重试和设备管理。
2. **借鉴 Windmill 的脚本、版本、依赖、结果与运行历史拆分。** 脚本上传不等于环境可运行；检查缺失组件、人工点击准备、准备结果和真正执行应有独立记录。
3. **借鉴 XXL-JOB 的失败告警和运行日志入口，但重新定义机器级占用。** 锁的粒度必须是执行电脑，不能只限制同一个脚本的重入。
4. **保留平台扩展点，先不引入 DAG/画布。** 当前固定机器、单任务串行与明确返回值足够形成第一版闭环；未来确需任务依赖再设计编排，不同时维护自有调度和另一平台调度两份事实来源。

采用任何候选前都应使用同一组验证：一台机器两种不同任务不能同时运行；断网时已启动任务不重复启动；重连能补传同一运行实例结果；超时及手动停止能清理本次启动的进程树而不误杀原有应用；窗口关闭不停止执行端；重启/锁屏/远程桌面断开场景下浏览器行为明确；两个 Python 解释器与依赖隔离正确；钉钉发送失败有独立记录并有限重试。这些是本项目验收需求，不是上述平台已被证明的特性。

## 6. 本次验证边界与记录

| 检查 | 实际结果 |
| --- | --- |
| GitHub REST API 直接请求 | 8 次 HTTP 403，保留真实失败 |
| 浏览工具读取官方 API | 4 个成功，Stars/SPDX/archived/pushed_at 已入 JSON |
| 官方 GitHub HTML 后备读取 | 4 个 HTTP 200：3 个候选及 1 个错误仓库路径重定向核对 |
| 官方文档与许可证 | 已核对上述链接；未复制或引入源码 |
| 文档与快照一致性 | Python 标准库内联检查实际退出码 0；13 项通过、0 失败、0 跳过，检查 7 个候选、正整数 Stars、4 个 API 完整字段、3 个缺失字段保持 null、8 个限流记录、重定向、正文数值及本地链接 |
| 部署、业务测试、Windows GUI/故障恢复、安全性能 | 未执行；此次没有业务实现，不适用“业务测试通过”的结论 |
| 3 个仓库 API `pushed_at` / `archived` / 自动 SPDX | 未验证，需后续 API 限额恢复后补查；不影响已经依据官方 LICENSE 得到的文字说明 |

本次自检仅覆盖来源、快照结构和事实/推断区分。建议结论为“有条件通过”：资料足以支持第一轮路线比较，实际技术兼容、实施成本和故障语义仍需小型验证。Codex 自检通过不等于开发自测确认、人工代码评审、CI 验证或发布审批通过。
