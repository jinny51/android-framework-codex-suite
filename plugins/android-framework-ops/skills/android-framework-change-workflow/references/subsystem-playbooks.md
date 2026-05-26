# Subsystem Playbooks

Read the section matching the suspected owner. These playbooks guide diagnosis and verification; they do not replace source reading.

## WindowManager And ActivityTaskManager

Common symptoms:

- Wrong bounds, focus loss, z-order jump, stale task/window state, wrong display, split-screen/PiP/freeform issue, transition artifact.

Check:

- Caller path into ATMS/WMS and whether it runs under the right lock.
- Task/display/window token identity.
- Lifecycle state: resumed/paused/stopping, visibility, focus, configuration, bounds.
- Transition/animation path and surface transaction ordering.
- Multi-window, rotation, density, display, and user/profile gates.

Verify:

- Repeat the target interaction multiple times.
- Test at least one mixed path: rotate, app switch, home/back, relaunch, lock/unlock, multi-window, or display change when relevant.
- Scan for WMS/ATMS exceptions, ANR, system_server restart, focus/bounds/z-order mismatch.
- Use recording/frame inspection for visible transient issues.

## Input

Common symptoms:

- Touch not delivered, wrong target, focus mismatch, gesture race, key event lost, pointer capture issue.

Check:

- InputReader/InputDispatcher state, focused window/application, display id, touchable region, pilfer/cancel path.
- Window flags, visibility, trusted overlay rules, input channel lifecycle.
- Native-to-Java boundary if the issue crosses inputflinger and framework.

Verify:

- Repeat gestures at different speeds.
- Check focus/touch target before and after action.
- Include rotation, lock/unlock, app switch, or overlay presence if relevant.
- Scan for input dispatch timeout and focus warnings.

## SystemUI

Common symptoms:

- Status bar/nav bar/quick settings/notification/recents/keyguard behavior wrong, visual state stale, restart loses state.

Check:

- SystemUI service/component lifecycle, dependency injection path, command queue, status bar state, keyguard state.
- User switch, config change, density/theme, doze/wakefulness, shade/keyguard transitions.
- Whether framework service state and SystemUI cached state diverge.

Verify:

- Target UI flow.
- SystemUI restart tolerance when relevant.
- Rotation/configuration/user switch if the changed state is cached.
- Logcat for SystemUI fatal exception, repeated restart, binder failure, or stale command queue state.

## Launcher Integration

Common symptoms:

- Home/recents/task icon, launch animation, workspace/taskbar, profile/user app visibility, recent task state wrong.

Check:

- Launcher process versus framework owner.
- Launcher model/cache invalidation.
- Package/user/profile visibility.
- Recents/task snapshot, activity launch options, taskbar/navigation mode state.

Verify:

- Home, recents, launch, back/home, profile switch if relevant.
- Process restart or data refresh path if cache invalidation changed.
- Interaction with SystemUI when recents/nav is involved.

## Resources And Overlays

Common symptoms:

- Bool/dimen/string/config value not taking effect, product mismatch, theme/layout behavior wrong.

Check:

- Resource owner: framework, SystemUI, app, vendor/product overlay, RRO.
- Product/variant and overlay priority.
- Runtime resource cache and whether reboot/app restart is required.
- Locale, density, orientation, smallest width, night mode qualifiers.

Verify:

- Confirm selected resource value on target product.
- Verify target UI/behavior after required restart.
- Test at least one nearby configuration if qualifier-sensitive.
- Ensure overlay does not leak to unintended product/variant.

## PackageManager, Permissions, Users, Profiles

Common symptoms:

- Package visibility, install state, permission grant, feature XML, user/profile behavior, launcher visibility wrong.

Check:

- UserId/profile parent/current user assumptions.
- Permission declaration versus grant path.
- Package setting persistence and migration.
- Cross-user permission checks and Binder identity.
- Feature/config XML and product partition placement.

Verify:

- Target package/user/profile behavior.
- Reboot or package manager restart path if state is persisted.
- Fresh install/update path when relevant.
- Logcat for PMS warnings, permission denial, settings parse errors.

## Surface And Visual State

Common symptoms:

- Flicker, stale layer, black frame, wrong crop, wrong alpha, wrong z-order, animation jump.

Check:

- SurfaceControl transaction creation/apply timing.
- Layer ownership and lifecycle.
- Bounds/crop/alpha/visibility state.
- Transition/animation participant ordering.
- Display and rotation transforms.

Verify:

- Use screen recording and frame sampling.
- Repeat with mixed timing and app switches.
- Compare logs with visible frame timeline.
- Scan SurfaceFlinger/WMS/transition logs for errors.
