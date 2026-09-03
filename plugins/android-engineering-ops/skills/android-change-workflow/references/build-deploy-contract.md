# Build Deploy Contract

Read this when handing off to or receiving results from the shared `android-remote-build-deploy` executor on WSL or macOS.

## Responsibility Split

The build/deploy skill proves delivery:

- Correct remote source path and git/checkpoint state.
- Correct build profile, lunch target, module, and command.
- Successful build.
- Produced artifact paths.
- Artifact push/deploy/sync result.
- Required remount/reboot/restart action.
- Basic post-delivery device health.

`android-change-workflow` proves correctness:

- Direct requirement was implemented or root cause was addressed.
- Target device behavior changed as intended.
- Relevant subsystem regression paths remain stable.
- Diagnostic logs were cleaned up or intentionally kept.
- Final report is complete.

## Before Build Handoff

Provide the build/deploy skill:

- Source tree path and remote path if known.
- Changed files.
- Expected artifact(s).
- Preferred build target/module if known.
- Required deploy behavior: push jar/apk/xml, reboot, restart SystemUI, restart Launcher, or full image/partition flow.
- Verification concern that delivery evidence must support.

## Required Return Evidence

Ask for concise evidence:

- Build command/profile.
- Build success/failure and failure snippet if any.
- Artifact path and timestamp or size if useful.
- Device serial/product if used.
- Push/deploy action and destination.
- Restart/reboot/remount action.
- Basic health result after delivery.
- Skipped steps and reason.

Build/deploy evidence uses `akbs-verification-evidence/v2` with `scope=build_delivery` and
`requirement_acceptance=unverified`. Keep that scope when handing control back. Only the
requirement-specific verification gate may produce `scope=feature` with
`requirement_acceptance=accepted`.

## Artifact Hints

Common framework artifacts:

- `frameworks/base/core` changes often affect `framework.jar`, `boot-framework.vdex/oat`, or broader system image depending build flow.
- `frameworks/base/services` changes often affect `services.jar`.
- `frameworks/base/packages/SystemUI` changes affect `SystemUI.apk`.
- Launcher changes affect the relevant Launcher APK.
- `framework-res` and framework resource changes affect `framework-res.apk`.
- Permission/config XML changes may require partition sync and reboot.
- Overlay changes affect overlay APK or product/vendor/system overlay files.

`scripts/artifact_probe.py` is retired and exits 64. Do not recursively search a mounted output tree by basename. The remote build profile must provide the exact artifact path, and the validated remote artifact manifest must bind that path before the artifact bridge is read.

## After Delivery

This workflow must still:

- Exercise target behavior.
- Run subsystem-specific verification.
- Scan focused logcat for new relevant failures.
- Decide rollback, iterate, or complete.
