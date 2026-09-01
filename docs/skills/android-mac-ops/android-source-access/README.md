# android-source-access

> GitHub 说明页。Runtime skill 文件位于 [../../../../plugins/android-mac-ops/skills/android-source-access](../../../../plugins/android-mac-ops/skills/android-source-access)；插件安装后的 skill 目录不包含本 README。文中的 `scripts/...` 指向该 runtime skill 目录。

macOS 原生 Android 服务器源码接入 skill。

公开入口由 `android-mac-ops` 提供，实现集中在 `android-framework-ops`。命令先验证核心版本和 macOS 主机，再执行核心内部 SMB/Keychain adapter；核心缺失、过旧或主机不匹配时不会挂载、写 registry 或保存凭据。

## 用途

该 skill 在 macOS 上提供 SMB/Samba 人工源码 CRUD 和产物桥。平台/项目识别由核心 helper 通过 `android-remote-channel` 在远程执行，平台脚本不扫描挂载源码。

macOS 和 WSL 使用同一目录模型：源码默认挂到 `$HOME/work/<平台>/<项目>`。差异只在挂载和凭据实现：WSL 使用 CIFS 和本机 sudo，macOS 使用原生 SMB 和 Keychain。两边都不能从远端目录名直接猜平台或项目名。

## 常用脚本

```bash
scripts/discover-samba-share.sh
scripts/mount-share.sh
scripts/detect-projects.sh
scripts/register-project.sh
scripts/restore-mounts.sh
scripts/unmount-share.sh
```

如果显式指定的 `--platform` 或 `--sdk-name` 与远端源码识别结果冲突，默认停止并展示两组值。成员确认该次精确冲突后，才可分别使用 `--accept-platform-conflict` 或 `--accept-sdk-name-conflict` 重试；接受参数不能脱离对应的显式值单独使用，也不是跳过远端识别的通用开关。

## 凭据存储

密码通过 macOS Keychain 管理。`scripts/_keychain_helpers.sh` 提供统一读写接口，`scripts/keychain-store.sh` 只在认证成功后保存凭据。无密码的引用位于 `~/.servers/credentials/`，项目映射统一写入 `~/.servers/projects/<server>.json`；不会再读取 ENV 项目注册表或明文密码文件。

默认目录边界：AKBS 系统根目录是 `$HOME/akbs`，Android 源码根目录是 `$HOME/work`。项目默认挂到 `$HOME/work/<平台>/<项目>`，不能挂到 AKBS 根目录。

项目注册表中的本地路径使用 `$HOME/...`，不会写死 macOS 用户名。服务器共享存在子目录时，`smb_path` 单独记录完整的服务器相对路径，例如 `work/mtk/u_mt8xxx_tablet`；恢复挂载时不会把它误当成单层 share 名。

## 和其他 skill 的关系

- `android-remote-build-deploy`：消费本 skill 的路径映射，执行远程构建和本地 adb 推送。
- `android-framework-change-workflow`：负责需求分析、源码修改、风险判断和最终验收。
- `android-knowledge-search`：负责开发前知识搜索。
