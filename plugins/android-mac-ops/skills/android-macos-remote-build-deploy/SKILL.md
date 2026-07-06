---
name: android-macos-remote-build-deploy
description: "Use after an Android source tree is already mounted via Samba on macOS and remote build mapping is available from android-macos-source-access registry or project .codex. Acts as the build/deploy executor for Android framework workflows: resolve local-to-remote handoff, maintain project .codex build profiles, run authoritative remote Android builds through the wrapper, push artifacts with local adb, reboot or restart target components, and return build/deploy/device health evidence."
---

# Android macOS Remote Build Deploy

Use this skill as the macOS build/deploy executor. It owns remote build wrapping, artifact mapping, adb deployment, and build delivery evidence. It does not own source mounting, framework diagnosis, or final verification.

## Boundary

This skill owns:

- Local-to-remote path mapping for build execution.
- Build profile inference and maintenance (`.codex/build-profile.json`).
- Remote build command wrapping via `android-remote-channel`.
- Artifact discovery and local adb push.
- Device restart/reboot/remount.
- Build delivery evidence (`.codex/evidence/latest-build-delivery.json`).

Do not use this skill for:

- Source mounting: use `android-macos-source-access`.
- Framework diagnosis/verification: use `android-framework-change-workflow`.

## Inputs

From `android-macos-source-access` registry or project `.codex`:

- `SSH_HOST`: remote SSH host (e.g., `test61`)
- `REMOTE_ROOT`: matching source path on remote server (e.g., `/home/test61/unisoc/huiwei_uis7885_5g`)
- `PLATFORM`: platform identifier (e.g., `unisoc`)
- `SDK_NAME`: project name (e.g., `huiwei_uis7885_5g`)

Input precedence:
1. Explicit user or calling workflow instruction.
2. Exact local-project mapping from `android-macos-source-access` registry.
3. Existing repo `.codex` config and memory.

## Execution Modes

- **context-only**: resolve mapping, `.codex` config, product out, and profile candidates.
- **build-only**: remote `plan` and `build`; return artifact evidence without pushing.
- **deploy-existing-artifact**: push known local mounted artifacts; do not build.
- **build-deploy**: default executor path after framework edits.
- **restart-only**: reboot, wait boot, or restart a target component.
- **diagnose-build-failure**: inspect wrapper `KEY_ERRORS` and saved build log.
- **record-memory**: update project-local profile, artifact destination, or verification recipe.

## Context Resolution

Resolve the mount handoff mapping:

```bash
SKILL_DIR="<path-to-this-skill>"
"$SKILL_DIR/scripts/resolve-remote-mapping.sh" \
  --project "$LOCAL_REPO" \
  > /tmp/android-project-remote-mapping.env
source /tmp/android-project-remote-mapping.env
```

This provides `SSH_HOST`, `REMOTE_ROOT`, `PLATFORM`, `SDK_NAME`, and `MAPPING_REGISTRY`.

## Scripts

- `scripts/resolve-remote-mapping.sh`: resolve `SSH_HOST` and `REMOTE_ROOT` from `android-macos-source-access` registry.
- `scripts/discover-project.sh`: detect project type and build target from source tree.
- `scripts/ensure-build-session.sh`: create or reuse remote tmux session via `android-remote-channel`.
- `scripts/generate-build-push.sh`: generate build command and push plan for changed files.
- `scripts/infer-profile.sh`: infer build profile from project structure.
- `scripts/push-artifacts.sh`: push built artifacts to device via local adb.

## Output

Report executor results with Chinese user-facing labels:

```text
路径关系: <local repo> -> <ssh host>:<remote root>
构建配置: profile=<profile> modules=<modules> artifacts=<artifacts>
构建结果: <成功/失败> log=<path> key_errors=<summary if failed>
编译产物: <local paths and freshness>
部署结果: <push/remount/reboot/restart status>
设备状态: <basic health evidence>
项目记忆: <.codex files updated>
交接: <next owner or blocker>
```

## Failure Classes

- `local-source-missing`: stop and use `android-macos-source-access`.
- `mapping-missing`: resolve from mount registry or list remembered projects.
- `remote-unreachable`: report SSH host and minimal connection error.
- `profile-missing`: infer/update `.codex/build-push.profiles.sh`.
- `build-failed`: return `KEY_ERRORS` and saved log path.
- `artifact-missing-or-stale`: fix profile/artifact list.
- `adb-device-missing`: report local device state.

## Related Skills

- `android-macos-source-access`: source mounting, remount recovery, and project mapping registry.
- `android-remote-channel`: shared SSH/tmux remote channel.
- `android-framework-change-workflow`: framework diagnosis, instrumentation, verification.
