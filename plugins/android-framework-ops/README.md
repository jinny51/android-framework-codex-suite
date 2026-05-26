# Android Framework Ops

Android Framework Ops 是本套件的核心工程插件。它负责 Android Framework 需求从源码接入、历史检索、诊断修改、远程构建、设备推送、验收证据、补丁归档到知识入库的闭环。

这个插件只提供中立工程能力，不内置个人代码风格，不替代项目本地规范，也不强制接管 review workflow。

## 包含的 skill

| 分类 | Skill | 职责 |
| --- | --- | --- |
| Framework 工作流 | [android-framework-change-workflow](skills/android-framework-change-workflow/README.md) | 统筹需求分析、问题诊断、源码修改、风险判断、验证验收和最终报告 |
| Framework 工作流 | [android-framework-patch-capture](skills/android-framework-patch-capture/README.md) | 将已完成或阶段性 Framework 修改整理成标准 patch、说明和验证材料补丁包 |
| 知识系统 | [android-knowledge-search](skills/android-knowledge-search/README.md) | 搜索团队知识库中的历史日报、周报、补丁、代码标识、验证记录和 v2 事件 |
| 知识系统 | [android-knowledge-intake](skills/android-knowledge-intake/README.md) | 生成、检查并提交日报、周报或维护者补丁贡献包到团队知识库 incoming 协议 |
| 远程执行 | [android-remote-channel](skills/android-remote-channel/README.md) | 统一管理 Android 构建服务器 SSH/tmux 长会话、命令日志、占用状态和锁 |
| WSL 源码接入 | [android-wsl-source-access](skills/android-wsl-source-access/README.md) | 在 WSL 中挂载或恢复 Android 服务器源码，并记录本地路径、远程路径和 SSH 主机映射 |
| WSL 构建交付 | [android-wsl-remote-build-deploy](skills/android-wsl-remote-build-deploy/README.md) | 在 WSL 源码接入场景下调用服务器完成 Android 编译、产物定位和设备推送 |
| Windows 源码接入 | [android-windows-source-access](skills/android-windows-source-access/README.md) | 在 Windows 中识别 SMB/UNC 源码路径，并记录本地路径、远程路径和 SSH 主机映射 |
| Windows 构建交付 | [android-windows-remote-build-deploy](skills/android-windows-remote-build-deploy/README.md) | 在 Windows SMB/UNC 场景下调用服务器完成 Android 编译、产物定位和本地 `adb.exe` 推送 |

## 推荐工作流

1. `android-wsl-source-access` 或 `android-windows-source-access` 先确认源码路径和远程映射。
2. `android-knowledge-search` 在正式分析前检索历史方案、补丁和验证证据。
3. `android-framework-change-workflow` 负责需求分析、源码修改、调试日志、风险判断和验收口径。
4. `android-remote-channel` 提供稳定远程会话，避免重复 SSH、重复 tmux、重复锁逻辑。
5. `android-wsl-remote-build-deploy` 或 `android-windows-remote-build-deploy` 负责服务器构建、产物定位、设备推送。
6. `android-framework-change-workflow` 根据需求和设备证据给最终验收结论。
7. `android-framework-patch-capture` 把可复用修改整理成补丁资料包。
8. `android-knowledge-intake` 把日报、周报或补丁包提交到团队知识库。

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

维护者当前本机迁移后路径：

```text
/mnt/c/Users/jinny/Documents/Codex/worktrees/knowledge-jinny
/mnt/c/Users/jinny/Documents/Codex/worktrees/knowledge-test
/mnt/c/Users/jinny/Documents/Codex/artifacts/android-knowledge-intake
/mnt/c/Users/jinny/.codex/report/config.toml
```

这些路径应写在本机配置里，不应作为团队成员的通用默认值。

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
