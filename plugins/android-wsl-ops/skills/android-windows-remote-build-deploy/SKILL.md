---
name: android-windows-remote-build-deploy
description: Use on Windows-side Codex agents in a Windows/WSL workflow after Android source has a Windows SMB drive/UNC mapping from android-windows-source-access. Resolves local-to-remote mapping, performs all Android source search/read/write/patch/git/repo/build operations on the remote Linux/WSL source tree over SSH, uses the Windows SMB mapping only to pick up build artifacts, deploys with local adb.exe, and returns build/deploy/device health evidence.
---

# Android Windows Remote Build Deploy

Use this skill as the Windows/WSL Android build/deploy executor.

It consumes an SMB mapping recorded by `android-windows-source-access`, runs all source-tree operations on the remote Linux path over SSH, then uses the Windows local mapping only to read produced artifacts for `adb.exe` deployment.

## Hard Boundary

On Windows-side agents, do not search, read, edit, patch, run `git`, run `repo`, or build against `X:\...` or `\\server\share\...` source paths.

Use the remote Linux source tree for all source operations. Prefer `android-windows-remote-channel` for repeated work; this skill's session helper is a compatibility wrapper around that channel:

```powershell
$SkillDir = "$env:USERPROFILE\.codex\skills\android-windows-remote-build-deploy"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$SkillDir\scripts\Invoke-WindowsRemoteSession.ps1" `
  -SshHost "test55@192.168.100.6" `
  -RemoteRoot "/home/test55/work/unisoc/rk3576" `
  -Action ensure
```

Short SSH commands are only the fallback path:

```powershell
ssh.exe test55@192.168.100.6 "cd '/home/test55/work/unisoc/rk3576' && rg 'pattern' frameworks/base"
```

Use the Windows SMB mapping only for artifact pickup after the remote build has produced files:

```powershell
$artifact = "X:\unisoc\rk3576\out\target\product\<product>\system\framework\services.jar"
```

Windows local commands in this skill are PowerShell and `ssh.exe` only. Any `.sh` wrapper is executed on the remote Linux source tree through SSH or the persistent remote session.

## Workflow

1. Resolve the Windows mapping:

```powershell
$SkillDir = "$env:USERPROFILE\.codex\skills\android-windows-remote-build-deploy"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$SkillDir\scripts\Resolve-WindowsRemoteMapping.ps1" `
  -LocalRepo "X:\unisoc\rk3576"
```

The resolver returns `LOCAL_REPO`, `SSH_HOST`, `REMOTE_ROOT`, optional `PLATFORM`, optional `SDK_NAME`, `SMB_ROOT`, and registry evidence.

2. Validate context:

- `LOCAL_REPO` exists and is a Windows SMB drive/UNC mapping.
- `SSH_HOST` is reachable.
- `REMOTE_ROOT` exists on the remote host.
- Remote source markers exist under `REMOTE_ROOT`.
- Local `adb.exe` is available before deploy.

3. Run source operations remotely only, preferably through the shared persistent channel:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$SkillDir\scripts\Invoke-WindowsRemoteSession.ps1" `
  -SshHost "$SSH_HOST" `
  -RemoteRoot "$REMOTE_ROOT" `
  -Action run `
  -Command "rg 'someSymbol' frameworks/base"
```

Use `-Lock exclusive` for source edits, git writes, and builds. Read-only searches may use the default `-Lock none`.

Short SSH remains the fallback path:

```powershell
ssh.exe "$SSH_HOST" "cd '$REMOTE_ROOT' && rg 'someSymbol' frameworks/base"
ssh.exe "$SSH_HOST" "cd '$REMOTE_ROOT' && git status --short"
```

For code changes, create or apply changes on the remote Linux tree. Do not use `apply_patch` against the SMB mapping. Prefer remote-native commands, remote patch files, or remote scripts executed through SSH.

4. Build remotely through the project wrapper. First ensure the remote source tree has `.codex/build-session.sh`; this checks `REMOTE_ROOT` first and bootstraps it remotely only when missing or forced:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$SkillDir\scripts\Ensure-WindowsRemoteBuildSession.ps1" `
  -SshHost "$SSH_HOST" `
  -RemoteRoot "$REMOTE_ROOT"
```

Then build through `.codex/build-session.sh` inside the persistent session:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$SkillDir\scripts\Invoke-WindowsRemoteSession.ps1" `
  -SshHost "$SSH_HOST" `
  -RemoteRoot "$REMOTE_ROOT" `
  -Action run `
  -Lock exclusive `
  -Command "source .codex/build-session.sh && codex_session_init && codex_session_build --profile <profile>"
```

If session bootstrap fails but an older `.codex/build-push.sh` already exists, use short SSH as the fallback:

```powershell
ssh.exe "$SSH_HOST" "cd '$REMOTE_ROOT' && bash .codex/build-push.sh plan --profile <profile>"
ssh.exe "$SSH_HOST" "cd '$REMOTE_ROOT' && bash .codex/build-push.sh build --profile <profile>"
```

Never run raw Android build commands from this skill. If both `.codex/build-session.sh` and `.codex/build-push.sh` are missing or broken, repair the remote project wrapper first; do not fall back to local Windows builds.

5. Convert build output paths to local artifact paths.

If the remote wrapper reports:

```text
PRODUCT_OUT_REL=out/target/product/<product>
ARTIFACT_REL=system/framework/services.jar
```

then the Windows artifact path is:

```powershell
Join-Path $LOCAL_REPO (($PRODUCT_OUT_REL, $ARTIFACT_REL) -join "\")
```

6. Deploy with local `adb.exe`:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$SkillDir\scripts\Invoke-WindowsAdbPush.ps1" `
  -Artifact "X:\...\services.jar" `
  -Destination "/system/framework/services.jar"
```

## Rules

- Treat `REMOTE_ROOT` as source-authoritative.
- Treat `LOCAL_REPO` as artifact-pickup-only.
- Do not run local Windows `rg`, `git`, `repo`, Android scripts, or builds on SMB mapped source.
- Use `Invoke-WindowsRemoteSession.ps1` for repeated source search/read/write/patch/git/repo/build; it delegates to `android-windows-remote-channel`. Use short `ssh.exe` only as a fallback or for one-off diagnostics.
- Use bundled PowerShell helpers for multi-line remote scripts; they send stdin as UTF-8 without BOM and decode remote output as UTF-8. Do not pipe ad hoc PowerShell here-strings directly into Bash.
- Use `adb.exe` locally because the device is attached to Windows.
- Keep project `.codex` build/deploy memory in the repo, but edit it through the remote Linux path.
- Return build/deploy evidence to `android-framework-change-workflow`; final behavior verification remains owned by that workflow.

## Evidence Handoff

Return concise evidence to the calling workflow, including:

- resolved `LOCAL_REPO`, `SSH_HOST`, `REMOTE_ROOT`, `PLATFORM`, `SDK_NAME`, and registry evidence when relevant
- persistent session name and command log path when used
- wrapper path, profile, modules, artifacts, product out, and saved build log path
- artifact local path, destination, freshness check, and push result
- remount, reboot, wait-boot, restart, and device health evidence when performed
- focused failure class and key error lines when blocked

Do not claim final framework behavior verification. Hand that back to `android-framework-change-workflow`.

## Capability Capture

Default final reports do not include capability-capture summaries. At task end, only consider a short `Skill 改进建议` when the work produced reusable Windows remote build/deploy executor knowledge: persistent session rules, PowerShell/SSH encoding boundaries, remote-only source operation rules, profile repair, artifact mapping, push or restart strategy, build failure signatures, device delivery evidence, reusable script ideas, or a clear gap in this skill.

When a trigger appears possible, read `references/capability-capture.md` before writing the final report. If it qualifies, append the candidate block at the very end. If it does not qualify, say nothing about capture.

Do not modify `SKILL.md`, `references/`, or `scripts/` for capture after ordinary build/deploy work unless the user explicitly confirms persistence.

## Failure Classes

- `mapping-missing`: resolve through `android-windows-source-access`; ask only for missing values.
- `mapping-conflict`: report registry and project `.codex` values; prefer exact Windows mapping registry unless overridden.
- `remote-session-missing`: create or reuse the persistent session; if `tmux` is missing, run `android-windows-remote-channel` `install-tmux`, or report `REMOTE_SUDO_PASSWORD_REQUIRED` and use short SSH only as a fallback.
- `build-session-missing`: run `Ensure-WindowsRemoteBuildSession.ps1`; if bootstrap fails and `.codex/build-push.sh` exists, fall back to short SSH wrapper commands.
- `profile-missing`: infer or create a project-local profile, then rerun `plan`.
- `build-failed`: report wrapper `BUILD_FAIL`, `KEY_ERRORS`, and saved log path.
- `artifact-missing`: report product out, expected artifact names, and freshness evidence.
- `adb-root-remount-failed`: report the key root/remount failure from local `adb.exe`.
- `device-unavailable`: report local `adb.exe devices` or wait-for-device evidence.

## Output Hygiene

Use Chinese field names for user-visible final reports while keeping technical variables, command names, and paths unchanged. Prefer this compact shape:

```text
路径关系: <local mapping> -> <ssh host>:<remote root>
远程会话: <session name/log path, if used>
构建配置: profile=<profile> modules=<modules> artifacts=<artifacts>
构建结果: <成功/失败> log=<path> key_errors=<summary if failed>
编译产物: <Windows local artifact paths and freshness>
部署结果: <push/remount/reboot/restart status>
设备状态: <basic health evidence>
项目记忆: <.codex files updated>
交接: <next owner or blocker>
```

If capability capture is triggered, append the candidate after the executor report using the exact format in `references/capability-capture.md`. Otherwise omit it entirely.

## Scripts

- `scripts/Resolve-WindowsRemoteMapping.ps1`: resolve `LOCAL_REPO`, `SSH_HOST`, `REMOTE_ROOT`, SMB path, and registry evidence from `android-windows-source-access-info\projects\*.env`.
- `scripts/Invoke-WindowsRemoteSession.ps1`: compatibility wrapper that delegates to `android-windows-remote-channel` for persistent remote `tmux` sessions keyed by `SSH_HOST` and `REMOTE_ROOT`.
- `scripts/Ensure-WindowsRemoteBuildSession.ps1`: check or remotely bootstrap `.codex/build-session.sh` before using the persistent build session.
- `scripts/remote-generate-build-push.sh`: Bash payload uploaded by `Ensure-WindowsRemoteBuildSession.ps1` and executed only on remote Linux to generate project `.codex` wrappers.
- `scripts/Invoke-WindowsAdbPush.ps1`: push one local artifact path with `adb.exe`, performing `wait-for-device`, `root`, `remount`, `push`, and `sync`.

## Related Skills

- `android-windows-source-access`: creates and restores Windows SMB mappings and account-level registry files.
- `android-windows-remote-channel`: provides the Windows/WSL remote SSH/tmux channel used by this executor.
- `android-framework-change-workflow`: owns Android framework diagnosis, change discipline, risk, final verification, and final reporting.
