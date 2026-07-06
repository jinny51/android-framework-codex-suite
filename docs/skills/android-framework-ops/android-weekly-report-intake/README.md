# android-weekly-report-intake

> GitHub 说明页。Runtime skill 文件位于 [../../../../plugins/android-framework-ops/skills/android-weekly-report-intake](../../../../plugins/android-framework-ops/skills/android-weekly-report-intake)。

成员个人周报入口。它只负责生成、替换、检查和提交周报包（weekly report package），并复用 `android-knowledge-intake` 的共享脚本和上传协议。成员侧不生成、不理解团队汇总报告；管理端汇总是管理员侧能力。

周报回答“这一周围绕哪些项目推进、项目概况还剩多少”。日报记录当天做了什么、怎么做、结果是什么；周报不复述每天流水，只做一周总结。新周报包生成：

- `reports/weekly.md`
- `materials/display/report_view.json`
- `materials/evidence/work_findings.json`

`report_view.json` 是同一份周报正文的 UI 读模型（UI read model），至少包含 `report_type=weekly`、`week_range`、`display_date`、`display_title`、`one_line_summary`、`project_ledgers[]`、`weekly_progress_summary`、`weekly_detail_sections[]`、`project_overview[]`、`source_lists[]`、`source_category_stats[]`、`item_statistics[]`、`remaining_items[]`、`risks[]`、`patch_outputs[]`、`delivery_verifications[]` 和 `next_week_plan[]`。周报包只归档，不进入知识库沉淀候选。

成员周报的核心是项目概况：项目名称、来源类型（定制 / Buglist / 混合 / 临时支持）、来源说明、启动时间、已持续时间、新增功能、移植适配、Bug、其他、合计、本周完成、累计完成、当前剩余、预计完成周和风险。生成结果允许成员在上传前手动修正；`project_ledgers[]` 是成员个人周报的结构化读模型，供管理端后续汇总使用，成员端不暴露团队汇总概念。

常用命令：

```bash
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> weekly --prepare
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> weekly --submit-latest
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> weekly --prepare --replace-weekly-run-id <old_run_id>
```
