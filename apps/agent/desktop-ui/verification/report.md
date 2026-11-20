# M0 本机 Vue 窗口工作包验证记录

日期：2026-11-19（Asia/Shanghai）。模式：全过程开发。本工作包 L2，整体 M0 按主计划 L3 门禁管理。当前无 Git 仓库；不存在可报告的分支、提交或 Git diff。工作包写入仅 `apps/agent/desktop-ui/` 及 `apps/agent/src/autojobs_agent/desktop_assets/`，未修改其他 worker 的文件。

后续集成补充：主 agent 已在 Windows 11 通过真实 pywebview/WebView2、Vue、SQLite 和 worker 的集成用例，验证关闭窗口后任务继续运行，并完成独立 AI 复核。以下工作包记录保留当时的验证边界；最新整体状态以 [M0 交付记录](../../../../docs/delivery/2026-11-19-agent-m0/report.md) 为准。

## 任务闭环

已完成真实只读 Vue 窗口、唯一 `get_status` 桥接边界、结构校验、每轮完成后两秒刷新、加载/未连接/读取失败/超时处理、在线与执行占用分离、当前任务、最近运行选择与结果显示，以及有界结果展示。没有演示快照进入生产源码，无任意文件读取或执行接口。用户已确认原型与技术方案，本轮沿用其视觉方向。

UI-01 至 UI-06 由 `tests/App.test.ts` 的 16 个用例覆盖；UI-07 由构建与浏览器验证覆盖。测试只替换 pywebview 宿主边界，不替换组件真实逻辑。测试中的进程号、任务名、结果和时间均为可识别测试数据，不能当作真实执行证据。

## 实际测试证据

工作目录：`D:\codex\autojobs\apps\agent\desktop-ui`。环境：Windows 11、Node v24.18.0、pnpm 11.9.0；浏览器检查使用本机已有 Python Playwright 和 Edge 独立无头会话。

| 命令 | 最终退出码 | 实际结果 |
| --- | --- | --- |
| `pnpm install` | 0 | 依赖安装并生成 lockfile；初次出现 TypeScript peer 警告，后续已解决 |
| `pnpm install --frozen-lockfile` | 0 | 锁文件可重复安装，无变更 |
| `pnpm add -D -E typescript@6.0.3` | 0 | 锁定与 vue-tsc 兼容的编译器，未改全局配置 |
| `pnpm typecheck` | 0 | 严格类型检查通过 |
| `pnpm peers check` | 0 | 无 peer dependency 问题 |
| `pnpm test` | 0 | 16 通过、0 失败、0 跳过 |
| `pnpm build` | 0 | Vue 类型检查及 Vite 构建通过；3 个离线资源发布到 desktop_assets |
| `python -B -X utf8 scripts/verify-browser.py` | 0 | 4 个场景，无页面/控制台错误或警告，无横向溢出，无外部资源请求 |
| `pnpm audit --prod --json --registry=https://registry.npmjs.org` | 0 | 官方注册表报告生产依赖已知漏洞 0；不代表完整应用安全验收 |

浏览器证据见 [browser-results.json](browser-results.json)、[空状态](empty.png)、[运行中](running.png)、[待核实窄窗口](reconciling.png)、[390 像素窄布局](narrow.png)。已目视检查空、运行中和待核实截图：主要文本、状态分离、表格与详情可读；较小窗口允许纵向滚动。

## 失败、修复与复验

1. 初次 `pnpm typecheck` exit 1：TypeScript 7.0.2 不再暴露 vue-tsc 所需的 `lib/tsc`，且 Volar 声明 peer `<7`。改用官方注册表可查的 6.0.3 后，typecheck、peer、构建与组件测试通过。没有关闭类型检查。
2. 初次组件测试 15 通过、1 失败：桥未建立用例在 Vue 异步渲染完成前断言。补齐渲染等待，保留原断言，复验 16 通过。
3. 初次内联浏览器脚本 exit 1：测试注入的箭头函数遗漏对象括号，另有默认 favicon 404。修正验证脚本并在页面显式声明空 favicon 后，四种布局全部通过。未修改业务逻辑来迎合测试结果。
4. 默认 `pnpm audit --prod --json` exit 1：当前镜像注册表不提供 audit 端点。使用单次命令参数切换到官方 registry 查询成功，未修改用户的全局注册表配置。

剩余 P3：安装工具提示传递开发依赖 `ini@1.3.4` deprecated；本轮没有为消除此提示升级或替换无关工具链。生产依赖审计结果为 0 已知漏洞，开发依赖完整审计和发布包许可证仍应随主任务复核。

## 第三方与兼容依据

已直接读取官方 npm 注册表版本元数据并锁定：Vue 3.5.45、Vite 8.3.8、@vitejs/plugin-vue 6.0.11、vue-tsc 3.3.14、Vitest 5.1.1、@vue/test-utils 2.6.0、jsdom 31.0.1；TypeScript 经兼容修订为 6.0.3。包来源和完整传递版本见 `pnpm-lock.yaml`，没有复制第三方项目源码。Vue/Vite/Vitest 等项目为 MIT，TypeScript 为 Apache-2.0；实际发布时仍需核对打包依赖及许可文件。

官方依据：[Vite 文档](https://vite.dev/guide/)、[Vue 测试指南](https://vuejs.org/guide/scaling-up/testing.html)、[Vitest 环境要求](https://vitest.dev/guide/)、[TypeScript 6.0.3 注册表](https://registry.npmjs.org/typescript/6.0.3)。本机 Node 满足此次实际安装与构建要求；未因此推断所有 Windows 10 WebView2 版本兼容。

## 质量状态

| 状态 | 结论 |
| --- | --- |
| Codex 工作包开发 | 已完成 |
| 测试计划与用例 | 已生成并实现 |
| 自动化组件/类型/构建/浏览器验证 | 已执行，见上表 |
| 人工验证 | 未执行；目视检查为 AI 检查 |
| 剩余未验证 | 真正 Python 宿主桥、原生窗口关闭与 worker 生命周期、两台 Win10/WebView2兼容、无障碍专项与完整应用安全 |
| 独立复核 | 本工作包未自行安排，由主 agent 统一执行 |
| CI、开发最终确认、人工代码评审 | 未执行 |
| 允许发布 | 否；当前仅本机 M0 工作包，需与宿主集成并完成整体门禁 |

AI 自检结论：有条件通过，仅限静态前端与桥边界测试。Codex 自检通过不等于开发自测确认、人工代码评审、CI 验证或发布审批通过。
