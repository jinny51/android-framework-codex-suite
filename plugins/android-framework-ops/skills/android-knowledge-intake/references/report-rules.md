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

## 一、本周整体概览

按项目统计来源清单数、本周事项总数、本周新增、本周完成、进行中、未开始、阻塞/风险、超3天未进展和整体状态。

## 二、本周按项目总结

### 项目编号

需求来源地：项目经理 / 上级 / 客户 / 测试 / 禅道 / 临时工作。
需求种类：需求清单 / Buglist / 临时工作。
来源清单：清单名称、总数、本周新增、本周完成、剩余、风险。
来源分类统计：功能添加、Bug处理、UI修改、功能移植。
本周事项统计：本周接收、历史遗留、本周完成、进行中、未开始、阻塞、剩余。
未完成 / 剩余事项：当前进度、未完成原因、风险、已卡多久、预计时间。

## 三、本周重点问题与风险

重点风险列表。

## 四、本周 Patch 产出

Patch 列表。

## 五、本周验证与交付情况

验证、交付和对外同步情况。

## 六、下周重点计划

下周优先事项。
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
