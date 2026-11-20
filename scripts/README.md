# 项目工具

使用 Python 3.11+ 标准库，无需安装额外包。在项目根目录执行：

```text
python scripts/init_project.py --name my-project --description "项目说明"
python scripts/check_project.py
python -m unittest discover -s tests/unit -v
```

- `init_project.py`：校验全部输入后维护元数据，独占创建缺失的 `.env`，不覆盖已有 `.env`。无参数执行保留元数据。配置更新使用同目录临时文件和原子替换；替换失败会尝试撤销本次新建的 `.env` 并清理临时文件。不提供并发初始化或断电恢复保证，请单进程运行。
- `init.ps1`：需要 PowerShell 7.3+；优先查找 `python`，其次 `py -3`，保留引号等参数内容并传递退出码；不修改执行策略。旧版会明确拒绝，请直接使用 Python 入口。
- `check_project.py`：只读检查必要文件/目录与配置格式；不读取 `.env`，不自动执行配置中的命令，不扫描业务代码或替代安全审计。删除或调整模板的强制目录时，应同步更新本脚本的清单和测试。
- `project_support.py`：配置校验的唯一实现，供两个入口使用。配置 JSON 使用 UTF-8，接受 UTF-8 BOM；写回时采用无 BOM 的 UTF-8。

工具总是定位脚本所在项目，不依赖当前工作目录。不接受任意输出目录参数，不创建 Git 仓库，不提交、推送、安装依赖或部署。失败返回非零退出码，不打印配置内容或环境变量。初始化的输入文件与 `.env` 不接受符号链接。

## project.config.json 格式

| 字段 | 约束 |
| --- | --- |
| `format_version` | 整数 `1` |
| `project.name` | 1~63 字符，小写字母开头，小写字母、数字、单个连字符；首尾不能是连字符 |
| `project.description` | 字符串，最多 500 字符，允许空字符串 |
| `stack.backend/frontend/jobs` | `null` 为未选型；已选型填写非空技术栈与版本说明 |
| `verification.build/lint/typecheck/unit/integration/e2e` | 字符串数组，每条命令非空；空数组为未登记 |

固定字段不允许多余键，防止拼写错误被静默忽略。业务命令登记时包含正确工作目录与真实入口；不要把凭据写进命令。执行前由人或 Codex 按任务范围核验命令内容。
