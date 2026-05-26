---
name: android-windows-source-access
description: Use to create, inspect, restore, or resolve Windows-native SMB drive/UNC mappings for Android remote build server source trees. Use when Codex runs as a Windows native agent and needs to map a local Windows Android source path such as X:\unisoc\rk3576 or \\server\share\project to a remote Linux build path, SMB share, SSH host, platform, and SDK/project name. This is the Windows SMB mapping counterpart to the WSL/CIFS source access workflow.
---

# Android Windows Source Access

Use this skill for Windows-native access to Android source trees shared from a remote Linux build server over SMB.

It owns the local mapping registry, optional Samba credential memory, and source access handoff. It does not run Android builds, push artifacts, or diagnose framework behavior.

Build/deploy skills consume this skill's `sshHost` and `remoteRoot` handoff and may then call `android-remote-channel`; this source-access skill should not create long-running remote sessions itself.

## Runtime Registry

Use this info directory for runtime memory:

```powershell
$InfoDir = "$env:USERPROFILE\.codex\android-windows-source-access-info"
```

Use WSL-compatible account-level files under the same info directory:

```text
credentials/<sha256(sambaUser@sambaServer)>.cred
projects/<sha256(sambaUser@sambaServer)>.env
```

The registry and account env files map:

- `localRepo`: Windows SMB drive/UNC path used only for artifact pickup and `adb.exe` deployment.
- `smbRoot`: SMB UNC path or mapped-drive root.
- `sshHost`: remote Linux SSH target.
- `remoteRoot`: authoritative remote Linux source path for build commands.
- `platform`: local platform folder such as `rk`, `mtk`, or `unisoc`.
- `sdkName`: local SDK/project folder name.
- `sambaUser`: SMB username, when known.
- `credentialTarget`: SMB server IP or host used for the account key.

Never store passwords, tokens, or SSH keys in the skill folder or project repo. If the user provides a Samba password and asks to remember it, store it only in `android-windows-source-access-info\credentials\<account-hash>.cred`, mirroring the WSL `android-wsl-source-access-info` layout.

## Workflow

1. Initialize or inspect the registry before adding entries:

```powershell
$SkillDir = "$env:USERPROFILE\.codex\skills\android-windows-source-access"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$SkillDir\scripts\Manage-AndroidSmbWindowsInfo.ps1" init
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$SkillDir\scripts\Manage-AndroidSmbWindowsInfo.ps1" list
```

2. For mapping-only work, do not inspect or require `platform` and `sdkName`. Record the SMB/local/remote mapping first. Inspect source identity only when a later build/deploy workflow needs `platform` or `sdkName`.

When identity is needed, inspect the remote source before choosing `platform` or `sdkName`. Do not use remote path segments or the basename as a fallback project name:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$SkillDir\scripts\Inspect-AndroidSdk.ps1" `
  -SshHost "test55@192.168.0.199" `
  -RemoteRoot "/home/test55/work/unisoc/rk3576"
```

If inspection returns `SDK_NAME_REQUIRED`, ask the user for the project name or require an explicit `-SdkName`. If user input conflicts with source evidence, stop unless the user explicitly confirms the override.

3. Add a mapping only from explicit user input or verified evidence:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$SkillDir\scripts\Manage-AndroidSmbWindowsInfo.ps1" add `
  -LocalRepo "C:\AndroidSrc\rk\TVA10A2R" `
  -SmbRoot "\\192.168.0.199\TVA10A2R" `
  -SshHost "test55@192.168.0.199" `
  -RemoteRoot "/home/test55/work/unisoc/rk3576" `
  -SambaUser "test55" `
  -CredentialTarget "192.168.0.199" `
  -SambaPassword "<password-if-user-provided>"
```

4. Resolve a project before handing off to build/deploy workflows:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$SkillDir\scripts\Manage-AndroidSmbWindowsInfo.ps1" resolve `
  -LocalRepo "C:\AndroidSrc\rk\TVA10A2R"
```

5. If the local source path is missing, verify the SMB path or mapped drive exists before asking the user for more information. Do not guess a remote path from Windows path segments.

## Source Operation Boundary

Do not use Windows SMB mapped paths for Android source operations.

Forbidden on `localRepo`, `smbRoot`, mapped drives, and UNC paths:

- `rg`, `grep`, `Select-String`, or broad source search.
- Reading source files for diagnosis.
- Editing, patching, formatting, or generating source files.
- `git`, `repo`, Android build scripts, Soong, Make, Ninja, or build discovery.

Run those operations on `remoteRoot` over SSH instead:

```powershell
ssh.exe "$SSH_HOST" "cd '$REMOTE_ROOT' && rg 'pattern' frameworks/base"
```

Use Windows SMB mapping only after remote build output exists, to read artifacts for local `adb.exe push`.

## Rules

- Prefer explicit mapping entries over path inference.
- Leave `platform` and `sdkName` empty for mapping-only records.
- Parse `platform` and `sdkName` from source evidence only when a build/deploy handoff needs them.
- Treat `remoteRoot` as the build-authoritative source path.
- Treat `localRepo` as the Windows artifact-pickup path.
- Do not perform source search/read/edit/patch/git/repo/build from Windows SMB-mapped source.
- Do not save credentials in the skill folder or project repo.
- Record SMB usernames and credential targets in the registry when known.
- Save Samba passwords in `credentials/<account-hash>.cred` only when the user explicitly provides the password.
- Generate `projects/<account-hash>.env` with account-level arrays, matching the WSL recovery shape.
- Use Windows-native commands such as PowerShell, `ssh.exe`, and `adb.exe`.
- Hand build/deploy work to a Windows-native remote build/deploy skill when available.

## Final Report

Use Chinese field names for user-visible final reports while keeping technical variables, command names, and paths unchanged. After creating, restoring, or resolving a mapping, prefer these fields and omit irrelevant ones:

```text
映射结果: <成功/已恢复/已存在/失败>
本地映射: <LOCAL_REPO>
远程路径: <REMOTE_ROOT>
SMB 映射: <SMB_ROOT>
SSH 主机: <SSH_HOST>
项目识别: <platform/sdkName, source if known>
凭据记录: <registry/credentials 是否已记录，是否可用于后续恢复>
交接: <是否可交给 android-windows-remote-build-deploy，或还缺什么>
```

Failure reports should state the blocker in Chinese while preserving technical identifiers such as `LOCAL_REPO`, `REMOTE_ROOT`, `SDK_NAME_REQUIRED`, SSH, SMB, registry, and `.codex`.

## Capability Capture

Default final reports do not include capability-capture summaries. At task end, only consider a short `Skill 改进建议` when the work produced a reusable Windows SMB mapping/recovery pattern, diagnostic rule, verification method, failure signature, skill gap, or explicit user instruction to remember the pattern.

When a trigger appears possible, read `references/capability-capture.md` before writing the final report. If it qualifies, append the candidate block at the very end. If it does not qualify, say nothing about capture.

Do not modify `SKILL.md`, `references/`, or `scripts/` for capture after ordinary source-access work unless the user explicitly confirms persistence.

## Bundled Scripts

`scripts/Manage-AndroidSmbWindowsInfo.ps1` manages the registry:

- `init`: create the info directory and registry file.
- `list`: print all remembered mappings as JSON.
- `add`: insert or update one exact mapping.
- `resolve`: find one mapping by `localRepo`, `remoteRoot`, or `sdkName`.

`scripts/Inspect-AndroidSdk.ps1` inspects remote source evidence over SSH:

- Infer platform from high-signal directories and `TARGET_BOARD_PLATFORM`.
- Infer project name from key repository branches or `BRANCH_BUILDTYPE`.
- Return `SDK_NAME_REQUIRED` instead of using a path basename fallback.

## Related Skills

- `android-windows-remote-build-deploy`: performs remote source operations, remote builds, artifact pickup, and local `adb.exe` deploy after a mapping exists.
- `android-framework-change-workflow`: owns Android framework diagnosis, change discipline, risk, final verification, and final reporting.
