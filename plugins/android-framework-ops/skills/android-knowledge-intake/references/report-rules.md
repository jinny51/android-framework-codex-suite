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
  5. explicit TVD/TVE/TVA/TVI project number in the conversation.
- Normalize TVD/TVE/TVA/TVI project numbers before grouping report items.
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

## 一、今日工作概览

| 项目 | 模块/功能 | 事项类型 | 当前状态 | 是否阻塞 | 今日一句话进展 |
| --- | --- | --- | --- | --- | --- |

## 二、今日具体事项

### 项目编号

#### 事项 1: 具体事项名称
- 事项来源：Codex 会话记录 / 本地工程证据
- 事项描述：具体事项描述
- 今日处理内容：今天实际处理了什么
- 处理方式/简要流程：如何排查、修改、验证或推进
- 今日结果：已完成 / 待验证 / 处理中 / 阻塞，或明确百分比
- 验证情况：是否编译、上机、回归、提测或仍缺验证条件
- 遗留问题：仍缺什么
- 下一步/明日计划：明日继续做什么

## 三、今日阻塞 / 风险

项目、阻塞事项、阻塞原因、需要谁支持、预计恢复时间。

## 四、今日产出

Patch、文档、验证结果、对外同步。

## 五、明日重点

明日优先事项。
```

## Weekly Template

```markdown
# YYYYMMDD-YYYYMMDD 周报 - 成员名

## 一、本周概览

按项目汇总：本周涉及项目数、项目总盘子事项合计、本周完成、累计完成、当前剩余、风险项目和一句话总结。

## 二、按项目汇报

### 项目编号

### 项目总盘子

- 来源类型：定制 / Buglist / 混合 / 临时支持。
- 来源说明：需求单、Buglist、客户、测试、项目经理、临时安排等。
- 启动时间：能证明时写日期，不能证明时写 `需成员确认`。
- 已持续时间：能证明时写持续时长，不能证明时写 `需成员确认`。
- 分类总量：新增功能、移植适配、Bug、其他、合计。
- 进度数字：本周完成、累计完成、当前剩余、预计完成周。

### 本周进展

围绕总盘子说明本周推进了多少、完成了多少、还剩多少。

### 本周重点说明

重要定制、移植、Bug、Patch、验证、交付、风险和依赖。

## 三、下周重点

按项目说明下周优先处理什么、剩余问题预计哪周完成。
```

## UI Read Model

Daily and weekly reports are the primary human-readable product. The package also writes `materials/display/report_view.json` as a structured UI read model for cards, lists, and detail views. The read model is generated from the same report inputs as `reports/daily.md` or `reports/weekly.md`; it is not a separate evidence or AI layer and must not contradict the report body.

```json
{
  "kind": "report_view",
  "payload": {
    "report_type": "daily",
    "display_title": "20260701_成员_日报",
    "one_line_summary": "今天处理了...",
    "projects": [],
    "work_items": [],
    "risks": [],
    "outputs": [],
    "tomorrow_focus": [],
    "ui_card": {
      "title": "20260701_成员_日报",
      "subtitle": "今天处理了...",
      "status": "正常推进"
    }
  }
}
```

Weekly `report_view.json` must preserve the same report facts in structured
form. Required weekly payload fields include `project_ledgers[]`,
`weekly_progress_summary`, and `weekly_detail_sections[]`; legacy fields such
as `project_overview[]`, `source_lists[]`, `source_category_stats[]`,
`item_statistics[]`, `remaining_items[]`, `patch_outputs[]`,
`delivery_verifications[]`, and `next_week_plan[]` remain for UI compatibility.
Management-side aggregation should prefer `project_ledgers[]` over re-counting
daily records. Member-side weekly report generation should still present this
only as a personal weekly report structure.
