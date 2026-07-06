# android-source-access

> GitHub 说明页。Runtime skill 文件位于 [../../../../plugins/android-wsl-ops/skills/android-source-access](../../../../plugins/android-wsl-ops/skills/android-source-access)；插件安装后的 skill 目录不包含本 README。文中的 `scripts/...`、`references/...` 指向该 runtime skill 目录。

WSL 场景下访问服务器 Android 源码的 skill。

## 用途

该 skill 用于在 WSL 中把服务器上的 Android 源码挂载到本地，处理 Samba/CIFS 挂载、项目路径识别、本地路径和远程路径对应关系，以及重启后的访问恢复。

它只负责让 Codex 能在本地访问源码，并记录 `本地路径 -> SSH 主机 -> 远程源码路径` 映射；不负责构建、编译产物推送或最终验收。

## 典型场景

- 用户给出服务器源码路径，例如 `/home/test35/work/rk/TVA10A2R`，需要在 WSL 中挂载到本地 `~/work/rk/TVA10A2R`。
- WSL 重启后挂载丢失，需要恢复之前记录过的源码访问。
- 本地路径、远程路径、SSH 主机之间的对应关系不明确，需要重新识别并记录。

## 文件入口

- [SKILL.md](../../../../plugins/android-wsl-ops/skills/android-source-access/SKILL.md)：给 Codex 自动加载的执行说明。
- [references/design.md](../../../../plugins/android-wsl-ops/skills/android-source-access/references/design.md)：源码访问设计。
- [references/manual-recovery.md](../../../../plugins/android-wsl-ops/skills/android-source-access/references/manual-recovery.md)：手工恢复流程。
- [scripts/](../../../../plugins/android-wsl-ops/skills/android-source-access/scripts/)：挂载、恢复、识别和校验脚本。
