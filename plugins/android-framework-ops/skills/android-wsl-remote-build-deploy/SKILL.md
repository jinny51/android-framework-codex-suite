---
name: android-wsl-remote-build-deploy
description: "Use after an Android source tree is already mounted in WSL and remote build mapping is available from android-wsl-source-access registry or project .codex. Acts as the build/deploy executor for Android framework workflows: resolve local-to-remote handoff, maintain project .codex build profiles, run authoritative remote Android builds through the wrapper, push artifacts with local adb, reboot or restart target components, and return build/deploy/device health evidence. Does not mount source, diagnose framework behavior, or own final requirement verification; use android-wsl-source-access for source mounting and android-framework-change-workflow for diagnosis, verification matrix, rollback decisions, and final reporting."
---

# Android WSL Remote Build Deploy

Use this skill as the Android build/deploy executor. It consumes an already mounted WSL source tree, builds on the remote Linux source path, deploys artifacts with local `adb`, and returns concise evidence to the calling workflow.

It is not the workflow owner for framework behavior changes. For framework/system work, `android-framework-change-workflow` diagnoses, patches, defines the verification matrix, calls this skill for build/deploy mechanics, then resumes final verification and completion decisions.

## Role And Boundaries

This skill owns:

- Resolving the mounted local project to its remote build server mapping.
- Creating or maintaining repo-local `.codex` build/deploy memory.
- Running remote authoritative `repo`/`git` reads, checkpoints, and Android builds.
- Calling `android-remote-channel` for persistent remote `tmux` sessions, command logs, busy state, and remote locks.
- Inferring or updating build profiles, modules, and deployable artifacts.
- Pushing artifacts from WSL-mounted paths with local `adb`.
- Rebooting or restarting target components when requested or project memory indicates it.
- Returning build/deploy/device health evidence.

This skill does not own:

- First-time CIFS/Samba mounting or reboot remount recovery. Use `android-wsl-source-access`.
- Root-cause diagnosis, instrumentation strategy, behavior patching, subsystem verification matrix, rollback decision, diagnostic log lifecycle, or final report for framework changes. Use `android-framework-change-workflow`.
- Raw Android build command selection outside the project wrapper.
- Remote `adb` workflows.

Never use PowerShell as part of this workflow.

## Inputs And Handoff Sources

Treat the current workspace and user request as the source of truth.

Common inputs:

- `LOCAL_REPO`: mounted WSL Android source path, usually `pwd`.
- `SSH_HOST`: remote SSH host or alias.
- `REMOTE_ROOT`: matching source path on the remote build server.
- `PLATFORM`, `SDK_NAME`: optional mount-derived project identity.
- `PROFILE`, `MODULES`, `ARTIFACTS`: build/deploy targets from the caller or inferred from source.
- `ADB`, `DEVICE_SERIAL`: optional local device selection.
- Restart policy: reboot, wait boot, or restart a named component/process.

Input precedence:

1. Explicit user or calling workflow instruction.
2. Exact local-project mapping from `android-wsl-source-access` registry.
3. Existing repo `.codex` config and memory.
4. Script discovery from the remote source tree.
5. Ask only for values that still cannot be inferred safely.

Do not compare local and remote path names as a path-consistency check. The mounted local path may intentionally differ from the remote path because `android-wsl-source-access` can correct platform and project naming from source evidence. Validate the handoff mapping instead.

## Execution Modes

Pick the smallest mode that satisfies the request:

- **context-only**: resolve mapping, `.codex` config, product out, and profile candidates.
- **build-only**: remote `plan` and `build`; return artifact evidence without pushing.
- **deploy-existing-artifact**: push known local mounted artifacts; do not build.
- **build-deploy**: default executor path after framework edits.
- **restart-only**: reboot, wait boot, or restart a target component after an already deployed change.
- **diagnose-build-failure**: inspect wrapper `KEY_ERRORS` and saved build log, then return focused findings.
- **record-memory**: update project-local profile, artifact destination, or verification/deploy recipe memory.

## Context Resolution

Resolve `LOCAL_REPO` first and confirm it looks like an Android source tree. If the path is missing or unusable, stop and use `android-wsl-source-access`.

Resolve the mount handoff mapping:

```bash
SKILL_DIR="<path-to-this-skill>"
"$SKILL_DIR/scripts/resolve-remote-mapping.sh" \
  --project "$LOCAL_REPO" \
  > /tmp/android-project-remote-mapping.env
source /tmp/android-project-remote-mapping.env
```

This should provide `SSH_HOST`, `REMOTE_ROOT`, and optionally `PLATFORM`, `SDK_NAME`, and `MAPPING_REGISTRY`.

If the mapping is missing, use `android-wsl-source-access` recovery or listing as the next diagnostic path; do not rederive remote paths from local path segments. If repo `.codex` and mount registry disagree, surface the conflict and prefer the exact mount registry unless the user or caller explicitly overrides it.

Validate the handoff with read-only checks:

- `LOCAL_REPO` is readable and contains Android source markers.
- `SSH_HOST` is reachable.
- `REMOTE_ROOT` exists on the remote host.
- The remote source tree can answer build discovery commands.

Do not run authoritative local `git` or local Android builds through the CIFS tree.

## Project .codex Memory

Treat repo `.codex` as project-local build/deploy memory:

- `.codex/build-push.config.sh`: remote build settings.
- `.codex/build-push.sh`: wrapper for plan/build and quiet log handling.
- `.codex/build-session.sh`: sourceable wrapper for persistent remote session builds.
- `.codex/build-push.profiles.sh`: named build profiles, modules, artifacts.
- `.codex/build-push.memory.sh`: successful-build memory maintained by the wrapper.
- `.codex/artifact-destinations.sh`: artifact-to-device destination memory.
- `.codex/verification-recipes.sh`: deploy/restart hints and verification handoff notes.

Updating `.codex` build/deploy memory is allowed as executor setup. Do not run `git add`, `git commit`, branch creation, rebase, reset, checkout, or other index/history-changing actions unless the user explicitly asks.

## Build Wrapper Contract

Always build on the remote Linux server through the project `.codex` wrapper. Use `.codex/build-session.sh` inside a persistent session when available; otherwise use `.codex/build-push.sh`. Never run raw Android build commands such as `make`, `m`, `soong_ui`, `ninja`, or `ckati` directly from the skill.

Read existing config first:

```bash
.codex/build-push.config.sh
.codex/build-push.sh
.codex/build-push.profiles.sh
.codex/build-push.memory.sh
```

If the wrapper is missing, stale, or incomplete, discover and generate it:

```bash
SKILL_DIR="<path-to-this-skill>"
"$SKILL_DIR/scripts/discover-project.sh" \
  --ssh-host "$SSH_HOST" \
  --remote-root "$REMOTE_ROOT" \
  --output /tmp/android-project-discovery.env

"$SKILL_DIR/scripts/generate-build-push.sh" \
  --repo "$LOCAL_REPO" \
  --discovery-file /tmp/android-project-discovery.env
```

The generator writes `.codex/build-push.config.sh`, `.codex/build-push.sh`, `.codex/build-session.sh`, and preserves `.codex/build-push.profiles.sh`.

Discover `lunch` from root-level project build entry scripts, preferring `debug.sh` and then `debug*.sh`; do not infer it from random device, tool, prebuilts, or nested shell snippets.

Confirm generated values with read-only remote commands such as `get_build_var PRODUCT_OUT` through the wrapper/discovered environment.

## Checkpoints

Use remote checkpoint patches as recovery points. Create one before broad build/deploy attempts on a nontrivial source diff, before risky framework artifact deployment, or before changing project build memory in a way that affects shared workflows.

```bash
SKILL_DIR="<path-to-this-skill>"
"$SKILL_DIR/scripts/create-checkpoint.sh" \
  --ssh-host "$SSH_HOST" \
  --remote-root "$REMOTE_ROOT" \
  --name <name> \
  --purpose <text>
```

Create post-success checkpoints only when the calling workflow has completed final verification or explicitly asks for a known-good recovery point.

## Profile And Artifact Resolution

Prefer profile/module/artifact hints from the calling workflow. If missing, infer them from requirement-relevant paths, changed files, nearest `Android.bp`/`Android.mk`, existing root build scripts, previous profile entries, and build output.

Use `scripts/infer-profile.sh` when source paths are known:

```bash
SKILL_DIR="<path-to-this-skill>"
"$SKILL_DIR/scripts/infer-profile.sh" \
  --repo "$LOCAL_REPO" \
  --path frameworks/base/packages/SystemUI/src/com/example/File.java \
  > /tmp/android-profile.env
source /tmp/android-profile.env
```

Store project-specific profiles in `.codex/build-push.profiles.sh`, not in this global skill. Treat `.codex/build-push.memory.sh` as successful-build memory and prefer proven profiles before inventing new ones.

Use stable requirement-oriented profile names such as `systemui`, `launcher3`, `settings`, `bootimage`, `framework-services`, or a lower-case app/module name. Include deployable artifact names such as `SystemUI.apk`, `Launcher3.apk`, `services.jar`, `framework.jar`, `framework-res.apk`, `boot.img`, or the app APK name.

Add or update a profile proactively when source evidence clearly maps to a missing profile:

```bash
"$SKILL_DIR/scripts/generate-build-push.sh" \
  --repo "$LOCAL_REPO" \
  --only-profile \
  --profile <profile> \
  --modules "<module names>" \
  --artifacts "<artifact names>"
```

Then verify before building:

```bash
ssh "$SSH_HOST" "cd '$REMOTE_ROOT' && bash .codex/build-push.sh plan --profile <profile>"
```

If the first build shows missing module or artifact evidence, update the same project-local profile once, rerun `plan`, then rebuild.

## Remote Build Execution

Prefer `android-remote-channel` for repeated remote `git`, checkpoint, plan, and build work. The channel keeps a remote `tmux` session in `REMOTE_ROOT`, preserves sourced Android build functions after `codex_session_init`, and keeps command logs under `~/.codex/android-remote-sessions/<hash>/`.

Ensure the remote source tree has `.codex/build-session.sh` before sourcing it. This checks `REMOTE_ROOT` first and generates the wrapper through the mounted WSL repo only when it is missing or forced:

```bash
SKILL_DIR="<path-to-this-skill>"
"$SKILL_DIR/scripts/ensure-build-session.sh" \
  --repo "$LOCAL_REPO" \
  --ssh-host "$SSH_HOST" \
  --remote-root "$REMOTE_ROOT"
```

Create or reuse the session:

```bash
CHANNEL_DIR="<path-to-this-skill>"
"$CHANNEL_DIR/scripts/remote-channel.sh" \
  --ssh-host "$SSH_HOST" \
  --remote-root "$REMOTE_ROOT" \
  ensure
```

If this reports `TMUX_MISSING`, run the channel's explicit install action. It will try passwordless sudo, `CODEX_REMOTE_SUDO_PASSWORD`, then saved `android-wsl-source-access` credentials; if none works, ask the user for the remote sudo password and rerun with that env var set.

Initialize build state once per session, then build through `.codex/build-session.sh`:

```bash
"$CHANNEL_DIR/scripts/remote-channel.sh" \
  --ssh-host "$SSH_HOST" \
  --remote-root "$REMOTE_ROOT" \
  run --lock exclusive -- \
  "source .codex/build-session.sh && codex_session_init && codex_session_build --profile <profile>"
```

For later builds in the same session, `codex_session_build --profile <profile>` can reuse the initialized environment. Use `--no-wait` only when the build should continue while Codex returns to other work; use channel `tail` or `status` to recover evidence later. `scripts/remote-session.sh` remains as a compatibility wrapper around `android-remote-channel`.

Use quiet non-session builds as the fallback path:

```bash
ssh "$SSH_HOST" "cd '$REMOTE_ROOT' && bash .codex/build-push.sh build --profile <profile>"
```

Use `--stream-log` only for active diagnosis of a failing or hanging build. On failure, rely first on the wrapper's `BUILD_FAIL`, bounded `KEY_ERRORS`, and saved log path. Return those high-signal lines to the caller unless deeper diagnosis is requested.

After success, collect artifact evidence from wrapper output:

- `PRODUCT_OUT_REL`
- `ARTIFACT_REL`
- build log path
- profile/modules/artifacts used
- timestamp or freshness evidence when available

Before deploy, ensure artifacts exist in the mounted local tree and are plausibly fresh enough for the current build. Do not push an artifact when freshness is unclear unless the user explicitly asks to deploy an existing artifact.

## Local Deploy And Restart Execution

Never assume server-side `adb` can see the phone. Push from local WSL with local `adb` or `scripts/push-artifacts.sh`; do not invoke `adb` over the remote SSH build host.

Generated `.codex/build-push.sh` prints `PRODUCT_OUT_REL` and `ARTIFACT_REL` lines. Convert them to local mounted paths by joining with `$LOCAL_REPO`:

```bash
artifact="$LOCAL_REPO/$PRODUCT_OUT_REL/$ARTIFACT_REL"
```

Use project-local artifact destination memory after a real successful push:

```bash
"$SKILL_DIR/scripts/push-artifacts.sh" \
  --artifact "$artifact" \
  --product-out "$LOCAL_REPO/$PRODUCT_OUT_REL" \
  --destinations-file "$LOCAL_REPO/.codex/artifact-destinations.sh" \
  --learn-destinations \
  --remote-build-host "$SSH_HOST" \
  --remote-source-root "$REMOTE_ROOT" \
  --remote-build-command "bash .codex/build-push.sh build --profile <profile>" \
  --remote-build-profile "<profile>" \
  --remote-artifact "$REMOTE_ROOT/$PRODUCT_OUT_REL/$ARTIFACT_REL" \
  --artifact-transfer "mounted Samba/CIFS product output" \
  --adb-serial "<local-adb-serial>"
```

`push-artifacts.sh` writes standard build-delivery evidence to:

```text
$LOCAL_REPO/.codex/evidence/latest-build-delivery.json
```

or to `--evidence-out` / `CODEX_BUILD_DELIVERY_EVIDENCE` when specified. `android-framework-patch-capture` reads this file automatically from each `--source-root`, so remote build host, remote source path, build command/profile, artifact paths, local transfer, adb serial, push actions, and restart actions enter the patch package without retyping them as capture arguments.

Project debug devices are expected to support `adb root` and `adb remount`. If either fails, return that key error as deploy evidence instead of trying a remote-device workaround.

Reboot, wait boot, or restart target components according to caller instructions and project memory. For framework, services, SystemUI, Launcher3, resources, boot image, or multi-component deployments, reboot by default unless a project-local recipe or caller instruction specifies a safer restart path.

This skill may perform basic device health checks after deployment:

- device visible to local `adb`
- root/remount result
- push result
- reboot command accepted
- boot completion observed when requested
- target process restart command result when requested
- immediate obvious crash or command failure evidence

Do not treat these health checks as final framework behavior verification.

## Evidence Handoff

Return concise evidence to the calling workflow, especially `android-framework-change-workflow`.

Include:

- resolved `LOCAL_REPO`, `SSH_HOST`, `REMOTE_ROOT`, `PLATFORM`, `SDK_NAME`, and mapping registry when relevant
- profile, modules, artifacts, and product out
- checkpoint path if created
- persistent session name/log path if used
- build result, `KEY_ERRORS` on failure, and saved build log path
- artifact local paths and freshness status
- push destinations and push result
- reboot/restart/wait-boot result
- basic device health status
- project memory files updated

For framework behavior changes, explicitly hand control back to `android-framework-change-workflow` for requirement-specific final verification, subsystem regression checks, diagnostic log lifecycle, rollback decisions, and final reporting.

## Capability Capture

Default to no capability-capture summary. Do not summarize lessons after every task.

Only consider a capture when the completed task produced reusable build/deploy executor knowledge: remote build profile rules, artifact mapping, push or restart strategy, build failure signatures, device delivery evidence, artifact-not-effective diagnosis, a reusable tool/script idea, or a clear gap in this skill.

When a trigger appears possible, read `references/capability-capture.md` before writing the final report. If it qualifies, append a short `Capability Capture Candidate` to the final report. If it does not qualify, say nothing about capture.

Never persist the candidate into this skill, a reference, or a script without explicit user confirmation. Never capture one-off project facts, private paths, server details, credentials, raw logs, temporary device state, or unverified guesses.

## Failure Classes

Handle failures by class:

- `local-source-missing`: stop and use `android-wsl-source-access`.
- `mapping-missing`: resolve from mount registry or list remembered projects; ask only for missing values.
- `mapping-conflict`: report registry and `.codex` values; prefer exact mount registry unless overridden.
- `remote-unreachable`: report SSH host and minimal connection error.
- `tmux-missing`: run `android-remote-channel install-tmux` or report `REMOTE_SUDO_PASSWORD_REQUIRED`; use short SSH wrapper fallback only for one-off work.
- `remote-channel-missing`: install or sync `android-remote-channel`; do not duplicate session logic here.
- `product-discovery-failed`: rerun discovery and inspect root build scripts before asking the user.
- `wrapper-missing`: generate `.codex/build-push.sh`; never bypass with raw build commands.
- `profile-missing`: infer/update `.codex/build-push.profiles.sh`, then rerun `plan`.
- `build-failed`: return `KEY_ERRORS` and saved log path; inspect focused source/build files only if requested or needed.
- `artifact-missing-or-stale`: fix profile/artifact list or ask whether to deploy an existing artifact.
- `adb-device-missing`: report local device state and command used.
- `adb-root-remount-failed`: report the key root/remount failure.
- `push-destination-unknown`: pass explicit `--dest`, then learn it after success.
- `restart-or-boot-failed`: return boot/restart evidence to the caller for rollback or diagnosis.
- `behavior-verification-failed`: hand back to `android-framework-change-workflow`; do not mask with unrelated workarounds.

## Output Hygiene

Keep chat output terse. Do not paste full build logs, long diffs, raw `rg` hits, `dumpsys`, `logcat`, or adb traces by default. Route noisy output to files or filter inside commands.

Report executor results with Chinese user-facing labels by default. Keep technical variable names and command terms in English, such as `profile`, `modules`, `artifacts`, `adb`, `log`, `.codex`, `SSH`, and `registry`.

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

If capability capture is triggered, append the candidate after the executor report using the exact format in `references/capability-capture.md`. Otherwise omit it entirely.

## Bundled Scripts

- `scripts/resolve-remote-mapping.sh`: resolve `SSH_HOST` and `REMOTE_ROOT` from `android-wsl-source-access` registry for a mounted local project.
- `scripts/remote-session.sh`: compatibility wrapper that delegates to `android-remote-channel`.
- `scripts/ensure-build-session.sh`: check or generate remote `.codex/build-session.sh` before using the persistent build session.
- `scripts/discover-project.sh`: discover remote `envsetup`, `lunch`, and `PRODUCT_OUT`, preferring root `debug.sh`/`debug*.sh`.
- `scripts/generate-build-push.sh`: generate or update repo `.codex/build-push.config.sh`, `.codex/build-push.sh`, `.codex/build-session.sh`, and `.codex/build-push.profiles.sh`.
- `scripts/infer-profile.sh`: infer project-local profile, modules, and artifacts from requirement-relevant source paths.
- `scripts/create-checkpoint.sh`: create remote checkpoint patches without `git add` or `git commit`.
- `scripts/push-artifacts.sh`: push local mounted artifacts with local `adb` and optionally learn artifact destination mappings.
- `scripts/record-verification-recipe.sh`: record project-local verification or deploy handoff recipes in `.codex/verification-recipes.sh`.

## Related Skills

- `android-wsl-source-access`: source mounting, remount recovery, and exact local-to-remote mapping registry.
- `android-remote-channel`: shared SSH/tmux remote channel used by this executor.
- `android-framework-change-workflow`: framework diagnosis, instrumentation, behavior edits, verification matrix, final validation, rollback decisions, and final reporting.
