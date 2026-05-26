# Framework Risk Model

Read this before editing shared Android framework paths or when the risk is unclear.

## Risk Ladder

- **Low**: product-specific config, overlay, string/dimen/bool resource, narrowly scoped UI resource.
- **Medium**: SystemUI/Launcher behavior, feature flag routing, settings/device_config integration, package visibility, non-shared service behavior.
- **High**: framework jar API behavior, WindowManager/ActivityTaskManager, input dispatch, surfaces, permissions, multi-user/profile logic, boot-time services.
- **Critical**: system_server startup, watchdog-sensitive paths, lock ordering, Binder identity, persistent settings migrations, service registration, boot loops, broad shared framework contracts.

Raise the risk one level when the change affects multiple products, displays, users, profiles, rotations, densities, overlays, or process boundaries.

## Always Preserve

- Binder identity: clear and restore identity in balanced scopes; avoid calling permission-sensitive code under the wrong identity.
- Lock ordering: do not add calls under existing global locks unless local patterns prove it is safe.
- Handler/thread affinity: keep state changes on the expected handler, looper, or service thread.
- Lifecycle timing: respect boot phases, user unlock state, activity/window lifecycle, and SystemUI start/restart timing.
- Transaction ordering: preserve surface/window transaction ordering and avoid stale state commits.
- Multi-user/profile semantics: check userId, profile parent, current user, managed profile, clone/private profile, and cross-user permissions.
- Resource precedence: confirm product overlay, vendor overlay, runtime resource overlay, and framework defaults.
- DeviceConfig/settings behavior: understand defaults, caching, observers, and per-user/global scope.

## Shared Path Cautions

- `frameworks/base/services`: assume system_server stability risk.
- `frameworks/base/core`: assume API/behavior consumers beyond the visible caller.
- `frameworks/base/packages/SystemUI`: expect restart/configuration/user-switch paths.
- `frameworks/base/packages/SettingsProvider`: expect persistence and migration risks.
- `frameworks/base/data/etc` and permission XML: expect permission, feature, and package-manager side effects.
- Resource overlays: expect variant mismatch and resource precedence surprises.

## Pre-Change Questions

- Is this a direct requirement or a bug/regression investigation?
- For requirements, what are the acceptance criteria and negative cases?
- Which process owns the state or new policy decision?
- Which artifact must change for the device to exercise the intended behavior?
- Which restart/reboot is required for that artifact?
- Which lock/thread/identity context will execute the change?
- Which product/variant/user/display/configuration can bypass the intended code path?
- What nearby behavior can regress if this branch now executes?

## High-Risk Exit Criteria

For high or critical changes, do not finish without:

- Delivery proof for the expected artifact.
- Reboot or process restart evidence when required.
- Logcat health scan after the exercised path.
- Target behavior verified more than once.
- At least one nearby regression path verified.
