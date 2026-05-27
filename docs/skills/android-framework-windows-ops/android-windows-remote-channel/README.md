# android-windows-remote-channel

> GitHub 说明页。Runtime skill 文件位于 [../../../../plugins/android-framework-windows-ops/skills/android-windows-remote-channel](../../../../plugins/android-framework-windows-ops/skills/android-windows-remote-channel)；插件安装后的 skill 目录不包含本 README。文中的 `scripts/...`、`references/...` 指向该 runtime skill 目录。

Windows 原生远程通道管理 skill。

该 skill 通过 PowerShell 和 `ssh.exe` 管理 Android 构建服务器上的 `tmux` 长会话、命令日志、占用状态和锁。它不负责 SMB/UNC 源码接入、Android 编译配置、产物路径映射、本地 `adb.exe` 推送或 Framework 最终验收。

## 典型场景

- Windows 原生 Codex 需要反复在同一个远程 Android 源码树执行命令。
- 远程构建时间较长，需要断开后通过 `status` / `tail` 找回状态和日志。
- 多个自动化可能同时操作同一个源码树，需要占用状态和独占锁。

## 文件入口

- [SKILL.md](../../../../plugins/android-framework-windows-ops/skills/android-windows-remote-channel/SKILL.md)：给 Codex 自动加载的执行说明。
- [scripts/Invoke-AndroidRemoteChannel.ps1](../../../../plugins/android-framework-windows-ops/skills/android-windows-remote-channel/scripts/Invoke-AndroidRemoteChannel.ps1)：Windows PowerShell 调用入口。
