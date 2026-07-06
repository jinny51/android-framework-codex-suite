---
name: android-source-access
description: Use to mount, remount, or restore Android remote build server Samba/CIFS SDK source roots into WSL project folders such as work/rk/TVA10A2R or work/unisoc/TVE1088U. Handles first-time project-level mounting, fast reboot/Codex-restart recovery from remembered projects, Samba share discovery, safe CIFS options, and source-based platform/project recognition when remote path segments are wrong or misleading.
---

# Android WSL Source Access

Use this skill only for WSL/CIFS access to Android source trees. It owns first-time mounting and reboot recovery. It does not run Android builds, authoritative git, adb deploy, or source edits beyond mount setup.

Before changing or extending this skill's scripts, read `references/design.md`.
It defines the non-expansion rules, platform/project recognition priority, and
module boundaries.

## Responsibilities

- Bootstrap passwordless SSH for first-time server access by installing the local public key.
- Discover a Samba URL from a user-provided SSH server and remote source path.
- If the remote SDK root is not covered by Samba config, configure a project-level Samba share by default, validate the config, reload/restart Samba, then continue mounting.
- Mount remote Android SDK roots into stable WSL project folders.
- Remember an already-mounted project path.
- Remember the matching SSH host and remote source path so project build/deploy work can resume without asking.
- Restore the exact same project path after Windows/WSL/device reboot.
- Verify that the local WSL path is usable before handing off to project work.

The skill folder is `<path-to-this-skill>/`. Runtime mount memory is a separate local info directory on the WSL Linux filesystem: `$HOME/.servers/`.

The info directory is not a skill:

- It stores remembered mount data by Samba account/server, not by SDK.
- For the same SSH/Samba account, `projects/` has one account-level registry file that can contain multiple SDK paths.
- For the same SSH/Samba account, `credentials/` has one account-level Samba credential file and one account-level password fallback file.
- Password storage has two scopes. The remote account/server scope stores server facts and server-side typed passwords in `.passwords.env`: `SAVED_SSH_PASSWORD`, `SAVED_SAMBA_PASSWORD`, and `SAVED_REMOTE_SUDO_PASSWORD`. The local WSL scope stores one local typed password in `local-sudo.env`: `SAVED_LOCAL_SUDO_PASSWORD`.
- SSH keys only affect SSH login; CIFS/Samba remount still needs Samba authentication unless the share allows guest access.
- Password resolution has five inputs during a run: one bare/default password plus four typed passwords. The four typed roles are SSH bootstrap, Samba, remote sudo, and local WSL sudo. A bare `密码...` value is only a runtime fallback: each role tries explicit typed password, then saved typed password, then the runtime default. If the runtime default succeeds for a role, store it as that role's typed password; do not persist a separate saved default password. Explicit `服务器密码...` or `远端密码...` targets the three remote roles; explicit `WSL密码...`, `本机密码...`, or `本地sudo密码...` targets local WSL sudo.
- Do not save a password just because it was available. Save it only after the corresponding role was actually verified in this run: SSH after key install succeeds with password auth, Samba after CIFS mount succeeds with password credentials, remote sudo after Samba auto-config succeeds with password sudo, and local sudo after local mount sudo succeeds with password sudo.
- Stored credentials live under `$HOME/.servers/credentials/` with mode `600`. Samba mount credentials use `.cred`; saved SSH/Samba/remote-sudo fallback passwords use account-level `.passwords.env` files; saved local-sudo fallback uses `local-sudo.env`.
- Do not package another user's info directory, registry, or credentials when distributing the skill.

Build/deploy skills consume this skill's `SSH_HOST` and `REMOTE_ROOT` handoff and may then call `android-remote-channel`; this source-access skill should not create long-running remote sessions itself.

## Platform Targets

Default targets, with `<wsl-user>` coming from the current WSL account:

```text
unisoc -> /home/<wsl-user>/work/unisoc
mtk    -> /home/<wsl-user>/work/mtk
rk     -> /home/<wsl-user>/work/rk
```

Only use a different target when the user explicitly provides one.

When the user explicitly states the real platform, treat that statement as the
platform authority. Otherwise, inspect the remote source tree to determine the
platform. The platform segment inside the remote path may be wrong, omitted, or
non-standard and must not be used as a platform fallback. If source inspection
cannot determine the platform, stop and ask the user for it. If source
inspection confidently identifies a different platform from the user-stated
platform, stop and ask which one to use.

Use project-level mounting by default so sibling projects or platform folders
from the remote parent directory are not exposed locally. Use key repository
branches such as `frameworks/base` as the SDK/project folder name when available.
Do not use the remote path basename as a fallback. If source inspection cannot
determine the project name, stop and ask the user for it or require an explicit
`--sdk-name`. If source inspection identifies a different project name from the
user-stated project name, stop and ask which one to use.

Example:

```text
remote source path: /home/test55/work/unisoc/rk3576
user states: "it shows unisoc, but the real platform is rk"
frameworks/base branch: TVA10A2R
local project path: /home/<wsl-user>/work/rk/TVA10A2R
mount shape: //server/<project-share> -> /home/<wsl-user>/work/rk/TVA10A2R
```

Low-level CIFS option shape:

```text
/home/<wsl-user>/work/<platform>/<project> -> //server/<project-share>
fstype: cifs
uid/gid: current WSL user
file_mode/dir_mode: 0644/0755
core opts: vers=3.0, cache=strict, soft, nounix, noperm, actimeo=1
```

## Inputs

Ask only for what is missing:

- remote source path to an Android SDK source tree, preferably `/home/<remote-user>/work/<platform>/<sdk>`, for example `/home/test55/work/rk/TVA10A2R`; tolerate missing `work`, wrong platform segment, extra `//home`, or misleading basename, but do not use those path segments to decide platform or project name
- optional password phrases:
  - `密码123` means runtime default fallback `SERVER_PASSWORD=123`; each role uses explicit typed password, then saved typed password, then `123`; successful defaults are saved as typed passwords, not as a separate default password
  - `服务器密码123` or `远端密码123` means `SERVER_PASSWORD=123` plus `--ssh-password-env SERVER_PASSWORD --samba-password-env SERVER_PASSWORD --remote-sudo-password-env SERVER_PASSWORD`
  - `WSL密码123`, `本机密码123`, or `本地sudo密码123` means `LOCAL_SUDO_PASSWORD=123` plus `--local-sudo-password-env LOCAL_SUDO_PASSWORD`
  - role-specific `SSH密码...`, `Samba密码...`, or `远端sudo密码...` may be passed with `--ssh-password-env`, `--samba-password-env`, or `--remote-sudo-password-env`
- optional explicit IP from phrases such as `ip192.168.0.199`; use it as `<remote-user>@IP` and as the Samba `--server-name`
- local WSL project path when restoring a remembered project path

Default remote path rule:

```text
/home/test61/mtk/tb8788p1
REMOTE_USER = test61
SSH_HOST    = test61
PLATFORM    = pending until user input or source inspection
SDK_NAME    = pending until user input or source inspection
LOCAL_PATH  = pending until platform and project name are known
```

The path user is the first SSH host/user hint. For `/home/test55/...`, derive `REMOTE_USER=test55`, try SSH candidates for `test55`, and use `test55` as the default Samba user.

Recognize these common user forms precisely:

```text
把/home/test55/work/unisoc/rk3576，挂载到rk平台
把/home/test55/work/unisoc/rk3576，挂载到rk平台，密码123
把/home/test55/work/unisoc/rk3576，挂载到rk平台，密码123，ip192.168.0.199
把/home/test61/unisoc/huiwei_uis7885_5g挂载到本地，WSL密码123，服务器密码123
把/home/test35/work/mtk/u_mt8xxx_tablet挂载到本地，密码2
```

Map them to `--remote-root /home/test55/work/unisoc/rk3576`, optional `--local-platform rk`, optional runtime default `SERVER_PASSWORD=123`, optional explicit server password flags `--ssh-password-env SERVER_PASSWORD --samba-password-env SERVER_PASSWORD --remote-sudo-password-env SERVER_PASSWORD`, optional `LOCAL_SUDO_PASSWORD=123 --local-sudo-password-env LOCAL_SUDO_PASSWORD`, and optional `--ip 192.168.0.199`. When the user gives only bare `密码2`, pass `SERVER_PASSWORD=2` and no typed password flags; the script should use saved typed passwords first and `2` only for roles that have no saved typed password. Project-level mounting is the default. Because the user said `rk平台`, do not trust the path's `unisoc` segment. Inspect the remote SDK root and prefer key repository branches such as `frameworks/base` as the local SDK name. If the SDK name is not available from source evidence and the user did not state it, stop and ask for the project name.

Do not use system DNS lookup as the main discovery path. Use SSH alias/config discovery:

- If an IP is provided, prefer `<remote-user>@IP`.
- Otherwise run `scripts/resolve-ssh-candidate.sh` or let `mount-from-remote-path.sh` run it. It checks WSL SSH config and the Windows/VSCode config at `/mnt/c/Users/<user>/.ssh/config` when present.
- Treat `User == <remote-user>` as the primary signal, because the `/home/<remote-user>/...` segment is the remote login account. One user may have multiple IPs; include all matching `User` entries and try them.
- Treat `Host == <remote-user>` as a secondary alias fallback. This catches simple aliases without making a stale alias outrank a better user match.
- Use short SSH/TCP checks and verify the remote root exists; do not wait on one stale alias.
- If no explicit IP or SSH config HostName candidate exists, stop and ask for the server IP. Do not try DNS names such as `test55`, scan networks, or invent adjacent hostnames.

Passwordless SSH after key bootstrap does not remove the need for Samba credentials when the CIFS mount has to be recreated.
Discover scripts should resolve the real Samba host/IP through the chosen SSH candidate; if that is wrong, ask for `--server-name` or accept an `ip...` value.

## First-Time Mount Flow

Do not use this flow for "remount", "restore", "after reboot", "Codex restarted",
or "mount it again" requests until the Reboot Recovery Flow has been tried. A
remembered project restore is the fast path and normally does not need SSH,
Samba discovery, Samba config inspection, or path re-derivation.

Default goal: the user gives one remote SDK path and Codex mounts it into WSL. Do not ask the user to decide whether Samba is already configured. Try the full path-driven flow first, and stop only on hard blockers such as missing password, missing remote path, unresolved platform/project name after source inspection, failed SSH, insufficient remote sudo permission, invalid Samba config, Samba reload/restart failure, conflicting existing local mount, or local sudo failure.

If the real project folder does not exist yet, start Codex from `/home/<wsl-user>/work` and perform the mount from there. After the project path appears, switch/open the real project folder for development.

Preferred one-shot command:

```bash
SKILL_DIR="<path-to-this-skill>"
read -rsp "Server password: " SERVER_PASSWORD; echo
SERVER_PASSWORD="$SERVER_PASSWORD" "$SKILL_DIR/scripts/mount-from-remote-path.sh" \
  --remote-root /home/test61/mtk/tb8788p1
unset SERVER_PASSWORD
```

When the remote path is non-standard or the platform directory is wrong, pass a
local platform override. The command still mounts only the project by default:

```bash
SKILL_DIR="<path-to-this-skill>"
read -rsp "Server password: " SERVER_PASSWORD; echo
SERVER_PASSWORD="$SERVER_PASSWORD" "$SKILL_DIR/scripts/mount-from-remote-path.sh" \
  --remote-root /home/test55/work/unisoc/rk3576 \
  --local-platform rk
unset SERVER_PASSWORD
```

When the user explicitly provides both WSL and server passwords, keep them
separate:

```bash
SKILL_DIR="<path-to-this-skill>"
SERVER_PASSWORD="123" LOCAL_SUDO_PASSWORD="123" "$SKILL_DIR/scripts/mount-from-remote-path.sh" \
  --remote-root /home/test61/unisoc/huiwei_uis7885_5g \
  --ssh-password-env SERVER_PASSWORD \
  --samba-password-env SERVER_PASSWORD \
  --remote-sudo-password-env SERVER_PASSWORD \
  --local-sudo-password-env LOCAL_SUDO_PASSWORD
```

When the user provides an explicit IP, pass it directly:

```bash
SKILL_DIR="<path-to-this-skill>"
SERVER_PASSWORD="123" "$SKILL_DIR/scripts/mount-from-remote-path.sh" \
  --remote-root /home/test55/work/unisoc/rk3576 \
  --local-platform rk \
  --ip 192.168.0.199
```

What the one-shot command does:

- Derives only the remote user, SSH seed, Samba user, and remote root from the path.
- Resolves SSH candidates from the path user, explicit IP, WSL SSH config, and Windows/VSCode SSH config; validates candidates with short checks before choosing one.
- Honors an explicit `--local-platform` override when the remote path uses the wrong platform directory.
- Treats the user path as the remote source root, inspects the SDK over SSH, and uses key repository branches such as `frameworks/base` as the local SDK/project name when available.
- Stops and asks for the platform or project name when neither user input nor source inspection can provide it.
- Stops and asks when user-stated platform/project values conflict with source-tree evidence; do not silently prefer either side.
- After the user confirms a conflict, continue with `--accept-platform-conflict` or `--accept-sdk-name-conflict` together with the explicit `--local-platform` or `--sdk-name`.
- Installs the local SSH public key if passwordless SSH is not ready.
- Discovers an existing Samba share.
- If no Samba share covers the remote SDK path, appends a project-level share such as `[TVA10A2R] path = /home/test55/work/unisoc/rk3576`, backs up `smb.conf`, validates with `testparm` when available, reloads/restarts Samba, and retries discovery.
- If the user explicitly requests platform-level mounting, create or use a parent share for the remote SDK parent directory only for that run.
- Mounts only the discovered project URL to `/home/<wsl-user>/work/<platform>/<sdk>` by default.
- Never mount a parent share such as `//server/work` onto `/home/<wsl-user>/work/<platform>` unless the user explicitly requests platform-level mounting.
- For project-level mounts, refuse to continue if `/home/<wsl-user>/work/<platform>` is already a mount point, because that indicates a previous parent-share mount that would pollute the platform folder.
- Refuse to mount over a non-empty local target directory that is not already the same mount.
- Verifies `/home/<wsl-user>/work/<platform>/<sdk>` is an Android source tree.
- Stores mount info, remote mapping, Samba credentials, account-level SSH/Samba/remote-sudo fallback passwords, and the global local-sudo fallback password under `.servers` for reboot recovery and project build/deploy handoff.

If the one-shot command fails and a narrower step is needed, read `references/manual-recovery.md`.

## Reboot Recovery Flow

Use this flow first whenever the user asks to remount, restore, mount again, or
continue after Windows/WSL/Codex restart. This flow is authoritative for known
projects. Do not re-run Samba discovery or first-time mounting just because the
user restated the remote path.

When an existing project no longer has a usable local WSL path after reboot, or
when Codex has restarted and the project may already be remembered:

Always list remembered projects first unless the user gave an exact local
project path and explicitly says to use it:

```bash
SKILL_DIR="<path-to-this-skill>"
"$SKILL_DIR/scripts/restore-project-mount.sh" --list
```

If the remembered project shows `credentials=stored`, restore without asking for
the Samba password:

```bash
SKILL_DIR="<path-to-this-skill>"
"$SKILL_DIR/scripts/restore-project-mount.sh" \
  --project "/home/<wsl-user>/work/<platform>/<project>" \
  --restore
```

If the path is already usable, restore reports `MOUNT_OK ... already_usable=true` and does not need credentials.

If local sudo is needed in a non-interactive Codex session, restore first tries
the saved local sudo fallback password. If the user supplied a replacement
password for this run, pass it with `--local-sudo-password-env`:

```bash
SKILL_DIR="<path-to-this-skill>"
LOCAL_SUDO_PASSWORD="$LOCAL_SUDO_PASSWORD" "$SKILL_DIR/scripts/restore-project-mount.sh" \
  --project "/home/<wsl-user>/work/<platform>/<project>" \
  --restore \
  --local-sudo-password-env LOCAL_SUDO_PASSWORD
```

If the remembered project shows `credentials=not_stored`, ask for the Samba password, restore once, then remember it for future reboot recovery:

```bash
SKILL_DIR="<path-to-this-skill>"
read -rsp "Samba password: " SAMBA_PASSWORD; echo
SAMBA_PASSWORD="$SAMBA_PASSWORD" "$SKILL_DIR/scripts/restore-project-mount.sh" \
  --project "/home/<wsl-user>/work/<platform>/<project>" \
  --restore
SAMBA_PASSWORD="$SAMBA_PASSWORD" "$SKILL_DIR/scripts/restore-project-mount.sh" \
  --project "/home/<wsl-user>/work/<platform>/<project>" \
  --remember-current \
  --remember-password
unset SAMBA_PASSWORD
```

The remembered registry supplies the share/user/version; stored Samba credentials remove the password prompt on the next remount.

If no remembered entry exists or restore fails because the registry is stale,
then perform the first-time mount flow again with the current server/path
information. A restore failure caused only by local sudo prompting is not a
reason to run first-time Samba discovery.

## Final Report

用户可见最终报告使用中文字段名，技术变量、命令名和路径保持原样。成功挂载或恢复后，优先覆盖这些信息；缺失或不适用的项可以省略：

```text
挂载结果: <成功/已恢复/已存在/失败>
本地路径: <LOCAL_PROJECT>
远程路径: <REMOTE_ROOT>
Samba 映射: <SAMBA_PROJECT_URL 或 SAMBA_SHARE_URL>
项目识别: <platform>/<SDK_NAME>，来源如 source inspection、PROJECT_BRANCH、BRANCH_BUILDTYPE 或用户确认
恢复信息: <registry/credentials 是否已记录，是否可用于 reboot/Codex-restart restore>
交接: <是否可交给 android-remote-build-deploy，或还缺什么>
```

失败报告也用中文说明阻塞点，但保留脚本输出中的技术标识，例如 `IP_REQUIRED`、`PASSWORD_REQUIRED`、`PLATFORM_CONFLICT`、`SDK_NAME_REQUIRED`、`FAILED_HINT`、SSH、Samba、registry、`.codex`。

## Capability Capture

Default final reports do not include capability-capture summaries. At task end,
only consider a short `Skill 改进建议` when the work produced a
reusable mount/recovery pattern, diagnostic rule, verification method, failure
handling lesson, script idea, or exposed a gap in this skill. If triggered, read
`references/capability-capture.md` and append the candidate block at the very
end of the final report.

Never persist a candidate into this skill automatically. Only update `SKILL.md`,
`references/`, or `scripts/` after the user explicitly confirms.

## Bundled Scripts

- `scripts/install-ssh-key.sh`: install a local SSH public key on the remote account using the first-time SSH password, then verify passwordless SSH.
- `scripts/resolve-ssh-candidate.sh`: derive and rank SSH targets from a remote path user, optional explicit IP, WSL SSH config, and Windows/VSCode SSH config; verifies the remote root with short checks.
- `scripts/plan-from-remote-path.sh`: derive only connection basics such as user, SSH host seed, Samba user, and remote root from `/home/<user>/...`; supports explicit local platform and SDK-name overrides without inventing them from path segments.
- `scripts/inspect-android-sdk.sh`: quickly inspect a remote SDK source root over SSH; infer `rk`, `unisoc`, or `mtk` from high-signal source-tree evidence such as `device/rockchip`, `vendor/sprd`, `vendor/mediatek`, and `TARGET_BOARD_PLATFORM`. For the SDK/project name, prefer key-repo branches such as `frameworks/base`, platform `device/...`, `vendor/.../common`, `kernel`, or `u-boot` (for example `TVA10A2R`). Treat Android `PRODUCT_NAME`/lunch values as build product names, not business SDK/project names; use them only as diagnostic output. Use `BRANCH_BUILDTYPE` next. If platform or project name is still missing, return `PLATFORM_REQUIRED` or `SDK_NAME_REQUIRED` instead of falling back to the path. If explicit user input disagrees with source evidence, return `PLATFORM_CONFLICT` or `SDK_NAME_CONFLICT`.
- `scripts/mount-from-remote-path.sh`: one-shot path-driven mount; resolves SSH candidates, installs SSH key, discovers or configures Samba, mounts, verifies, saves passwords, and remembers reboot recovery info; supports project-level mounting for remote/local platform mismatches.
- `scripts/ensure-samba-share.sh`: check or create a Samba share covering a remote SDK path; defaults to project-level shares and only creates parent shares when the caller explicitly passes a parent `--share-name` and `--share-path`.
- `scripts/discover-samba-share.sh`: read server Samba config over SSH and derive a Samba URL from a remote source path.
- `scripts/mount-platform.sh`: low-level CIFS mount helper; normal project-level flows pass `--target /home/<wsl-user>/work/<platform>/<project>`, while the platform-folder default is only for explicit parent/platform share operations.
- `scripts/restore-project-mount.sh`: list, remember, and restore exact project paths after reboot; stores remote source mapping, stores Samba credentials with `--remember-password`, and reuses saved local sudo/Samba fallback passwords when available.
- `scripts/validate-skill.sh`: one-command non-destructive regression check for script syntax, path non-inference, project-level Samba defaults, conflict-acceptance flags, stale wording, and optional remote inspect checks.

## Safety Rules

- Store requested SSH/Samba/remote-sudo/local-sudo passwords only under the WSL Linux `$HOME/.servers/credentials/` directory with file mode `600`, not under `/mnt/c`.
- Still prefer SSH public-key login after bootstrap; saved SSH password is a fallback for first-time or repaired hosts, not the normal connection method.
- Never put credentials in skills, repo files, generated project configs, build scripts, or distributable handoff packages.
- Do not ask the user to inspect Samba config manually; auto-configure it when needed, but stop and report if remote sudo/config validation/service reload fails.
- Do not guess a parent/platform share from an old project or old server.
- Do not unmount or replace an existing platform mount unless the user explicitly asks.
- Do not run authoritative Android `git` or builds through CIFS.
- Use WSL/CIFS paths for local source inspection and edits only.
- If `sudo` requires a password locally, show the exact command or ask the user to run it.
- After mount/restore succeeds, hand project work to `android-remote-build-deploy`.
