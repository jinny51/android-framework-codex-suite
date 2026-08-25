# Daily Work Facts Contract

Use this contract only when authorized development evidence cannot resolve a
daily work scope, when the inferred scope needs correction, or when the member
explicitly overrides it. Normal high-confidence Patch/App/GMS/Doc/Other inference does not
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
      "work_type": "Doc",
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
  ],
  "standalone_work": [
    {
      "work_type": "Other",
      "work_name": "团队共用 GMS ATS 环境搭建",
      "work_items": [
        {
          "name": "完成双 Worker 验证",
          "did": ["完成 CTS 多机协同验证"],
          "how": ["运行测试并核对 Worker 状态"],
          "result": "基础链路通过，分片联调中",
          "status": "处理中"
        }
      ],
      "tomorrow_focus": ["继续跨 Worker 分片联调"]
    }
  ]
}
```

Rules:

- `report_date` must equal the generated daily date.
- `projects[]`, `documents[]`, and `standalone_work[]` are arrays; at least one
  must be non-empty.
- In `projects[]`, `project` and direct `customer` are required. Optional
  `downstream_customer` means the direct customer's customer.
- Project `work_type` is `Patch`, `App`, `GMS`, `Doc`, or `Other`. The five visible categories
  are `Patch`, `App`, `GMS`, `Doc`, and `Other`.
  Explicit facts override automatic inference. Never infer from vague work-item
  wording alone.
- `App` requires `app_name`; other project types must not provide it.
- In `documents[]`, `work_type` is only `Doc` and a concrete `document_name` is
  required. In `standalone_work[]`, `work_type` is only `Other` and a concrete
  `work_name` is required. Neither array carries project/customer/App fields.
  GMS is always project-bound. Historical `Document` normalizes to `Doc`.
  Do not use “文档” as a fake company project code.
- Scope identity is project/customer + work type; App additionally includes its
  name. The same project may contain one Patch, multiple differently named
  Apps, and one scope for each of GMS, Doc, and Other.
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
