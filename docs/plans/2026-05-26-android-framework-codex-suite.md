# Android Framework Codex Suite 设计计划

## 目标

建立 Android Framework Codex 插件套件，并把它作为团队成员安装 Android Framework 工程能力的插件市场来源。

这个套件不是把所有 skill 强行打成一个包，而是拆成可选择安装的插件：

- `android-framework-ops`：核心插件，给所有 Android Framework 成员使用。
- `jinny-android-practices`：可选实践插件，放代码风格、review、项目规范等 opinionated 规则。
- `codex-workspace-care`：独立维护插件，放 Codex 历史清理和上下文交接能力。

## 当前状态

已完成：

1. 新仓库已独立创建。
2. 三个插件目录、`.codex-plugin/plugin.json` 和 suite marketplace 已创建。
3. Android Framework 核心 skill 已复制到 `android-framework-ops`。
4. Codex 本地历史维护 skill 已复制到 `codex-workspace-care`。
5. `jinny-android-practices` 作为可选实践插件保留边界，当前不包含具体实践 skill。
6. 插件校验脚本和同步脚本已建立。

## 分发策略

插件仓库作为主线分发入口。成员在 Codex 插件市场添加本仓库 marketplace，然后按需安装插件。

后续顺序：

1. 本机试装并验证 Codex 能识别插件。
2. 小范围团队试用 `android-framework-ops`。
3. 根据团队反馈补齐 `jinny-android-practices`。
4. 稳定后把知识库 incoming 自动化接入成员日常流程。

## 核心原则

`android-framework-ops` 必须保持中立、可组合。它不接管别人的代码风格，不替代项目本地规范，不强制使用某个 review 规则。

如果别人有自己的 skill、项目 `AGENTS.md`、本地规范或 review workflow，核心插件应当保留这些规则，只补 Android Framework 专项工程能力。

## 第一阶段完成标准

- 三个插件目录存在。
- 三个插件都有合法的 `.codex-plugin/plugin.json`。
- suite marketplace 存在。
- 顶层 README 说明插件选择和兼容原则。
- plugin validator 通过。
