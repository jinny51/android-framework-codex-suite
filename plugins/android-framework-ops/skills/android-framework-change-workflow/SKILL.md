---
name: android-framework-change-workflow
description: "Use when implementing requirements, modifying, diagnosing, or verifying Android platform/framework code such as frameworks/base, system_server services, WindowManager, ActivityTaskManager, PackageManager, SystemUI, Launcher3 integration, input, resources/overlays, surfaces, boot/runtime services, or OEM/system-level behavior. Orchestrates requirement contracts, evidence-backed diagnosis, targeted instrumentation, scoped framework changes, failure recovery, final acceptance verification, diagnostic log lifecycle cleanup, and concise reporting. Use WSL source/build skills on WSL agents and Windows source/build skills on Windows native agents."
---

# Android Framework Change Workflow

Use this skill as the framework engineer's operating protocol. It owns requirement specification, diagnosis, code-change discipline, risk judgment, final acceptance verification, and final reporting.

## Composable Use Contract

When user-provided skills, project-local rules, or review workflows exist, preserve them. Use this skill only for Android Framework-specific source access, diagnosis, build/deploy coordination, verification, patch capture, and knowledge reuse.

If the user explicitly asks for a personal coding-style skill, project `AGENTS.md`, local engineering rule, or review skill, treat that instruction as part of the active requirement. Do not replace it with this workflow. Combine the user's rule with this workflow's Android Framework evidence and verification discipline.

Use it for both direct requirement implementation and bug/regression work. Do not force requirement work into a root-cause narrative; use a requirement contract and acceptance evidence instead.

It coordinates with adjacent Android skills:

- `android-knowledge-search` searches prior reports, archived patches, modified files, symbols, and validation evidence before re-analysis or re-implementation. Use it as the pre-analysis knowledge gate when the team knowledge repository is available.
- WSL agents: `android-wsl-source-access` proves the source tree is mounted and usable; `android-wsl-remote-build-deploy` proves artifacts were built and delivered.
- Windows native agents: `android-windows-source-access` proves the SMB mapping and local-to-remote registry are usable; `android-windows-remote-build-deploy` proves artifacts were built remotely, picked up through the Windows mapping, and delivered with `adb.exe`.
- Build/deploy executors may use `android-remote-channel` internally for reusable SSH/tmux remote sessions; this workflow should still call the platform build/deploy executor rather than the channel directly.
- `android-framework-patch-capture` turns an implemented or stage-worthy Framework change into a patch/readme/evidence package after this workflow has produced a concrete change. Use it before `android-knowledge-intake` when the result should enter the team knowledge base.
- This skill proves the framework change satisfies the requirement or diagnosis outcome on device.

## Core Contract

Follow this ownership boundary:

```text
android-knowledge-search
  -> search prior reports/patches/symbols/validation evidence before reimplementing

android-wsl-source-access OR android-windows-source-access
  -> access/recover/identify source tree handoff

android-framework-change-workflow
  -> specify requirement or diagnose issue -> instrument if needed -> change -> define verification

android-wsl-remote-build-deploy OR android-windows-remote-build-deploy
  -> build -> push/deploy -> return delivery evidence

android-framework-change-workflow
  -> final acceptance verification -> recover/iterate or complete

android-framework-patch-capture
  -> package accepted or stage-worthy changes into patch/readme/evidence when the result should be preserved
```

Build/deploy evidence is necessary but not sufficient. Final completion must come from this skill because only the framework workflow knows the requirement contract or root cause, touched subsystem, risk matrix, and expected device behavior.

## Load References As Needed

Keep this file as the orchestrator. Load only the reference needed for the current task:

- `references/framework-risk-model.md`: read before changing system_server, WM/ATM, input, surfaces, Binder identity, locks, handlers, boot phases, users/profiles, resources, or shared framework APIs.
- `references/requirements-implementation.md`: read when the user asks for a new behavior, feature, policy change, product customization, or any direct requirement rather than a bug investigation.
- `references/diagnosis-and-instrumentation.md`: read when root cause is unclear, diagnostic logs are needed, visual evidence is needed, or temporary logs must be audited.
- `references/subsystem-playbooks.md`: read after identifying the likely owner subsystem.
- `references/verification-matrix.md`: read before build/deploy verification and again before final reporting.
- `references/failure-signatures.md`: read when build, boot, deploy, logcat, or behavior verification fails.
- `references/build-deploy-contract.md`: read when coordinating with `android-wsl-remote-build-deploy` or `android-windows-remote-build-deploy`.
- `references/capability-capture.md`: read near final reporting only when the task produced reusable process knowledge, exposed a skill gap, or the user asks to remember/summarize a lesson.

Use scripts in `scripts/` as optional helpers. Prefer them for log slicing, health scans, artifact probing, diagnostic log audits, dumpsys capture, and video frame extraction when the matching artifact exists.

## Start Triage

Before editing behavior:

1. Identify whether the request is a new requirement, behavior change, bug/regression, verification task, or failure recovery.
2. For Android Framework implementation work, use `android-knowledge-search` before source edits when the team knowledge repository is available. Search with feature words, subsystem, file/class names, properties, Settings keys, resource keys, artifact names, and visible log keywords. Treat matches as evidence, not final truth. Record the query terms, top relevant results, reuse decision, and reason so `android-framework-patch-capture` can later write `search-before-change.json`. If search is impossible, record the concrete reason in the final report and later patch package evidence.
3. For direct requirements, capture acceptance criteria, negative cases, product/device/variant scope, and expected owner subsystem. Load `references/requirements-implementation.md`.
4. For bugs or regressions, capture visible symptom, reproduction, expected behavior, and evidence source.
5. Identify likely owner process and subsystem: app, SystemUI, launcher, system_server, WM/ATM, PMS, input, resources/overlays, display/surface/compositor, native service, or build config.
6. Identify affected artifact: `framework.jar`, `services.jar`, `framework-res.apk`, `SystemUI.apk`, Launcher APK, permission/config XML, overlay APK, native binary, or mixed artifacts.
7. Check source/build/deploy readiness. On WSL, use `android-wsl-source-access` first if source access is broken and `android-wsl-remote-build-deploy` later for build/delivery. On Windows native agents, use `android-windows-source-access` for SMB mapping/registry and `android-windows-remote-build-deploy` later for remote build and local `adb.exe` delivery.
8. Check dirty files before editing and preserve unrelated user work.
9. Choose mode: direct requirement, analysis only, diagnostics, behavior change, build/deploy coordination, final verification, or failure recovery.

Ask the user only when evidence cannot be obtained from source search, logs, dumpsys, recordings, screenshots, adb, or available local/remote tools.

## Hard Stops

Stop and resolve the blocker before continuing when:

- A behavior edit is being made without either a direct requirement contract or source/log/dumpsys/visual/reproduction evidence.
- A first diagnosis attempt failed and no stronger diagnostic plan exists.
- A direct requirement lacks acceptance criteria, scope, owner subsystem, or negative/regression boundaries.
- A broad shared-path edit lacks owner process, caller/callee, thread/lock, lifecycle, state, artifact, and downstream mutation understanding.
- A change fails build, deploy, boot, health scan, or target behavior verification.
- Temporary diagnostics were added but no remove/guard/downgrade/keep decision exists.
- The proposed change masks a framework requirement with an app-side or unrelated workaround.
- Completion would rely only on "compiled" or "pushed" rather than target behavior evidence.

## Gate 1: Diagnose Or Specify

Exit only when either the direct requirement is specified enough to implement or root cause is known. If neither is true, use targeted instrumentation or requirement clarification.

For direct requirements, minimum specification:

- Desired behavior and user-visible/system-visible outcome.
- Product, variant, display, user/profile, configuration, and feature-flag scope.
- Owner subsystem, process, artifact, and build profile.
- Acceptance criteria and negative cases.
- Nearby regression paths before changing code.

For bugs or regressions, minimum evidence:

- Restate the symptom precisely enough to verify later.
- Trace caller, callee, lifecycle owner, state transition, and downstream mutation.
- Check product, build variant, resource overlay, feature flag, device config, runtime state, permission, user/profile, and process boundary gates.
- Name the affected subsystem, process, artifact, and build profile.
- Identify nearby regression paths before changing code.

If diagnosis stalls, load `references/diagnosis-and-instrumentation.md` and instrument the uncertainty instead of guessing. If requirement scope is unclear and cannot be inferred safely, ask a concise question before editing.

## Gate 2: Instrument

Use instrumentation to answer named uncertainties, not to create noisy logs.

Temporary diagnostics must:

- Use stable tags or keywords.
- Include relevant IDs, state values, bounds, flags, caller/reason, user/profile/display/window/task IDs, process/thread context, and timing when useful.
- Avoid sensitive user data.
- Be easy to search and remove.

For visual or timing-sensitive behavior, capture recording or screenshots and align visible frames with logs before deciding the implementation path or root cause.

Before final completion, audit diagnostics with source search or `scripts/diagnostic_log_audit.py` and decide remove, guard, downgrade, or keep with reason.

## Gate 3: Change

Enter only after the requirement is specified or the diagnosis has converged.

Before editing, have:

- Requirement contract or root-cause statement.
- Planned files/modules and ownership boundary.
- Risk level and rollback/checkpoint approach.
- Build profile and expected artifacts.
- Verification matrix for target behavior and nearby regressions.

Change with framework discipline:

- Match local patterns and existing framework APIs.
- Preserve lock ordering, Binder identity, handler/thread affinity, lifecycle timing, transaction ordering, resource precedence, and multi-user/profile semantics.
- Keep edits scoped to the responsible subsystem.
- Avoid unrelated refactors, formatting churn, and unrelated dirty files.
- On Windows native agents, do not search, read, edit, patch, format, or run `git`/`repo`/build commands against Windows SMB mapped paths. Run source operations on the remote Linux `REMOTE_ROOT` over SSH. Use the Windows SMB mapping only for artifact pickup after remote builds.

## Gate 4: Build And Delivery

Use the platform-appropriate build/deploy executor for remote build and push mechanics:

- WSL: `android-wsl-remote-build-deploy`.
- Windows native: `android-windows-remote-build-deploy`.

Require it to return:

- Build target/profile and result.
- Produced artifact paths.
- Pushed/deployed artifact paths or partitions.
- Required restart/reboot/remount actions.
- Basic device health evidence after delivery.
- Any skipped or failed delivery step.

Do not treat delivery as final correctness. Continue to Gate 5.

## Gate 5: Final Verification

Load `references/verification-matrix.md` and verify according to touched subsystem.

Always verify:

- Target behavior on the device.
- Process or boot stability for affected components.
- Relevant nearby regression paths.
- Logcat health for system_server, SystemUI, Launcher, target app/process, ANR, watchdog, crash, or fatal exception signals.
- Diagnostic log lifecycle cleanup.

For UI/windowing/input/surface changes, use repeated mixed interactions and visual evidence when the behavior is transient, timing-sensitive, or frame-visible.

## Failure Recovery

When build, deploy, boot, health, or behavior verification fails:

1. Stop stacking changes.
2. Capture the failure symptom, minimal log lines, artifact path, and whether it is new or pre-existing.
3. Load `references/failure-signatures.md`.
4. Compare the failure with the requirement/root cause and changed files.
5. Revert/narrow the last local edit, or return to requirement clarification, diagnosis, or instrumentation with new uncertainty points.
6. Report the failure and next action concisely.

## Final Report

Use Chinese field names for the user-visible final report. Report only high-signal facts and keep technical terms such as profile, modules, artifacts, adb, log, `.codex`, SSH, Samba, and registry in English when appropriate.

Suggested user-visible fields:

- 根因/需求: requirement implemented or root cause addressed.
- 证据（验证记录/验证结果）: source/log/dumpsys/recording/device evidence used to support the conclusion.
- 修改文件: files changed.
- 构建部署: build/deploy evidence from the platform build/deploy executor, including profile, modules, artifacts, push/deploy destination, restart/reboot/remount when relevant.
- 验证结果: final device verification performed by this workflow.
- 日志处理: diagnostics added, removed, guarded, downgraded, or kept.
- 结论: failures, skipped checks, remaining risk, and whether the work is accepted.

If verification was not run, state exactly why and what remains unverified under `结论`.

Add a `Skill 改进建议` section only when `references/capability-capture.md` says the task meets the trigger threshold. Do not modify this skill automatically; propose persistence and wait for explicit user confirmation.

When the final change is valuable as a reusable patch or process record, mention that it is ready for `android-framework-patch-capture` and include the intended platform/version token, feature slug, summary, status, and verification facts. Do not package unrelated dirty files.
