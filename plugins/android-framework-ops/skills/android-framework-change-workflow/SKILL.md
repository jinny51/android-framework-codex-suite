---
name: android-framework-change-workflow
description: "Use when implementing, diagnosing, modifying, or verifying Android source changes across Framework, SystemApp, App, HAL, native services/libraries, vendor/BSP integration, kernel, drivers, device/board configuration, or build integration. Orchestrates explicit domain and source-authority selection, knowledge search, policy, build-route selection, domain verification, local patch capture, and capability-gated Framework incoming v1 submission."
---

# Android Change Workflow

Use this Skill as the end-to-end engineering workflow for Android source work.
`framework` is one domain profile, not the product boundary.

## Required Contracts

Before modifying source, read:

- `../../contracts/change-domain/v1/domain-profiles.json`
- `../android-change-policy/SKILL.md`
- the current host's `android-source-access` Skill when source access or recovery is needed

For Framework work, also read `references/framework-domain-workflow.md` and its linked
references. For other domains, read `references/domain-routing.md`.

## Remote-Only Source Contract

Classify each affected repository as `registered_remote_tree` or `local_project` before
reading or editing it. A path mounted or registered by `android-source-access` is always
`registered_remote_tree`: the mount is only a human CRUD surface and a confirmed
artifact bridge, never the Codex working tree. Codex must perform every source read/search/edit,
Git/repo or patch operation, checkpoint, and build for that tree through
`android-remote-channel`. Direct SSH is reserved for source-access infrastructure.

A real local Git project explicitly opened as the Codex workspace may use normal local
project tools; this commonly applies to standalone Gradle Apps and independently cloned
repositories. Never reclassify SMB/CIFS-mounted Android source as `local_project`. For a
mixed requirement, record source authority per repository. If authority or remote
project identity cannot be proven, stop before touching that repository.

## Gate 1: Requirement and Primary Domain

Write a concise requirement contract: requested behavior, current behavior, acceptance
criteria, target product/build, constraints, out-of-scope work, and rollback.

Select exactly one primary `change_domain` from the controlled contract. It is the
principal ownership/build/verification surface, not a filename guess and not a claim
that the requirement touches only one layer. Record additional touched surfaces as
components. If ownership remains ambiguous after source/build evidence, ask only for the
missing product decision.

## Gate 2: Knowledge and Source Authority

Run `android-knowledge-search` before implementation and record `reuse`, `adapt`,
`reference_only`, `not_applicable`, or `not_found` with the evidence used.

For a `registered_remote_tree`, use the host platform's `android-source-access` entry
when mount or registry preparation is needed. It routes to the single core
implementation and verifies WSL or macOS before side effects; then use
`android-remote-channel` for all source and build operations. For a `local_project`,
verify its real Git root and project instructions, then use normal local project tools.

## Gate 3: Policy and Change Plan

Apply `android-change-policy` before edits. Universal member/patch attribution applies
to every patch-archived Android change; only the selected domain overlay applies.

Identify repositories and their source authority, modules, API/ABI boundaries,
generated files, build targets and build route, runtime/deployment mechanism,
regression surface, diagnostics, and rollback. Preserve unrelated user changes and use
the smallest coherent change.

## Gate 4: Implement and Verify by Domain

Choose a build route from authoritative project files and instructions:

- `remote_profile`: use `android-remote-build-deploy` for a registered remote AOSP
  Soong/Make module build or an explicitly configured vendor full build. It owns exact
  artifact manifests and supported local adb delivery.
- `remote_project_command`: for a registered remote Gradle, Kbuild/kernel, external
  driver, Bazel, or other project build not supported by that Skill, run the project's
  documented build entry through `android-remote-channel`. Record the exact command,
  environment/profile, exit status, artifact identity, and delivery evidence.
- `local_project_command`: for a real local project, use its wrapper/build entry in the
  local workspace and record equivalent evidence.

Do not invent a generic build command or make `android-remote-build-deploy` claim
support for arbitrary Gradle/Kbuild pipelines. Build success and file transfer are
necessary evidence, not final acceptance. Deploy only through the selected domain's
safe project/device mechanism and keep an explicit rollback.

Apply the selected domain's risks and evidence:

- Framework: Binder/system_server, locks, Handler/Looper, boot, multi-user, resources,
  FrameworkLog, service restart or reboot.
- SystemApp: platform build/signing, privileged permissions, shared UID, privapp,
  SystemUI/Launcher/Settings integration, process or SystemUI restart.
- App: Gradle variant, manifest, unit/UI tests, APK/AAB, signing and install/upgrade.
- HAL: AIDL/HIDL interface/version, VINTF, service registration, SELinux, vendor/system
  boundary and device behavior.
- Native: Soong module, ABI/API, linker namespace, service lifecycle, native tests,
  tombstones and sanitizer evidence when relevant.
- Vendor/BSP: proprietary ownership, product integration, partition boundary,
  compatibility and rollback.
- Kernel: Kconfig/Makefile, subsystem behavior, image/module build, boot, dmesg and
  regression evidence.
- Driver: probe/bind, firmware, power/suspend, device I/O, module/image packaging and
  hardware verification.
- Device/board: product/device configuration, DTS/DTBO/overlays, partition or boot
  integration and board-specific rollback.
- Build: Soong/Make/Gradle/release integration, dependency graph, clean/incremental
  behavior, reproducibility and artifact contract.

Run final acceptance against the requirement contract and nearby regressions. Remove or
explicitly retain temporary diagnostics with a reason.

## Gate 5: Capture and Submission

Use `android-framework-patch-capture --change-domain <domain>` to create one coherent,
reviewable local material package. Capture verifies policy and evidence but does not
repair code after the fact.

The production server currently accepts only frozen incoming v1 `framework_change`:

- `framework`: a validated capture may continue to
  `android-framework-patch-intake`, preserving `patch_package_id` and v1 wire behavior.
- every other domain: stop after a validated local `android_feature_patch`. Report
  submission as capability-gated, not failed and not completed. Never relabel it as
  Framework or invent a v2 package.

## Hard Stops

Stop before claiming completion when:

- the requirement, primary domain, source authority, build route, owner, acceptance, or
  rollback is unresolved;
- registered remote source work would bypass `android-remote-channel`;
- mandatory policy or member identity is missing;
- build, boot, device behavior, safety, or nearby regression verification failed;
- temporary diagnostics have no cleanup decision;
- a non-Framework package would be sent through Framework incoming v1.

## Final Report

Report the requirement/domain, source authority per repository, root cause or design,
changed repositories/files, policy result, selected build route, exact
builds/tests/device evidence, risks/rollback, capture path/status, and whether submission
was performed or capability-gated. Never claim publication, install, server activation,
production deployment, or knowledge curation without its own evidence.
