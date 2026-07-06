# android-macos-remote-build-deploy

> GitHub 说明页。Runtime skill 文件位于 [../../../../plugins/android-mac-ops/skills/android-macos-remote-build-deploy](../../../../plugins/android-mac-ops/skills/android-macos-remote-build-deploy)；插件安装后的 skill 目录不包含本 README。文中的 `scripts/...` 指向该 runtime skill 目录。

macOS 原生远程构建和本地部署 skill。

## 用途

该 skill 在 macOS SMB 源码映射已经建立后使用。它读取 `android-macos-source-access` 的项目映射或项目 `.codex` 配置，解析本地挂载路径对应的远程 Linux 源码路径，然后通过 `android-remote-channel` 在远程服务器执行构建，并用 macOS 本地 `adb` 推送产物。

## 边界

- 不负责源码挂载；源码挂载使用 `android-macos-source-access`。
- 不负责 Framework 需求诊断或最终验收；这些由 `android-framework-change-workflow` 负责。
- 不在 macOS SMB 挂载路径上执行权威 `git`、`repo` 或 Android 构建。
- 不提交、上传或沉淀 AKBS incoming 包。

## 常用脚本

```bash
scripts/resolve-remote-mapping.sh
scripts/discover-project.sh
scripts/ensure-build-session.sh
scripts/generate-build-push.sh
scripts/infer-profile.sh
scripts/push-artifacts.sh
```

## 输出要求

返回时说明本地路径到远程路径的映射、构建配置、构建结果、产物位置、部署结果、设备状态和下一步阻塞项。构建和部署证据可以交给 `android-framework-change-workflow` 判断最终需求是否完成。
