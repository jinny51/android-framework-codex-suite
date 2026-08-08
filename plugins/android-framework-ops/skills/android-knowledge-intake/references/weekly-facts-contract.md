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
  "schema": "akbs-weekly-project-facts-v2",
  "week_range": "20260601-20260607",
  "projects": [
    {
      "project": "TVE1086U",
      "customer": "青鸾云",
      "project_role": "主责",
      "requirement_date": "2026-05-18",
      "requirement_source": "CR",
      "requirement_structure": {"demand": 7, "migration": 8, "bug": 15},
      "completed_this_week": {"demand": 3, "migration": 5},
      "remaining": {"demand": 4, "migration": 3},
      "completed_items": ["完成系统接口联调", "移植状态栏策略补丁"],
      "remaining_items": ["完成客户验收"],
      "key_points": ["攻克状态同步时序问题"],
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
- `customer` is the required direct customer. Optional `downstream_customer`
  means the direct customer's customer.
- Each canonical `project` appears exactly once in `projects[]`. App, feature,
  and workstream names belong in `completed_items[]`, `remaining_items[]`, or
  `next_week_plan[]`; do not split one project into work-item-specific rows.
  Identity validation is based on canonical fields and confirmed source
  context, not on an enumerated list of module names.
- `project_role` is required and must be `主责` or `协作`.
- `requirement_date` is required and uses `YYYY-MM-DD`.
- `requirement_source` is required and must be one of `CR`, `TL`, `PM`, `TE`,
  or `BSP`. Do not infer it from daily-report wording.
- `completed_this_week` and `remaining` are required for every member.
  `requirement_structure` is required for `主责`; `协作` may omit it.
- Count objects use only `demand`, `migration`, `bug`, and optional `bsp`.
  Display labels are `需求`, `移植`, `Bug`, and `BSP`.
- `需求` means a customer requirement the team has not implemented before;
  `移植` means reusing or porting a requirement already implemented before;
  `Bug` means defect work.
- `BSP` is allowed only in project total and current remaining. It must never
  appear as a positive completion count. Work completed by the Android team is
  `需求`, `移植`, or `Bug`, not `BSP`.
- A positive count line must contain at least one positive `demand`,
  `migration`, or `bug`; `BSP` cannot be the only business category.
- Zero categories may be omitted. The generated line total is always the sum
  of its categories.
- Old `custom` or `定制` counts are invalid. They cannot be split into
  `需求` and `移植` automatically; the member must confirm the split.
- `key_points` records external project news, scope changes, or a key
  difficulty overcome this week. Use `["无"]` when there is none.
- When completed or remaining count is positive, provide the corresponding
  item list. When remaining is positive, provide `next_week_plan`.
- When there is no next-week action, use `next_week_plan: []`. Do not use `无`,
  `暂无`, or another placeholder; the Markdown plan section omits that project.
- Markdown and `report_view.json` are regenerated from this same object. Do not
  repair only one representation.

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
