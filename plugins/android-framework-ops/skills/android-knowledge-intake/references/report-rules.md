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

## 一、今日概况

### 项目名 客户名

- 今日主题：今天主要处理了什么。
- 当前结果：今天处理到什么程度。

## 二、今日工作

### 项目名 客户名

#### 1. 事项名称

做了什么：
- 具体做了哪些工作。

怎么做的：
- 通过什么方式排查、修改、验证或推进。

结果：
- 当前结果是什么，是否还要继续。

## 三、明日重点

### 项目名 客户名
- 明天优先处理什么。
```

## Weekly Template

```markdown
# YYYYMMDD-YYYYMMDD 周报 - 成员名

周报目的：按项目汇总这一周完成多少、还剩多少、风险和依赖是什么、下周怎么收敛。周报不复述每天流水。

## 一、本周概况

### 项目名 客户名

本周围绕 项目名 客户名 项目推进：简短说明本周主要处理的方向。

- 接到文档时间：2026-06-18
- 来源说明：客户需求文档 / TL指派 / Buglist / 测试反馈 / BSP配合 中选择一个
- 需求类型：纯定制 / Buglist / 混合 中选择一个
- 需求结构：18 项（定制 8、Bug 8、BSP 2）
- 本周完成：5 项（定制 4、Bug 1）
- 当前剩余：3 项（定制 3、Bug 0）
- 预计完成：预计完成时间或收敛说明

多项目时，在“本周概况”下按项目重复上述块；不要使用“总盘子”这类说法，也不要用大表格堆字段。

## 二、项目详情

### 项目编号 客户名称

#### 1. 本周完成

列出本周已完成事项。

#### 2. 当前剩余

列出当前剩余事项。

#### 3. 风险 / 依赖

风险：超过 3 天无进展的事项；没有则写“无超过 3 天无进展事项。”
依赖：依赖外部推进的事项；没有则写“无外部依赖事项。”

## 三、下周计划

按项目说明下周优先处理什么、剩余问题预计哪周完成。
```

## UI Read Model

Daily and weekly reports are the primary human-readable product. The package also writes `materials/display/report_view.json` as a structured UI read model for cards, lists, and detail views. The read model is generated from the same report inputs as `reports/daily.md` or `reports/weekly.md`; it is not a separate evidence or AI layer and must not contradict the report body.

```json
{
  "kind": "report_view",
  "payload": {
    "schema": "akbs-report-view-human-v1",
    "report_type": "daily",
    "material_name": "TVE1086U（青鸾云）",
    "material_summary": "TVE1086U：今日处理锁屏鼠标位置刷新、云电脑崩溃排查。",
    "projects": [
      {
        "project": "TVE1086U",
        "customer": "青鸾云",
        "today_topic": "锁屏鼠标位置刷新",
        "current_result": "已完成基础验证",
        "work_items": [
          {"name": "锁屏鼠标位置刷新", "did": ["完成属性映射处理"], "how": ["按输入链路排查"], "result": "已完成"}
        ],
        "tomorrow_focus": ["继续回归验证"]
      }
    ]
  }
}
```

Report card fields are authoritative:

- `material_name`：项目 + 客户。多项目写 `TVE1086U（青鸾云）、TVE8801M（未标注客户）`，超过 3 个项目时只列前 3 个并追加 `等 N 个项目`。
- `material_summary`：日报写各项目“今日主题”；周报写各项目“本周完成、剩余、风险/依赖”。它是卡片小字，不要拿日期、成员名或包路径充当摘要。
- Daily project rows contain `project/customer/today_topic/current_result/work_items/tomorrow_focus`.
- Weekly project rows contain `project/customer/week_summary/received_date/source/requirement_type/requirement_structure/completed_this_week/remaining/expected_finish/completed_items/remaining_items/risks/dependencies/next_week_plan`.
- Do not emit deprecated `display_title`, `ui_card`, `one_line_summary`, `project_ledgers`, `weekly_progress_summary`, or `weekly_detail_sections`.
