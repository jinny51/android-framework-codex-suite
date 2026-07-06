---
name: android-macos-source-access
description: "Use to mount, remount, or restore Android remote build server Samba/SMB shares on macOS. Discovers Samba shares from the server, mounts them via macOS native SMB, scans the mounted tree for Android projects, and registers project mappings for build workflows."
---

# Android macOS Source Access

Use this skill to access Android remote build server source trees on macOS through Samba/SMB. It owns Samba share discovery, macOS native SMB mounting, project detection from the mounted tree, and project mapping registry.

## Boundary

This skill owns:

- Samba share discovery on remote build servers (read `/etc/samba/smb.conf` over SSH).
- macOS SMB/Samba source access using the platform's native SMB implementation.
- Post-mount project detection: scan the mounted tree to identify Android source projects.
- Platform inference from source evidence (not from directory names).
- Local project registry under `~/.servers/projects`.
- Remount/recovery from saved projects.
- Samba credential reuse and storage through macOS Keychain.

Do not use this skill for:

- Build/deploy: use `android-macos-remote-build-deploy`.
- Framework diagnosis/verification: use `android-framework-change-workflow`.
- Knowledge search: use `android-knowledge-search`.

## Key Difference from WSL

In WSL, CIFS can mount directly to a project subdirectory (e.g., `//server/rk3576`).
With macOS Samba, the share is typically a parent directory (e.g., `[unisoc]` at `/home/test61/unisoc`),
and Android projects are subdirectories inside it. Therefore:

- **Project detection happens AFTER mount**, by scanning the mounted tree.
- Platform is inferred from source evidence inside the project, not from remote path segments.
- The mount target is a share-level directory; projects within it are registered separately.

## Flow

```
1. discover-samba-share.sh  → 列出服务器 Samba 共享
2. mount-share.sh           → 挂载共享到本地
3. detect-projects.sh       → 扫描挂载树，识别 Android 项目 + 平台
4. register-project.sh      → 注册到 ~/.servers/projects/<server>.json
```

恢复流程：

```
restore-mounts.sh → 从 JSON registry 恢复所有已记录的 SMB/Samba share root 挂载
```

AKBS system root and Samba source root are separate:

```text
AKBS_ROOT default:          /Users/jinny/Work/AKBS
SAMBA_SOURCE_ROOT default:  /Users/jinny/Work/Samba
```

`AKBS_ROOT` is only for the AKBS local system checkout. Do not mount source shares under it.

## Credential Storage

在 `~/.servers/credentials/` 下保存 Keychain 引用，不保存明文密码；项目映射写入 `~/.servers/projects/`。

```text
~/.servers/
├── credentials/
│   ├── <sha256(remote-user@server)>.keychain.env    # Keychain 引用（无密码）
│   └── local.keychain.env                             # 本机 sudo Keychain 引用
└── projects/
    └── <server>.json                                  # 项目 registry（无密码）
```

旧目录 `~/.codex/android-macos-source-access-info` 不再作为运行时读取位置。升级后如本机已有旧目录，先显式执行：

```bash
scripts/migrate-state-dir.sh
```

### Keychain Service 命名

| 角色 | Service 格式 |
|---|---|
| SSH | `codex.android-macos-source-access.ssh.<hash>` |
| SMB/Samba | `codex.android-macos-source-access.smb.<hash>` |
| Remote sudo | `codex.android-macos-source-access.remote-sudo.<hash>` |
| Local sudo | `codex.android-macos-source-access.local.<local-hash>` |

### <hash>.keychain.env 内容

```bash
ACCOUNT_KEY=<sha256 hash>
REMOTE_USER=test55
SERVER=192.168.100.6

SSH_KEYCHAIN_SERVICE=codex.android-macos-source-access.ssh.<hash>
SMB_KEYCHAIN_SERVICE=codex.android-macos-source-access.smb.<hash>
REMOTE_SUDO_KEYCHAIN_SERVICE=codex.android-macos-source-access.remote-sudo.<hash>

SSH_PASSWORD_STATE=stored|missing|failed
SMB_PASSWORD_STATE=stored
REMOTE_SUDO_PASSWORD_STATE=missing

UPDATED_AT=2026-06-16T12:00:00+08:00
```

### 密码复用和保存规则

默认优先复用 macOS 本地已保存的 Keychain 凭据。不要把重新保存密码作为默认路径。
只有凭据缺失、失效或权限不足时，才提示用户使用明确修复入口重新保存。

"验证后才保存" — 不因为用户输入了密码就保存。只有对应角色实际操作成功后才写入 Keychain。

| 角色 | 验证条件 |
|---|---|
| SSH | SSH key bootstrap 成功后保存 |
| SMB | SMB/Samba share 挂载或认证成功后保存 |
| Remote sudo | 远端 sudo 操作成功后保存 |
| Local sudo | 本机 sudo 操作成功后保存 |

### 密码读取优先级

```text
1. 本次运行时显式传入的密码环境变量
2. Keychain 中已保存的密码
3. 提示用户输入
```

### macOS vs WSL 差异

| WSL | macOS |
|---|---|
| 明文 `<hash>.cred` 文件 | **无** - 密码在 Keychain 中 |
| 明文 `<hash>.passwords.env` | **无** - 密码在 Keychain 中 |
| 明文 `local-sudo.env` | **无** - 密码在 Keychain 中 |
| 无 | **新增** `<hash>.keychain.env` - Keychain 引用 |
| mount.cifs credentials 文件 | 运行时临时生成，EXIT trap 删除 |

Do not package credentials when distributing this skill.

## Platform Detection

Platform is determined by source evidence inside the project:
- `device/rockchip` → `rk`
- `vendor/sprd` or `device/sprd` → `unisoc`
- `vendor/mediatek` → `mtk`

Directory names (e.g., `unisoc/`, `rk3576/`) are NOT used as platform signals.

## Project Naming

Project/SDK name is determined by:
1. Key repo branches: `frameworks/base`, platform `device/...`, `vendor/.../common`, `kernel`
2. `BRANCH_BUILDTYPE` from build config
3. Ask user if neither works

`PRODUCT_NAME` / lunch target is a build product name, NOT the SDK/project name.

## Local Mount Path Convention

```text
/Users/jinny/Work/Samba/<hostname>/   → share mount point
/Users/jinny/Work/Samba/<hostname>/<project>/   → project root (detected)
```

For test61 with share `[unisoc]`:

```text
/Users/jinny/Work/Samba/test61/                   → share root
/Users/jinny/Work/Samba/test61/huiwei_uis7885_5g/  → project root
```

## Scripts

- `scripts/discover-samba-share.sh`: discover available Samba shares from remote server's `/etc/samba/smb.conf` over SSH.
- `scripts/resolve-akbs-root.sh`: resolve the local AKBS system root (`AKBS_ROOT` override supported).
- `scripts/resolve-samba-root.sh`: resolve the SMB/Samba source root (`SAMBA_SOURCE_ROOT` override supported).
- `scripts/mount-share.sh`: mount a Samba share through macOS SMB support.
- `scripts/detect-projects.sh`: scan a mounted share tree to identify Android projects and infer platforms.
- `scripts/register-project.sh`: register project mapping in `~/.servers/projects/<server>.json`.
- `scripts/unmount-share.sh`: unmount a Samba share.
- `scripts/restore-mounts.sh`: remount all projects from the local registry (reboot/restart recovery).
- `scripts/migrate-state-dir.sh`: one-time move from the old `.codex` state directory to `~/.servers`.

## Registry Format

`~/.servers/projects/<server>.json`:

```json
{
  "server": "test61",
  "server_ip": "192.168.100.23",
  "smb_user": "test61",
  "shares": {
    "unisoc": {
      "mount_point": "/Users/jinny/Work/Samba/test61",
      "remote_path": "/home/test61/unisoc",
      "smb_user": "test61",
      "projects": {
        "huiwei_uis7885_5g": {
          "platform": "unisoc",
          "local_path": "/Users/jinny/Work/Samba/test61/huiwei_uis7885_5g",
          "remote_path": "/home/test61/unisoc/huiwei_uis7885_5g"
        }
      }
    }
  }
}
```

## Handoff

After successful mount + register, hand project work to `android-macos-remote-build-deploy`
with `SSH_HOST`, `REMOTE_ROOT`, `PLATFORM`, and `SDK_NAME`.

## Output

Report results in Chinese with technical identifiers in English:

```text
Samba 共享: //192.168.100.23/unisoc
挂载点: /Users/jinny/Work/Samba/test61
发现项目: huiwei_uis7885_5g (平台: unisoc)
远端路径: /home/test61/unisoc/huiwei_uis7885_5g
注册状态: 已记录
交接: 可交给 android-macos-remote-build-deploy
```

## Safety Rules

- Store credentials only under `~/.servers/credentials/` with mode `600`.
- Never put credentials in skills, repo files, or build scripts.
- Do not unmount or replace an existing mount unless the user explicitly asks.
- Do not run authoritative Android `git` or builds through the SMB mount.
- If the mount target directory is non-empty, refuse to mount over it.
- Do not mount SMB/Samba source shares under `AKBS_ROOT`; use `SAMBA_SOURCE_ROOT`.
