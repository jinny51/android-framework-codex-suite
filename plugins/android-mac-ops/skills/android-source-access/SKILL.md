---
name: android-source-access
description: "Use to mount, remount, or restore Android remote build server Samba/SMB projects on macOS under $HOME/work/<platform>/<project>. Discovers Samba shares, mounts them with macOS native SMB, verifies project identity, and registers local-to-remote mappings for build workflows."
---

# Android macOS Source Access

Use this skill to access Android remote build server source trees on macOS through Samba/SMB. Like the WSL platform skill, it maps each project to `$HOME/work/<platform>/<project>` by default. It owns Samba share discovery, macOS native SMB mounting, project verification, and project mapping registry.

## Boundary

This skill owns:

- Samba share discovery on remote build servers (read `/etc/samba/smb.conf` over SSH).
- macOS native SMB mount (`mount -t smbfs`), no extra software required.
- Post-mount project detection: scan the mounted tree to identify Android source projects.
- Platform inference from source evidence (not from directory names).
- Project mapping registry under `~/.servers/projects/<server>.json`.
- Remount/recovery from saved projects.
- Passwords in macOS Keychain, with password-free references under `~/.servers/credentials/`.

Do not use this skill for:

- Build/deploy: use `android-remote-build-deploy`.
- Framework diagnosis/verification: use `android-framework-change-workflow`.
- Knowledge search: use `android-knowledge-search`.

## Platform Difference from WSL

Both platform plugins use the same local project shape: `$HOME/work/<platform>/<project>`. The differences are implementation details:

- WSL mounts with `mount.cifs` and local sudo; macOS mounts with native SMB and normally needs no sudo.
- WSL keeps verified local credentials in its platform state; macOS stores passwords in Keychain.
- Both infer platform and project from source evidence, never from remote path text alone.
- Project-level Samba shares are the default. A parent share is an explicit exception, not a separate macOS directory model.

## Flow

```
1. discover-samba-share.sh  → 列出服务器 Samba 共享和远端路径
2. mount-share.sh           → 挂载项目 share 到 $HOME/work/<platform>/<project>
3. detect-projects.sh       → 验证挂载根或显式父 share 内的 Android 项目 + 平台
4. register-project.sh      → 注册到 ~/.servers/projects/<server>.json
```

恢复流程：

```
restore-mounts.sh → 从 registry 恢复所有已记录的项目挂载
```

## Credential Storage

密码只保存到 macOS Keychain；`~/.servers/credentials/` 只保存无密码的 Keychain 引用和状态。

```text
~/.servers/
├── credentials/
│   ├── <sha256(remote-user@server)>.keychain.env    # Keychain 引用（无密码）
│   └── local.keychain.env                             # 本机 sudo Keychain 引用
└── projects/
    └── <server>.json                                   # 项目和 share 映射（无密码）
```

### Keychain Service 命名

| 角色 | Service 格式 |
|---|---|
| SSH | `codex.android-mac-source-access.ssh.<hash>` |
| SMB/Samba | `codex.android-mac-source-access.smb.<hash>` |
| Remote sudo | `codex.android-mac-source-access.remote-sudo.<hash>` |
| Local sudo | `codex.android-mac-source-access.local.<local-hash>` |

### <hash>.keychain.env 内容

```bash
ACCOUNT_KEY=<sha256 hash>
REMOTE_USER=test55
SERVER=192.168.100.6

SSH_KEYCHAIN_SERVICE=codex.android-mac-source-access.ssh.<hash>
SMB_KEYCHAIN_SERVICE=codex.android-mac-source-access.smb.<hash>
REMOTE_SUDO_KEYCHAIN_SERVICE=codex.android-mac-source-access.remote-sudo.<hash>

SSH_PASSWORD_STATE=stored|missing|failed
SMB_PASSWORD_STATE=stored
REMOTE_SUDO_PASSWORD_STATE=missing

UPDATED_AT=2026-06-16T12:00:00+08:00
```

### 密码保存规则

"验证后才保存" — 不因为用户输入了密码就保存。只有对应角色实际操作成功后才写入 Keychain。

| 角色 | 验证条件 |
|---|---|
| SSH | SSH key bootstrap 成功后保存 |
| SMB | smbutil view / mount_smbfs 认证成功后保存 |
| Remote sudo | 远端 sudo 操作成功后保存 |
| Local sudo | 本机 sudo 操作成功后保存 |

### 密码读取优先级

```text
1. 本次运行时显式输入密码
2. Keychain 中已保存的密码
3. 本次 bare fallback 密码
4. 提示用户输入
```

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
$HOME/work/<platform>/<project>/   → 默认项目级挂载点
$HOME/work/<platform>/             → 仅在成员明确要求父 share 时使用
```

For test61 project `TVE1088U`:

```text
$HOME/work/unisoc/TVE1088U/  → project root
```

## Scripts

- `scripts/discover-samba-share.sh`: discover available Samba shares from remote server's `/etc/samba/smb.conf` over SSH.
- `scripts/mount-share.sh`: mount a Samba share via macOS native `mount -t smbfs`.
- `scripts/detect-projects.sh`: scan a mounted share tree to identify Android projects and infer platforms.
- `scripts/register-project.sh`: register project mapping in `~/.servers/projects/<server>.json`.
- `scripts/unmount-share.sh`: unmount a Samba share.
- `scripts/restore-mounts.sh`: remount all projects from the local registry (reboot/restart recovery).

## Registry Format

`~/.servers/projects/<server>.json`:

```json
{
  "server": "test61",
  "server_ip": "192.168.100.23",
  "smb_user": "test61",
  "shares": {
    "TVE1088U": {
      "mount_point": "$HOME/work/unisoc/TVE1088U",
      "remote_path": "/home/test61/unisoc/huiwei_uis7885_5g",
      "smb_user": "test61",
      "projects": {
        "TVE1088U": {
          "platform": "unisoc",
          "local_path": "$HOME/work/unisoc/TVE1088U",
          "remote_path": "/home/test61/unisoc/huiwei_uis7885_5g"
        }
      }
    }
  }
}
```

## Handoff

After successful mount + register, hand project work to `android-remote-build-deploy`
with `SSH_HOST`, `REMOTE_ROOT`, `PLATFORM`, and `SDK_NAME`.

## Output

Report results in Chinese with technical identifiers in English:

```text
Samba 共享: //192.168.100.23/TVE1088U
挂载点: $HOME/work/unisoc/TVE1088U
发现项目: TVE1088U (平台: unisoc)
远端路径: /home/test61/unisoc/huiwei_uis7885_5g
注册状态: 已记录
交接: 可交给 android-remote-build-deploy
```

## Safety Rules

- Store passwords only in macOS Keychain. Keychain reference files under `~/.servers/credentials/` must use mode `600`.
- Use `$HOME/akbs` as the default `AKBS_ROOT` and `$HOME/work` as the default `ANDROID_WORK_ROOT`; never mount Android source below AKBS_ROOT.
- Never put credentials in skills, repo files, or build scripts.
- Do not unmount or replace an existing mount unless the user explicitly asks.
- Do not run authoritative Android `git` or builds through the SMB mount.
- If the mount target directory is non-empty, refuse to mount over it.
