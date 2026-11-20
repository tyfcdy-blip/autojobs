# Windows 10 验证准备交付

日期：2026-11-20，Asia/Shanghai。模式：开发后自检。等级：L1，范围仅为文档和既有产物打包，不改变执行端业务代码或依赖版本。用户已同意先完成本机开发，再安排两台电脑安装测试版并协助验证；**现场尚未执行**。

## 结果与变更

生成 `dist/autojobs-win10-validation-0.1.0-20261120.zip`，430,087 字节。包含使用说明、逐台记录、同一已验证 wheel、源码快照、带哈希的运行依赖清单、两个已有示例脚本和文件摘要，共 8 个文件。源码快照含原有自动化测试和预构建窗口，现场无需 Node 构建。

新增本目录 [计划](plan.md)、[使用说明](README.md)、[现场记录](现场记录.md)、产物与实测 JSON；更新现场手册的用户授权及准备状态。无运行代码、接口、数据库或配置变更；无依赖升级，无 Git 提交、部署或真实执行机操作。当前不是 Git 仓库，查询 Git 状态退出 1；未虚构差异基准。

ZIP SHA-256：`7cb478c511a5f5a4bcae70f92e633c8b1f12c784edff9ec9c8492eeb5778b5cf`。wheel 摘要与 2026-11-19 的真实安装验证一致，源码包的 uv.lock 与当前锁文件逐字节一致。逐文件摘要见 [package-manifest.json](package-manifest.json)。

## 计划与实际验证

| 用例 | 实际结果 | 状态 |
| --- | --- | --- |
| KIT-01 原产物及锁文件 | wheel 与历史实测摘要一致；sdist 锁文件一致；无归档链接/路径越界 | 通过 |
| KIT-02 ZIP 完整性 | 固定 8 成员、CRC、7 项内容摘要一致；明确文件清单不含状态库或本机环境 | 通过 |
| KIT-03 独立安装与示例 | 新目录、新虚拟环境；按包内命令安装；真实 CSV 2 行、succeeded；源码 CLI 解包成功 | 通过 |
| KIT-04 现场表与文档 | 两台记录均未执行；包内链接有对应文件；没有预填现场通过 | 通过 |

以上为 4 项直接检查，不冒称新增 4 个 pytest 用例。原执行端代码未改，本轮不重复此前 139 项回归；它们的历史证据仍见 [M0 报告](../2026-11-19-agent-m0/report.md)。现场 Windows 10、会话、浏览器和人工步骤均未验证。

开发机 Windows 11 / Python 3.12.7。只使用新建的 `data/tmp/win10-kit-smoke-20261120`，样本是无外部调用合成 CSV，没有 Mock 代替实际执行。实际命令：

| 工作目录 | 命令 | 退出码 / 结果 |
| --- | --- | --- |
| 仓库根 | `uv export --project apps/agent --frozen --no-dev --extra desktop --no-emit-project --output-file data/tmp/win10-validation-requirements.txt` | 0，导出锁定运行依赖 |
| 解包测试目录 | `uv venv --python 3.12 --no-python-downloads .venv` | 0，使用已有 Python，新建隔离环境 |
| 解包测试目录 | `uv pip sync --python .venv/Scripts/python.exe --require-hashes --link-mode copy requirements-runtime.txt` | 0，15 个锁定运行依赖安装完成 |
| 解包测试目录 | `uv pip install --python .venv/Scripts/python.exe --no-deps --link-mode copy autojobs_agent-0.1.0-py3-none-any.whl` | 0，安装包内 wheel |
| 解包测试目录 | 包内 README 的生成示例、check、submit、serve --once、show，以及 `python -m tarfile -e` | 6 条命令均退出 0；完整 argv/stdout/stderr 见下方 JSON |

归档构建与检查通过标准库 `hashlib/tarfile/zipfile` 内联脚本执行，退出 0。实际子进程记录保存在 [smoke-results.json](smoke-results.json)。构建项为 ZIP 打包和原有二进制/源码产物复核；本轮无业务编译改动。未发现失败用例或需修复产品缺陷。

## 未验证与下一门禁

包需要现场已有 Python 3.12、uv，窗口需要 WebView2；锁定依赖仍需联网下载，不是完整离线安装器。现场软件情况未知，不能假定两台电脑已满足。短 CSV 示例不证明锁屏期间长任务可运行；长任务与登录场景需用经过确认的测试脚本逐台验证。

未执行自动化源码回归的现场命令、真实会话/登录、人工评审、CI 或生产发布；本次本机安装成功不替代这些结果。测试包在 `dist/`，属本地忽略产物；打包依据和校验记录保留在本目录。没有生产回退操作，现场回退继续遵守既有手册：停止自有测试 worker，保留待核实账本，不按进程名清理或删除未知状态。

AI 自检：**本轮验证资料与测试包准备通过**；完整 M0 仍未验收。下一门禁为两台 Windows 10 的实际验证和人工专项确认。Codex 自检通过不等于开发自测确认、人工代码评审、CI 验证或发布审批通过。
