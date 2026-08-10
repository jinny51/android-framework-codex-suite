# Daily Project Facts Contract

Use this contract after reading the authorized daily work window and confirming
each work scope with the member. Write it under:

```text
$CODEX_HOME/artifacts/android-knowledge-intake/daily-facts/<report-date>.json
```

Do not write runtime facts into the plugin source, skill, or plugin-cache directory.

```json
{
  "schema": "akbs-daily-project-facts-v1",
  "report_date": "2026-08-10",
  "projects": [
    {
      "project": "TVE1086U",
      "customer": "青鸾云",
      "work_type": "Patch"
    },
    {
      "project": "TVE1086U",
      "customer": "青鸾云",
      "work_type": "App",
      "app_name": "设备管理工具"
    }
  ]
}
```

Rules:

- `report_date` must equal the generated daily date.
- `project` and direct `customer` are required. Optional
  `downstream_customer` means the direct customer's customer.
- `work_type` is required and must be exactly `Patch` or `App`. Patch means
  system-source customization; App means application or demo development.
  Never infer it from vague work-item wording.
- `App` requires `app_name`; `Patch` must not provide it.
- Scope identity is one Patch or one named App under a project/customer chain.
  The same project may contain one Patch and multiple differently named Apps.
- When a project has only one scope, `work_items`, `today_topic`,
  `current_result`, and `tomorrow_focus` may be omitted; the generator fills
  them from the authorized session-derived daily work.
- When the same project has multiple scopes, each scope must explicitly carry
  its own `work_items[]` so work cannot be assigned to the wrong Patch or App.
- Every work item contains `name`, non-empty `did[]`, non-empty `how[]`,
  `result`, and `status`. Status is exactly `已完成`, `处理中`, `待验证`, or
  `阻塞`.
- A scope containing `处理中`, `待验证`, or `阻塞` work must have a non-empty
  `tomorrow_focus[]`. A fully completed scope may use an empty array.
- Codex writes this JSON from member-confirmed facts. Do not ask the member to
  hand-edit JSON, Markdown, or `report_view.json`.
- Markdown and `report_view.json` are regenerated from the normalized object.
  Editing only one representation invalidates the render binding and blocks
  submission.

Generate with:

```bash
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" \
  --profile <member_alias> daily \
  --session-consent --session-field work_summary --session-field command_summary \
  --daily-facts "$CODEX_HOME/artifacts/android-knowledge-intake/daily-facts/<report-date>.json" \
  --prepare
```
