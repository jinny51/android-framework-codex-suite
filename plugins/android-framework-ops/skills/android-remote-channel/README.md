# android-remote-channel

Android 远程通道管理 skill。

## 用途

该 skill 为 Windows/WSL Codex 智能体统一管理远程 SSH/tmux 长会话。

它负责远程命令执行、日志恢复、占用状态（正在执行中）和锁；不负责源码接入、Android 编译配置、编译产物路径对应关系、adb 推送或 Framework 最终验收。

`tmux` 缺失时只通过显式 `install-tmux` 动作安装；该动作只读取环境变量或 source-access 已保存凭证，不保存新密码。

## 典型场景

- 同一个 Android 源码树需要反复执行 `rg`、`git status`、`repo status`、构建命令，不希望每次重新建立 SSH 连接和工作目录信息。
- 远程构建时间较长，需要断开后还能通过 `status` / `tail` 找回命令状态和日志。
- 多个自动化可能同时操作同一个源码树，需要通过占用状态（正在执行中）和独占锁避免并发冲突。

## 文件入口

- [SKILL.md](SKILL.md)：给 Codex 自动加载的执行说明。
- [references/protocol.md](references/protocol.md)：远程 session、日志、占用状态和锁的规则。
- [scripts/remote-channel.sh](scripts/remote-channel.sh)：WSL/Linux 调用入口。
- [scripts/Invoke-AndroidRemoteChannel.ps1](scripts/Invoke-AndroidRemoteChannel.ps1)：Windows PowerShell 调用入口。
