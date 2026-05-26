---
name: android-remote-channel
description: Provide a shared remote execution channel for Android build servers using SSH and persistent remote tmux sessions. Use when WSL or Windows Android skills need to create/reuse a remote session, run repeated remote source/git/build commands, tail logs, check busy state, keep long builds recoverable, or avoid duplicating remote-session logic across android-wsl-remote-build-deploy and android-windows-remote-build-deploy.
---

# Android Remote Channel

Use this skill as the shared remote channel layer for Android build-server workflows. It owns remote command transport, persistent `tmux` sessions, command logs, busy state, and coarse locking. It does not own Android source mounting, build profile inference, build wrapper generation, artifact mapping, adb deployment, or framework verification.

## Boundary

Use this skill from:

- `android-wsl-remote-build-deploy` when a WSL agent needs repeated remote Linux commands.
- `android-windows-remote-build-deploy` when a Windows native agent needs repeated remote Linux commands.

Do not use this skill as a replacement for:

- `android-wsl-source-access` or `android-windows-source-access`: they own local source mapping and registry.
- `android-wsl-remote-build-deploy` or `android-windows-remote-build-deploy`: they own Android build/deploy semantics.
- `android-framework-change-workflow`: it owns diagnosis, implementation discipline, risk, and final behavior verification.

## Protocol

Remote state is stored on the build server:

```text
~/.codex/android-remote-sessions/<hash>/
├── session.env
├── busy
├── current.log
├── project.lock
└── commands/
    ├── <command_id>.line
    ├── <command_id>.log
    └── <command_id>.exit
```

The session key is `SSH_HOST|REMOTE_ROOT`. Commands always run from `REMOTE_ROOT`.

Use `--lock exclusive` or `-Lock exclusive` for source edits, git writes, `repo` operations, and builds. Read-only searches can use the default `none` lock.

## WSL/Linux Entry

```bash
CHANNEL_DIR="<path-to-this-skill>"
"$CHANNEL_DIR/scripts/remote-channel.sh" \
  --ssh-host "$SSH_HOST" \
  --remote-root "$REMOTE_ROOT" \
  check
```

Create or reuse the remote session:

```bash
"$CHANNEL_DIR/scripts/remote-channel.sh" \
  --ssh-host "$SSH_HOST" \
  --remote-root "$REMOTE_ROOT" \
  ensure
```

Run a command:

```bash
"$CHANNEL_DIR/scripts/remote-channel.sh" \
  --ssh-host "$SSH_HOST" \
  --remote-root "$REMOTE_ROOT" \
  run --lock exclusive -- \
  "source .codex/build-session.sh && codex_session_init && codex_session_build --profile services"
```

Recover status or logs:

```bash
"$CHANNEL_DIR/scripts/remote-channel.sh" --ssh-host "$SSH_HOST" --remote-root "$REMOTE_ROOT" status
"$CHANNEL_DIR/scripts/remote-channel.sh" --ssh-host "$SSH_HOST" --remote-root "$REMOTE_ROOT" tail --lines 160
```

The Bash entry enables OpenSSH multiplexing by default with command-line options only; it does not edit `~/.ssh/config`. Set `CODEX_REMOTE_CHANNEL_SSH_MUX=0` to disable it for troubleshooting.

If `tmux` is missing, install it only through the explicit action:

```bash
"$CHANNEL_DIR/scripts/remote-channel.sh" \
  --ssh-host "$SSH_HOST" \
  --remote-root "$REMOTE_ROOT" \
  install-tmux
```

`install-tmux` first tries passwordless sudo, then `CODEX_REMOTE_SUDO_PASSWORD`, then credentials already saved by `android-wsl-source-access`. It does not save new passwords. If no usable password exists, it prints `REMOTE_SUDO_PASSWORD_REQUIRED env=CODEX_REMOTE_SUDO_PASSWORD action=install_tmux`; stop and ask the user for the remote sudo password, then rerun with the env var set.

## Windows Entry

```powershell
$ChannelDir = "$env:USERPROFILE\.codex\skills\android-remote-channel"
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

Windows uses `ssh.exe` and the same remote `tmux` protocol. Do not depend on Windows SSH ControlMaster behavior.

Windows also supports the explicit install action:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$ChannelDir\scripts\Invoke-AndroidRemoteChannel.ps1" `
  -SshHost "$SSH_HOST" `
  -RemoteRoot "$REMOTE_ROOT" `
  -Action install-tmux
```

It uses the same priority: passwordless sudo, `CODEX_REMOTE_SUDO_PASSWORD`, then saved `android-windows-source-access` credentials as candidates. It never writes credentials.

## Failure Handling

- `TMUX_MISSING`: run the explicit `install-tmux` action, install `tmux` manually, or use short SSH fallback from the calling build skill.
- `REMOTE_SUDO_PASSWORD_REQUIRED`: read source-access credentials failed or no usable credential exists; ask the user for the remote sudo password and rerun with `CODEX_REMOTE_SUDO_PASSWORD`.
- `REMOTE_ROOT_MISSING`: resolve the source mapping again through the platform source-access skill.
- `SESSION_BUSY`: inspect `status` and `tail`; do not start another exclusive build over the same source tree.
- Missing or stale `current.log`: use `status`, then tail a specific `--command-id` / `-CommandId` if known.

For details, read `references/protocol.md`.
