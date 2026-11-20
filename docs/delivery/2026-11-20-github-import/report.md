# 当前项目导入 GitHub 与 CI 修复记录

日期：2026-11-20，Asia/Shanghai。模式：修复与复验（首次上传后发现 CI 编码问题）。等级：L1，整理版本控制、首次项目导入与 CI 环境修复，不修改业务实现。用户明确要求初始化当前项目并上传到 `https://github.com/tyfcdy-blip/autojobs`，本轮 commit/push 已获授权，不再次请求确认。

## 基准与范围

开始时本地没有 Git，远程 `main` 为 `add6897f527622da08dc4dd462ae187a6a3f7731`，只有内容为 `# autojobs` 的 README。初始化本地 `main` 后取回该提交，以它作为父历史并保留全部本地文件，不强推、不删除远程历史。

提交范围是当前源码、依赖锁文件、工程模板、产品/技术文档、原型和脱敏测试证据。沿用现有忽略规则，排除 `.env`、虚拟环境、node_modules、缓存、临时运行数据、日志和 `dist/` 测试包。可直接运行窗口所需的离线页面资源继续纳入版本控制。

文档只同步当前 Git 状态和本轮证据，历史交付中的无 Git、未执行 CI 等记录保留原时点事实。Git 作者使用当前电脑已配置的用户身份，不伪造身份或改全局配置。

## 已执行检查

| 检查 | 实际结果 |
| --- | --- |
| 远程分支/历史只读查询 | main 初始提交；再次经 GitHub HTTPS 查询摘要一致 |
| 待提交文件枚举与大小 | 首轮 152 文件约 9.98 MB；最大单文件约 1.64 MB，无超大文件 |
| 内容扫描 | 私钥标记、GitHub/OpenAI/AWS token、钉钉真实 Webhook、带凭据 URL 及常见敏感赋值模式均无命中；不宣称完整安全审计 |
| `python -X utf8 scripts/check_project.py` | 退出 0；38 必要文件、13 目录、配置有效 |
| `python -X utf8 -m unittest discover -s tests/unit -v` | 退出 0；27 项，24 通过/0 失败/3 跳过，9.155 秒 |
| `uv run --project apps/agent --frozen --extra desktop pytest apps/agent/tests/test_contracts.py -q` | 退出 0；22 通过，0 失败/跳过 |
| `uv run --project apps/agent --frozen --extra desktop ruff check apps/agent/src/autojobs_agent/contracts.py` | 退出 0 |

3 项跳过是既有的符号链接权限用例，未更改断言或扩大跳过。原执行端/UI 实现未改，不重复运行已记录的 139 项 agent 和 16 项 Vue 测试；原证据见 [M0 报告](../2026-11-19-agent-m0/report.md)。

首次暂存检查发现 4 处格式问题：contracts.py 末尾多余空行、许可文本与两份原型提示词的行尾空格。仅去除这四处空白，不改代码逻辑、许可文字或提示词内容；契约用例和 Ruff 已针对性复验。此前生成的测试 ZIP 保留为原构建快照，不改写历史产物摘要。

本机 Git 直连 GitHub 超时，随后使用当前电脑已有的系统代理，通过 GitHub HTTPS 正常读取远程。仅在本仓库 `.git/config` 设置连接方式，不更改全局配置；代理配置与本机凭据不会提交。

## 提交前后门禁

随后执行暂存范围检查、忽略规则核对、`git diff --cached --check`，再创建提交和正常推送 `main`，并比较远程/本地提交摘要。此文件记录提交前已完成的证据，不把尚未发生的推送或 CI 写成已成功；最终结果以 Git 记录及本轮交付回复为准。

当前没有业务构建或数据迁移改动，相关专项门禁不适用。没有生产发布、数据库连接或实际执行机操作。上传源代码不等于允许生产部署，两台 Windows 10 现场门禁仍未完成。

本地检查通过，远程推送与 CI 需要分别核实。Codex 自检通过不等于开发自测确认、人工代码评审、CI 验证或发布审批通过。

## 首次推送与 CI 修复

首次提交 `36472744c79698117d40504cc9527572446745f8` 已正常推送到 `origin/main`，153 个文件；`git ls-remote` 与本地 HEAD 完全一致，工作区干净，原初始提交仍为父历史。上述“提交前”段落保留当时证据。

[首轮 GitHub Actions](https://github.com/tyfcdy-blip/autojobs/actions/runs/44653080943) 总体失败。读取实际日志定位到两个 Windows 任务的 `Check template`：Python stdout 为 cp1252，中文提示触发 `UnicodeEncodeError`；Ubuntu 的相同步骤通过。这是输出编码问题，不能删除 Windows 测试或降低模板检查。

缺陷 Git-CI-01，P2：仅在 `.github/workflows/template-check.yml` 设置 `PYTHONUTF8=1` 和 `PYTHONIOENCODING=utf-8`，不改系统环境、权限、矩阵、检查脚本或测试断言。

本地以 `PYTHONUTF8=0 / PYTHONIOENCODING=cp1252` 重现同一错误，退出 1；切换到工作流声明的 UTF-8 后，`python scripts/check_project.py`、`python -m unittest discover -s tests/unit -v`、`python -m compileall -q scripts tests` 均退出 0。模板测试 27 项，24 通过、3 原有权限跳过，用时 8.769 秒。完整命令和实际输出见 [编码复验证据](ci-encoding-verification.json)。

该修复按单独追加提交推送，不重写首次提交。此修复记录保存于再次推送前，远程 CI 最终状态需以新提交对应的 Actions 运行及最终交付回复核实；不会用本地通过替代远程结果。
