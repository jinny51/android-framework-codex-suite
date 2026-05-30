# Incoming Work Package Protocol

Member-side automation and maintainer patch contribution must submit only `incoming` work packages. The knowledge repository hook validates accepted packages and generates final `daily/`, `weekly/`, `patches/by-id/`, `knowledge-events/`, `index/`, and `site/`.

The path layout is stable:

```text
incoming/YYYYMMDD/member_alias/run_id/
```

Rules:

- `YYYYMMDD` is the package date.
- `member_alias` must exist in the repository `config/team.yaml`.
- `run_id` must start with `YYYYMMDD-HHMMSS`.
- `schema_version` is an internal compatibility field. Do not expose it as a user-facing workflow name, and do not use it to name an incoming generation.

## Deprecated Local Format

The old report-package format with top-level `daily.md`, `weekly.md`, `type=daily`, or `type=weekly` is no longer accepted by the knowledge repository. Current member automation must generate the package shape below.

## Current Incoming Packages

Current incoming treats packages as Codex-generated knowledge and evidence packages, not manual report uploads.

Channels:

- `light`: daily/weekly/session traces. Allowed quality: `imported`, `trace`, `candidate`.
- `strict`: Framework changes, patch contributions, reuse decisions. Allowed quality: `imported`, `candidate`, `validated`, `released`, `buggy`.

Quality:

- `imported`: historical or reconstructed material without modern validation evidence.
- `trace`: only proves work happened.
- `candidate`: useful assets exist, but verification is incomplete or limited.
- `validated`: suitable as a first-class reuse candidate.
- `released`: validated and known to have shipped or entered a release baseline.
- `buggy`: known-bad or failed attempt retained as learning evidence.

Runtime behavior changes in the modified module require device verification for `validated`. Equivalent verification is allowed for resource-only, build-only, packaging-only, static config, or documentation changes when the package records method, reason, coverage, and remaining risk.

### Current Daily Trace

```text
manifest.json
reports/
└── daily.md
evidence/
├── source.json
└── codex-sessions.json
```

Minimal manifest:

```json
{
  "schema_version": "2.0",
  "package_kind": "daily_trace",
  "channel": "light",
  "quality": "trace",
  "member": "member_alias",
  "member_name": "成员姓名",
  "date": "2026-05-26",
  "run_id": "20260526-210000",
  "project": "全局项目",
  "summary": "今日工作摘要",
  "source": {
    "tool": "android-knowledge-intake"
  },
  "reports": [
    {
      "id": "report-daily",
      "kind": "daily",
      "path": "reports/daily.md",
      "title": "20260526_成员_日报"
    }
  ],
  "patches": [],
  "evidence": [
    {
      "id": "source",
      "kind": "source",
      "path": "evidence/source.json",
      "result": "INFO",
      "summary": "package source metadata"
    },
    {
      "id": "codex-sessions",
      "kind": "codex_sessions",
      "path": "evidence/codex-sessions.json",
      "result": "INFO",
      "summary": "Codex session trace evidence"
    }
  ],
  "relations": [],
  "quality_claims": {}
}
```

### Current Strict Patch Contribution

```text
manifest.json
patches/
├── <patch-name>.patch
└── <patch-name>.readme.md
evidence/
├── source.json
├── patch-contribution.json
├── patch-diff-facts.json
├── patch-problem-inference.json
├── risk-surface.json
├── capture-verification-result.json
└── capture-search-before-change.json
```

Patch item:

```json
{
  "id": "patch-id",
  "path": "patches/xxx.patch",
  "readme": "patches/xxx.readme.md",
  "status": "candidate",
  "reusable": false,
  "repo_path": "frameworks/base",
  "artifact": "services.jar",
  "facts": {
    "modified_files": [],
    "symbols": [],
    "system_properties": [],
    "settings_keys": [],
    "resource_keys": [],
    "framework_log_keys": []
  }
}
```

## Patch Analysis Evidence

Patch files are evidence, not opaque attachments. Member-side intake should do the primary patch understanding while it still has Codex session context. Repository normalization may do deterministic patch parsing to fill missing direct facts and improve search, but it should not be treated as the main AI reasoning step.

Direct facts belong in `patch_diff_facts`:

```text
modified_files
symbols
system_properties
settings_keys
resource_keys
framework_log_keys
modules
```

Problem explanation, solution explanation, keywords, applicability, and risks belong in `patch_problem_inference` or `risk_surface`. These are reasoning outputs and must include:

```json
{
  "confidence": "medium",
  "basis": ["补丁修改文件: frameworks/base/..."],
  "limits": ["补丁内容不能单独证明原始需求文字"]
}
```

Rules:

- Patch explanation fields improve search and reuse judgment.
- Patch explanation fields must not be presented as verified facts.
- Patch explanation alone cannot upgrade `quality` to `validated`.
- Historical imports may use patch analysis to recover missing title, summary, module, files, keywords, likely problem, likely solution, and risk surface.
- New incoming packages may use patch analysis as a consistency check against the human readme.

When importing an `android-framework-patch-capture` output directory with `--patch-package`, intake preserves its evidence entries under `evidence/capture-*.json`. A strict patch contribution may claim `quality=validated` only when it carries PASS device verification or accepted equivalent verification evidence. Strict patch contributions without verification evidence should stay `candidate`, even if the human-facing patch status is `validated`.
