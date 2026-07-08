# android-daily-report-intake

> GitHub 说明页。Runtime skill 文件位于 [../../../../plugins/android-framework-ops/skills/android-daily-report-intake](../../../../plugins/android-framework-ops/skills/android-daily-report-intake)。

成员个人日报入口。它只负责生成、替换、检查和提交日报包（daily report package），并复用 `android-knowledge-intake` 的共享脚本和上传协议。

日报回答“今天干了什么”。新日报包生成：

- `reports/daily.md`
- `materials/display/report_view.json`
- `materials/evidence/work_findings.json`

`report_view.json` 是同一份日报正文的 UI 读模型（UI read model），至少包含 `report_type=daily`、`report_date`、`display_title`、`one_line_summary`、`projects[]`、`work_items[]`、`risks[]`、`outputs[]` 和 `tomorrow_focus[]`。它不是 AI 证据层，也不改变日报只归档的性质。

日报项目行必须同时有公司项目名和客户名。成员可以直接说 `TVE1086U 青鸾云，帮我生成日报并提交`；生成阶段会识别为项目 `TVE1086U`、客户 `青鸾云`。如果缺项目或客户，包会保留给成员修正，但提交会被本地校验拦住。

执行生成或提交前，Codex 应先从当前请求和可见会话上下文里找项目名 + 客户名；找不到时先在会话里提示 `缺少项目名和客户名，请补充，例如：TVE1086U 青鸾云。`，不要直接跑命令。

常用命令：

```bash
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> daily --prepare
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> daily --submit-latest
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> daily --prepare --replace-daily-run-id <old_run_id>
```
