# AKBS rules single-source contract

This contract classifies rules that may be exported from `android_framework_ops.knowledge_rules` into server-side validation copies. The shared source is deterministic Python only; it must not depend on Codex sessions, plugin cache paths, Windows user paths, local worktrees, network calls, AI inference, or production database state.

## Shared deterministic rules

These rules are safe to keep in the plugin source and export into `akbs_validation_rules.py`:

| Rule family | Representative functions |
| --- | --- |
| Plugin/source capability versions | `current_plugin_version`, `source_version_compatibility_matrix`, `source_version_errors` |
| Project name normalization | `valid_project_model`, `find_company_project`, `complete_company_project_with_platform`, `parse_company_project` |
| Platform and Android version parsing | `parse_known_platform_token`, `find_platform_tokens`, `parse_platform_arg`, `normalize_android_version` |
| Patch asset prefix checks | `patch_asset_name_prefix`, `has_uncontrolled_patch_asset_prefix`, `classify_patch_asset_names` |
| Aggregate/function scope hard gates | `aggregate_package_scope_errors`, `classify_function_scope`, `curation_text_missing_fields` |
| Pre-change search evidence classification | `classify_pre_change_search`, `normalize_reuse_decision`, `search_results_need_usage_decision` |
| Supplement relation and field policy | `supplement_target_relation_errors`, `supplement_field_policy`, `patch_asset_correction_source_errors` |
| Upload text quality hard gates | `text_field_quality_errors`, `template_leak_errors`, `future_run_id_errors` |

## Member-only rules

These rules stay in member-side skills and scripts:

- Codex plugin install/update/doctor flow.
- Current session skill-cache freshness checks and automatic plugin update attempts.
- Local package generation, report rendering, patch capture, member config discovery, SSH source access, and remote build orchestration.
- Any prompt wording that tells Codex how to gather evidence from a developer workspace.
- Any use of Codex tool state, plugin cache directories, user home paths, Windows paths, or active WSL mounts.

## Server-only rules

These rules stay in the AKBS server system, legacy database repository, intake branch, curation runner, UI API, or maintainer-side skills:

- New knowledge versus merge versus archive decisions.
- Knowledge validity scoring, RAG ranking, duplicate source grouping, and materialization decisions.
- Business queue mutation, old package cleanup, production query database rebuilds, and UI read-model publication.
- Authentication, storage, service deployment, systemd state, and test35 synchronization.
- Any database query, filesystem promotion, or production state transition.

## Export contract

Use `plugins/android-framework-ops/scripts/export_akbs_validation_rules.py` to generate a self-contained server validation copy into a temporary directory:

```bash
python3 plugins/android-framework-ops/scripts/export_akbs_validation_rules.py \
  --output-dir /tmp/akbs-rules-export
```

The generated `/tmp/akbs-rules-export/akbs_validation_rules.py` must be importable without the plugin repository on `PYTHONPATH`. Its header records:

- `GENERATED FROM android_framework_ops.knowledge_rules`
- `android-framework-ops` plugin version
- `AKBS_RULES_CONTRACT_VERSION`
- source commit
- a do-not-edit-by-hand notice

Phase 1-2 only proves generation into a temporary directory. In the new AKBS path, server validation lives in the AKBS server system and should not be mechanically copied from the member plugin during ordinary uploads. Replacing database repository and intake branch copies is legacy/rollback compatibility work only.
