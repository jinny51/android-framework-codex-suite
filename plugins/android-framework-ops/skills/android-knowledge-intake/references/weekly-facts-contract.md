# Weekly Project Facts Contract

Use this contract only when effective AKBS daily reports and the previous weekly
ledger cannot prove every required project fact. Ask the member only for fields
listed by `weekly_fact_sources.missing_fields`.

Write the completed JSON under:

```text
$CODEX_HOME/artifacts/android-knowledge-intake/weekly-facts/<week-range>.json
```

Do not write runtime facts into the plugin, skill, or plugin-cache directory.

```json
{
  "schema": "akbs-weekly-project-facts-v1",
  "week_range": "20260601-20260607",
  "projects": [
    {
      "project": "TVE1086U",
      "customer": "青鸾云",
      "week_summary": "本周完成系统接口联调和设备验证。",
      "received_date": "2026-05-18",
      "source": "客户需求文档",
      "requirement_type": "混合",
      "requirement_structure": {"custom": 8, "bug": 8, "bsp": 2},
      "completed_this_week": {"custom": 4, "bug": 1},
      "remaining": {"custom": 3, "bug": 0, "bsp": 2},
      "expected_finish": "预计下周完成整体收敛",
      "completed_items": ["完成系统接口联调", "修复状态同步问题"],
      "remaining_items": ["完成客户验收"],
      "risks": [],
      "dependencies": ["等待客户提供验收环境"],
      "next_week_plan": ["完成客户验收并关闭剩余问题"]
    }
  ]
}
```

Rules:

- `week_range` must equal the generated weekly period.
- `project` must be a recognized TVD/TVE/TVA/TVI company project.
- `source` is one of `客户需求文档`, `TL指派`, `Buglist`, `测试反馈`, or
  `BSP配合`.
- `requirement_type` is one of `纯定制`, `Buglist`, or `混合`.
- `requirement_structure` and `remaining` contain non-negative `custom`, `bug`,
  and `bsp` integers. `completed_this_week` contains `custom` and `bug`; a
  legacy `bsp` key is accepted only when its value is `0`.
- `移植`, `适配`, and patch reuse describe implementation methods. Historical
  `移植`/`适配` count keys are normalized to `custom`, never to `bsp`.
- `bsp` is only for explicitly BSP-owned or BSP-dependent outstanding work.
  Android customization-team completions must be counted as `custom` or `bug`.
- `week_summary` describes this week's result; it must not repeat the next-week
  plan.
- Markdown and `report_view.json` are regenerated from this same object. Do not
  manually repair one while leaving the other unchanged.

Generate with:

```bash
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" \
  --profile <member_alias> weekly \
  --session-consent --session-field work_summary \
  --weekly-facts "$CODEX_HOME/artifacts/android-knowledge-intake/weekly-facts/<week-range>.json" \
  --prepare
```

If an earlier local package for the same week already exists, use the explicit
replacement option named by the duplicate guard.
