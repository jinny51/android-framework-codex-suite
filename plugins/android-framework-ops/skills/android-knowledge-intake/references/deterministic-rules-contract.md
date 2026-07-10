# AKBS Deterministic Rules Contract

`android_framework_ops.knowledge_rules` is the single source for deterministic member-package rules. It must remain pure Python and must not depend on Codex session state, plugin cache locations, network calls, AI inference, or production database state.

## Shared Rule Families

| Rule family | Representative functions |
| --- | --- |
| Source capability versions | `current_plugin_version`, `source_version_compatibility_matrix`, `source_version_errors` |
| Project normalization | `valid_project_model`, `find_company_project`, `complete_company_project_with_platform`, `parse_company_project` |
| Platform and Android version parsing | `parse_known_platform_token`, `find_platform_tokens`, `parse_platform_arg`, `normalize_android_version` |
| Patch asset names | `patch_asset_name_prefix`, `has_uncontrolled_patch_asset_prefix`, `classify_patch_asset_names` |
| Function scope | `aggregate_package_scope_errors`, `classify_function_scope`, `curation_text_missing_fields` |
| Pre-change search evidence | `classify_pre_change_search`, `normalize_reuse_decision`, `search_results_need_usage_decision` |
| Supplement relationships | `supplement_target_relation_errors`, `supplement_field_policy`, `patch_asset_correction_source_errors` |
| Upload text quality | `text_field_quality_errors`, `template_leak_errors`, `future_run_id_errors` |

Member generation, patch capture, and upload preflight import this module directly from `android-framework-ops`.

The local `akbs-curation-maintainer` loads the same source module from `$AKBS_ROOT/plugin` when it needs deterministic boundary checks before AI curation. It must not reimplement project, platform, Android version, aggregate, search, supplement, or patch-asset rules.

The Linux/test35 AKBS service owns HTTP authentication, storage, active SQLite transactions, queue state, and API validation. It neither loads the Codex plugin cache nor keeps a generated copy of this module.

## Member-Only Behavior

- Plugin install/update and current-session cache gates.
- Local report, patch, and supplement generation.
- Evidence collection from Codex sessions and developer workspaces.
- Platform source access and remote build/deploy orchestration.
- Upload preflight and actionable member prompts.

## Maintainer-Only Behavior

- AI decisions for new knowledge, merge, archive, reject, or evidence requests.
- Knowledge validity, applicability, confidence, and risk assessment.
- Active SQLite read-only curation analysis and materialization plans.
- Team aggregation and main-control operation.

## Server-Only Behavior

- HTTP authentication and package receipt.
- Active SQLite persistence, lifecycle transitions, and transactional writes.
- Admin/member API read models and UI data.
- Service deployment and runtime health.

Do not add an exporter or copied server rule module. A rule that must be shared between member generation and local curation belongs in `knowledge_rules.py`; a server state rule belongs in the AKBS system.
