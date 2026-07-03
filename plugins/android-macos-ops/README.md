# Android macOS Ops

Android macOS Ops 是可选 macOS 原生兼容插件。它用于 Codex 运行在 macOS 原生环境、需要通过 macOS SMB 挂载 Android 服务器源码、用 Keychain 保存凭据引用，并用本地 `adb` 推送产物的场景。

团队默认主链路仍是 WSL 版 [android-framework-ops](../android-framework-ops/README.md)。只有确实需要 macOS 原生 Codex 时，才额外安装本插件。

## 包含的 skill

每个 skill 的详细说明放在 GitHub 源仓库的 `docs/skills/android-macos-ops/` 下。插件安装后的 runtime skill 目录只保留 Codex 执行需要的文件，不放 `README.md`。

| 分类 | Skill | 职责 |
| --- | --- | --- |
| macOS 源码接入 | [android-macos-source-access](https://github.com/jinny51/android-framework-codex-suite/tree/main/docs/skills/android-macos-ops/android-macos-source-access) | 通过 macOS 原生 SMB 挂载或恢复 Android 服务器源码，检测项目并记录路径映射 |
| macOS 构建交付 | [android-macos-remote-build-deploy](https://github.com/jinny51/android-framework-codex-suite/tree/main/docs/skills/android-macos-ops/android-macos-remote-build-deploy) | 调用远程 Linux 服务器完成 Android 编译，通过 macOS 挂载路径定位产物并用本地 `adb` 推送 |

## 使用边界

- 不要把 macOS SMB 挂载路径当作权威 Android 源码操作路径。源码搜索、修改、`git`、`repo` 和构建都必须在远程 Linux 源码树上执行。
- 本插件是 `android-framework-ops` 的可选补充，不是团队默认主链路。
- WSL 环境不要使用本插件；使用 `android-wsl-source-access`、`android-remote-channel` 和 `android-wsl-remote-build-deploy`。
- Windows 原生环境不要使用本插件；使用 `android-framework-windows-ops`。

## 依赖

- `android-framework-ops`：平台无关工作流、知识搜索、补丁归档和 incoming 上传材料。
- `android-remote-channel`：远程 SSH/tmux 会话管理。

## 验证

从仓库根目录执行：

```bash
scripts/validate_plugins.sh
```
