# Android Framework Patch Rules

## Naming

Patch filename pattern:

```text
平台Android版本-模块名@补丁功能名.patch
```

Example:

```text
mtk14-frameworks-base@allow_powerkey_to_user.patch
```

Suggested regex:

```text
^[a-z0-9]+[0-9]+-[A-Za-z0-9._-]+@[a-z0-9_.-]+\.patch$
```

## Required Feature README Headings

Each framework change package must include one feature README with:

```markdown
## 功能描述
## 修改点
## 日志控制
## SystemProperties
## 字符串国际化
## 可回滚性
```

Recommended additional headings:

```markdown
## 验证方式
## 风险说明
```

## Log And Property Checks

- New direct `Log.*` and `Slog.*` calls are forbidden.
- Use `FrameworkLog`.
- `persist.sys.framework.debug.*` must be centralized in `FrameworkLog.java`.
- User-visible strings should use resources and include Chinese/English values.
