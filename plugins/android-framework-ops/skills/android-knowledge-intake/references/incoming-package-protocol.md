# Incoming Work Package Protocol

Member-side automation and maintainer patch contribution must submit only `incoming` work packages. Server-side scripts generate final `daily/`, `weekly/`, `patches/by-id/`, `knowledge-events/`, `index/`, and `site/`.

The path layout is stable for v1 and v2:

```text
incoming/YYYYMMDD/member_alias/run_id/
```

Rules:

- `YYYYMMDD` is the package date.
- `member_alias` must exist in the server `config/team.yaml`.
- `run_id` must start with `YYYYMMDD-HHMMSS`.
- `schema_version` decides the server behavior.

## V1 Packages

V1 is kept for compatibility.

Allowed `type` values:

- `daily`: member daily report plus optional patches.
- `weekly`: member weekly report plus optional patches.
- `patch`: maintainer patch contribution only.

Daily:

```text
manifest.json
daily.md
patches/
evidence/
```

Weekly:

```text
manifest.json
weekly.md
patches/
evidence/
```

Patch contribution:

```text
manifest.json
patches/
evidence/
```

Minimal v1 manifest:

```json
{
  "schema_version": "1.0",
  "type": "daily",
  "member": "member_alias",
  "date": "2026-05-26",
  "project": "全局项目",
  "summary": "今日工作摘要",
  "patches": []
}
```

## V2 Packages

V2 treats incoming as knowledge event packages, not report uploads.

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

### V2 Light Daily

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
  "date": "2026-05-26",
  "run_id": "20260526-210000",
  "project": "全局项目",
  "summary": "今日工作摘要",
  "source": {},
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

### V2 Strict Patch Contribution

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

Patch files are evidence, not opaque attachments. Intake and server normalization may inspect patch content to fill missing facts and improve search.

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

Likely problem, likely solution, keywords, applicability, and risks belong in `patch_problem_inference` or `risk_surface`. These are inferred conclusions and must include:

```json
{
  "confidence": "medium",
  "basis": ["patch modifies frameworks/base/..."],
  "limits": ["original issue text was not found"]
}
```

Rules:

- Inferred fields improve search and reuse judgment.
- Inferred fields must not be presented as verified facts.
- Inference alone cannot upgrade `quality` to `validated`.
- Historical imports may use patch analysis to recover missing title, summary, module, files, keywords, likely problem, likely solution, and risk surface.
- New incoming packages may use patch analysis as a consistency check against the human readme.

When importing an `android-framework-patch-capture` output directory with `--patch-package`, intake preserves its evidence entries under `evidence/capture-*.json`. A strict patch contribution may claim `quality=validated` only when it carries PASS device verification or accepted equivalent verification evidence. Strict patch contributions without verification evidence should stay `candidate`, even if the human-facing patch status is `validated`.
