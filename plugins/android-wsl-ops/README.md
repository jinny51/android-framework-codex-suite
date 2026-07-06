# Android WSL Ops

Android WSL Ops 是 WSL 平台层插件，在 `android-framework-ops` 提供的共享工作流基础上，负责 WSL 侧的源码接入和远程构建交付。

必须先安装 `android-framework-ops`，再安装本插件。

## 包含的 skill

| 分类 | Skill | 职责 |
| --- | --- | --- |
| WSL 源码接入 | [android-source-access](https://github.com/jinny51/android-framework-codex-suite/tree/main/docs/skills/android-wsl-ops/android-source-access) | 在 WSL 中挂载或恢复 Android 服务器源码，记录本地路径、远程路径和 SSH 主机映射 |
| WSL 构建交付 | [android-remote-build-deploy](https://github.com/jinny51/android-framework-codex-suite/tree/main/docs/skills/android-wsl-ops/android-remote-build-deploy) | 调用服务器完成 Android 编译、产物定位和设备推送 |

每个 skill 的详细说明放在 GitHub 源仓库的 `docs/skills/android-wsl-ops/` 下。插件安装后的 runtime skill 目录只保留 Codex 执行需要的文件，不放 `README.md`。

## 和其他插件的关系

- `android-framework-ops`（必须）：提供 `android-remote-channel`（远程 SSH/tmux 会话管理）、`android-framework-change-workflow`（诊断修改和验证验收）等共享能力。
- `android-mac-ops`：macOS 平台层，与本插件互斥——WSL 环境用本插件，macOS 环境用 `android-mac-ops`。

## 使用边界

- 不要把 SMB/CIFS 挂载路径当作权威 Android 源码操作路径。源码搜索、修改、`git`、`repo` 和构建都必须在远程 Linux 源码树上执行。
- 本插件只用于 WSL 环境；macOS 环境使用 `android-mac-ops`。

## 验证

从仓库根目录执行：

```bash
scripts/validate_plugins.sh
```
