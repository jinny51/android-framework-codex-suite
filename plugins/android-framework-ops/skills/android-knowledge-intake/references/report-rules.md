# Report Rules

## Session Filtering

- Read sessions only after explicit consent for this report run. The report date or week is the exact time window, and only the selected `work_summary`, `project_hint`, `command_summary`, or `patch_discovery` fields may be derived.
- Keep only sanitized derived summaries and minimal source session IDs. Do not retain thread titles, cwd, raw messages, raw commands, clipboard content, environment values, credentials, paths, or temporary extraction files.
- Skip automation sessions, empty sessions, report self-test sessions, and pure report-maintenance sessions.
- Keep cross-day sessions when messages on the target date contain real work.
- Discover cross-day sessions by message timestamp and file activity, not only
  by the directory in which a session was originally created.
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
- For daily generation, ask only for the missing project + direct customer
  identity, then continue after the member supplies it. Also remind the member
  of the normal Codex workflow: create the project first, then create development
  sessions under that project. Do not ask for weekly ledger fields during daily
  generation.

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

### **项目名** 客户名 [客户的客户]

- 今日主题：今天主要处理了什么。
- 当前结果：今天处理到什么程度。

## 二、今日工作

### **项目名** 客户名 [客户的客户]

#### 1. 事项名称

做了什么：
- 具体做了哪些工作。

怎么做的：
- 通过什么方式排查、修改、验证或推进。

结果：
- 当前结果是什么，是否还要继续。

状态：
- 已完成 / 处理中 / 待验证 / 阻塞（只选一个）

## 三、明日重点

### **项目名** 客户名 [客户的客户]
- 明天优先处理什么。
```

## Weekly Template

Weekly project facts are not derived by counting sessions. Resolve current
effective daily reports from AKBS, carry the current previous-week project
ledger forward, apply report replacement chains, and use sessions only to
supplement work absent from effective daily reports. `weekly_fact_sources`
records this provenance. Missing ledger fields block upload and are completed
through the explicit `akbs-weekly-project-facts-v2` contract. Requirement
source is created when the member receives the demand and must not be inferred
from daily-report wording.

```markdown
# YYYYMMDD-YYYYMMDD 周报 - 成员名

周报目的：按项目汇总这一周完成多少、还剩多少、风险和依赖是什么、下周怎么收敛。周报不复述每天流水。

## 一、本周概况

### **项目名** 客户名 [客户的客户]

本周围绕 **项目名** 客户名 [客户的客户] 项目推进：简短说明本周主要处理的方向。

- 项目角色：主责 / 协作 中选择一个
- 需求时间：2026-06-18
- 需求来源：CR / TL / PM / TE / BSP 中选择一个
- 共 18 项：需求 4、移植 4、Bug 8、BSP 2（主责必填，协作可省略）
- 本周完成 5 项：需求 2、移植 2、Bug 1
- 当前剩余 5 项：需求 1、移植 2、BSP 2

`需求`表示团队以前没有做过的客户需求，`移植`表示复用或移植团队以前做过的
客户需求，`Bug`表示缺陷处理。不要保留`定制`父分类。Bug 修复补丁的移植仍计
`Bug`。`BSP`仅统计项目总量或当前剩余中的 BSP 负责项，不得作为本周完成项。
旧`定制`计数不能自动拆分，必须由成员确认。正数计数行至少包含一项`需求`、
`移植`或`Bug`，为 0 的分类省略，行总数必须等于分类之和。

多项目时，在“本周概况”下按项目重复上述块；不要使用“总盘子”这类说法，也不要用大表格堆字段。

每个公司项目在结构化 `projects[]` 中只出现一次。App/功能模块属于本周完成、
当前剩余或下周计划事项，不得按事项名称拆成多个同项目块。身份门禁验证规范项目
编号、唯一项目行、当前上下文已确认的客户链和同源证据一致性，不枚举模块名称。

## 二、项目详情

### **项目编号** 客户名称 [客户的客户]

#### 1. 本周完成

列出本周已完成事项。

#### 2. 当前剩余

列出当前剩余事项。

#### 3. 重点说明

说明项目外部消息、范围变化或本周攻克的关键难点；没有则写“无”。

#### 4. 风险 / 依赖

风险：超过 3 天无进展的事项；没有则写“无超过 3 天无进展事项。”
依赖：依赖外部推进的事项；没有则写“无外部依赖事项。”

## 三、下周计划

按项目说明下周优先处理什么、剩余问题预计哪周完成。
没有下周动作的项目不在本节生成项目块，禁止用“无”或“暂无”占位。
```

Markdown 中项目名在所有出现位置都加粗，包括标题、概况正文、完成项、剩余项、
风险、依赖和计划；只加粗项目名，不连带客户或客户的客户。该规则只作用于
`reports/*.md`。`report_view.json` 的 `project`、`material_name`、
`material_summary` 和其他结构化字段保持纯文本，不写 `**`。

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
          {"name": "锁屏鼠标位置刷新", "did": ["完成属性映射处理"], "how": ["按输入链路排查"], "result": "基础验证通过", "status": "已完成"}
        ],
        "tomorrow_focus": ["继续回归验证"]
      }
    ]
  }
}
```

`customer` is the direct customer. `downstream_customer` is optional and means
the direct customer's customer. For example, `TVE1091U AOC 福建移动高清`
becomes `project=TVE1091U`, `customer=AOC`, and
`downstream_customer=福建移动高清`. Do not collapse the two customer levels
into aliases. A two-segment identity such as `TVE1086U 青鸾云` remains valid.

Report card fields are authoritative:

- `material_name`：项目 + 客户链路。多项目写 `TVE1086U（青鸾云）、TVE1091U（AOC → 福建移动高清）`，超过 3 个项目时只列前 3 个并追加 `等 N 个项目`。
- `material_summary`：日报写各项目“今日主题”；周报写各项目“本周完成、剩余、风险/依赖”。它是卡片小字，不要拿日期、成员名或包路径充当摘要。
- Daily project rows contain `project/customer/[downstream_customer]/today_topic/current_result/work_items/tomorrow_focus`; every work item contains `name/did/how/result/status` and status is one of `已完成/处理中/待验证/阻塞`.
- Weekly project rows contain `project/customer/[downstream_customer]/project_role/week_summary/requirement_date/requirement_source/[requirement_structure]/completed_this_week/remaining/completed_items/remaining_items/key_points/risks/dependencies/next_week_plan`.
- The current read model does not emit `display_title`, `ui_card`, `one_line_summary`, `project_ledgers`, `weekly_progress_summary`, or `weekly_detail_sections`.
