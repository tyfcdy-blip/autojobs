# Windows 10 本机执行端测试包

版本 0.1.0，整理日期 2026-11-20。本包用于两台执行电脑的隔离兼容验证，**现场结果均未验证**。它包含已在 Windows 11 验证的 wheel、源码快照、锁定依赖清单、合成 CSV 示例和现场记录。

## 1 准备

安排没有业务任务运行的时间。两台电脑分别解压到一个新目录，例如个人测试目录下的 `autojobs-m0-test`。不要覆盖现有环境；全部命令在解压后的包根目录执行，每条成功后再执行下一条。

需要电脑已有 Python 3.12、uv、可用网络；打开窗口还需要 WebView2。无需安装 Node 或重新构建前端。Python/uv/WebView2 不存在或安装失败时记录缺项，先由维护人员安排；以下命令不会自动下载 Python，不更改系统执行策略。

先填写 [现场记录](现场记录.md) 的电脑信息。包内 `SHA256SUMS.txt` 列出文件摘要，可用 PowerShell `Get-FileHash -Algorithm SHA256 <文件名>` 对照。

## 2 在独立目录安装

确认本目录还没有 `.venv`；若已有测试记录，保留它们，另取全新解压目录进行新的安装验证。

```powershell
uv venv --python 3.12 --no-python-downloads .venv
uv pip sync --python .venv/Scripts/python.exe --require-hashes --link-mode copy requirements-runtime.txt
uv pip install --python .venv/Scripts/python.exe --no-deps --link-mode copy autojobs_agent-0.1.0-py3-none-any.whl
```

依赖仅安装到该包目录的 `.venv`。第二条需联网获取锁定依赖，本包不是完整离线安装器。任一步失败就保留错误输出，不继续后续命令。

## 3 先验证无外部调用示例

```powershell
.venv/Scripts/python.exe examples/create_example.py sample-task
.venv/Scripts/autojobs-agent.exe --state-dir state check sample-task/task.json
.venv/Scripts/autojobs-agent.exe --state-dir state submit sample-task/task.json --run-id field-sample-001
.venv/Scripts/autojobs-agent.exe --state-dir state serve --once
.venv/Scripts/autojobs-agent.exe --state-dir state show field-sample-001
```

预期：实际读取生成的两行 CSV，最终状态 `succeeded`，结果 `processed_rows: 2`。示例不会访问浏览器、网络接口或数仓。生成器拒绝覆盖已存在的 `sample-task`；重复同一运行编号不会重新执行业务。不要删除运行账本来绕过异常状态。

## 4 打开常驻程序与窗口

在第一个 PowerShell 窗口执行：

```powershell
.venv/Scripts/autojobs-agent.exe --state-dir state serve
```

在第二个 PowerShell 窗口进入同一个解压目录，执行：

```powershell
.venv/Scripts/autojobs-agent.exe --state-dir state window
```

预期：窗口显示“本地验证模式 / 尚未连接中台”，常驻程序在线，可查看刚才的真实记录。关闭窗口不退出第一个窗口中的 worker；需要停止 worker 时在第一个窗口按 Ctrl+C。当前没有托盘、开机启动或生产恢复放行功能。

## 5 自动化与现场兼容验证

先停止上述 worker，避免机器级锁与测试冲突。源码快照来自同一构建，含预构建页面，使用独立的源码开发环境运行测试：

```powershell
.venv/Scripts/python.exe -m tarfile -e autojobs_agent-0.1.0.tar.gz source
cd source/autojobs_agent-0.1.0
uv sync --frozen --extra desktop --no-python-downloads
uv run --frozen --extra desktop pytest -q --junitxml=field-junit.xml
```

首次执行前确认没有 `source` 目录，避免覆盖旧记录。记录真实通过/失败/跳过数及 `field-junit.xml`。测试使用临时脚本、自有进程和 SQLite；窗口用例需要 WebView2；浏览器用例使用独立 profile 和本地 HTML，跳过时必须记录原因。测试通过不等于真实网页登录或会话兼容已验证。

随后由维护人员按现场记录逐项验证：窗口关闭/重开、隔离长任务停止、锁屏、RDP 断开（如使用）、注销/重启、自启动浏览器和连接已有应用。只使用批准的测试任务/测试账号，不以现有生产任务试错；当前合成 CSV 示例运行很快，不能用于证明“锁屏期间长任务仍运行”。长任务和登录场景需结合现场脚本另行准备，再确认其可安全执行。

重启/注销后需手工启动 worker；旧活跃运行应保留为 `reconciling`，不能据此自动重跑或放行后续任务。登录失效/扫码当前仍由人工恢复，脚本应按业务实际返回失败。每项记录预期、实际、时间和证据。

## 6 保存结果

两台电脑各填一份“现场记录”，不要把第一台结论复制为第二台通过。返回软件版本、测试计数和脱敏错误即可；不分享密码、Cookie、Token、Webhook、原始业务数据或含敏感返回的完整账本。

当前包不包含云端连接、定时中台、上传分发、业务环境自动安装或钉钉。现场验证与人工评审完成前，不用于生产长期运行。Codex 自检通过不等于开发自测确认、人工代码评审、CI 验证或发布审批通过。
