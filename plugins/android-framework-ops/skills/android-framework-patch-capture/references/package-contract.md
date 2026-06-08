# Framework Feature Patch Package Contract

This package is a local handoff artifact. One package represents one Framework feature. A feature may touch multiple repo-managed Git repositories, so the package has one feature README and one patch per affected source repository.

`android-knowledge-intake` submits the whole feature package through the server submission channel as incoming. The user's local `android-knowledge-curation-maintainer` skill later decides whether and how material enters the knowledge repository.

## Directory

```text
.codex/patch-packages/YYYYMMDD-HHMMSS-feature/
├── manifest.json
├── README.md
├── patches/
│   ├── <platform>-<module>@<feature>.patch
│   └── <platform>-<module>@<feature>.patch
└── evidence/
    ├── changed-files.json
    ├── patch-diff-facts.json
    ├── patch-problem-summary.json
    ├── risk-surface.json
    ├── coding-standard-check.json
    ├── build-result.json
    ├── verification-result.json
    ├── search-before-change.json
    └── package-check.json
```

There is no `patches/*.readme.md` in the capture package. The README is feature-level and lives at the package root.

## Manifest

```json
{
  "schema_version": "2.0",
  "package_type": "framework_feature_patch",
  "feature": "display-policy-settings-entry",
  "readme": "README.md",
  "project": "TVE8402M",
  "summary": "功能摘要",
  "status": "candidate",
  "implementation_origin": "manual",
  "captured_by": "codex",
  "coding_standard_check": {
    "required": true,
    "mode": "capture_gate",
    "path": "evidence/coding-standard-check.json",
    "result": "PASS"
  },
  "related_report_run_ids": ["20260601-210000-daily"],
  "source_roots": [
    "/home/<wsl-user>/work/rk/TVE8402M/frameworks/base",
    "/home/<wsl-user>/work/rk/TVE8402M/packages/apps/Settings"
  ],
  "git_repositories": [
    {
      "repo_path": "frameworks/base",
      "root": "/home/<wsl-user>/work/rk/TVE8402M/frameworks/base",
      "git": {
        "branch": "feature/TVE8402M-policy",
        "remote": "ssh://example/frameworks/base.git",
        "head": "abc1234"
      }
    }
  ],
  "project_inference": {
    "project": "TVE8402M",
    "recognized": true,
    "basis": ["source_root: /home/<wsl-user>/work/rk/TVE8402M"],
    "checked_sources": ["命令参数 project", "source_root", "repo_path", "git branch", "git remote"],
    "limits": [],
    "recognition_scope": "TVE/TVA/TVI"
  },
  "evidence": [
    {
      "id": "verification-result",
      "kind": "verification_result",
      "path": "evidence/verification-result.json",
      "result": "PASS",
      "scope": "feature",
      "summary": "device verification evidence"
    },
    {
      "id": "patch-diff-facts",
      "kind": "patch_diff_facts",
      "path": "evidence/patch-diff-facts.json",
      "result": "INFO",
      "scope": "feature",
      "summary": "功能补丁 diff 中解析出的客观事实"
    },
    {
      "id": "coding-standard-check",
      "kind": "coding_standard_check",
      "path": "evidence/coding-standard-check.json",
      "result": "PASS",
      "scope": "feature",
      "summary": "团队补丁开发与日志规范检查"
    }
  ],
  "patches": [
    {
      "id": "rk14-frameworks-base@display-policy-settings-entry",
      "path": "patches/rk14-frameworks-base@display-policy-settings-entry.patch",
      "repo_path": "frameworks/base",
      "source_root": "/home/<wsl-user>/work/rk/TVE8402M/frameworks/base",
      "content_sha1": "40-hex-sha1",
      "status": "candidate",
      "reuse_hint": false,
      "implementation_origin": "manual",
      "captured_by": "codex",
      "facts": {
        "content_sha1": "40-hex-sha1",
        "repo_path": "frameworks/base",
        "modified_files": [],
        "modules": [],
        "symbols": [],
        "system_properties": [],
        "settings_keys": [],
        "resource_keys": [],
        "framework_log_keys": []
      }
    }
  ]
}
```

## Fact-First Rule

Store objective evidence. Do not force permanent AI judgments into the package.

Good facts:

- repository path
- modified files
- patch content sha1
- added/deleted symbols
- property keys
- Settings keys
- resource keys
- FrameworkLog keys
- build target and result
- device verification steps
- equivalent verification method, reason, coverage, and remaining risk
- failure evidence

Patch-content explanation is allowed only when it carries basis and limits:

```json
{
  "kind": "patch_problem_summary",
  "scope": "feature",
  "confidence": "medium",
  "problem_summary": "窗口或 Activity 焦点行为需要按产品需求调整。",
  "solution_summary": "修改 WindowManager 或 ActivityTaskManager 相关路径中的焦点处理逻辑。",
  "keywords": [],
  "basis": ["功能涉及源码仓库: frameworks/base"],
  "limits": ["补丁内容不能单独证明原始需求文字"]
}
```

These judgments should still happen at search/use time:

- applicability to a new project
- reuse risk
- likely conflicts
- whether a newer patch replaces this one
- whether to apply, adapt, or only reference

## Coding Standard Check

Coding standards should be applied during development, especially when a team practice skill such as `jinny-framework-coding-standards` is active. Capture-time checks are a safety net for manual, historical, external, or half-inherited code.

`coding-standard-check.json` records:

- author/date marker presence
- direct `Log.*` or `Slog.*` additions
- FrameworkLog keys
- `persist.sys.framework.debug.*` usage
- resource keys
- repository-level errors and warnings

Noncompliant code should fail or be downgraded; do not present it as validated.

## Package Status Is A Hint

Allowed statuses:

- `draft`: generated or unfinished, not enough validation
- `candidate`: implemented, waiting for broader validation
- `validated`: compiled and device-verified for the original scope
- `failed`: retained as failed verification or failed implementation evidence
- `blocked`: retained as blocked work evidence

Status helps ranking member-side materials, but it is not a curation decision and must not be used as the only reuse decision. `reuse_hint` is only a hint for later review by the user's local curation maintainer skill.

## Project Recognition

`project` must be a recognized company project model in the current scope:

```text
TVE
TVA
TVI
```

Recognition priority:

1. Explicit `--project` containing a scoped company project model.
2. Feature package project or patch item project.
3. Source context: `source_root`, `repo_path`, git branch, git remote, local mount path, or the WSL source-access registry.
4. README/diff/summary text.

Generic labels such as `android16`, `Camera2`, or `mtk android16 Camera2` are checked inputs, not project names. When no company project model is found, write `project: "unknown"` and preserve the checked sources in `project_inference`.

## Report Link

When the feature came from a known daily or weekly incoming run, include the run id. Weekly run ids are provenance only; weekly packages remain database archive records and are not materialized into the knowledge repository:

```json
{
  "related_report_run_ids": ["20260601-210000-daily"]
}
```

This is an explicit deterministic link for the server. Do not invent report links from fuzzy similarity.

## Verification Evidence

Runtime behavior changes in the modified module should use device verification. Equivalent verification is allowed for resource-only, build-only, packaging-only, static config, or documentation changes when device interaction is not the right proof.

`verification-result.json` should record:

```json
{
  "result": "PASS",
  "method": "device",
  "device": "rk3576",
  "steps": [],
  "observed": "",
  "health_checks": [],
  "artifacts": []
}
```

Equivalent verification must be explicit:

```json
{
  "result": "PASS",
  "method": "equivalent",
  "equivalent_type": "artifact_static_check",
  "reason": "资源/配置类变更不涉及被修改模块运行时行为",
  "coverage": [],
  "remaining_risk": ""
}
```
