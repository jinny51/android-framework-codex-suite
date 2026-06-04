# Report Rules

## Session Filtering

- Skip automation sessions, empty sessions, report self-test sessions, and pure report-maintenance sessions.
- Keep cross-day sessions when messages on the target date contain real work.
- Keep sessions that produced patches, completed diagnosis, finished validation, or delivered a usable conclusion.
- Daily and weekly reports are project-work summaries, not chat title summaries.
- Skip or downgrade Codex system text, approval history, plugin install/update chatter, report-generation chatter, SSH key prompts, file-upload captions, and pure local workspace maintenance unless the same session contains a clear project anchor and real engineering work.
- Do not use local Codex worktree names, plugin cache paths, `.codex` paths, generic Android branch names, or temporary file labels as project names.

## Project Anchors

- Prefer project anchors in this order:
  1. remote Android source path used in the session,
  2. remote git branch or local mounted source branch,
  3. build or lunch target,
  4. patch file name, patch readme, or changed source path,
  5. explicit TVE/TVA/TVI project number in the conversation.
- Normalize TVE/TVA/TVI project numbers before grouping report items.
- Keep trailing business text out of the project name:
  - `TVE1086U整体项目交接` -> project `TVE1086U`, item `整体项目交接`.
  - `TVE1091UAOC移动高清` -> project `TVE1091U`, item or label `AOC移动高清`.
  - `TVA10A2R_camera_fix` -> project `TVA10A2R`, source context `camera_fix`.
- If no project anchor can be identified, use `未识别项目` only when the content is still real work. Do not invent a project from directory names.

## Report Summary

- Build the daily or weekly overview from accepted project items.
- Do not form the overview by concatenating session names, last user messages, or command output.
- The overview should mention main project numbers, main work areas, completion state, patch output, and risk or missing evidence.

## Progress

- `已完成`: code completed, patch generated, verified, submitted, or delivered.
- `已解决`: issue located and fixed with validation.
- `待验证`: change or plan is ready, waiting for device/customer validation.
- `处理中`: still diagnosing or implementing.
- `阻塞`: blocked by device, logs, permissions, requirements, or dependency.
- `已归档`: historical/documentation work that needs no follow-up.
- Preserve explicit progress when available, such as `80%`, `0%->100%`, or `40%~60%`.
- For incomplete work, include the current progress and reason, for example `80%，待验证` or `40%，处理中`.

## Daily Template

```markdown
# YYYY-MM-DD 日报 - 成员名

## 今日概览

1 到 3 句话概括当天主要项目、主要事项、完成状态和风险。

## 项目事项

### 项目编号

- 事项：具体事项名称
- 进度：已完成 / 已解决 / 待验证 / 处理中 / 阻塞 / 已归档，或明确百分比

## 附录：今日产出 Patch

今日无产出 Patch
```

## Weekly Template

```markdown
# YYYYMMDD-YYYYMMDD 周报 - 成员名

## 本周概览

截至周六 22:00，按项目概括本周完成事项、未完成事项、重点问题、风险和下周重点。

## 项目事项

### 项目编号

- 事项：
- 进度：

## 附录：本周产出 Patch

本周无产出 Patch
```
