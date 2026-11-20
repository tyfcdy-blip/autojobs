# autojobs Windows 执行端 · M0

这是已实现的本机执行基础与验证工具，包含 Python worker、持久队列/运行账本、环境检查和独立 Vue 状态窗口。**当前是本地验证模式，尚未接入云端中台、定时计划、脚本上传、环境自动安装或钉钉。** 本机界面会明确显示该状态，不以演示数据冒充连接状态。

开发基线为 Windows 11、Python 3.12；两台 Windows 10 的现场兼容性待验证。本程序执行经维护人员信任的脚本，不是恶意脚本安全沙箱。只结束本轮 Job 内的进程，不按进程名关闭已有浏览器。

## 安装与构建

以下命令从本目录 `apps/agent/` 执行。需本机已有 Python 3.12 和 uv；本机窗口需 WebView2。开发前端需 Node 24.15–24.x、pnpm 11.9.0，锁文件为唯一安装基准。

```powershell
uv sync --frozen --extra desktop
pnpm --dir desktop-ui install --frozen-lockfile
pnpm --dir desktop-ui build
```

Python 依赖只装到本目录 `.venv`；不会修改任何业务脚本环境或系统 Python。正式发布前仍需人工专项评审、第三方许可核查及 Windows 10 现场验证。

## 可直接运行的本地示例

以下首次执行会在项目忽略的 `data/tmp/` 生成独立测试文件。目标已存在时生成器拒绝覆盖；重复演示请换一个新的目录名。

```powershell
uv run --frozen --extra desktop python examples/create_example.py ../../data/tmp/agent-example-01
uv run --frozen --extra desktop autojobs-agent --state-dir ../../data/tmp/agent-state-01 check ../../data/tmp/agent-example-01/task.json
uv run --frozen --extra desktop autojobs-agent --state-dir ../../data/tmp/agent-state-01 submit ../../data/tmp/agent-example-01/task.json --run-id local-example-001
uv run --frozen --extra desktop autojobs-agent --state-dir ../../data/tmp/agent-state-01 serve --once
uv run --frozen --extra desktop autojobs-agent --state-dir ../../data/tmp/agent-state-01 show local-example-001
uv run --frozen --extra desktop autojobs-agent --state-dir ../../data/tmp/agent-state-01 window
```

预期：示例读取实际生成的两行 CSV，结果为 `succeeded`、`processed_rows: 2`。`serve --once` 完成一轮后退出，因此随后打开窗口时“执行程序离线”是正常状态，历史结果仍在。

要持续运行，在一个终端执行不带 `--once` 的 `serve`，另一个终端打开 `window` 或提交任务。worker 与窗口是两个独立进程；关窗口不退出 worker。当前 M0 **没有托盘及安装器**，关闭后可重新执行 `window`；完整托盘/开机启动仍在后续阶段。

```powershell
uv run --frozen --extra desktop autojobs-agent --state-dir ../../data/tmp/agent-state-01 serve
uv run --frozen --extra desktop autojobs-agent --state-dir ../../data/tmp/agent-state-01 stop local-example-001
uv run --frozen --extra desktop autojobs-agent --state-dir ../../data/tmp/agent-state-01 status
```

运行中的停止先给脚本取消标记，超过声明的清理宽限再强制结束本轮 Job。`Ctrl+C` 停止 worker 时也走清理流程。不要为了恢复待核实任务而删除账本或换状态目录重新运行。

## 当前接入协议

任务声明采用 UTF-8 JSON，入口为声明文件所在目录内的相对 `.py` 文件；必须指定 Python 绝对路径和正数排队时限。运行默认 86,400 秒，清理宽限默认 10 秒；这两个时限可在声明覆盖。M0 数值边界为排队/运行不超过一年，清理宽限 0–300 秒。正式中台配置将在后续接口阶段统一。

支持 `requirements`（PEP 508 包名/版本/marker，当前不支持 extras/直接 URL）、`required_files`（固定文件）、`browser_executable`（仅检查路径）。环境检查读取目标解释器及包元数据，**不导入业务依赖、不安装、不升级**；浏览器版本、登录状态、锁屏/桌面兼容性会明确列为未验证。

执行端提供 `AUTOJOBS_RUN_ID`、`AUTOJOBS_RESULT_PATH`、`AUTOJOBS_CANCEL_PATH`，并通过受控 `PYTHONPATH` 提供标准库实现的 `autojobs_agent.script_sdk`。脚本可以使用：

```python
from autojobs_agent.script_sdk import cancellation_requested, write_result

write_result("success", "本轮处理完成", {"processed_rows": 2})
```

返回值应取自实际业务，示例仅说明接口。脚本完成清理并退出后，执行端还会确认自有子进程全部结束。没有结果、错误轮次、非法 JSON、成功配非零退出码都不能算成功。结果最大 1 MiB，消息最多 4,096 字符；普通 stdout/stderr 各最多保存 1 MiB，超限继续排空并标记截断。

不继承宿主的无关密钥环境变量；如业务需要认证，须在后续正式配置协议中设计，不把凭据加入示例或命令行。当前固定文件只是检查存在性，不代表已验证所有业务内容及访问权限。

## 账本、恢复与窗口边界

- `journal.sqlite3` 保存请求、状态、结果及待回传事件；事件写入与状态同事务。当前未连接云端，待回传数量不会自动归零，CLI 没有“假确认上报”命令。
- 所有 worker 使用固定机器级命名互斥，不因更换状态目录同时运行多个任务。
- 重复相同 `run_id` 与请求不会再执行；同标识不同内容拒绝。新一轮需要新标识。
- worker 意外退出后，未完成记录转为 `reconciling` 并保留占用。M0 不提供无条件解除占用入口；真实进程及业务副作用需核实后再通过后续恢复流程处理。
- `runs/<运行标识摘要>/` 保存结果、两条日志和环境检查，避免 Windows 保留文件名与路径歧义；旧轮次目录不覆盖。
- 窗口仅通过 `get_status()` 读取本地状态，不创建数据库、不接收远程命令。最近记录上限 50，超大结果窗口仅展示标注的摘要，完整结果留在账本。
- 单轮日志有界，但本地总队列、运行保留及磁盘配额尚未实现完整运维策略，不能作为长期生产部署使用。

## 验证命令

```powershell
uv run --frozen --extra desktop ruff check src tests examples
uv run --frozen --extra desktop mypy src/autojobs_agent
uv run --frozen --extra desktop pytest -q
pnpm --dir desktop-ui typecheck
pnpm --dir desktop-ui test
pnpm --dir desktop-ui build
uv build
```

Windows 测试在临时目录启动自有进程；浏览器用独立临时 profile 和本地 HTML，不连接现有用户登录态。真实 WebView2 桥接测试打开隐藏测试窗口并自动关闭，确认 worker 仍继续运行。完整证据与未验证项见 [M0 交付记录](../../docs/delivery/2026-11-19-agent-m0/report.md)，后续步骤见 [Windows 10 现场验收](../../docs/runbooks/windows-agent-m0-acceptance.md)。

前端依赖的许可文本随包保存在 `src/autojobs_agent/THIRD_PARTY_NOTICES.txt`。更新前端依赖时应同步核对许可快照；版本、来源和当前审核边界记录在 M0 交付文档中。
