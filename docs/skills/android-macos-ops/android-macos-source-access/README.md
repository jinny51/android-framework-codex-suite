# android-macos-source-access

> GitHub 说明页。Runtime skill 文件位于 [../../../../plugins/android-macos-ops/skills/android-macos-source-access](../../../../plugins/android-macos-ops/skills/android-macos-source-access)；插件安装后的 skill 目录不包含本 README。文中的 `scripts/...` 指向该 runtime skill 目录。

macOS 原生 Android 服务器源码接入 skill。

## 用途

该 skill 用于在 macOS 上通过 SMB/Samba 访问 Android 远程构建服务器源码。它负责发现 Samba 共享、挂载共享、扫描挂载树识别 Android 项目、推断平台，并登记本地路径到远程 Linux 源码路径的映射。

macOS 版和 WSL 版的关键差异是：macOS 通常先挂载 share 级目录，再在挂载树里识别项目；不要直接从目录名推断平台或项目名。

## 常用脚本

```bash
scripts/discover-samba-share.sh
scripts/resolve-akbs-root.sh
scripts/resolve-samba-root.sh
scripts/mount-share.sh
scripts/detect-projects.sh
scripts/register-project.sh
scripts/restore-mounts.sh
scripts/unmount-share.sh
```

## 路径边界

- AKBS 系统根目录默认是 `/Users/jinny/Work/AKBS`，可用 `AKBS_ROOT` 覆盖。
- SMB/Samba 源码挂载根目录默认是 `/Users/jinny/Work/Samba`，可用 `SAMBA_SOURCE_ROOT` 覆盖。
- 源码 share 不得挂到 AKBS 系统根目录下面。

## 凭据边界

密码不写入插件仓库，也不写入 runtime skill 目录。macOS 适配层优先复用本机 Keychain 中已有的 SMB/Samba 凭据；只有凭据缺失、失效或权限不足时，才提示用户使用明确修复入口重新保存。只有 SSH、SMB、远端 sudo 或本机 sudo 对应动作验证成功后，才允许保存对应角色的凭据引用。

## 和其他 skill 的关系

- `android-macos-remote-build-deploy`：消费本 skill 的路径映射，执行远程构建和本地 adb 推送。
- `android-framework-change-workflow`：负责需求分析、源码修改、风险判断和最终验收。
- `android-knowledge-search`：负责开发前知识搜索。
