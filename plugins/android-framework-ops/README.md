# Android Framework Ops

Android Framework Ops 是本套件的 WSL 主链路核心工程插件。它负责让成员端 Codex 完成 Android Framework 需求从 WSL 源码接入、历史检索、诊断修改、远程构建、设备推送、验收证据、补丁归档到 incoming 入库的闭环。

这个插件只提供中立工程能力，不内置个人代码风格，不替代项目本地规范，也不强制接管 review workflow。

Windows 原生 Codex 的 SMB/UNC、PowerShell 和本地 `adb.exe` 兼容能力不放在本核心插件中；需要时额外安装 `android-framework-windows-ops`。

## 包含的 skill

每个 skill 的详细说明放在 GitHub 源仓库的 `docs/skills/android-framework-ops/` 下。插件安装后的 runtime skill 目录只保留 Codex 执行需要的文件，不放 `README.md`。

| 分类 | Skill | 职责 |
| --- | --- | --- |
| Framework 工作流 | [android-framework-change-workflow](https://github.com/jinny51/android-framework-codex-suite/tree/main/docs/skills/android-framework-ops/android-framework-change-workflow) | 统筹需求分析、问题诊断、源码修改、风险判断、验证验收和最终报告 |
| Framework 工作流 | [android-framework-patch-capture](https://github.com/jinny51/android-framework-codex-suite/tree/main/docs/skills/android-framework-ops/android-framework-patch-capture) | 将已完成或阶段性 Framework 修改整理成标准 patch、说明和验证材料补丁包 |
| 知识系统 | [android-knowledge-search](https://github.com/jinny51/android-framework-codex-suite/tree/main/docs/skills/android-framework-ops/android-knowledge-search) | 默认搜索 AI 可复用案例、平台实现、补丁、检索锚点和验证记录；归档记录需显式查询 |
| 知识系统 | [android-knowledge-intake](https://github.com/jinny51/android-framework-codex-suite/tree/main/docs/skills/android-framework-ops/android-knowledge-intake) | 从会话、git、patch 和验证结果生成 incoming 包并提交到团队知识库 |
| 远程执行 | [android-remote-channel](https://github.com/jinny51/android-framework-codex-suite/tree/main/docs/skills/android-framework-ops/android-remote-channel) | 统一管理 Android 构建服务器 SSH/tmux 长会话、命令日志、占用状态和锁 |
| WSL 源码接入 | [android-wsl-source-access](https://github.com/jinny51/android-framework-codex-suite/tree/main/docs/skills/android-framework-ops/android-wsl-source-access) | 在 WSL 中挂载或恢复 Android 服务器源码，并记录本地路径、远程路径和 SSH 主机映射 |
| WSL 构建交付 | [android-wsl-remote-build-deploy](https://github.com/jinny51/android-framework-codex-suite/tree/main/docs/skills/android-framework-ops/android-wsl-remote-build-deploy) | 在 WSL 源码接入场景下调用服务器完成 Android 编译、产物定位和设备推送 |

## 推荐工作流

1. `android-wsl-source-access` 先确认源码路径和远程映射。
2. `android-knowledge-search` 在正式分析前检索历史方案、补丁和验证证据。
3. `android-framework-change-workflow` 负责需求分析、源码修改、调试日志、风险判断和验收口径。
4. `android-remote-channel` 提供稳定远程会话，避免重复 SSH、重复 tmux、重复锁逻辑。
5. `android-wsl-remote-build-deploy` 负责服务器构建、产物定位、设备推送。
6. `android-framework-change-workflow` 根据需求和设备证据给最终验收结论，并决定 `validated`、`candidate`、`draft`、`failed` 或 `blocked` 成熟度。
7. `android-framework-patch-capture` 把已完成、阶段性、失败或阻塞但有价值的 Framework 修改整理成补丁、readme 和 evidence。
8. `android-knowledge-intake` 把成员端 Codex 生成的知识资产打成 incoming 包并提交到团队知识库。

默认原则：能自动沉淀就先沉淀，再按成熟度排序和复用。没有人工确认不等于丢弃知识；只有敏感信息、混杂无关 diff、高风险误导或身份/配置不可用时才停止入库，并在最终报告中说明。

## 和其他 skill 的兼容方式

如果用户或项目同时提供了自己的 skill，应按组合方式使用：

- 个人代码风格、项目本地规范、review 口径由用户提供的 skill 或项目 `AGENTS.md` 负责。
- 本插件只补 Android Framework 工程证据链和远程构建链路。
- 当个人规范和本插件流程都适用时，Codex 应同时满足个人规范，并保留本插件的源码证据、构建证据、设备验证证据和风险说明。
- 不要把 `jinny-android-practices` 当成本插件的硬依赖；它是可选实践层。

## 配置入口

成员个人配置不提交到插件仓库。常见配置位置：

```text
$CODEX_HOME/report/config.toml
$CODEX_HOME/<skill-name>.toml
<project>/.codex/report.toml
```

知识库和产物目录建议使用：

```text
<Codex documents>/worktrees/knowledge-<member_alias>
<Codex documents>/artifacts/android-knowledge-intake
```

这些路径是模板，不是插件硬编码要求。成员端和管理员端都应通过各自私有配置指定实际路径。

## 验证

从仓库根目录执行：

```bash
scripts/validate_plugins.sh
```

修改本插件中的 Python 脚本后，额外执行：

```bash
python3 -m pytest --capture=no \
  plugins/android-framework-ops/skills/android-framework-patch-capture/tests \
  plugins/android-framework-ops/skills/android-knowledge-intake/tests \
  plugins/android-framework-ops/skills/android-knowledge-search/tests
```

## 维护边界

不要在本插件中加入个人偏好型规则。代码风格、review 偏好、项目约定应放在 `jinny-android-practices` 或用户自己的插件/skill 中。

不要提交真实配置、凭据、私钥、构建输出、日志、知识库 worktree 或 Codex 本地历史数据库。
