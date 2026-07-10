# Android Remote Build Deploy

`android-remote-build-deploy` 是 WSL 与 macOS 共用的 Android 远程构建和本地设备交付技能。

平台插件里的 `android-source-access` 只负责源码挂载和远程路径登记。挂载完成后，本技能读取 `$HOME/.servers/projects` 中的当前映射，在远程 Linux 源码树执行构建，通过本机 `adb` 推送产物，并把构建、产物和设备动作写入补丁采集可读取的证据。

它不会判断 Framework 需求是否真正完成。最终行为验证、回归范围和回滚结论仍由 `android-framework-change-workflow` 负责。

## 当前结构

- WSL ENV 注册表和 macOS JSON 注册表共用一个解析器。
- 构建发现、profile、远程会话和检查点共用一套脚本。
- 产物推送使用跨平台 Python 执行器，不再维护 WSL/Mac 两套脚本。
- 项目记忆写入项目自己的 `.codex` 目录，不写插件源码或插件缓存。

## 主要入口

```text
scripts/resolve_remote_mapping.py
scripts/discover-project.sh
scripts/generate-build-push.sh
scripts/ensure-build-session.sh
scripts/infer-profile.sh
scripts/create-checkpoint.sh
scripts/push_artifacts.py
```

详细执行合同见插件内 `SKILL.md`。
