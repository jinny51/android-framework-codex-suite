# android-windows-source-access

> GitHub 说明页。Runtime skill 文件位于 [../../../../plugins/android-framework-windows-ops/skills/android-windows-source-access](../../../../plugins/android-framework-windows-ops/skills/android-windows-source-access)；插件安装后的 skill 目录不包含本 README。文中的 `scripts/...`、`references/...` 指向该 runtime skill 目录。

Windows 场景下访问服务器 Android 源码的 skill。

## 用途

该 skill 用于在 Windows 原生 Codex 智能体中识别 SMB/UNC 源码路径，并解析本地 Windows 路径、远程 Linux 源码路径和 SSH 主机之间的关系。

它只负责让 Codex 能从 Windows 侧访问源码，并记录 `本地路径 -> SSH 主机 -> 远程源码路径` 映射；不负责远程构建、编译产物推送或最终验收。

## 典型场景

- Windows 上已经有 `X:\rk\TVA10A2R` 或 `\\192.168.x.x\share\project`，需要识别它对应哪台服务器、哪个远程源码路径。
- Windows 原生 Codex 智能体需要从 SMB/UNC 路径找到 `SSH_HOST` 和 `REMOTE_ROOT`，交给远程构建 skill。
- 本地映射存在，但项目名、平台名或远程路径不确定，需要基于源码内容重新识别。

## 文件入口

- [SKILL.md](../../../../plugins/android-framework-windows-ops/skills/android-windows-source-access/SKILL.md)：给 Codex 自动加载的执行说明。
- [references/capability-capture.md](../../../../plugins/android-framework-windows-ops/skills/android-windows-source-access/references/capability-capture.md)：Skill 改进建议记录规则。
- [scripts/Inspect-AndroidSdk.ps1](../../../../plugins/android-framework-windows-ops/skills/android-windows-source-access/scripts/Inspect-AndroidSdk.ps1)：Android SDK 检查脚本。
- [scripts/Manage-AndroidSmbWindowsInfo.ps1](../../../../plugins/android-framework-windows-ops/skills/android-windows-source-access/scripts/Manage-AndroidSmbWindowsInfo.ps1)：Windows SMB 映射信息管理脚本。
