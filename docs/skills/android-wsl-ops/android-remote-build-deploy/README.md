# android-remote-build-deploy

> GitHub 说明页。Runtime skill 文件位于 [../../../../plugins/android-wsl-ops/skills/android-remote-build-deploy](../../../../plugins/android-wsl-ops/skills/android-remote-build-deploy)；插件安装后的 skill 目录不包含本 README。文中的 `scripts/...` 指向该 runtime skill 目录。

WSL 远程构建和部署 skill。

## 用途

该 skill 用于 WSL 环境中调用远程 Linux 服务器编译 Android，定位编译产物，并通过本地 `adb` 推送到设备。它依赖 `android-source-access` 提供的路径映射和 `android-remote-channel` 提供的 SSH/tmux 会话。

## 常用脚本

```bash
scripts/ensure-build-session.sh
scripts/generate-build-push.sh
scripts/push-artifacts.sh
scripts/resolve-remote-mapping.sh
```

## 和其他 skill 的关系

- `android-source-access`：提供源码路径映射。
- `android-remote-channel`：提供远程 SSH/tmux 会话。
- `android-framework-change-workflow`：负责诊断修改和最终验收。
