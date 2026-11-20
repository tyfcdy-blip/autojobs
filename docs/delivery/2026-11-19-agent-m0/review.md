# M0 执行端独立 AI 审查记录

日期：2026-11-19，Asia/Shanghai。模式：独立审查。等级：L3；涉及本机并发、运行账本与 Windows 自有进程控制。审查只修改本记录，不修改实现与测试。当前目录不是 Git 仓库，无提交号或 Git 差异基线；结论针对本轮实际读取的文件及落盘测试记录。

最终结论：**M0 本机开发交付有条件通过；完整 M0 验收仍未完成，不允许发布。** R01–R05 已修复并有对应回归证据，无未关闭 P0/P1；本机实现范围的独立 AI 复核通过。Windows 10 现场和人工门禁未完成，不能据此承诺长期无人值守。

## 审查范围与边界

对照 [M0 计划](plan.md)、[技术方案](../../architecture/automation-control-platform-technical-design.md) 和 [接入规范](../../standards/script-integration.md)，检查 `apps/agent/src/autojobs_agent/`、对应测试及 `pyproject.toml`。重点为 Windows Job、句柄清理、跨状态目录的机器互斥、SQLite 幂等与事务、终态与重启恢复、排队截止、停止/完成顺序、结果有限解析、重解析路径、环境检查和只读窗口。

本轮是本机验证工具的审查，不要求 M0 已有云端调度、上传分发、钉钉或自动安装环境。开发机为 Windows 11，不能以本机证据替代两台 Windows 10 的锁屏、RDP、注销、浏览器登录和现场恢复验收。没有执行人工评审、CI 或发布审批。

## 发现、修订与复核

| 编号 | 等级 | 原始问题及位置 | 当前状态 |
| --- | --- | --- | --- |
| M0-R01 | P1 | `runtime.py` 原第 131–143 行：进程对象尚未返回时发生 `ProcessCleanupError`，仍记失败并释放槽；环境 probe 同类异常也受影响。Windows 创建后的异常清理另需确保所有未确认情况使用这一错误类型 | 已关闭：最终代码、八个新增 Windows 故障场景及 probe/spawn 回归均复核，JUnit 无失败 |
| M0-R02 | P2 | `runtime.py` 原 `_monitor`：运行中的长任务不清理到期队列，超时事件要等活动任务结束后才生成 | 已关闭：忙碌时过期用例在最终 JUnit 中通过 |
| M0-R03 | P2 | `runtime.py` 原第 197–203 行与 `journal.py` 第 350 行：合法 4096 字符消息追加平台说明后超限，原成功被改为通用失败，结构化结果丢失 | 已关闭：成功/失败两个消息边界用例在最终 JUnit 中通过，平台诊断保留 |
| M0-R04 | P2 | `contracts.py` 原第 57–63 行：先以跟随目标的 `exists()` 判断，断链 junction 因而绕过重解析限制 | 已关闭：真实断链 junction 回归在最终 JUnit 中通过 |
| M0-R05 | P2 | `environment.py` 允许检查最长 10 秒，但原循环不维护心跳；`status.py` 在 5 秒后显示离线，且预检期间到期队列也不处理 | 已关闭：真实慢检查、在线状态、忙时过期及取消用例在最终 JUnit 中通过 |

### M0-R01：未确认清理不能变成已释放

初次复现使用真实临时 SQLite 与准确的故障边界注入：领取一轮后，将环境检查替换为就绪，再让 `WindowsJobProcess.spawn` 抛出 `ProcessCleanupError`。没有创建业务进程。实际输出为 `state=failed`、`active=null`、`error=EXECUTION_ERROR`，与“不确定时占用并待核实”的要求矛盾。

修订后的 `runtime.py` 在检查到该错误时调用 `mark_interrupted()` 并重新抛出，即使 `process` 仍为 `None` 也保留占用；`environment.py` 将检查进程 `close()` 的异常转换为 `ProcessCleanupError`。`test_runtime_failures.py::test_cleanup_uncertainty_keeps_slot_before_process_return` 分别覆盖 probe/spawn，并检查 `reconciling`、占用仍在、不能再次领取。

最终 Windows 层已核验：`windows/process.py` 第 49–87 行的 `_stop_and_confirm` 在关闭句柄前同时检查 Job 活动数和入口进程信号；一个终止/核对 API 失败也继续尝试其余清理，保留任一失败并统一报告 `ProcessCleanupError`。未纳管入口同时处理 Job 和入口进程，不依赖不确定的分配结果。第 241–246 行最先运行失败启动清理回调，之后才关闭句柄；第 290–305 行将关闭异常统一包装，重复关闭仍保持失败，不把旧失败变成清理成功。

新增八个故障场景已逐条审查：创建时间查询、日志线程启动、恢复线程三个启动失败点；Job 终止、Job 统计查询、入口等待三个清理证据失败点；未纳管入口终止报错；资源关闭报错及再次关闭。测试创建真实自有进程，并检查 Job 归零、进程信号、进程退出和业务标记未写入；注入清理错误时先完成真实终止再模拟证据失败，避免遗留测试进程。主 agent 转达 Windows 工作包 `24 passed`、ruff/mypy 退出 0，以及 runtime 故障边界 `4 passed`。最终全量 JUnit 已逐项核对这些用例，无失败；本审查没有重复运行系统测试。

### M0-R02：忙碌时也要结束到期排队

初次复现用真实临时账本、0.03 秒队列时限及 0.2 秒的受控进程替身，执行 `_execute`。结束时等待轮次已超过截止约 0.204 秒，仍为 `queued`，待回传事件只有 `queued`。该复现验证运行循环遗漏，不证明 Windows 进程执行行为。

当前 `_maintenance()` 负责心跳与有节流的 `expire_queued()`，业务监督循环调用它。新增 `test_runtime.py::test_queue_expires_while_another_run_is_busy` 启动真实长任务，在它仍为 `running` 时验证第二轮已经 `queue_expired`、没有 PID 且有到期事件；不是只等前一轮结束后检查。最终 JUnit 记录该用例通过，用时 1.105 秒。

### M0-R03：摘要限制不得丢弃脚本结果

初次复现返回合法的 4096 字符 `message`、`success`、退出码 0，并使日志截断标志为真。执行边界实际保存为 `failed / EXECUTION_ERROR / result=null`。业务失败配退出码 0 时追加说明也会触发同类问题。

当前仅把平台展示 `message` 限制至 4096 字符并附摘要截断提示，完整脚本消息与返回值仍保存在结构化 `result`。新增 `test_maximum_message_keeps_original_result` 覆盖成功配日志截断、失败配退出码 0，检查业务状态、完整消息和摘要上限。代码与用例复核通过。

后续复核同时关闭了平台诊断被裁掉的建议：当前先独立组成 `diagnostics`，为必要诊断和摘要提示预留长度，再裁业务消息展示部分。回归用例明确断言日志截断提示保留；完整脚本结果未裁切。

### M0-R04：断链目录联接仍是重解析点

在审查自己的 Windows 临时目录创建普通目标和 junction，然后删除空目标。此时真实结果为 `junction.exists() == False`、`junction.is_junction() == True`。原 `require_plain_path(junction / "new-state")` 没有拒绝，返回已经不存在的目标目录下路径，后续创建状态目录会写到该目标位置。仅删除了审查创建的空目标和 junction，未操作现有目录。

当前无条件检查 `is_symlink()` / `is_junction()`，再使用不跟随目标的 `lstat()` 检查 Windows 重解析属性，只忽略路径不存在。新增 `test_contracts.py::test_dangling_junction_parent_is_rejected` 使用相同真实目录步骤，断言 `UNSAFE_PATH` 且未创建目标。最终 JUnit 记录该用例通过，用时 0.086 秒；本审查遵循协作要求，不重复进行系统目录实验。

### M0-R05：环境检查期间维护状态

这是代码路径推导出的稳定性问题，未把推导写成已执行测试。原 `_probe_python` 可等待 10 秒，`StatusReader` 心跳在线阈值为 5 秒。现在 `inspect_environment` 接受 `on_poll`，probe 等待循环调用该回调；worker 传入 `_maintenance`，因而预检等待时也能更新心跳及处理到期队列。

已复核 `test_runtime.py::test_slow_probe_keeps_heartbeat_and_expires_other_requests`：只替换 probe 入口为先等 6 秒、再执行原检查脚本的包装，仍使用真实 Job/解释器/账本；验证检查期间另一轮到期、超过旧在线阈值后心跳仍在线，以及取消后未启动业务。主 agent 报告该定向用例 `1 passed in 7.07s`；最终全量 JUnit 中该用例通过，用时 6.622 秒。本审查没有重复执行。

## 已核对的其他边界

- 机器互斥默认名固定为 `Global\AutojobsAgentWorker-v1`，不依赖状态目录。获取失败不另换锁名；同线程多 wrapper 重入也被拒绝。worker 获取机器锁之后才把旧活动记录标为待核实。
- SQLite 使用 `BEGIN IMMEDIATE`、唯一活动槽索引以及事务内的状态和事件写入；重复提交不延长截止，相同终态重放不新增事件，冲突终态被拒绝。重启不重跑未完成记录，`reconciling` 继续占用。
- 结果文件读取有字节上限，拒绝重复 JSON 键、非有限数、非法 UTF-8、错误 run 标识和不受支持协议；成功需要合法业务成功、退出码 0 及 Job 无活动进程。普通 stdout 不充当最终结果。
- 代码先检查自然完成，再处理本轮尚未观察到的停止请求；已观察到停止后保持停止流程。排队取消与领取在事务内裁决，已领取的停止不会被 `set_running` 覆盖。
- worker 与窗口入口独立；状态读取使用只读账本，不初始化缺失目录。窗口桥只暴露状态读取。现有真实窗口集成用例检查关闭窗口后 worker 和任务仍在运行，本审查没有再次打开窗口或宣称人工视觉验收。
- 环境 probe 使用声明的解释器执行独立标准库文件，读取包元数据，不依赖 worker 已安装包来推断业务环境。浏览器版本、登录与会话能力明确未验证；此处不是自动安装环境实现。
- 路径检查属于受信脚本工具的输入边界，不应宣称它构成恶意脚本安全沙箱。本审查没有扩展到未实现的云端认证/授权和生产部署。

## 实际证据与验证边界

审查执行的诊断命令：

1. `git status --short --branch`：退出 1，实际输出不是 Git 仓库；没有可用分支/提交基线。
2. `@' ... '@ | & apps/agent/.venv/Scripts/python.exe -`：退出 0；内联脚本使用 `TemporaryDirectory`、真实 `Worker/Journal` 和限定的 `unittest.mock.patch`，依次复现 R01/R03/R02。原始输出如下。没有启动真实业务进程、全局 worker 或访问网络。
3. 同一解释器执行仅创建审查临时 junction 的内联脚本：退出 0，真实观察到断链联接被原路径函数接受。脚本 `finally` 清理自己的联接。
4. 修订后只读复核相关实现和新增用例；按主 agent 分工，不重跑系统操作、全套测试或目录实验。主 agent 已报告进程专项 24 项、runtime 故障边界 4 项、慢检查 1 项通过；这是执行者提供的定向结果，不是本审查独立执行的测试日志。
5. 只读解析 [agent-junit.xml](agent-junit.xml)，核对全量 `tests=139 / failures=0 / errors=0 / skipped=0`，并逐项定位 R01–R05 的回归用例。XML suite 时间为 36.878 秒；执行者报告 pytest 摘要为 `139 passed in 37.12s`，属于不同计时口径。

```text
{"case": "spawn_cleanup_unknown", "state": "failed", "active": null, "error": "EXECUTION_ERROR"}
{"case": "max_message_log_truncated", "state": "failed", "result": null, "error": "EXECUTION_ERROR"}
{"case": "queue_during_busy", "state": "queued", "seconds_past_deadline": 0.204, "events": ["queued"]}
```

上述三项为确认缺陷的定向实验，不能记为产品测试“3 项通过”。没有伪造构建、性能或现场结论。

主 agent 最终执行的全量命令及退出码：工作目录 `D:\codex\autojobs\apps\agent`，命令 `uv run --frozen --extra desktop pytest tests -q --junitxml=../../docs/delivery/2026-11-19-agent-m0/agent-junit.xml`，退出 0。落盘 XML 已由本审查独立读取，计数和关联用例一致。ruff、mypy（15 个文件）、Vue 16 项测试/typecheck/build 与 Python 包构建均由主 agent 报告退出 0；本审查没有将这些报告计作自己执行的检查，完整命令与构建结果由交付总报告保存。

额外只读复核 `tests/unit/test_project_tools.py` 第 239–242 行的测试数据修订：该用例原本验证“未登记验证命令”，而 fixture 复制了当前已登记命令的项目配置。现在仅在该用例把各 `verification` 列表设空，再记录新的不变性比较基准；仍保留退出 0、“尚未配置”、文件字节不变及没有生成环境文件的全部断言。没有修改模板业务实现，也没有降低原断言。

主 agent 提供的模板复验：仓库根目录执行 `python -X utf8 -m unittest discover -s tests/unit -v`，退出 0，27 项用时 8.283 秒，其中 24 通过、0 失败、3 跳过。3 项为原有符号链接用例，受本机创建权限限制；未增加跳过。真实 junction 回归在 agent 的 139 项中实际执行通过。此为执行者报告，未冒称本审查重复实测，模板数量不与 agent 混计。

## 当前质量状态

- 独立 AI 静态审查：已执行；R01–R05 的最终修订及回归设计复核通过。
- R01–R05：已关闭；最终 139 项全量回归证据已读取，无失败/错误/跳过，未发现未关闭 P0/P1。
- 慢预检维护及长消息平台诊断保留：代码和针对性用例已复核。
- 本审查自动化执行：完成原缺陷定向实验及最终 XML 读取；最终全套回归由主 agent 执行，未冒称重复实测。
- 人工专项评审、两台 Win10 现场验证、CI、开发最终确认和发布审批：未验证/未执行，不允许据此发布。

**Codex 自检通过不等于开发自测确认、人工代码评审、CI 验证或发布审批通过。**
