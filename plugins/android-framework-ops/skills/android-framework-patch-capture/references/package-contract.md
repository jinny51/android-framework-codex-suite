# Framework Patch Package Contract

This package is a local handoff artifact. `android-knowledge-intake` can later submit the generated patch file and readme to the team knowledge repository.

## Directory

```text
.codex/patch-packages/YYYYMMDD-HHMMSS-patch/
├── manifest.json
├── patches/
│   ├── <patch-name>.patch
│   └── <patch-name>.readme.md
└── evidence/
    ├── changed-files.json
    ├── patch-diff-facts.json
    ├── patch-problem-inference.json
    ├── risk-surface.json
    ├── build-result.json
    ├── verification-result.json
    ├── search-before-change.json
    └── package-check.json
```

## Manifest

```json
{
  "schema_version": "1.0",
  "package_type": "framework_patch",
  "project": "Android Framework",
  "summary": "功能摘要",
  "status": "candidate",
  "evidence": [
    {
      "id": "verification-result",
      "kind": "verification_result",
      "path": "evidence/verification-result.json",
      "result": "PASS",
      "summary": "device verification evidence"
    },
    {
      "id": "patch-diff-facts",
      "kind": "patch_diff_facts",
      "path": "evidence/patch-diff-facts.json",
      "result": "INFO",
      "summary": "facts parsed directly from patch content"
    },
    {
      "id": "patch-problem-inference",
      "kind": "patch_problem_inference",
      "path": "evidence/patch-problem-inference.json",
      "result": "INFO",
      "summary": "likely problem and solution inferred from patch content"
    },
    {
      "id": "risk-surface",
      "kind": "risk_surface",
      "path": "evidence/risk-surface.json",
      "result": "INFO",
      "summary": "risk surface inferred from changed files and symbols"
    },
    {
      "id": "search-before-change",
      "kind": "search_before_change",
      "path": "evidence/search-before-change.json",
      "result": "INFO",
      "summary": "knowledge search performed before development"
    }
  ],
  "patches": [
    {
      "path": "patches/rk14-frameworks-base@feature.patch",
      "readme": "patches/rk14-frameworks-base@feature.readme.md",
      "facts": {
        "modified_files": [],
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

- modified files
- added/deleted symbols
- property keys
- Settings keys
- resource keys
- build target and result
- device verification steps
- equivalent verification method, reason, coverage, and remaining risk
- failure evidence

Patch-content inference is allowed only when it is labeled as inference and carries basis and limits:

```json
{
  "kind": "patch_problem_inference",
  "confidence": "medium",
  "inferred_problem": "likely problem inferred from modified paths and diff content",
  "inferred_solution": "likely solution inferred from changed code path",
  "inferred_keywords": [],
  "basis": [],
  "limits": []
}
```

These judgments should still happen at search/use time:

- applicability to a new project
- reuse risk
- likely conflicts
- whether a newer patch replaces this one
- whether to apply, adapt, or only reference

## Status Is A Hint

Allowed statuses:

- `draft`: generated or unfinished, not enough validation
- `candidate`: implemented, waiting for broader validation
- `validated`: compiled and device-verified for the original scope
- `released`: delivered or merged
- `buggy`: retained as failure/process evidence

Status helps ranking, but it must not be used as the only reuse decision.

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
