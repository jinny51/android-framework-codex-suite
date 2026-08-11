# Daily Work Facts Contract

Use this contract only when authorized development evidence cannot resolve a
daily work scope, when the inferred scope needs correction, or when the member
explicitly overrides it. Normal high-confidence Patch/App/Document inference does not
require this file. Write it under:

```text
$CODEX_HOME/artifacts/android-knowledge-intake/daily-facts/<report-date>.json
```

Do not write runtime facts into the plugin source, skill, or plugin-cache directory.

```json
{
  "schema": "akbs-daily-work-facts-v2",
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
  ],
  "documents": [
    {
      "work_type": "Document",
      "document_name": "Android Framework Orchestrator 功能介绍文档",
      "work_items": [
        {
          "name": "完成功能介绍文档",
          "did": ["整理组件职责、调用流程和使用边界"],
          "how": ["核对实现代码和现有说明后按功能模块重写"],
          "result": "文档已完成并可供评审",
          "status": "已完成"
        }
      ],
      "tomorrow_focus": []
    }
  ]
}
```

Rules:

- `report_date` must equal the generated daily date.
- `projects[]` and `documents[]` are arrays; at least one must be non-empty.
- In `projects[]`, `project` and direct `customer` are required. Optional
  `downstream_customer` means the direct customer's customer.
- `work_type` is required and must be exactly `Patch` or `App`. Patch means
  system-source customization; App means application or demo development.
  Explicit facts override automatic inference. Never infer from vague work-item
  wording alone.
- `App` requires `app_name`; `Patch` must not provide it.
- In `documents[]`, `work_type` must be `Document` and `document_name` is
  required. Do not provide project, customer, downstream customer, or App name.
  Do not use “文档” as a fake company project code.
- Scope identity is one Patch or one named App under a project/customer chain.
  The same project may contain one Patch and multiple differently named Apps.
- Document scope identity is its concrete document name. Merge repeated work on
  the same document instead of creating duplicate rows.
- When a project has only one scope, `work_items`, `today_topic`,
  `current_result`, and `tomorrow_focus` may be omitted; the generator fills
  them from the authorized session-derived daily work.
- When the same project has multiple scopes, each scope must explicitly carry
  its own `work_items[]` so work cannot be assigned to the wrong Patch or App.
- Every work item contains `name`, non-empty `did[]`, non-empty `how[]`,
  `result`, and `status`. Status is exactly `已完成`, `处理中`, `待验证`, or
  `阻塞`.
- A scope containing `处理中`, `待验证`, or `阻塞` work must have a non-empty
  `tomorrow_focus[]`. When the member says there is no next-day focus, write
  `["无"]`; do not turn that answer into an empty array or block submission.
  Explicit empty/no-focus values are normalized to `["无"]` for compatibility.
- Codex writes this JSON from the current development evidence and only asks the
  member for facts that remain ambiguous. Do not ask the member to hand-edit
  JSON, Markdown, or `report_view.json`.
- Markdown and `report_view.json` are regenerated from the normalized object.
  Editing only one representation invalidates the render binding and blocks
  submission.

Generate with:

```bash
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" \
  --profile <member_alias> daily \
  --session-consent --session-field work_summary --session-field command_summary \
  --session-field project_hint --session-field work_scope_hint \
  --daily-facts "$CODEX_HOME/artifacts/android-knowledge-intake/daily-facts/<report-date>.json" \
  --prepare
```
