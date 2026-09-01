# Android Mac Ops

Android Mac Ops 是 macOS 平台插件，只负责原生 SMB/Samba 源码接入、Keychain 凭据引用和远程路径登记。

公开 Skill 和命令由本插件提供，真实 SMB、Keychain、项目识别和 registry 实现集中在 `android-framework-ops`；本插件只做经过核心版本与 macOS 主机校验的薄转发。

必须先安装 `android-framework-ops`，再安装本插件。

## 包含的 skill

| 分类 | Skill | 职责 |
| --- | --- | --- |
| macOS 源码接入 | android-source-access | 在 macOS 上通过 SMB/Samba 挂载或恢复 Android 服务器源码，记录本地路径、远程路径和 SSH 主机映射 |

每个 skill 的详细说明放在 GitHub 源仓库的 `docs/skills/android-mac-ops/` 下。

## 和其他插件的关系

- `android-framework-ops`（必须）：提供共享的 `android-remote-build-deploy`、`android-remote-channel` 和 `android-framework-change-workflow`。
- `android-wsl-ops`：WSL 平台层，与本插件互斥——macOS 环境用本插件，WSL 环境用 `android-wsl-ops`。

## 使用边界

- 不要把 SMB/Samba 挂载路径当作权威 Android 源码操作路径。源码搜索、修改、`git`、`repo` 和构建都必须在远程 Linux 源码树上执行。
- 本插件只用于 macOS 环境；WSL 环境使用 `android-wsl-ops`。

## 验证

从仓库根目录执行：

```bash
scripts/validate_plugins.sh
scripts/validate_macos_over_ssh.sh jinny
```

第一条在当前开发机运行全部静态和模拟回归；第二条把 macOS 源码接入插件、共享构建 skill 和测试复制到远端临时目录，用真实 macOS、系统 Bash 3.2 和系统 Python 复验，完成后删除临时目录，不修改 Mac 上已安装插件或 AKBS 文件。
