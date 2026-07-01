# android-weekly-report-intake

> GitHub 说明页。Runtime skill 文件位于 [../../../../plugins/android-framework-ops/skills/android-weekly-report-intake](../../../../plugins/android-framework-ops/skills/android-weekly-report-intake)。

成员个人周报入口。它只负责生成、替换、检查和提交周报包（weekly report package），并复用 `android-knowledge-intake` 的共享脚本和上传协议。团队周报汇总不属于成员插件仓库。

周报回答“这一周整体推进得怎么样”。新周报包生成：

- `reports/weekly.md`
- `materials/display/report_view.json`
- `materials/evidence/work_findings.json`

`report_view.json` 是同一份周报正文的 UI 读模型（UI read model），至少包含 `report_type=weekly`、`week_range`、`display_date`、`display_title`、`one_line_summary`、`project_overview[]`、`source_lists[]`、`source_category_stats[]`、`item_statistics[]`、`remaining_items[]`、`risks[]`、`patch_outputs[]`、`delivery_verifications[]` 和 `next_week_plan[]`。周报包只归档，不进入知识库沉淀候选。

常用命令：

```bash
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> weekly --prepare
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> weekly --submit-latest
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> weekly --prepare --replace-weekly-run-id <old_run_id>
```
