# android-daily-report-intake

> GitHub 说明页。Runtime skill 文件位于 [../../../../plugins/android-framework-ops/skills/android-daily-report-intake](../../../../plugins/android-framework-ops/skills/android-daily-report-intake)。

成员个人日报入口。它只负责生成、替换、检查和提交日报包（daily report package），并复用 `android-knowledge-intake` 的共享脚本和上传协议。

日报回答“今天干了什么”。新日报包生成：

- `reports/daily.md`
- `materials/display/report_view.json`
- `materials/evidence/work_findings.json`

`report_view.json` 是同一份日报正文的 UI 读模型（UI read model），至少包含 `report_type=daily`、`report_date`、`display_title`、`one_line_summary`、`projects[]`、`work_items[]`、`risks[]`、`outputs[]` 和 `tomorrow_focus[]`。它不是 AI 证据层，也不改变日报只归档的性质。

常用命令：

```bash
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> daily --prepare
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> daily --submit-latest
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> daily --prepare --replace-daily-run-id <old_run_id>
```

