# Report Rules

## Session Filtering

- Skip automation sessions, empty sessions, report self-test sessions, and pure report-maintenance sessions.
- Keep cross-day sessions when messages on the target date contain real work.
- Keep sessions that produced patches, completed diagnosis, finished validation, or delivered a usable conclusion.

## Progress

- `已完成`: code completed, patch generated, verified, submitted, or delivered.
- `已解决`: issue located and fixed with validation.
- `验证中`: change or plan is ready, waiting for device/customer validation.
- `处理中`: still diagnosing or implementing.
- `阻塞`: blocked by device, logs, permissions, requirements, or dependency.
- `已归档`: historical/documentation work that needs no follow-up.

## Daily Template

```markdown
# YYYY-MM-DD 日报 - 成员名

## 今日概览

1 到 3 句话概括当天主要工作、结果和风险。

## 项目事项

### 项目名 / 模块名

- 事项：具体事项名称
- 进度：已完成 / 已解决 / 验证中 / 处理中 / 阻塞 / 已归档

## 附录：今日产出 Patch

今日无产出 Patch
```

## Weekly Template

```markdown
# YYYYMMDD-YYYYMMDD 周报 - 成员名

## 本周概览

截至周六 22:00，概括本周完成事项、重点问题和风险。

## 项目事项

### 项目名 / 模块名

- 事项：
- 进度：

## 附录：本周产出 Patch

本周无产出 Patch
```

