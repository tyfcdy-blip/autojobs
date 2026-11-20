# 应用组件与前端基座调研

调研日期：2026-11-19。这里只记录方案候选，尚未安装任何项目。精确 Star、抓取时间、HTML 摘要和 API 失败记录见 [组件快照](components-github-snapshot.json)。数据从官方 GitHub 仓库 HTML 的 `stargazerCount` 字段取得；匿名 REST API 返回 403 限流。无法取得 `pushed_at`、`archived` 的项目保留 `null`，不能据此宣称近期活跃或未归档。

## 1 候选比较

| 项目与官方来源 | Star 快照 | 许可证依据 | 本项目建议 |
| --- | ---: | --- | --- |
| [FastAPI](https://github.com/fastapi/fastapi) | 104,890 | MIT，仓库许可证元数据 | 推荐后端 API；团队已有 Python 脚本经验，减少新增服务端语言 |
| [Vue 3](https://github.com/vuejs/core) | 55,034 | MIT，仓库许可证元数据 | 推荐管理端；正式控件承接现有原型 |
| [Element Plus](https://github.com/element-plus/element-plus) | 27,861 | MIT，仓库许可证元数据 | 推荐表格、表单、抽屉、弹窗等基础控件 |
| [Vue Vben Admin](https://github.com/vbenjs/vue-vben-admin) | 33,830 | MIT，仓库许可证元数据 | 参考布局、导航、权限展示方式；首期不整体复制其多包工程 |
| [Pydantic](https://github.com/pydantic/pydantic) | 29,564 | MIT，仓库许可证元数据 | 推荐接口及结果结构校验；不能替代业务权限与状态校验 |
| [SQLAlchemy](https://github.com/sqlalchemy/sqlalchemy) | 12,295 | MIT，仓库许可证元数据 | 推荐数据库访问；事务、唯一约束和锁仍需明确设计 |
| [APScheduler](https://github.com/agronholm/apscheduler) | 7,715 | MIT，仓库许可证元数据 | 采用稳定 3.x 的时间触发计算；不把它当远程执行器或业务队列 |
| [Celery](https://github.com/celery/celery) | 29,228 | [源码为 BSD-3-Clause；文档另有许可](https://github.com/celery/celery/blob/main/LICENSE)；GitHub自动识别为 NOASSERTION | 首期不采用；不能作为受官方支持的 Windows worker |
| [Django](https://github.com/django/django) | 91,815 | BSD-3-Clause，仓库许可证元数据 | 备选；若团队已有 Django 资产可重评。目前其内置管理后台不能消除执行端开发 |
| [Caddy](https://github.com/caddyserver/caddy) | 79,250 | Apache-2.0，仓库许可证元数据 | 推荐云端 HTTPS 入口及静态网页服务；已有统一网关时可替换 |

Star 反映关注度，不是安全认证、服务等级或适配性证明。APScheduler 的 Star 较少，但在这里仅承担窄范围日历计算，没必要为追求 Star 引入完整编排平台。Vue Vben Admin 自述为 Vue 3、Vite、TypeScript 管理端模板；是否引用具体源码需要记录文件、版本和许可，不能把参考页面写成已复用代码。

## 2 核验后的技术限制

- FastAPI 官方支持自行构建 Linux 容器并通过 Docker Compose 等方式部署；并不要求另加 Kubernetes。[官方容器部署说明](https://fastapi.tiangolo.com/deployment/docker/)
- APScheduler 官方 4.x 文档仍包含预发布、不可用于生产的警示；建议首期锁定经验证的 3.x 补丁版本。3.x FAQ 明确不支持多进程共用 job store。方案仅用触发器计算下一时点，运行事实与排队由业务数据库维护，调度扫描为独立单实例。[版本说明](https://apscheduler.readthedocs.io/en/master/versionhistory.html)、[3.x FAQ](https://apscheduler.readthedocs.io/en/3.x/faq.html)
- Celery 官方 FAQ 明确自 4.x 起不再支持 Windows；“有人的脚本能运行”不能当官方支持。因此本项目不在两台 Windows 电脑上部署 Celery worker，也不依赖其撤销语义保证浏览器进程停止。[官方 FAQ](https://docs.celeryq.dev/en/stable/faq.html)
- PostgreSQL 提供行锁与 `SKIP LOCKED`，适合实现受事务保护的队列领取，但不能自动实现跨 Windows 进程的恰好一次业务执行。后者仍需要设备账本、启动去重与不确定状态处理。[行锁说明](https://www.postgresql.org/docs/current/explicit-locking.html)、[SELECT 说明](https://www.postgresql.org/docs/current/sql-select.html)
- SQLAlchemy 2.0 提供 psycopg 3 方言；采用显式驱动配置，不依赖连接 URL 默认驱动推断。[官方 PostgreSQL 方言](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html)

## 3 选型边界

推荐复用库的稳定能力，自研本产品的任务台账、设备队列、协议、环境检查规则和通知策略。不能宣称库自带本项目所需的“失联不重复执行”“本地离线超时”“只终止自有进程”等保证。

核心版本线建议为 Python 3.12、Vue 3、Pydantic 2、SQLAlchemy 2、APScheduler 3；这是候选组合，不是已通过的兼容矩阵。开发初始化时才选稳定补丁、锁依赖和镜像摘要，并验证受支持的运行环境。不得从 `master` 文档照搬尚未发布的 API。

本轮只读取官方文档和仓库元数据，没有复制第三方实现代码，也未确认全部传递依赖许可证。投产前须按实际 lockfile/SBOM 再审查；尤其不能将仓库根许可证直接等同于浏览器、驱动、运行时及安装包的全部许可。
