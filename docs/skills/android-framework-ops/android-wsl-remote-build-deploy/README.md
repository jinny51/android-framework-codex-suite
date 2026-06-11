# android-wsl-remote-build-deploy

> GitHub 说明页。Runtime skill 文件位于 [../../../../plugins/android-framework-ops/skills/android-wsl-remote-build-deploy](../../../../plugins/android-framework-ops/skills/android-wsl-remote-build-deploy)；插件安装后的 skill 目录不包含本 README。文中的 `scripts/...`、`references/...` 指向该 runtime skill 目录。

WSL 源码接入场景下的 Android 远程编译和推送 skill。

## 用途

该 skill 用于在 WSL 已经接入服务器源码的前提下，调用远程服务器完成 Android 编译、定位编译产物，并通过本地 adb 推送到设备。

远程长会话、占用状态（正在执行中）和日志恢复由 [android-remote-channel](../android-remote-channel/README.md) 提供；本 skill 只负责构建命令、编译产物定位、推送动作和对应验证结果。

它不负责源码接入，也不负责 Framework 需求的完整验收流程。

## 典型场景

- WSL 已经接入 Android 源码，需要调用服务器编译 `services.jar`、`framework.jar`、`SystemUI.apk` 等文件。
- 构建完成后，需要从 WSL 挂载路径定位编译产物，并通过本地 `adb` 推送到设备。
- Framework 开发流程需要一份构建、编译产物路径、推送结果和设备状态记录，但最终验收结论由 `android-framework-change-workflow` 判断。

## 构建到本机 adb 证据

`scripts/push-artifacts.sh` 支持写出标准验证证据：

```text
<source-root>/.codex/evidence/latest-build-delivery.json
```

或通过 `--evidence-out` / `CODEX_BUILD_DELIVERY_EVIDENCE` 指定路径。该文件记录远端构建服务器、远端源码路径、构建命令、构建 profile、远端产物、产物 SHA1、本机产物、本机 adb serial、push/install/reboot 动作和结果。

`android-framework-patch-capture` 会从每个 `--source-root` 自动读取这份证据并合并进补丁包的 `verification-result.json`，成员不需要在补丁打包时重复手工录入同一串远端构建和本机 adb 参数。

## 文件入口

- [SKILL.md](../../../../plugins/android-framework-ops/skills/android-wsl-remote-build-deploy/SKILL.md)：给 Codex 自动加载的执行说明。
- [references/capability-capture.md](../../../../plugins/android-framework-ops/skills/android-wsl-remote-build-deploy/references/capability-capture.md)：Skill 改进建议记录规则。
- [scripts/](../../../../plugins/android-framework-ops/skills/android-wsl-remote-build-deploy/scripts/)：远程构建、编译产物定位、adb 推送和验证记录采集脚本。
