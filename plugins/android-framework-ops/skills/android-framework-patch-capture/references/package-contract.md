# Android Feature Patch Package Contract

This package is a local handoff artifact. One package represents one Android feature. A feature may touch multiple repo-managed Git repositories, so the package has one feature README and one patch per affected source repository.

The public `android-framework-patch-capture` Skill accepts an explicit controlled
domain from `contracts/change-domain/v1/domain-profiles.json`. Its default is
`--change-domain framework`, which produces the established
`framework_feature_patch` manifest:

- `framework` produces `framework_feature_patch` and may continue to the existing
  Framework incoming v1 flow after validation.
- every other domain produces `android_feature_patch` for local engineering evidence
  only. The current Framework intake must reject it; it must not be relabelled and
  uploaded through incoming v1.

This is a public cross-domain local-capture capability. The server submission boundary
is separate and remains Framework incoming v1 only.

`android-framework-patch-intake` submits the whole feature package through the server submission channel as incoming, using the shared `android-knowledge-intake` kernel. The user's local `akbs-curation-maintainer` skill later decides whether and how material enters the knowledge repository.

Project metadata is an applicability boundary. If project clues conflict across `--project`, the verified remote snapshot, Git metadata, the platform-neutral source-access registry, summary, or diff text, the capture package must keep `project=unknown`, preserve all candidate TVD/TVE/TVA/TVI models in `project_inference.candidates`, and record the conflict in `project_inference.limits`.

For `current_codex_skill`, all source facts come from an immutable
`android-remote-patch-snapshot-v1` created inside `android-remote-channel` v2.
The snapshot binds the canonical remote root, workspace and command identities,
Git/repo status, HEAD/branch/remotes, staged and unstaged binary diffs, final
HEAD-relative binary diff, untracked inventory/content patch, changed files,
per-blob hashes, generation time, and a canonical snapshot SHA-256. The local
packager verifies every field and copies the validated snapshot into package
evidence. It never accepts `--source-root` or a caller patch for this workflow.

The manifest `project` field stores only the normalized company model. Branch suffixes, customer suffixes, build branches, business labels, module labels, Chinese descriptions, and other non-standard trailing text must stay in `project_inference` evidence. For example, `TVE1067M1_H031` becomes `TVE1067M1`, `TVE1086U_MAIN_HANGYAN` becomes `TVE1086U`, and `TVE1091U福建移动高清` becomes `TVE1091U`.

Patch capture filters diff sections that contain only file mode metadata, such as `old mode 100755` / `new mode 100644`. Mode-only changes are not feature evidence and must not create a standalone patch package. If a file mode change is intentional, it must appear with content, summary, risk, and verification evidence explaining why executable permission is part of the feature.

## Directory

```text
$CODEX_HOME/artifacts/android-framework-patch-capture/packages/<run-id>/
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
    ├── remote-source-snapshot.json
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
  "change_domain": "framework",
  "feature": "display-policy-settings-entry",
  "readme": "README.md",
  "project": "TVE8402M",
  "summary": "功能摘要",
  "status": "candidate",
  "implementation_origin": "codex",
  "workflow_contract": "current_codex_skill",
  "captured_by": "codex",
  "coding_standard_check": {
    "required": false,
    "mode": "development_safety_net",
    "path": "evidence/coding-standard-check.json",
    "result": "PASS"
  },
  "related_report_run_ids": ["20260601-210000-daily"],
  "source_snapshot": {
    "path": "evidence/remote-source-snapshot.json",
    "schema": "android-remote-patch-snapshot-v1",
    "workspace_id": "0123456789abcdef",
    "command_id": "patch-snapshot-20260826",
    "remote_root": "/home/test61/unisoc/project",
    "sha256": "64-hex-sha256"
  },
  "source_roots": [
    "/home/test61/unisoc/project/frameworks/base",
    "/home/test61/unisoc/project/packages/apps/Settings"
  ],
  "git_repositories": [
    {
      "repo_path": "frameworks/base",
      "root": "/home/test61/unisoc/project/frameworks/base",
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
    "basis": ["source_root: /home/test61/unisoc/project"],
    "checked_sources": ["命令参数 project", "remote snapshot", "repo_path", "git branch", "git remote"],
    "limits": [],
    "recognition_scope": "TVD/TVE/TVA/TVI"
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
      "source_root": "/home/test61/unisoc/project/frameworks/base",
      "content_sha1": "40-hex-sha1",
      "status": "candidate",
      "reuse_hint": false,
      "implementation_origin": "codex",
      "workflow_contract": "current_codex_skill",
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

`capture_framework_patch.py` accepts a paired `--problem-summary` and `--solution-summary` from the Codex workflow after it has read the actual request, diff, and verification evidence. The script writes those values into the generated evidence and records their explicit capture basis. Passing only one is invalid. Module-based inference is retained for backward-compatible draft or candidate capture; generated JSON must never be edited by hand to replace a generic fallback.

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
unknown          未记录：历史包或异常场景没有形成明确决策。
```

`implementation_origin` identifies who wrote the code. `workflow_contract` identifies how the patch entered AKBS. They are independent and must never be inferred from one another. `current_codex_skill` requires pre-change knowledge search before source edits; if the search did not find reusable knowledge, set `reuse_decision=not_found`. If that search did not really happen, do not fabricate it or mark the current-workflow package `validated`. A truthful `manual_import` or `historical_import` may record `searched=false`, keep real verification evidence, and let admin-side curation run post-change overlap check without search-loop score.

## Remote Build To Local ADB Evidence

When Android work is built on a remote server and delivered to a local USB
device, pass the build/deploy receipt explicitly with `--build-result`. Current
capture must not read `.codex` evidence through a mounted source root. The
expected receipt shape is:

```json
{
  "contract_version": "akbs-verification-evidence/v2",
  "scope": "build_delivery",
  "requirement_acceptance": "unverified",
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

The top-level `PASS` in this automatic file means the build/delivery operation passed. It is not
requirement acceptance. `capture_framework_patch.py` preserves this fail-closed scope, including
for older delivery files that lack the v2 fields. Manual capture arguments can still supplement
the automatic file for historical or exceptional packages, but only explicit device-behavior or
qualified equivalent verification can produce requirement acceptance.

## Coding Standard Check

The canonical `android-change-policy/v1` is applied during development. Capture-time
checks verify the same versioned contract and remain a safety net for manual,
historical, external, or half-inherited code. The currently optional
`jinny-android-practices` layer may add non-conflicting preferences, but it is not a
second policy authority.

`coding-standard-check.json` records:

- policy ID/version, selected member profile and expected `member_alias`
- per-file comment adapter, paired/legacy marker counts, aliases, dates and violations
- legacy import exceptions, which remain `WARN` and never become canonical-policy `PASS`
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

Status helps ranking member-side materials, but it is not a curation decision and must not be used as the only reuse decision. Build/device or accepted equivalent verification is necessary for `validated`, but it is not sufficient for the `current_codex_skill` workflow: that workflow must also record a real pre-change knowledge search and close any search usage decision. If the search did not happen, keep the current-workflow package out of `validated`; do not relabel its implementation origin or fabricate search evidence. A truthful `manual_import` or `historical_import` may still be `validated` by real verification while recording `searched=false`; admin-side curation must then run a post-change overlap check and avoid search-loop score. `reuse_hint` is only a hint for later review by the user's local curation maintainer skill.

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
3. Source context: verified remote snapshot root, `repo_path`, Git branch, Git remote, or the platform-neutral source-access registry.
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
  "contract_version": "akbs-verification-evidence/v2",
  "scope": "feature",
  "requirement_acceptance": "accepted",
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
  "contract_version": "akbs-verification-evidence/v2",
  "scope": "feature",
  "requirement_acceptance": "accepted",
  "result": "PASS",
  "method": "equivalent",
  "equivalent_type": "artifact_static_check",
  "reason": "资源/配置类变更不涉及被修改模块运行时行为",
  "coverage": [],
  "remaining_risk": "未覆盖真机运行时行为；该变更不涉及被修改模块的运行时路径"
}
```

Legacy unscoped verification records remain readable as historical evidence, but they cannot
upgrade a package to `validated`.
