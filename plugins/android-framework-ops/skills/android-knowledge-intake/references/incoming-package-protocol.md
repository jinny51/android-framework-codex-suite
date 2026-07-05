# Incoming Package Protocol

Member-side Codex creates only `incoming` packages and sends them through the server submission channel. It does not clone, pull, directly search, or push the database repository, and it does not write final knowledge views such as reports, patches, index, or site. The normal server submission channel is the AKBS HTTP API. It receives packages into the server-side AKBS facts database and exposes them to the curation flow. Legacy SSH/intake-branch submission is rollback compatibility only, not the normal member path.

Only the user's local `akbs-curation-maintainer` skill and the AI knowledge loop can decide whether and how an uploaded package enters the knowledge repository.

The server does not run Codex and must not be the main AI reasoning layer. Project inference, patch problem summary, risk, verification status, search-before-change evidence, remote build evidence, and local device delivery evidence are produced by member-side Codex. Curation decisions, materialization plans, and knowledge validity are produced by the user's local curation maintainer skill, not by the member-side intake skill.

## Server Merge Anchors

Member-side packages must provide enough deterministic anchors for the server to merge without AI inference:

- package identity: `date + member_alias + run_id`
- framework identity: `case_id` and `variant_id`
- variant natural key: `case_id + platform + android_version + project + repo_paths`
- patch identity: patch file content `sha1`
- optional report link: `related_report_run_ids`
- pre-change knowledge use evidence when it happened: search queries, matched object ids, decision (`reuse`, `adapt`, `reference_only`, `not_applicable`, `not_found`, or `unknown`), match/mismatch points, reason, and outcome
- cross-machine verification evidence: remote build host/source root/profile/artifact plus local transfer, adb serial, device push/install/restart, and verification result

The server may merge two framework_change packages into the same variant when the natural key matches, even when the incoming `variant_id` differs. The server must not let a later `failed` or `blocked` package overwrite stronger existing evidence; that later package is retained as evidence.

## Path

```text
incoming/YYYYMMDD/member_alias/run_id/
```

Rules:

- path date uses `YYYYMMDD`
- manifest date uses `YYYY-MM-DD`
- `member_alias` in path must match manifest
- `run_id` must start with `YYYYMMDD-HHMMSS`
- package identity is `date + member_alias + run_id`
- `schema_version` is internal and must not be used as a workflow name

## Common Manifest Fields

```json
{
  "schema": "knowledge-incoming-package",
  "schema_version": "1",
  "package_kind": "framework_change",
  "member_alias": "lincong",
  "member_name": "林聪",
  "date": "2026-06-01",
  "run_id": "20260601-213000-framework-change",
  "tool": "android-knowledge-intake",
  "summary": "..."
}
```

Allowed `package_kind`:

```text
daily_trace
weekly_trace
framework_change
```

## Default Automation Policy

The default policy is:

```text
preserve automatically first
rank by package status later
```

Daily and weekly incoming automation should run even when no patch is complete. It must preserve session facts, git activity, discovered patch files, build or verification signals, WIP state, failed paths, blocked paths, and missing evidence.

Patch package status is evidence-quality based. Member-side upload preparation and admin-side local promotion are stricter than local preservation: ordinary patch packages and evidence supplements must be `validated`; other statuses stay local or in daily/weekly context unless a separate archive-only path is explicitly designed.

```text
validated
  Clear scope, clean diff, build pass, and device or accepted equivalent verification pass.
  Project, platform, and Android version are traceable and non-conflicting.

candidate
  Clear implementation evidence, but validation or acceptance evidence is incomplete.
  Also used when project, platform, or Android version metadata is missing, unknown, or conflicting.

draft
  Partial or WIP implementation evidence.

failed
  Failed implementation or verification retained as negative evidence.

blocked
  Blocked work retained with cause and checked paths.
```

Non-`validated` patch packages stop ordinary upload. Daily or weekly trace should still record what happened, why it is incomplete, failed, or blocked, and what evidence remains missing.

Patch package project inference may use a same-member same-day daily package only when no explicit `related_report_run_ids` were provided and the daily context exposes exactly one TVD/TVE/TVA/TVI project candidate. This is a member-side generation convenience, not a server-side guess. Ambiguous daily context, multiple projects, or missing daily packages must keep `project=unknown` and rely on a later evidence supplement package.

## Daily Or Weekly Trace

Required shape:

```text
manifest.json
reports/daily.md or reports/weekly.md
materials/display/report_view.json
materials/evidence/source.json
materials/evidence/codex_sessions.json
materials/evidence/work_findings.json
```

Manifest excerpt:

```json
{
  "package_kind": "daily_trace",
  "report_type": "daily",
  "report_path": "reports/daily.md",
  "files": {
    "display": [
      "materials/display/report_view.json"
    ],
    "evidence": [
      "materials/evidence/source.json",
      "materials/evidence/codex_sessions.json",
      "materials/evidence/work_findings.json"
    ]
  }
}
```

Report traces must not carry `case_id` or `variant_id`. `reports/daily.md` and `reports/weekly.md` are the primary human-readable products. `materials/display/report_view.json` is a UI read model for cards, lists, and detail panes; it is generated from the same report inputs and must not contain a separate fact set.

`report_view` is required:

```json
{
  "kind": "report_view",
  "payload": {
    "report_type": "daily",
    "display_title": "20260701_成员_日报",
    "report_date": "2026-07-01",
    "week_range": "",
    "member_alias": "member01",
    "member_name": "成员",
    "overview": "今天处理了...",
    "one_line_summary": "今天处理了...",
    "ui_card": {
      "title": "20260701_成员_日报",
      "subtitle": "今天处理了...",
      "status": "正常推进"
    },
    "projects": [],
    "work_items": [],
    "tomorrow_focus": [],
    "daily_overview": [],
    "items": [],
    "risks": [],
    "outputs": [],
    "next_steps": []
  }
}
```

For `report_type=weekly`, `payload` must include `week_range`, `display_date`, `one_line_summary`, `project_overview[]`, `source_lists[]`, `source_category_stats[]`, `requirement_origin[]`, `requirement_list_type[]`, `item_statistics[]`, `completed_items[]`, `in_progress_items[]`, `remaining_items[]`, `risks[]`, `patch_outputs[]`, `delivery_verifications[]`, and `next_week_plan[]`. `display_date` is the last workday of the week range, not the upload day.

`work_findings` is required:

```json
{
  "kind": "work_findings",
  "payload": {
    "scanned_sources": ["codex_sessions", "git_activity", "patch_files", "build_or_verification_records"],
    "items": [
      {
        "title": "锁屏永不休眠策略调整",
        "kind": "possible_framework_change",
        "work_status": "candidate",
        "basis": ["会话提到修复锁屏永不休眠", "frameworks/base 存在 diff"],
        "missing_evidence": ["缺少设备或等价验证"],
        "recommended_action": "补验证后可升级为 framework_change"
      }
    ],
    "blocked_or_failed": []
  }
}
```

## Framework Change

Required shape:

```text
manifest.json
materials/case.json
materials/variant.json
materials/display/patch_view.json
materials/evidence/source.json
materials/evidence/patch_diff_facts.json
materials/evidence/patch_ai_facts.json
materials/evidence/project_inference.json
materials/evidence/patch_problem_summary.json
materials/evidence/risk_surface.json
materials/evidence/verification_result.json
materials/evidence/search_before_change.json
patches/*.patch
```

Manifest excerpt:

```json
{
  "package_kind": "framework_change",
  "case_id": "case-...",
  "variant_id": "variant-...",
  "package_status": "candidate",
  "platform": "mtk",
  "android_version": "15",
  "project": "TVE8402M",
  "related_report_run_ids": ["20260601-210000-daily"],
  "supplement_for_package_key": "20260612/lincong/20260612-172836-patch",
  "supplement_reason": "补充项目（project）证据",
  "files": {
    "case": "materials/case.json",
    "variant": "materials/variant.json",
    "display": [
      "materials/display/patch_view.json"
    ],
    "patches": ["patches/example.patch"],
    "evidence": [
      "materials/evidence/source.json",
      "materials/evidence/patch_diff_facts.json",
      "materials/evidence/patch_ai_facts.json",
      "materials/evidence/project_inference.json",
      "materials/evidence/patch_problem_summary.json",
      "materials/evidence/risk_surface.json",
      "materials/evidence/verification_result.json",
      "materials/evidence/search_before_change.json",
      "materials/evidence/evidence_supplement.json"
    ]
  }
}
```

`patch_view` is required for human-facing member/admin display. It is not an AI evidence layer:

```json
{
  "kind": "patch_view",
  "payload": {
    "material_kind_label": "原始包",
    "display_title": "导航策略适配",
    "problem_summary": "要解决什么问题",
    "solution_summary": "补丁如何解决",
    "result_summary": "验证或处理结果",
    "project": "TVE8402M",
    "platform": "mtk",
    "android_version": "15",
    "member_alias": "member01",
    "member_name": "成员",
    "supplement_for_package_key": "",
    "ui_card": {
      "title": "导航策略适配",
      "subtitle": "TVE8402M / mtk / Android 15",
      "summary": "要解决什么问题",
      "risk_or_gap": "暂无明确遗留风险"
    },
    "detail_sections": []
  }
}
```

`patch_ai_facts` is required for admin-side validation, curation review, search indexing, and merge judgement. It must not be the UI primary display source:

```json
{
  "kind": "patch_ai_facts",
  "case_id": "case-...",
  "variant_id": "variant-...",
  "payload": {
    "module": "frameworks/base/services/core",
    "feature_domain": "导航策略",
    "patch_behavior_goal": "用户可见或系统行为目标",
    "code_anchors": {
      "files": [],
      "symbols": [],
      "resource_keys": [],
      "settings_keys": [],
      "system_properties": [],
      "framework_log_keys": []
    },
    "patch_assets": [],
    "verification_targets": {},
    "search_usage": {},
    "search_match_class": {
      "decision": "adapt",
      "merge_hint": "reference_only",
      "explanation": "adapt 只能作为参考证据，不能直接触发合并。"
    },
    "merge_gate_inputs": {},
    "protocol_version": "patch-human-ai-evidence-v1",
    "plugin_version": "1.0.72"
  }
}
```

`package_status` must match `materials/variant.json` `package_status`.

`validated` requires `verification_result.payload.result = PASS`.

## Source Version Compatibility

Generation-time plugin freshness and historical package compatibility are separate rules.

Member-side generation or upload must stop when `materials/evidence/source.json` records `plugin_version_check.blocking=true` or `plugin_version_check.status=SESSION_CACHE_STALE`. A stale Codex session cannot be treated as a valid package generator.

Admin-side processing of older incoming packages must not require `plugin_version` or `skill_version` to equal the latest plugin version at processing time. It should call the shared deterministic rules layer:

```python
source_version_compatibility_matrix()
source_version_errors(source_payload, required_capabilities=[...])
```

Current capability minima:

```text
source_version_evidence = 1.0.60
report_view_v1 = 1.0.61
patch_view_v1 = 1.0.62
patch_ai_facts_v1 = 1.0.62
split_report_skills = 1.0.63
report_view_v2 = 1.0.63
lightweight_supplement_v1 = 1.0.65
```

The required capabilities come from package contents, not from the current plugin release. For example, a package that only needs source version evidence can remain compatible at `1.0.60`; a patch package with `patch_view.json` and `patch_ai_facts.json` requires `1.0.62`; a package relying on split report skills or report view v2 requires `1.0.63`; a field correction supplement requires `1.0.65`.

Codex normal development should carry pre-change knowledge search evidence in `materials/evidence/search_before_change.json`. If no reusable knowledge was found, record the explicit search result as `not_found` instead of omitting the evidence. When pre-change search did not really happen, `validated` still means the verification evidence passed; preserve `payload.searched = false`, warn locally, and let admin-side curation perform post-change overlap check without awarding search-loop reuse score. Manual, external, historical, mixed, or unknown implementation origin must not fabricate pre-change search and can still carry verification and patch facts for later admin-side curation.

`candidate`, `draft`, `failed`, and `blocked` are local/report-context states by default. They must not be uploaded as ordinary patch packages, and they must not be presented as knowledge entries or reuse-ready validated solutions by member-side tooling.

If a previous `framework_change` package is marked 需补证据（needs_evidence）, the supplement remains a normal `framework_change` package. Set `supplement_for_package_key` to the original incoming package key and include `materials/evidence/evidence_supplement.json`:

```json
{
  "kind": "evidence_supplement",
  "case_id": "case-...",
  "variant_id": "variant-...",
  "payload": {
    "target_package_key": "20260612/lincong/20260612-172836-patch",
    "reason": "补充项目（project）证据",
    "project": "TVE1067M",
    "platform": "mtk",
    "android_version": "16",
    "package_status": "validated"
  }
}
```

This association only says the new patch package supplements evidence for an earlier package. It is not a curation decision and does not create another allowed `package_kind`.

Supplement packages use `supplement_mode` to distinguish lightweight field/display correction from asset recapture:

```text
field_correction
  Corrects project, platform, Android version, material name, feature name, patch_view/report_view display fields, or equivalent structured display metadata.
  Must include corrected_fields, correction_reason, evidence_supplement, and field_correction evidence.
  Must not include patch diff, verification_result, search_before_change, patch_ai_facts, build/deploy evidence, or patch assets.

asset_correction
  Corrects patch diff, polluted patch assets, local-check, verification, or patch_ai_facts.
  Must come from a fresh android-framework-patch-capture package for the same feature.
```

The member-side local check treats supplement packages as evidence closure attempts. If `supplement_reason` says the package补项目（project）, the new package must carry a traceable TVD/TVE/TVA/TVI project in `manifest.project` and `project_inference` must confirm `recognized=true`, `company_rule_match=true`, `basis`, and `checked_sources`. If it补平台（platform） or Android 版本（Android version）, the new package cannot keep the requested field as `unknown`; when capture evidence cannot prove those fields, `android_knowledge_intake.py patch` may use explicit `--platform mtk|rk|unisoc|unknown` and `--android-version <number>` to write the corrected boundary into `manifest.json`, `materials/variant.json`, and `materials/evidence/evidence_supplement.json`. If it补验证（verification）, `verification_result` must be `PASS`. If it补补丁资产修正（patch asset correction）, patch filenames must use a legal project（project）prefix or controlled platform prefixes such as `TVE1067M1-`, `mtk15-`, `rk14-`, or `unisoc16-`; other uncontrolled prefixes remain invalid because they cannot prove the project/platform boundary. If the old gap is pre-change knowledge search but the search did not happen before development, the member must not fabricate it; record the implementation origin and let admin-side curation perform post-change overlap check.

`materials/evidence/search_before_change.json` records member-side knowledge use before or during the change. It can come from an explicit patch capture package, or from same-day `android-knowledge-search` usage records only when those records match the current patch feature anchors. Same member and same day are not enough:

```json
{
  "kind": "search_before_change",
  "payload": {
    "result": "INFO",
    "method": "knowledge_search",
    "searched": true,
    "queries": ["电源键 rk3576"],
    "decision": "adapt",
    "reuse_decision": "adapt",
    "targets": ["case-power-key"],
    "reason": "同类策略可参考，当前项目需适配"
  }
}
```

This is development evidence only. It must not be treated as a curation decision.

`patch_diff_facts` should include the patch content hash. For a single patch, set top-level `content_sha1`; for multiple patches, fill `patches[]`:

```json
{
  "kind": "patch_diff_facts",
  "payload": {
    "content_sha1": "40-hex-sha1-for-single-patch",
    "patches": [
      {
        "path": "patches/mtk15-frameworks-base@feature.patch",
        "content_sha1": "40-hex-sha1"
      }
    ],
    "modified_files": ["frameworks/base/services/core/java/..."]
  }
}
```

## Project Inference

Project must come from traceable evidence:

```text
explicit incoming project containing a TVD/TVE/TVA/TVI model
capture package manifest or patch item project containing a TVD/TVE/TVA/TVI model
source_root, repo_path, git branch, git remote, local mount path, or WSL source-access registry
patch/feature README/diff/summary text
explicit related daily or weekly report context
```

Daily reports are not just prose. When a daily package context contains exactly one traceable TVD/TVE/TVA/TVI project model, `manifest.project` and `materials/evidence/project_inference.json` must carry it so the database repository can show accurate member work context and later curation can use it as evidence. If the daily context contains multiple projects, keep the single `project` field unknown and preserve the checked candidates and limits in project inference evidence.

If the daily context contains multiple traceable candidates that share one canonical project, such as `TVE1067M1` and `TVE1067M1_H031`, write the canonical project `TVE1067M1` to `manifest.project` and keep the full raw candidates in `project_inference`. Do not truncate it to `TVE1067M`, because `TVE1067M` and `TVE1067M1` are distinct projects.

The structured project field stores only the company model that matches the TVD/TVE/TVA/TVI naming rule: `TV[D/E/A/I] + two LCD-size digits + two sequence characters + platform M/R/U + optional digit`. Any text outside that model is evidence text, not part of `manifest.project` or `materials/variant.json project`: branch suffixes, customer suffixes, build branches, business labels, module labels, Chinese descriptions, and other non-standard trailing text must remain in `project_inference.raw_inputs` or `basis`. Examples: `TVE1067M1_H031` -> `TVE1067M1`, `TVE1086U_MAIN_HANGYAN` -> `TVE1086U`, `TVE1091U福建移动高清` -> `TVE1091U`. Confirmed historical alias `TVE8402` must normalize to `TVE8402M`; new packages must not write `TVE8402` as the structured project. This is conservative normalization for one project model, not permission to merge unrelated TVD/TVE/TVA/TVI models.

Patch packages should not depend on the UI or server to guess the project. Prefer explicit project evidence from the capture package or `--project`; otherwise attach the related daily run id so the patch can inherit that daily context. If no traceable project exists, the package can still be preserved, but curation must treat the missing project as an evidence gap and must not promote it to high-confidence reusable knowledge.

Current automatic project recognition scope:

```text
TVD
TVE
TVA
TVI
```

If the project cannot be identified from traceable evidence, use:

```json
{
  "project": "unknown"
}
```

and explain checked sources and limits in `project_inference`.

Generic labels such as `android16`, `Camera2`, or `mtk android16 Camera2` are not company project names. They must remain checked raw inputs in `project_inference`, but they must not be written to `manifest.project` or `materials/variant.json project`.
