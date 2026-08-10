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
  "schema": "akbs-weekly-project-facts-v3",
  "week_range": "20260601-20260607",
  "projects": [
    {
      "project": "TVE1086U",
      "customer": "青鸾云",
      "work_type": "Patch",
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
    },
    {
      "project": "TVI2343R",
      "customer": "海信",
      "work_type": "App",
      "app_name": "蓝牙播放器",
      "project_role": "主责",
      "requirement_date": "2026-06-25",
      "requirement_source": "CR",
      "work_total": 10,
      "completed_this_week": 3,
      "remaining": 7,
      "completed_items": ["完成串口协议接入"],
      "remaining_items": ["完成整机链路验证"],
      "key_points": ["完成原生服务和产品模块接入"],
      "risks": [],
      "dependencies": ["等待客户提供正式 API"],
      "next_week_plan": ["完成整机链路验证"]
    }
  ]
}
```

Rules:

- `week_range` must equal the generated weekly period.
- `project` must be a recognized TVD/TVE/TVA/TVI company project.
- `customer` is the required direct customer. Optional `downstream_customer`
  means the direct customer's customer.
- `work_type` is required and must be exactly `Patch` or `App`; do not infer it
  from work-item wording. `App` requires `app_name`; `Patch` must not provide it.
- Each reporting scope appears exactly once. Patch identity is `project + direct
  customer + Patch`; App identity adds `app_name`. The same project may contain
  one Patch row and multiple differently named App rows. Feature names remain
  work items and do not create additional rows.
- `project_role` is required and must be `主责` or `协作`.
- `requirement_date` is required and uses `YYYY-MM-DD`.
- `requirement_source` is required and must be one of `CR`, `TL`, `PM`, `TE`,
  or `BSP`. Do not infer it from daily-report wording.
- `completed_this_week` and `remaining` are required for every member. For a
  Patch row they are category objects. For an App row they are non-negative
  integers without Patch categories.
- A Patch main requires `requirement_structure`; an App main requires integer
  `work_total`. Collaborators may omit the corresponding total.
- Patch count objects use only `demand`, `migration`, `bug`, and optional `bsp`.
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
- App counts must satisfy `completed_this_week + remaining <= work_total` when
  the total is present. Patch and App quantities are never added together.
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
