# Android Remote Build Deploy

`android-remote-build-deploy` 是 WSL 与 macOS 共用的 Android 远程构建和本地设备交付技能。

平台插件里的 `android-source-access` 只负责供人使用的源码挂载和远程路径登记。本技能读取 `$HOME/.servers/projects` 的映射，但 Codex 的源码发现、profile 推断、wrapper 安装、checkpoint 和构建全部通过 `android-remote-channel` v2 在远程 Linux 项目根执行。挂载只作为经过 manifest 校验的产物桥，随后由本机 `adb` 推送。

它不会判断 Framework 需求是否真正完成。最终行为验证、回归范围和回滚结论仍由 `android-framework-change-workflow` 负责。

## 当前结构

- WSL ENV 注册表和 macOS JSON 注册表共用一个解析器，并明确区分 `PROJECT_ROOT` 与 `WORKING_SUBPATH`。
- `remote-build-v2.py` 是唯一正式入口；所有源码侧动作都进入 canonical remote workspace。
- 远端 runtime 以 content-addressed release 原子安装到 `PROJECT_ROOT/.codex/remote-v2`，旧 wrapper 只允许显式旁路保留，绝不静默覆盖。
- module build 使用稳定 command ID；断线后相同 ID attach，不重复编译。
- install/configure/profile-set 每次调用使用新的幂等 ensure ID，避免 runtime/config/profile 被清理后误 attach 旧 completed 状态；单次 SSH 不确定窗口仍用同一 ID attach，显式 wait timeout 124 不自动延长。
- 已存在的 content-addressed release 会逐文件复核 SHA-256、权限和 `release.sha256`；篡改返回 `REMOTE_V2_RELEASE_TAMPERED`，不覆盖现场。
- 远端从产物本身生成闭合 SHA-256 manifest；本地重新映射、哈希一致后才允许 adb。
- 本地 manifest、destination memory 和 delivery evidence 写入 `$CODEX_HOME/artifacts`，不写挂载源码。

## 主要入口

```text
scripts/resolve_remote_mapping.py
scripts/remote-build-v2.py
scripts/remote_build_runtime.sh
scripts/remote_profile_infer.py
scripts/remote_artifact_manifest_cli.py
scripts/discover-project.sh
scripts/ensure-build-session.sh
scripts/infer-profile.sh
scripts/create-checkpoint.sh
scripts/push_artifacts.py
```

`discover-project.sh`、`ensure-build-session.sh`、`infer-profile.sh` 和
`create-checkpoint.sh` 仅是 remote-v2 兼容 shim；旧 mounted `--repo` 路径硬失败。
`generate-build-push.sh` 已退役并始终返回迁移指引。

详细执行合同见插件内 `SKILL.md`。
