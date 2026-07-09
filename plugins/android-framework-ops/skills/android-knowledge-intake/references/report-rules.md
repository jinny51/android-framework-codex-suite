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

日报目的：讲清楚今天干了什么、怎么干的、结果是什么。日报不是周总结，不要写成项目总账。

## 一、今日工作概览

| 项目 | 客户 | 模块/功能 | 事项类型 | 当前状态 | 是否阻塞 | 今日一句话进展 |
| --- | --- | --- | --- | --- | --- | --- |

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

周报目的：按项目汇总这一周完成多少、还剩多少、风险和依赖是什么、下周怎么收敛。周报不复述每天流水。

## 一、本周概况

单项目直接写：

- 项目名称：TVE1086U
- 客户名称：青鸾云
- 接到文档时间：2026-06-18
- 需求类型：混合，包含定制需求、Bug / Debug 处理及 BSP 配合事项
- 当周完成情况：本周从上周剩余 8 项中完成 5 项，当前剩余 3 项，预计下周完成整体收敛。

多项目时，在“本周概况”下按项目重复上述块；不要使用“总盘子”这类说法，也不要用大表格堆字段。

## 二、项目详情

### 项目编号 客户名称

#### 1. 基本信息

- 来源类型：定制 / Buglist / 混合 / 临时支持。
- 来源说明：需求单、Buglist、客户、测试、项目经理、临时安排等。
- 接到文档时间：能证明时写日期，不能证明时写 `需成员确认`。
- 已持续时间：能证明时写持续时长，不能证明时写 `需成员确认`。
- 需求结构：定制需求、移植适配、Bug、BSP、其他、合计。
- 上周一剩余：从上周或本周初延续下来的事项；混合项目要按定制 / Bug / BSP 等分类说明。
- 本周完成：本周闭环事项；混合项目要按定制 / Bug / BSP 等分类说明。
- 当前剩余：仍未闭环事项；混合项目要按定制 / Bug / BSP 等分类说明。

#### 2. 本周进展

已完成事项和当前剩余事项分开列出。

#### 3. 本周重点说明

重要定制、移植、Bug、Patch、验证、交付、风险和依赖。

#### 4. 风险与依赖

列出客户确认、BSP、设备、测试、第三方 App、编译环境等风险或依赖。

## 三、下周计划

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
    "material_name": "TVE1086U（青鸾云）",
    "material_summary": "TVE1086U：今日处理锁屏鼠标位置刷新、云电脑崩溃排查。",
    "one_line_summary": "TVE1086U：今日处理锁屏鼠标位置刷新、云电脑崩溃排查。",
    "projects": [],
    "work_items": [],
    "risks": [],
    "outputs": [],
    "tomorrow_focus": [],
    "ui_card": {
      "title": "TVE1086U（青鸾云）",
      "subtitle": "TVE1086U：今日处理锁屏鼠标位置刷新、云电脑崩溃排查。",
      "status": "正常推进"
    }
  }
}
```

Report card fields are authoritative:

- `material_name`：项目 + 客户。多项目写 `TVE1086U（青鸾云）、TVE8801M（未标注客户）`，超过 3 个项目时只列前 3 个并追加 `等 N 个项目`。
- `material_summary`：日报写各项目“今日主题”；周报写各项目“本周完成、剩余、风险/依赖”。它是卡片小字，不要拿日期、成员名或包路径充当摘要。
- `ui_card.title` 必须等于 `material_name`，`ui_card.subtitle` 必须等于 `material_summary`。

Weekly `report_view.json` must preserve the same report facts in structured
form. Required weekly payload fields include `project_ledgers[]`,
`weekly_progress_summary`, and `weekly_detail_sections[]`; legacy fields such
as `project_overview[]`, `source_lists[]`, `source_category_stats[]`,
`item_statistics[]`, `remaining_items[]`, `patch_outputs[]`,
`delivery_verifications[]`, and `next_week_plan[]` remain for UI compatibility.
Management-side aggregation should prefer `project_ledgers[]` over re-counting
daily records. Member-side weekly report generation should still present this
only as a personal weekly report structure.
