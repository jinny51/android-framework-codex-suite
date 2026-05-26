# Android Framework Codex Suite

团队 Codex 插件套件，用于分发 Android Framework 工程工作流、可选团队实践规则，以及独立的 Codex 工作区维护能力。

这个仓库不把所有 skill 做成一个不可拆分的包。团队成员可以只安装核心插件 `android-framework-ops`，也可以按需额外安装 `jinny-android-practices` 或 `codex-workspace-care`。

## 插件一览

| 插件 | 是否核心 | 定位 | 适合谁安装 |
| --- | --- | --- | --- |
| `android-framework-ops` | 是 | Android Framework 源码接入、远程构建、验证验收、补丁归档和知识复用 | 所有需要 Codex 处理 Android Framework 工程任务的成员 |
| `jinny-android-practices` | 否 | Jinny 团队可选代码风格、review 和项目实践规则 | 想沿用 Jinny 团队规范的成员 |
| `codex-workspace-care` | 否 | Codex 本地历史清理和上下文交接 | 需要维护本地 Codex 历史状态的成员 |

## 兼容原则

`android-framework-ops` 是中立核心插件。它不强制替代成员自己的代码风格 skill、项目本地 `AGENTS.md`、review workflow 或团队内部规范。

如果成员提供了自己的代码风格、项目规则或评审规则，Codex 应该保留这些规则，并只使用 `android-framework-ops` 补齐 Android Framework 专项工程能力：源码接入、远程执行、构建推送、验证验收、补丁归档和知识复用。

## 当前迁移策略

旧仓库 `codex-team-skills` 先保持现状，作为当前可用版本和迁移来源。本仓库先完成插件骨架、manifest、marketplace 和验证链路。确认新插件套件稳定后，再从旧仓库复制 skill 内容。

不要直接删除旧 skill。正确顺序是复制、验证、试用、稳定后再归档旧分发方式。

## 目录结构

```text
android-framework-codex-suite/
├── .agents/plugins/marketplace.json
├── plugins/
│   ├── android-framework-ops/
│   ├── jinny-android-practices/
│   └── codex-workspace-care/
├── manifests/
├── docs/
└── scripts/
```

## 验证

```bash
scripts/validate_plugins.sh
```

## 从旧仓库同步 skill

当前迁移阶段从旧仓库复制 skill，不移动、不删除旧内容：

```bash
scripts/sync_from_team_skills.sh
```

默认来源是 `${CODEX_HOME:-$HOME/.codex}/team-skills`。如果要从其他路径同步：

```bash
scripts/sync_from_team_skills.sh /path/to/codex-team-skills
```
