# Incoming Package Protocol

Member-side Codex creates only `incoming` packages and sends them through the server submission channel. It does not clone, pull, directly search, or push the database repository, and it does not write final knowledge views such as reports, patches, index, or site. The server validates packages, stores them in the database repository, and commits as the server-side authority; it does not approve knowledge or materialize the knowledge repository.

Only the user's local `android-knowledge-curation-maintainer` skill and the AI knowledge loop can decide whether and how an uploaded package enters the knowledge repository.

The server does not run Codex and must not be the main AI reasoning layer. Project inference, patch problem summary, risk, verification status, search-before-change evidence, remote build evidence, and local device delivery evidence are produced by member-side Codex. Curation decisions, materialization plans, and knowledge validity are produced by the user's local curation maintainer skill, not by the member-side intake skill.

## Server Merge Anchors

Member-side packages must provide enough deterministic anchors for the server to merge without AI inference:

- package identity: `date + member_alias + run_id`
- framework identity: `case_id` and `variant_id`
- variant natural key: `case_id + platform + android_version + project + repo_paths`
- patch identity: patch file content `sha1`
- optional report link: `related_report_run_ids`
- pre-change knowledge use evidence: search queries, matched object ids, decision (`reuse`, `adapt`, `reference_only`, `not_applicable`, `not_found`, or `unknown`), match/mismatch points, reason, and outcome
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

Patch upload is package-status based:

```text
validated
  Clear scope, clean diff, build pass, and device or accepted equivalent verification pass.

candidate
  Clear implementation evidence, but validation or acceptance evidence is incomplete.

draft
  Partial or WIP implementation evidence.

failed
  Failed implementation or verification retained as negative evidence.

blocked
  Blocked work retained with cause and checked paths.
```

Only sensitive material, mixed unrelated diffs, unclear task boundaries, or high-risk misleading reuse hints should stop patch upload. Even then, daily or weekly trace should record what happened and why it was blocked.

## Daily Or Weekly Trace

Required shape:

```text
manifest.json
reports/daily.md or reports/weekly.md
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
    "evidence": [
      "materials/evidence/source.json",
      "materials/evidence/codex_sessions.json",
      "materials/evidence/work_findings.json"
    ]
  }
}
```

Report traces must not carry `case_id` or `variant_id`. They preserve context and evidence only.

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
materials/evidence/source.json
materials/evidence/patch_diff_facts.json
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
  "files": {
    "case": "materials/case.json",
    "variant": "materials/variant.json",
    "patches": ["patches/example.patch"],
    "evidence": [
      "materials/evidence/source.json",
      "materials/evidence/patch_diff_facts.json",
      "materials/evidence/project_inference.json",
      "materials/evidence/patch_problem_summary.json",
      "materials/evidence/risk_surface.json",
      "materials/evidence/verification_result.json",
      "materials/evidence/search_before_change.json"
    ]
  }
}
```

`package_status` must match `materials/variant.json` `package_status`.

`validated` requires `verification_result.payload.result = PASS`.

`candidate`, `draft`, `failed`, and `blocked` are uploaded as curation input materials only. They must not be presented as knowledge entries or reuse-ready validated solutions by member-side tooling.

`materials/evidence/search_before_change.json` records member-side knowledge use before or during the change. It can come from an explicit patch capture package, or from same-day `android-knowledge-search` usage records:

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
explicit incoming project containing a TVE/TVA/TVI model
capture package manifest or patch item project containing a TVE/TVA/TVI model
source_root, repo_path, git branch, git remote, local mount path, or WSL source-access registry
patch/feature README/diff/summary text
explicit related daily or weekly report context
```

Current automatic project recognition scope:

```text
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
