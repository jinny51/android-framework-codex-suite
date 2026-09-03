# Requirements Implementation

Read this when the user asks for a new framework behavior, OEM policy, feature customization, config change, or product requirement rather than a bug investigation.

## Requirement Contract

Before editing behavior, establish:

- Desired behavior in observable terms.
- Product/device/variant scope.
- User/profile/display/configuration scope.
- Owner subsystem and process.
- Expected artifact and restart/reboot requirement.
- Acceptance criteria for success.
- Negative cases: what must not change.
- Nearby regression paths.
- Feature flag, resource overlay, DeviceConfig, Settings, or build-time gating strategy when needed.

If a requirement is underspecified, infer conservatively from source/product context when safe. Ask the user only when the missing choice changes user-visible behavior, product scope, privacy/security policy, or rollout risk.

## Requirement Design Pattern

Use this order:

1. Locate the current behavior and owner subsystem.
2. Identify the lowest-risk extension point: config, overlay, DeviceConfig, Settings, policy class, service boundary, or UI state owner.
3. Check existing product/OEM patterns before adding a new mechanism.
4. Define gate conditions clearly: product, feature flag, user/profile, display, package, permission, or runtime state.
5. Preserve default behavior for out-of-scope products and users.
6. Add diagnostics only if needed to prove the new path is exercised.
7. Build verification from acceptance criteria and negative cases.

## Good Requirement Examples

- "On product X, force a specific framework config value while preserving other variants."
- "Add a system policy that blocks/permits behavior for a package/user/profile under defined conditions."
- "Change SystemUI/Launcher integration for a device mode, with restart/configuration behavior preserved."
- "Add WindowManager behavior for a specific display/windowing mode while preserving focus and bounds elsewhere."

## Requirement Risk Checks

Before implementation, check:

- Could this be product overlay/config rather than code?
- Does this require persistence, migration, or rollback behavior?
- Does the behavior differ by user, managed profile, clone/private profile, or current user?
- Does it cross Binder/process boundaries or require permission changes?
- Does it run under locks, boot phases, or handler threads?
- Does it affect resource precedence, runtime overlays, or cached state?
- Does it need a kill switch or feature flag for product rollout?

## Verification For Requirements

Verify both positive and negative behavior:

- Positive: acceptance criteria works on the target product/device.
- Negative: out-of-scope product/user/profile/display/configuration keeps old behavior.
- Stability: affected process survives restart/reboot path required by the artifact.
- Regression: nearby behavior still works.
- Health: focused logcat scan shows no new relevant crash, ANR, watchdog, permission denial, or resource failure.

For visual/window/input requirements, use repeated mixed interactions and recording/frame evidence when timing or transient UI state matters.
