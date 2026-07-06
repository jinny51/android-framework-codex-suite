---
name: android-wsl-remote-channel
description: Provide a Windows/WSL remote execution channel for Android build servers using PowerShell, ssh.exe, and persistent remote tmux sessions. Use when Windows-side Android Framework skills need to create or reuse a remote session, run repeated remote source/git/build commands, tail logs, check busy state, install tmux, or avoid duplicating remote session logic.
---

# Android WSL Remote Channel

Use this skill as the Windows/WSL remote channel layer for Android build-server workflows. It owns PowerShell/`ssh.exe` transport, persistent remote `tmux` sessions, command logs, busy state, and coarse locking.

It does not own Windows SMB source mapping, Android build profile inference, build wrapper generation, artifact mapping, local `adb.exe` deployment, or Framework behavior verification.

## Boundary

Use this skill from `android-wsl-remote-build-deploy` when a Windows-side agent needs repeated remote Linux commands.

Do not use this skill as a replacement for:

- `android-wsl-source-access`: owns SMB/UNC source mapping and registry.
- `android-wsl-remote-build-deploy`: owns Android build/deploy semantics and local `adb.exe` delivery.
- `android-framework-change-workflow`: owns diagnosis, implementation discipline, risk, and final behavior verification.

WSL agents should not use this skill. Use `android-remote-channel` from `android-framework-ops` instead.

## PowerShell Entry

```powershell
$ChannelDir = "$env:USERPROFILE\.codex\skills\android-wsl-remote-channel"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$ChannelDir\scripts\Invoke-AndroidRemoteChannel.ps1" `
  -SshHost "$SSH_HOST" `
  -RemoteRoot "$REMOTE_ROOT" `
  -Action check
```

Run a command:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$ChannelDir\scripts\Invoke-AndroidRemoteChannel.ps1" `
  -SshHost "$SSH_HOST" `
  -RemoteRoot "$REMOTE_ROOT" `
  -Action run `
  -Lock exclusive `
  -Command "source .codex/build-session.sh && codex_session_init && codex_session_build --profile services"
```

Use `install-tmux` only as an explicit action. It tries passwordless sudo, `CODEX_REMOTE_SUDO_PASSWORD`, then credential candidates saved by `android-wsl-source-access`. It never writes credentials.

## Failure Handling

- `TMUX_MISSING`: run `install-tmux`, install `tmux` manually, or use a short SSH fallback from the calling build skill.
- `REMOTE_SUDO_PASSWORD_REQUIRED`: no usable sudo credential exists; ask for the remote sudo password and rerun with `CODEX_REMOTE_SUDO_PASSWORD`.
- `REMOTE_ROOT_MISSING`: resolve the source mapping again through `android-wsl-source-access`.
- `SESSION_BUSY`: inspect `status` and `tail`; do not start another exclusive build over the same source tree.
