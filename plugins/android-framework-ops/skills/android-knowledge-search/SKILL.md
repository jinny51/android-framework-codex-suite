---
name: android-knowledge-search
description: Search the team knowledge repository for reusable cases, platform variants, archived patches, search anchors, validation notes, and prior Android Framework solutions. Use before re-implementing a feature, during Android Framework requirement triage, or when a user asks to find existing patches or team knowledge.
---

# Android Knowledge Search

Use this skill to search the team knowledge repository before starting new analysis or implementation. It is the member-side search entry for the knowledge system: `android-daily-report-intake`, `android-weekly-report-intake`, `android-framework-patch-intake`, and `android-framework-patch-capture` submit materials through the server submission channel using the shared intake kernel, and the user's local `akbs-curation-maintainer` skill promotes AI-usable knowledge into the knowledge repository for this skill to retrieve.

This skill does not submit reports, create patches, edit source, or decide correctness by itself. It returns prior facts so Codex can judge whether an existing case, variant, patch, symbol, or validation fact is relevant to the current requirement.

Default search uses the AKBS member hybrid search endpoint when reachable. The request must carry `X-AKBS-User=<member_alias>` and `X-AKBS-Role=member`, and the endpoint address comes from the AKBS endpoint resolver defaults or `CODEX_REPORT_AKBS_ENDPOINT_*` admin/test overrides. Do not ask ordinary members to configure test35, server paths, submit commands, or a raw database repository path for search.

If the server endpoint is unavailable, unauthorized, or times out, the script falls back to the local JSONL knowledge repository worktree and marks the result as `source=local_jsonl_fallback`. Treat fallback output as local text search that has not passed server hybrid grading.

For merge confirmations, this skill can read the member-only AKBS merge confirmation API: list, detail, target knowledge, compare, and a Codex analysis summary. These actions are read-only. It must not submit a merge dispute unless the user explicitly asks to send an objection and the command includes `--merge-confirmation dispute --send-dispute` plus a reason or assessment.

Each normal search writes a member-side search usage record under the intake artifact directory so later daily and patch packages can carry the pre-change knowledge use evidence. The record is development evidence only; it is not a curation decision.

If a search result shows a recommended replacement case, treat it as curation guidance from the local knowledge loop: inspect the replacement before reusing the obsolete or contradicted case. The replacement hint is still evidence, not an automatic reuse decision.

## Quick Command

```bash
python3 "scripts/android_knowledge_search.py" \
  "电源键 frameworks/base" \
  --limit 8
```

Useful variants:

```bash
# Search primary cases. Default `--source auto` prefers server hybrid search.
python3 "scripts/android_knowledge_search.py" \
  "通知音量 SystemUI" --type case

# Search platform/project implementations.
python3 "scripts/android_knowledge_search.py" \
  "TVE8402M VolumeDialogImpl" --type variant

# Search only patch assets.
python3 "scripts/android_knowledge_search.py" \
  "persist.sys launcher" --type patch

# Return machine-readable output for another workflow.
python3 "scripts/android_knowledge_search.py" \
  "WindowManager display" --json

# Force local JSONL fallback for offline work.
python3 "scripts/android_knowledge_search.py" \
  "PackageManager permission" --source local --root /path/to/knowledge

# Record an explicit member-side use decision with the search.
python3 "scripts/android_knowledge_search.py" \
  "电源键 rk3576" \
  --reuse-decision adapt \
  --reuse-target case-power-key \
  --reuse-reason "同类策略可参考，当前项目需适配"

# Use an explicit mounted or cloned knowledge repository root.
python3 "scripts/android_knowledge_search.py" \
  "PackageManager permission" --root /path/to/knowledge

# Review pending merge confirmations without sending anything.
python3 "scripts/android_knowledge_search.py" \
  --merge-confirmation list

# Generate a human-readable and Codex-evidence merge analysis.
python3 "scripts/android_knowledge_search.py" \
  --merge-confirmation analyze \
  --merge-confirmation-id review-20260703-member-patch

# Send a dispute only after the member explicitly asks for it.
python3 "scripts/android_knowledge_search.py" \
  --merge-confirmation dispute \
  --merge-confirmation-id review-20260703-member-patch \
  --send-dispute \
  --dispute-reason "目标知识没有覆盖当前补丁的功能目标"
```

## Source Selection

In `--source auto`, the script first tries the server hybrid endpoint. Local JSONL fallback searches the first valid knowledge repository root it can find:

1. `--root <path>`
2. `CODEX_KNOWLEDGE_ROOT`
3. `CODEX_KNOWLEDGE_REPO_WORKTREE` or `CODEX_REPORT_KNOWLEDGE_REPO_WORKTREE`
4. `knowledge_repo_worktree` or `knowledge_worktree` from the selected profile in `$CODEX_HOME/report/config.toml`, `$CODEX_HOME/android-knowledge-search.toml`, or the nearest `.codex/report.toml`
5. current directory or its parents, when they contain current `index/*.jsonl` knowledge indexes
6. generic Codex worktrees such as `$CODEX_HOME/worktrees/knowledge` or detected Windows `Documents/Codex/worktrees/knowledge`
7. common mapped server locations such as `/mnt/z/knowledge/knowledge`

The search skill must not automatically read the database repository. If a local maintainer needs to inspect database internals, pass that path explicitly with `--root` and understand that it is not the normal member reuse path.

Pass `--refresh` only when using a local Git clone and the latest server content is required. Refresh runs `git pull --ff-only`; it skips refresh when the worktree is dirty.

## Search Discipline

When handling a new Android Framework requirement:

1. Search with feature words, affected module, likely class name, property key, Settings key, resource key, search anchor, and artifact name.
2. Read the top matching case, variant, patch readme, or validation fact before deciding whether to reuse.
3. Treat `status`, `package_status`, `reuse_hint`, platform, and validation fields as hints, not truth.
4. Prefer case and variant results first; then inspect related patches, AI evidence, and symbols.
5. Compare facts: modified files, touched symbols, artifact, risk notes, build evidence, device verification, rollback path.
6. If a prior patch looks relevant, report the evidence and remaining uncertainty before applying or adapting it.
7. Use explicit `--type report`, `--type event`, or `--type evidence` only for administrator trace-back or debugging archive material. Default `--type all` is the AI reuse view and does not return report/event archive rows.
8. Default member search filters out retracted cases, variants, patch assets, symbols, and evidence rows. It also redacts retracted object references embedded inside ordinary search evidence payloads, such as older `search_before_change.results` entries. The knowledge repository can retain those rows for traceability, but they must not appear as reusable member results. Explicit archive/debug queries may still show archived or retracted material.

For `android-framework-change-workflow`, this is the pre-analysis search gate. Search first; if no useful result exists, continue with normal requirement analysis and implementation.

## Search Usage Evidence

默认会写入搜索使用证据（search usage evidence）：

```text
$CODEX_HOME/artifacts/android-knowledge-intake/search-usage/<YYYYMMDD>/*.json
```

如果报告配置里设置了 `out_dir`，记录写入该输出目录下的 `search-usage/`。后续 `android-daily-report-intake` 和 `android-framework-patch-intake` 会通过共享 intake 脚本读取同一天同成员的记录，并生成 `materials/evidence/search_before_change.json`。

可记录的成员侧使用决策：

```text
reuse
adapt
reference_only
not_applicable
not_found
unknown
```

这些值只说明成员侧 Codex 如何使用知识库仓库。它们不能替代管理端本地知识沉淀技能做出的沉淀结论（curation decision）。

## References

Read `references/search-contract.md` before changing the script output format or integrating this skill into another workflow.
