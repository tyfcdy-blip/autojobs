# 第三方来源记录

核验日期：2026-11-19（Asia/Shanghai）。模板 Python 工具仅用标准库，没有下载或复制第三方业务代码，没有新增 Python/Java/Node 依赖。

GitHub 工作流引用的 Action 固定为完整提交摘要，使用只读 contents 权限，不保留 checkout 凭据。它们仅在远程 CI 执行时下载：

| 组件 | 固定摘要（v6 标签核验值） | 来源 / 许可证 |
| --- | --- | --- |
| actions/checkout | `d23441a48e516b6c34aea4fa41551a30e30af803` | [官方仓库](https://github.com/actions/checkout) / MIT |
| actions/setup-python | `ece7cb06caefa5fff74198d8649806c4678c61a1` | [官方仓库](https://github.com/actions/setup-python) / MIT |

摘要通过 `git ls-remote <对应官方仓库.git> refs/tags/v6` 只读核验。固定 v6 不表示它是最新版本；升级时核验官方发布、兼容性与摘要后再更新。参考 [setup-python 官方说明](https://github.com/actions/setup-python)：v6 的自托管 runner 需要 v2.327.1 或以上版本。本工作流选用 GitHub 托管 runner，尚未执行远程 CI。

项目自身许可证由所有者另行决定，此记录不替代第三方许可条款或项目授权。
