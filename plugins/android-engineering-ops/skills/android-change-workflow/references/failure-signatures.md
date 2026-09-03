# Failure Signatures

Read this when build, deploy, boot, health, or behavior verification fails.

## First Response

- Stop adding behavioral changes.
- Preserve the failing artifact/log/recording path.
- Identify whether the failure is new, pre-existing, flaky, or caused by delivery mismatch.
- Compare failure timing with the last changed file, requirement/root-cause hypothesis, and last deployed artifact.
- Decide whether to rollback, narrow, or return to diagnosis.

## Common Signatures

### Artifact Mismatch

Signals:

- Build succeeded but device behavior unchanged.
- Pushed artifact path does not match touched module.
- Process was not restarted or rebooted after framework jar/resource change.
- Product/variant artifact differs from target device.

Action:

- Re-check build target, artifact path, partition, device product, restart requirement, and build timestamp.

### system_server Crash Or Restart

Signals:

- `system_server` died, watchdog, boot loop, service repeatedly restarting, fatal Java exception in services path.

Action:

- Treat as high severity.
- Inspect smallest crash stack.
- Compare with changed services/core code.
- Prefer rollback or a narrower change before another attempt.

### SystemUI Or Launcher Restart Loop

Signals:

- Fatal exception in SystemUI/Launcher, repeated process start, UI disappearing, navigation/status bar missing.

Action:

- Check dependency initialization, resource ids, null cached state, user/config changes, and binder service availability.

### ANR Or Watchdog

Signals:

- Input dispatch timeout, broadcast/service ANR, watchdog blocked thread, long lock hold.

Action:

- Inspect blocked thread, locks, binder calls under lock, synchronous work on main/handler thread.
- Return to risk model before editing again.

### Boot Loop Or Soft Reboot

Signals:

- Device repeatedly returns to boot animation, `zygote` or system_server cycling, framework resource parse failure.

Action:

- Prioritize rollback to restore device.
- Check resource XML, permissions XML, service registration, class loading, static initialization.

### Visual Regression

Signals:

- Flicker, black frame, stale layer, wrong bounds, wrong z-order, transition jump.

Action:

- Capture recording, extract frames, align with WMS/SurfaceFlinger/transition logs.
- Do not rely only on screenshots after the final state settles.

### Permission/User/Profile Regression

Signals:

- Permission denial, package hidden, work profile behavior wrong, cross-user exception.

Action:

- Check caller identity, userId/profile id, permission grant path, package visibility, and persistent package settings.

### Resource Or Overlay Mismatch

Signals:

- Config value unchanged, wrong layout/string/dimen, resource not found, overlay parse error.

Action:

- Check product/vendor/system partition, overlay priority, qualifiers, target package, and restart/reboot requirements.

## Recovery Choices

- **Rollback** when system stability is broken or root cause was disproven.
- **Narrow** when the failure is local to the change but the requirement contract or diagnosis remains valid.
- **Instrument** when the failure reveals a new unknown.
- **Rebuild/redeploy** when delivery evidence is weak.

Do not mask a framework failure with an unrelated workaround.
