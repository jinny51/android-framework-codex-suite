# Verification Matrix

Read this before final verification and final reporting.

## General Rule

Build and delivery prove the intended change reached the device. They do not prove framework correctness. Final verification must exercise the target behavior and nearby risk paths on device unless the user explicitly asked only for analysis or code drafting.

## Always Collect

- Requirement acceptance criteria or bug/root-cause verification target.
- Build target/profile and result.
- Artifact path and delivery action.
- Restart/reboot/remount action if required.
- Target behavior result.
- Basic health scan after exercising behavior.
- Skipped checks and residual risk.

Use `scripts/health_scan_logcat.py` on focused logcat files when available.

## By Change Type

| Change type | Required verification |
| --- | --- |
| Resource/overlay/config | Confirm selected value, target behavior, product/variant scope, and no obvious nearby UI regression. |
| SystemUI | Target UI flow, SystemUI stability, relevant config/user/restart path, logcat exceptions. |
| Launcher | Home/recents/launch flow, cache/model refresh if relevant, profile/user visibility, interaction with SystemUI if involved. |
| framework core jar | Target caller path, dependent process restart/reboot, API/behavior consumer path, logcat health. |
| system_server service | Reboot or service restart path, system_server continuity, target behavior, nearby service regression, watchdog/ANR/crash scan. |
| WM/ATM | Repeated interaction, focus/bounds/visibility/z-order, rotation/app switch/home/back/multi-window if relevant, WMS/ATMS log health. |
| Input | Repeated gestures/keys, focus/touch target, speed variation, rotation/overlay/app switch if relevant, input timeout scan. |
| Surface/visual/animation | Recording or screenshots, frame inspection, repeated mixed timing, log timeline comparison. |
| PMS/permissions/users | Target package/user/profile behavior, reboot or PMS restart if needed, fresh install/update path when relevant, permission denial scan. |
| Cross-module | Verify each delivered artifact and one integrated end-to-end flow. |

## Device Health Signals

Scan after deploy and after exercising target behavior:

- system_server death or restart.
- SystemUI or Launcher crash/restart loop.
- ANR, watchdog, fatal exception, native crash.
- Boot loop, soft reboot, binder transaction failures.
- Permission denial related to touched path.
- Resource/overlay parse failure.
- Input dispatch timeout.

## Repetition Requirements

Use repeated mixed interactions when the change affects:

- Gesture, key, touch, or focus.
- Window/task/display bounds.
- Z-order, visibility, transition, surface, animation.
- Process restart, boot, user switch, lock/unlock.
- Cached state or async observer behavior.

One happy path is insufficient for these categories.

## Final Acceptance

Accept completion only when:

- Direct requirement has acceptance evidence or root cause has evidence.
- Expected artifact was delivered.
- Target behavior was verified on device.
- Health scan did not show new relevant failures.
- Diagnostics were cleaned up or intentionally kept.
- Skipped checks are explicit and acceptable for the request.
