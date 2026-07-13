# android-weekly-report-intake

> GitHub 说明页。Runtime skill 文件位于 [../../../../plugins/android-framework-ops/skills/android-weekly-report-intake](../../../../plugins/android-framework-ops/skills/android-weekly-report-intake)。

成员个人周报入口。它只负责生成、替换、检查和提交周报包（weekly report package），并复用 `android-knowledge-intake` 的共享脚本和上传协议。成员侧不生成、不理解团队汇总报告；管理端汇总是管理员侧能力。

周报回答“这一周完成多少、还剩多少、风险和依赖是什么”。日报记录当天做了什么、怎么做、结果是什么；周报不复述每天流水，只做一周总结。新周报包生成：

- `reports/weekly.md`
- `materials/display/report_view.json`
- `materials/evidence/work_findings.json`
- `materials/evidence/weekly_fact_sources.json`

周报事实优先读取 AKBS 中本周当前有效日报和上一周当前有效周报；API 不可用时回退到本机 `submitted` 包，并按替换链只选补交后的叶节点。Codex session 只补充有效日报未覆盖的事项，不能再把“一段会话”统计成“一项需求”。跨日长会话按消息日期和文件活跃时间补扫，不只修补周一。

如果接到文档时间、需求来源、需求总量、剩余事项身份或预计完成时间仍缺失，本地检查会列出准确字段并阻止上传。成员只补这些事实，Codex 将其写入 `$CODEX_HOME/artifacts/android-knowledge-intake/weekly-facts/` 下的 `akbs-weekly-project-facts-v1` JSON，再通过 `--weekly-facts <path>` 重新生成；不再要求成员大面积手改 Markdown。

`report_view.json` 是同一份周报正文的 UI 读模型（UI read model），使用 `schema=akbs-report-view-human-v1`，至少包含 `report_type=weekly`、`week_range`、`display_date`、`material_name`、`material_summary`、`member_alias`、`member_name` 和 `projects[]`。每个项目行包含 `project`、`customer`、`week_summary`、`received_date`、`source`、`requirement_type`、`requirement_structure`、`completed_this_week`、`remaining`、`expected_finish`、`completed_items[]`、`remaining_items[]`、`risks[]`、`dependencies[]` 和 `next_week_plan[]`。周报包只归档，不进入知识库沉淀候选。

需求数量按归属分类为定制、Bug 和明确待 BSP 负责/配合的事项。补丁移植、适配和复用是实现方式：客户需求计入定制，缺陷修复计入 Bug。BSP 可出现在需求结构和剩余统计中，但不得出现在 Android 定制组的本周完成统计中。

成员周报以范文为基线：`本周概况` 先按项目写项目名称、客户名称、接到文档时间、来源说明、需求类型、需求结构、本周完成、当前剩余、预计完成；`项目详情` 再写本周完成、当前剩余、风险 / 依赖；最后写 `下周计划`。多项目时重复同一项目块，不用大表格堆字段。成员可以直接说 `TVE1086U 青鸾云，本周主要推进...`；生成阶段会识别为项目 `TVE1086U`、客户 `青鸾云`。如果缺项目或客户，包会保留给成员补充，但提交会被本地校验拦住；补齐结构化事实后重新生成 Markdown 和 JSON，不单独手改其中一份。新包不得再写已废弃的 `report_view` 字段，例如 `display_title`、`ui_card`、`one_line_summary`、`project_ledgers`、`weekly_progress_summary` 或 `weekly_detail_sections`。

周报卡片不使用周范围当标题。`material_name` 写项目 + 客户，例如 `TVE1086U（青鸾云）`；多项目时每个项目都带自己的客户。`material_summary` 写各项目本周完成、剩余、风险或依赖，例如 `TVE1086U：本周完成 5 项，剩余 3 项，有风险。`。

执行生成或提交前，Codex 应先从当前请求和可见会话上下文里找项目名 + 客户名；找不到时先在会话里提示 `缺少项目名和客户名，请补充，例如：TVE1086U 青鸾云。`，不要直接跑命令。

成员本次明确要求生成周报，只授权本次周范围和本次选择的派生字段。最小范围使用 `--session-consent --session-field work_summary`；只有确有需要时才增加 `project_hint`、`command_summary` 或 `patch_discovery`，其中 `patch_discovery` 还要求 `project_hint`。没有本次明确请求时，必须在读取 session、打包和 HTTP 前停止；不得复用旧授权或给定时任务长期授权。

常用命令：

```bash
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> weekly --session-consent --session-field work_summary --prepare
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> weekly --submit-latest
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> weekly --session-consent --session-field work_summary --prepare --replace-weekly-run-id <old_run_id>
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> weekly --session-consent --session-field work_summary --weekly-facts "$CODEX_HOME/artifacts/android-knowledge-intake/weekly-facts/<week>.json" --prepare
```
