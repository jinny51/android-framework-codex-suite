# android-weekly-report-intake

> GitHub 说明页。Runtime skill 文件位于 [../../../../plugins/android-framework-ops/skills/android-weekly-report-intake](../../../../plugins/android-framework-ops/skills/android-weekly-report-intake)。

成员个人周报入口。它只负责生成、替换、检查和提交周报包（weekly report package），并复用 `android-knowledge-intake` 的共享脚本和上传协议。成员侧不生成、不理解团队汇总报告；管理端汇总是管理员侧能力。

周报回答“这一周完成多少、还剩多少、风险和依赖是什么”。日报记录当天做了什么、怎么做、结果是什么；周报不复述每天流水，只做一周总结。新周报包生成：

- `reports/weekly.md`
- `materials/display/report_view.json`
- `materials/evidence/work_findings.json`

`report_view.json` 是同一份周报正文的 UI 读模型（UI read model），使用 `schema=akbs-report-view-human-v1`，至少包含 `report_type=weekly`、`week_range`、`display_date`、`material_name`、`material_summary`、`member_alias`、`member_name` 和 `projects[]`。每个项目行包含 `project`、`customer`、`week_summary`、`received_date`、`source`、`requirement_type`、`requirement_structure`、`completed_this_week`、`remaining`、`expected_finish`、`completed_items[]`、`remaining_items[]`、`risks[]`、`dependencies[]` 和 `next_week_plan[]`。周报包只归档，不进入知识库沉淀候选。

成员周报以范文为基线：`本周概况` 先按项目写项目名称、客户名称、接到文档时间、来源说明、需求类型、需求结构、本周完成、当前剩余、预计完成；`项目详情` 再写本周完成、当前剩余、风险 / 依赖；最后写 `下周计划`。多项目时重复同一项目块，不用大表格堆字段。成员可以直接说 `TVE1086U 青鸾云，本周主要推进...`；生成阶段会识别为项目 `TVE1086U`、客户 `青鸾云`。如果缺项目或客户，包会保留给成员修正，但提交会被本地校验拦住。新包不得再写旧 `report_view` 字段，例如 `display_title`、`ui_card`、`one_line_summary`、`project_ledgers`、`weekly_progress_summary` 或 `weekly_detail_sections`。

周报卡片不使用周范围当标题。`material_name` 写项目 + 客户，例如 `TVE1086U（青鸾云）`；多项目时每个项目都带自己的客户。`material_summary` 写各项目本周完成、剩余、风险或依赖，例如 `TVE1086U：本周完成 5 项，剩余 3 项，有风险。`。

执行生成或提交前，Codex 应先从当前请求和可见会话上下文里找项目名 + 客户名；找不到时先在会话里提示 `缺少项目名和客户名，请补充，例如：TVE1086U 青鸾云。`，不要直接跑命令。

常用命令：

```bash
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> weekly --prepare
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> weekly --submit-latest
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> weekly --prepare --replace-weekly-run-id <old_run_id>
```
