# Android Framework Coding Standards

Source documents:

- `Android Framework 补丁开发规范`, v2.1, 2025-10-16
- `Android Framework 日志管理规范`, v1.0, 2025-10-16

## Development Timing

Apply these rules while implementing the requirement. Do not wait until patch capture to retrofit style. Patch capture is a verification and evidence step; it is not a style repair step.

Use capture-time checks mainly for code not authored through the plugin, such as manual edits, historical patches, external patches, or half-inherited dirty trees.

## Patch Structure

Repository-managed Android source can involve multiple Git repositories for one feature. Package by feature:

- one feature README
- one patch per affected source repository
- evidence covering build, device verification, search-before-change, risk, rollback, and coding-standard checks

Patch filename:

```text
平台Android版本-模块名@补丁功能名.patch
```

Example:

```text
mtk14-frameworks-base@allow_powerkey_to_user.patch
```

## Author And Date Markers

Every custom code block must include author/date markers:

```java
//gyf 20251016@{
// custom logic
//gyf 20251016@}
```

Single-line changes should carry the marker on the line or directly adjacent to it.

## Helper Methods And Utility Classes

- New helper method names should carry the author suffix, for example `isInWhiteListGyf()`.
- When a feature adds two or more custom helper methods, extract a same-package utility class.
- Utility class names should end with the author suffix and `Utils`, for example `ActivityManagerGyfUtils`.
- Utility classes should be small and focused on custom logic, reducing intrusion into platform classes.

## FrameworkLog

Framework logs must use:

```text
frameworks/base/services/core/java/com/android/server/FrameworkLog.java
```

Do not add direct `Log.*` or `Slog.*` calls in patches. Use `FrameworkLog.d/i/w/e` behind the appropriate debug switch.

Module debug switches use:

```text
persist.sys.framework.debug.<module>
```

Examples:

```text
persist.sys.framework.debug
persist.sys.framework.debug.ams
persist.sys.framework.debug.wm
persist.sys.framework.debug.pms
persist.sys.framework.debug.power
persist.sys.framework.debug.settings
persist.sys.framework.debug.input
```

New module switches must be added to `FrameworkLog.java`. Module code should not directly define or read its own `persist.sys.framework.debug.*` switch.

## Configuration

Dynamic configuration priority:

1. `SystemProperties` for system-level control that can require restart.
2. `SettingsProvider` for runtime settings that should change live.

Document all new or reused properties and settings keys in the feature README.

## Strings

Avoid hard-coded user-visible strings and reusable log templates. Prefer string resources and include localized resources where applicable.

Required README section:

```markdown
## 字符串国际化
```

State whether strings were added, which resource keys were touched, and whether Chinese/English resources were updated.

## Feature README

The feature README must include:

```markdown
## 功能描述
## 修改点
## 日志控制
## SystemProperties
## 字符串国际化
## 可回滚性
```

Recommended:

```markdown
## 构建验证
## 设备验证
## 风险说明
## 开发前知识库检索
```
