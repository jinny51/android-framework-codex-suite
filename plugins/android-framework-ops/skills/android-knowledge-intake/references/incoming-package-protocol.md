# Incoming Package Protocol

Member-side Codex submits only `incoming` packages. It does not write final knowledge views such as reports, patches, index, or site. The server validates the package and materializes case, variant, patch, report, evidence, event, search index, and admin site.

The server does not run Codex and must not be the main AI reasoning layer. Project inference, patch problem inference, risk, verification status, and search-before-change evidence are produced by member-side Codex.

## Server Merge Anchors

Member-side packages must provide enough deterministic anchors for the server to merge without AI inference:

- package identity: `date + member_alias + run_id`
- framework identity: `case_id` and `variant_id`
- variant natural key: `case_id + platform + android_version + project + repo_paths`
- patch identity: patch file content `sha1`
- optional report link: `related_report_run_ids`

The server may merge two framework_change packages into the same variant when the natural key matches, even when the incoming `variant_id` differs. The server must not downgrade a stronger mature variant just because a later package is `failed` or `blocked`; that later package is retained as evidence.

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
rank by maturity later
```

Daily and weekly automation should run even when no patch is complete. It must preserve session facts, git activity, discovered patch files, build or verification signals, WIP state, failed paths, blocked paths, and missing evidence.

Patch upload is maturity-based:

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

Only sensitive material, mixed unrelated diffs, unclear task boundaries, or high-risk misleading reuse should stop patch upload. Even then, daily or weekly trace should record what happened and why it was blocked.

## Daily Or Weekly Trace

Required shape:

```text
manifest.json
reports/daily.md or reports/weekly.md
knowledge/evidence/source.json
knowledge/evidence/work_findings.json
```

Manifest excerpt:

```json
{
  "package_kind": "daily_trace",
  "report_type": "daily",
  "report_path": "reports/daily.md",
  "files": {
    "evidence": [
      "knowledge/evidence/source.json",
      "knowledge/evidence/codex_sessions.json",
      "knowledge/evidence/work_findings.json"
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
        "maturity": "candidate",
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
knowledge/case.json
knowledge/variant.json
knowledge/evidence/source.json
knowledge/evidence/patch_diff_facts.json
knowledge/evidence/project_inference.json
knowledge/evidence/patch_problem_inference.json
knowledge/evidence/risk_surface.json
knowledge/evidence/verification_result.json
knowledge/evidence/search_before_change.json
patches/*.patch
```

Manifest excerpt:

```json
{
  "package_kind": "framework_change",
  "case_id": "case-...",
  "variant_id": "variant-...",
  "maturity": "candidate",
  "platform": "mtk",
  "android_version": "15",
  "project": "TVE8402M",
  "related_report_run_ids": ["20260601-210000-daily"],
  "files": {
    "case": "knowledge/case.json",
    "variant": "knowledge/variant.json",
    "patches": ["patches/example.patch"],
    "evidence": [
      "knowledge/evidence/source.json",
      "knowledge/evidence/patch_diff_facts.json",
      "knowledge/evidence/project_inference.json",
      "knowledge/evidence/patch_problem_inference.json",
      "knowledge/evidence/risk_surface.json",
      "knowledge/evidence/verification_result.json",
      "knowledge/evidence/search_before_change.json"
    ]
  }
}
```

`maturity` must match `knowledge/variant.json` `status`.

`validated` requires `verification_result.payload.result = PASS`.

`candidate`, `draft`, `failed`, and `blocked` may enter the knowledge base, but must not be presented as directly reusable validated solutions.

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
explicit incoming project
patch readme or handover notes
daily or weekly context
attachment or directory name
patch filename
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
