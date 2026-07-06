# android-wsl-remote-build-deploy

> GitHub 说明页。Runtime skill 文件位于 [../../../../plugins/android-wsl-ops/skills/android-wsl-remote-build-deploy](../../../../plugins/android-wsl-ops/skills/android-wsl-remote-build-deploy)；插件安装后的 skill 目录不包含本 README。文中的 `scripts/...`、`references/...` 指向该 runtime skill 目录。

Windows/WSL SMB/UNC 场景下的 Android 远程编译和推送 skill。

## 用途

该 skill 用于 Windows 主机侧 Codex + WSL/远程 Linux 场景：调用远程服务器构建 Android 编译产物，通过 Windows SMB/UNC 路径定位产物，并使用本地 `adb.exe` 推送到设备。

远程长会话、占用状态（正在执行中）和日志恢复由 [android-wsl-remote-channel](../android-wsl-remote-channel/README.md) 提供；本 skill 只负责 Windows 路径转换、编译产物定位、`adb.exe` 推送和对应验证结果。

它依赖 `android-wsl-source-access` 提供稳定的本地路径、远程源码路径和 SSH 主机映射；不负责 Framework 需求的完整验收流程。

## 典型场景

- Windows 主机侧 Codex 需要通过远程服务器编译 Android 产物，不能直接在 `X:\` 或 UNC 路径上跑 `git/repo/build`。
- 构建完成后，需要通过 SMB/UNC 路径找到编译产物，并用本地 `adb.exe` 推送到设备。
- 需要返回构建日志、编译产物路径、adb 推送结果和设备状态记录，交给 Framework 开发流程做最终判断。

## 文件入口

- [SKILL.md](../../../../plugins/android-wsl-ops/skills/android-wsl-remote-build-deploy/SKILL.md)：给 Codex 自动加载的执行说明。
- [references/capability-capture.md](../../../../plugins/android-wsl-ops/skills/android-wsl-remote-build-deploy/references/capability-capture.md)：Skill 改进建议记录规则。
- [scripts/](../../../../plugins/android-wsl-ops/skills/android-wsl-remote-build-deploy/scripts/)：路径解析、远程构建、编译产物定位、adb 推送和验证记录采集脚本。
