---
name: android-remote-build-deploy
description: "Use after Android source access is healthy on WSL or macOS and the source-access registry maps the local project to a remote Linux build root. Owns platform-neutral remote build setup, persistent build sessions, build profiles, artifact discovery, local adb deployment, and build-delivery evidence. Does not mount source or decide whether a Framework requirement is complete."
---

# Android Remote Build Deploy

Use this core skill for the build and delivery portion of Android Framework work on both WSL and macOS. Platform plugins only mount source and maintain the source-access registry; this skill consumes that registry and keeps one build/deploy implementation.

## Boundary

This skill owns:

- resolving a mounted local project to its registered SSH host and remote source root
- discovering the remote Android build target
- creating project-local `.codex` build profiles and wrappers
- running authoritative builds on the remote Linux source tree
- using `android-remote-channel` for persistent SSH/tmux execution
- locating build artifacts in the mounted source tree
- pushing artifacts with the administrator machine's local `adb`
- writing build-delivery evidence for patch capture

It does not own:

- WSL CIFS or macOS SMB mounting; use the platform `android-source-access` skill
- Framework diagnosis, code changes, final behavior verification, or rollback decisions; use `android-framework-change-workflow`
- remote-device `adb`; devices are reached from the local WSL or macOS host
- Git history changes unless the user explicitly requests them

## Inputs

Start from the current Android project path. The source-access registry under `$HOME/.servers/projects` is authoritative for:

- local project path
- SSH host
- remote source root
- platform
- project name

Both current registry formats are supported by the same resolver: WSL ENV registry and macOS JSON registry.

```bash
python3 "<skill>/scripts/resolve_remote_mapping.py" \
  --project "$PWD" \
  > /tmp/android-project-remote-mapping.env
source /tmp/android-project-remote-mapping.env
```

Do not derive a remote path from local directory names when a registry mapping exists.

## Project Memory

Project-local `.codex` files are build/deploy memory, not plugin source:

- `.codex/build-push.config.sh`: SSH host, remote root, lunch target, product output
- `.codex/build-push.sh`: remote plan/build wrapper
- `.codex/build-session.sh`: sourceable persistent-session wrapper
- `.codex/build-push.profiles.sh`: project build profiles
- `.codex/build-push.memory.sh`: successful remote build memory
- `.codex/artifact-destinations.json`: artifact-to-device destinations
- `.codex/evidence/latest-build-delivery.json`: patch-capture evidence

Generated output must stay in the project `.codex` directory or the configured Codex artifact directory. Never write output into this skill directory or plugin cache.

## Setup

Validate the registered mapping, then discover the remote build environment:

```bash
"<skill>/scripts/discover-project.sh" \
  --ssh-host "$SSH_HOST" \
  --remote-root "$REMOTE_ROOT" \
  --output /tmp/android-project-discovery.env
```

Generate the project-local wrappers through the mounted source tree:

```bash
"<skill>/scripts/generate-build-push.sh" \
  --repo "$PWD" \
  --discovery-file /tmp/android-project-discovery.env
```

The generator runs on both macOS Bash 3.2 and WSL Bash. Generated build wrappers run on the remote Linux build server.

## Profiles

Infer a profile from changed source paths when the caller has not supplied one:

```bash
"<skill>/scripts/infer-profile.sh" \
  --repo "$PWD" \
  --path frameworks/base/packages/SystemUI/src/com/example/File.java \
  > /tmp/android-profile.env
```

Store confirmed modules and artifacts in the project profile file:

```bash
"<skill>/scripts/generate-build-push.sh" \
  --repo "$PWD" \
  --only-profile \
  --profile systemui \
  --modules SystemUI \
  --artifacts SystemUI.apk
```

Use stable requirement-oriented names such as `systemui`, `launcher3`, `settings`, `framework-services`, `framework-res`, or `bootimage`.

## Build

Ensure the sourceable build-session wrapper exists on the remote source tree:

```bash
"<skill>/scripts/ensure-build-session.sh" \
  --repo "$PWD" \
  --ssh-host "$SSH_HOST" \
  --remote-root "$REMOTE_ROOT"
```

Use `android-remote-channel` for repeated commands and long builds. Initialize the build environment once in the remote tmux session, then reuse it:

```bash
source .codex/build-session.sh
codex_session_init
codex_session_build --profile systemui
```

For a single foreground operation, the remote wrapper can run directly:

```bash
ssh "$SSH_HOST" "cd '$REMOTE_ROOT' && bash .codex/build-push.sh plan --profile systemui"
ssh "$SSH_HOST" "cd '$REMOTE_ROOT' && bash .codex/build-push.sh build --profile systemui"
```

Do not run authoritative Android builds through the mounted local tree. On failure, return the wrapper's bounded `KEY_ERRORS` and saved log path.

Create a remote checkpoint before a broad or risky build/deploy attempt:

```bash
"<skill>/scripts/create-checkpoint.sh" \
  --ssh-host "$SSH_HOST" \
  --remote-root "$REMOTE_ROOT" \
  --name before-systemui-build \
  --purpose "preserve current Framework diff before build"
```

## Deploy

Push from local WSL or macOS with the shared Python executor:

```bash
python3 "<skill>/scripts/push_artifacts.py" \
  --artifact "$PWD/$PRODUCT_OUT_REL/$ARTIFACT_REL" \
  --product-out "$PWD/$PRODUCT_OUT_REL" \
  --destinations-file "$PWD/.codex/artifact-destinations.json" \
  --learn-destinations \
  --remote-build-host "$SSH_HOST" \
  --remote-source-root "$REMOTE_ROOT" \
  --remote-build-command "bash .codex/build-push.sh build --profile systemui" \
  --remote-build-profile systemui \
  --remote-artifact "$REMOTE_ROOT/$PRODUCT_OUT_REL/$ARTIFACT_REL" \
  --artifact-transfer "mounted SMB/CIFS product output" \
  --adb-serial "<serial>"
```

Set `ADB` when the executable is not on `PATH`. WSL may point it at `adb.exe`; macOS uses the native `adb` executable. The executor handles path conversion only when Windows `adb.exe` is selected.

Reboot or restart only as required by the caller, artifact type, or established project memory. `adb root`, remount, push, reboot, boot wait, and immediate device health are delivery evidence, not final requirement verification.

## Output

Return:

- local project, SSH host, remote source root, platform, project, and registry path
- profile, modules, artifacts, product output, and build log
- build result and bounded key errors
- local artifact path and remote artifact identity
- adb serial, push destinations, reboot/restart result
- `.codex/evidence/latest-build-delivery.json` path

Hand control back to `android-framework-change-workflow` for requirement-specific verification, regression checks, rollback decisions, diagnostic cleanup, and final completion reporting.
