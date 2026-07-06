# Android Remote Channel Protocol

## Ownership

`android-remote-channel` owns transport and session mechanics only:

- SSH reachability.
- Remote `tmux` session lifecycle.
- Command dispatch into `REMOTE_ROOT`.
- Command logs and exit files.
- Busy marker and exclusive project lock.

It does not own Android build profiles, wrapper generation, artifact mapping, local adb deploy, or framework acceptance verification.

## Session Identity

Session identity is derived from:

```text
SSH_HOST|REMOTE_ROOT
```

The remote session name is:

```text
codex-android-<12-char-sha256>
```

The remote state directory is:

```text
~/.codex/android-remote-sessions/<12-char-sha256>/
```

## Actions

- `check`: verify SSH, `tmux`, and `REMOTE_ROOT`.
- `install-tmux`: explicitly install `tmux` on the remote host when missing.
- `ensure`: create or reuse the remote `tmux` session.
- `run`: send a command to the session and optionally wait for completion.
- `status`: print running/stopped, busy marker, and current log.
- `tail`: tail `current.log` or a command-specific log.
- `stop`: kill the session without deleting historical logs.

`check` and `ensure` never install packages. Package installation is a server mutation and must go through `install-tmux`.

## Credential Policy

`android-remote-channel` consumes credentials but does not own or save them.

For `install-tmux`, credential priority is:

1. passwordless remote sudo
2. explicit env var, default `CODEX_REMOTE_SUDO_PASSWORD`
3. source-access credential registry candidates
4. stop with `REMOTE_SUDO_PASSWORD_REQUIRED env=CODEX_REMOTE_SUDO_PASSWORD action=install_tmux`

On WSL, source-access candidates come from:

- `~/.servers/projects/*.env`
- `~/.servers/credentials/*.passwords.env`
- `~/.servers/credentials/*.cred`

The channel prefers `SAVED_REMOTE_SUDO_PASSWORD`, then `SAVED_SSH_PASSWORD`, then `SAVED_SAMBA_PASSWORD`, and finally the Samba `.cred` password for the matched project. These are only tried as candidates; failures do not overwrite local files.

## Locking

The `busy` file prevents concurrent command dispatch through the same channel. The `project.lock` file is an additional `flock` used when a command is run with `exclusive`.

Use exclusive lock for:

- source edits
- `git` writes
- `repo` sync/update-like operations
- checkpoint creation
- Android builds

Read-only `rg`, `git status`, `git diff`, and log inspection can use no lock.

## SSH Multiplexing

The Bash entry uses OpenSSH multiplexing by default through command-line options:

```text
ControlMaster=auto
ControlPersist=2h
ControlPath=$HOME/.ssh/controlmasters/codex-%C
```

This avoids editing `~/.ssh/config`. Disable with:

```bash
CODEX_REMOTE_CHANNEL_SSH_MUX=0
```

## Build Skill Contract

Build/deploy skills should:

1. Resolve `SSH_HOST` and `REMOTE_ROOT` themselves.
2. Ensure project `.codex/build-session.sh` exists themselves.
3. Call this skill for `check`, `ensure`, `run`, `status`, and `tail`.
4. Interpret Android build output themselves.
5. Deploy artifacts locally themselves.

This keeps the channel generic and the Android build logic in the build/deploy skills.
