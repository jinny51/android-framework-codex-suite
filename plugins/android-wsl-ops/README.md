# Android WSL Ops

Android WSL Ops 是可选 Windows/WSL 兼容插件。它用于 Codex 运行在 Windows 主机侧、需要通过 SMB/UNC 路径识别远程 Linux/WSL 源码映射、用 PowerShell/`ssh.exe` 管理远程会话，并用本地 `adb.exe` 推送产物的场景。

团队主推荐链路仍是 WSL 版 [android-framework-ops](../android-framework-ops/README.md)。只有确实需要 Windows 主机侧入口配合 WSL/远程 Linux 链路时，才额外安装本插件。

## 包含的 skill

每个 skill 的详细说明放在 GitHub 源仓库的 `docs/skills/android-wsl-ops/` 下。插件安装后的 runtime skill 目录只保留 Codex 执行需要的文件，不放 `README.md`。

| 分类 | Skill | 职责 |
| --- | --- | --- |
| Windows/WSL 源码接入 | [android-windows-source-access](https://github.com/jinny51/android-framework-codex-suite/tree/main/docs/skills/android-wsl-ops/android-windows-source-access) | 识别 SMB/UNC 源码映射，记录本地路径、远程 Linux/WSL 源码路径和 SSH 主机 |
| Windows/WSL 远程执行 | [android-windows-remote-channel](https://github.com/jinny51/android-framework-codex-suite/tree/main/docs/skills/android-wsl-ops/android-windows-remote-channel) | 通过 PowerShell 和 `ssh.exe` 管理远程 `tmux` 会话、命令日志、占用状态和锁 |
| Windows/WSL 构建交付 | [android-windows-remote-build-deploy](https://github.com/jinny51/android-framework-codex-suite/tree/main/docs/skills/android-wsl-ops/android-windows-remote-build-deploy) | 调用服务器完成 Android 编译，通过 Windows SMB/UNC 取产物并用本地 `adb.exe` 推送 |

## 使用边界

- 不要把 Windows SMB/UNC 路径当作 Android 源码操作路径。源码搜索、修改、`git`、`repo` 和构建都必须在远程 Linux/WSL 源码树上执行。
- 本插件是 `android-framework-ops` 的可选补充，不是团队默认主链路。
- 已经在 WSL 内运行的 Codex 不要使用本插件；使用 `android-wsl-source-access`、`android-remote-channel` 和 `android-wsl-remote-build-deploy`。

## 验证

从仓库根目录执行：

```bash
scripts/validate_plugins.sh
```

Windows/WSL 兼容层维护者也可以执行：

```powershell
.\scripts\validate_plugins.ps1
```
