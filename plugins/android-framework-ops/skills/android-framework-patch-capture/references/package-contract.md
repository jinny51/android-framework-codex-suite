# Framework Feature Patch Package Contract

This package is a local handoff artifact. One package represents one Framework feature. A feature may touch multiple repo-managed Git repositories, so the package has one feature README and one patch per affected source repository.

`android-knowledge-intake` submits the whole feature package through the server submission channel as incoming. The user's local `android-knowledge-curation-maintainer` skill later decides whether and how material enters the knowledge repository.

Project metadata is an applicability boundary. If project clues conflict across `--project`, source roots, git metadata, WSL source-access registry, summary, or diff text, the capture package must keep `project=unknown`, preserve all candidate TVE/TVA/TVI models in `project_inference.candidates`, and record the conflict in `project_inference.limits`.

Patch capture filters diff sections that contain only file mode metadata, such as `old mode 100755` / `new mode 100644`. Mode-only changes are not feature evidence and must not create a standalone patch package. If a file mode change is intentional, it must appear with content, summary, risk, and verification evidence explaining why executable permission is part of the feature.

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
  "verification_chain": {
    "remote_build": true,
    "local_delivery": true,
    "device_verification": true
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
- remote build host/source root/command/profile/artifact path/artifact SHA1
- local artifact transfer path, local adb serial, push/install action, and restart/reload action
- search-before-change decision, match points, mismatch points, and later outcome
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

`search-before-change.json` records the member-side AI use decision before the change. It is evidence for later curation, not a curation decision:

```json
{
  "result": "INFO",
  "method": "knowledge_search",
  "searched": true,
  "queries": ["电源键 用户态 控制"],
  "results": ["命中 case-power-key-to-app，但项目和 Android 版本不同"],
  "decision": "adapt",
  "reuse_decision": "adapt",
  "targets": ["case-power-key-to-app"],
  "match_points": ["同类按键策略需求"],
  "mismatch_points": ["旧变体是 rk12，当前项目是 rk14"],
  "reason": "复用案例思路，按当前项目源码适配",
  "outcome": "adapted_success"
}
```

Allowed `decision` values:

```text
reuse            直接复用：命中知识和当前平台/版本/路径/验证范围足够匹配。
adapt            适配：同类问题成立，但平台、Android 版本、项目、源码路径或实现细节不同。
reference_only   仅参考：机制、风险或排查方向有用，但不能作为实现依据。
not_applicable   不适用：命中知识与当前需求或源码条件冲突。
not_found        未命中：搜索后没有找到可用知识。
unknown          未记录：旧包或异常场景没有形成明确决策。
```

## Remote Build To Local ADB Evidence

When Android work is built on a remote server and delivered to a local USB device, the deploy executor should write:

```text
<source-root>/.codex/evidence/latest-build-delivery.json
```

`capture_framework_patch.py` reads this file automatically from each `--source-root` and merges it into `verification-result.json`. The expected shape is:

```json
{
  "kind": "verification_result",
  "result": "PASS",
  "method": "device",
  "build": ["framework-services build PASS"],
  "device": "ABC123",
  "steps": ["adb -s ABC123 push services.jar /system/framework/services.jar"],
  "remote_build": {
    "host": "builder01",
    "source_root": "/build/android/TVE8402M",
    "command": "bash .codex/build-push.sh build --profile framework-services",
    "profile": "framework-services",
    "artifacts": [
      {"path": "/build/android/TVE8402M/out/target/product/tve/system/framework/services.jar", "sha1": "40-hex-sha1"}
    ]
  },
  "local_delivery": {
    "transfer": "mounted Samba/CIFS product output",
    "local_artifacts": ["/mnt/repo/out/target/product/tve/system/framework/services.jar"],
    "adb_serial": "ABC123",
    "adb_actions": ["adb -s ABC123 push services.jar /system/framework/services.jar"],
    "device_restarts": ["adb -s ABC123 reboot"]
  }
}
```

Manual capture arguments can still override or supplement the automatic file for historical or exceptional packages.

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
  "artifacts": [],
  "remote_build": {
    "host": "builder01",
    "source_root": "/build/android/TVE8402M",
    "command": "bash .codex/build-push.sh build --profile framework-services",
    "profile": "framework-services",
    "artifacts": [
      {
        "path": "/build/android/TVE8402M/out/target/product/tve8402m/system/framework/services.jar",
        "sha1": "40-hex-sha1"
      }
    ]
  },
  "local_delivery": {
    "transfer": "scp builder01:/build/android/TVE8402M/out/.../services.jar ~/.codex/artifacts/services.jar",
    "local_artifacts": ["~/.codex/artifacts/services.jar"],
    "adb_serial": "ABC123",
    "adb_actions": ["adb -s ABC123 push services.jar /system/framework/services.jar"],
    "device_restarts": ["adb -s ABC123 reboot"]
  }
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
