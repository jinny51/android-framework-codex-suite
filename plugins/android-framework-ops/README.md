# Android Framework Ops

Android Framework Ops 是面向团队使用的 Codex 核心插件，负责 Android Framework 工程闭环中的中立能力：源码接入、远程执行、构建推送、验证验收、补丁归档和知识复用。

## 边界

本插件不提供个人代码风格，不替代项目本地规范，不强制接管 review workflow。

如果用户已有自己的代码风格 skill、项目 `AGENTS.md`、本地规范或 review skill，应优先保留这些规则。本插件只补 Android Framework 专项工程能力。

## 计划包含的 skill

- `android-framework-change-workflow`
- `android-framework-patch-capture`
- `android-knowledge-search`
- `android-knowledge-intake`
- `android-remote-channel`
- `android-wsl-source-access`
- `android-wsl-remote-build-deploy`
- `android-windows-source-access`
- `android-windows-remote-build-deploy`

当前阶段先完成插件骨架。确认结构和验证链路后，再从旧 `codex-team-skills` 复制这些 skill。

