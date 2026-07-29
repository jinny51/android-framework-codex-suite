---
name: android-knowledge-intake
description: Use when handling member first setup, doctor checks, plugin updates, current member configuration, or the shared member-side incoming kernel used by the daily, weekly, and patch intake skills. Do not use for knowledge curation decisions.
---

# Android Knowledge Intake

Use this skill for the member-side incoming 共享内核（shared kernel）, setup, doctor checks, plugin updates, and current configuration. Member-facing business entrypoints are `android-daily-report-intake`, `android-weekly-report-intake`, and `android-framework-patch-intake`; they all call this one script and protocol layer instead of copying upload logic.

The skill does not write final knowledge reports, curated patches, index, or site directories. It creates a local pending incoming package first, then sends that package through the server submission channel. The member-side skill does not clone, pull, directly search, or push the database repository; member viewing UI is a separate server-side database view.

The member-side Codex agent is the material producer. It should collect session context, git activity, patch diff, build results, verification records, failed paths, blocked paths, and optional human notes, then generate incoming. The only member upload channel is the AKBS HTTP API; it receives the package, validates it, and stores it in active SQLite. Knowledge projections and curation decisions are produced later by the AKBS curation flow, not by the member-side plugin.

Ordinary members use `android-daily-report-intake` for daily reports, `android-weekly-report-intake` for weekly reports, and `android-framework-patch-intake` for one complete patch package or a queue information completion for that same package. Those skills invoke the `daily`, `weekly`, and `patch` commands in this shared kernel. For patches, the server-assigned `patch_package_id` is the sole business subject across queue and main; `package_key` is only the immutable upload-source identity. Request, notification, and confirmation IDs remain causal event identifiers. Weekly packages are progress archives only; they do not become knowledge materialization candidates. Non-member profiles are only for protocol and server-chain tests; they must not be confused with the user's local `akbs-curation-maintainer` skill.

Default policy: preserve work facts locally first, then upload only packages that pass the member-side upload gate. Daily traces must preserve `work_findings`; weekly traces preserve progress summaries for database archive and member view only. A framework-change upload must be one `validated` patch package: clear function boundary, traceable project/platform/Android version, clean immutable patch assets, and PASS build plus device or accepted equivalent verification. `candidate`, `draft`, `failed`, and `blocked` are local or report-context states; they do not enter the server upload queue. These values are not curation decisions.

Daily and weekly generation have no "future submission" mode. A daily package date later than the current local date must stop with "不能提交未来日期的日报，请重新生成正确日期的日报。". A weekly package whose anchor date is later than the current local date, or whose `week_range` is later than the current local week, must stop with "不能提交未来周期的周报，请重新生成正确周期的周报。". Older daily dates and older weekly periods are late submissions and are allowed.

Daily and weekly report bodies are the primary human-readable product. Generate `reports/daily.md` and `reports/weekly.md` with the Codex office report templates. Daily reports answer 今天干了什么、怎么做的、结果和状态是什么. Weekly reports answer 本周完成多少、还剩多少、重点信息、风险和依赖是什么、下周怎么收敛. Weekly project blocks use 项目名称、直接客户、可选客户的客户、项目角色、需求时间、需求来源、项目总量（主责必填，协作可不填）、本周完成、当前剩余, then 本周完成详情、当前剩余详情、重点说明、风险 / 依赖 and 下周计划. Counts use only 需求、移植、Bug and the constrained BSP dependency count; never retain a 定制 parent category. Do not use a large overview table in the weekly `本周概况`, and do not repeat daily execution logs. In both Markdown reports, bold every project-name occurrence, including body text, while leaving the customer chain unbolded. This presentation rule must not add Markdown markers to structured fields. Also write `materials/display/report_view.json` as the current UI read model for cards, lists, and member report detail; it is a structured index of the same report, not a separate AI/evidence layer. `report_view.json` uses `schema=akbs-report-view-human-v1`; `material_name` is project + customer chain, `customer` is the direct customer, optional `downstream_customer` is the direct customer's customer, and `material_summary` is the daily topic or weekly completed/remaining/risk summary. Management-side aggregation may consume the same fields later, but the member-side flow must not ask members to understand team summary concepts. Keep `work_findings.json` as evidence for audit and later analysis.

Weekly generation uses effective AKBS report facts before sessions: current daily reports for the target week, then the current previous-week report as the rolling ledger, then local submitted replacement leaves when the API is unavailable. Sessions are supplementary and must never be counted as requirements. The weekly package writes `materials/evidence/weekly_fact_sources.json`; missing ledger facts make local check fail. Close only those missing fields with an `akbs-weekly-project-facts-v2` artifact and `weekly --weekly-facts <path>`. The artifact belongs under `$CODEX_HOME/artifacts/android-knowledge-intake/weekly-facts/`, not in this skill directory. Read `references/weekly-facts-contract.md` before creating it.

Daily and weekly generation is idempotent by member and report identity: daily uses `date`, weekly uses `week_range`. If a local pending or submitted report package already exists for the same member and identity, `--prepare`, `--upload`, and `--submit-latest` must stop instead of silently creating or uploading a second ordinary report package. The member must either cancel the new run or explicitly replace the old package. Use `daily --replace-daily-run-id <old_run_id>` or `weekly --replace-weekly-run-id <old_run_id>`; the replacement package writes `replacement_for_run_id` and `supersedes` metadata so it is not another silent ordinary report package.

Use configuration profiles for identity. Ordinary member config stores identity, optional local knowledge fallback worktree, git author, role, allowed modes, and optional test behavior. AKBS HTTP endpoint values come from the endpoint resolver or controlled environment overrides, not member profiles. Upload, search, and merge-confirmation requests send only `X-AKBS-User=<member_alias>` plus content-negotiation/type headers; the server verifies the fixed workstation source IP. Prefer explicit `--profile <name>` in automations so a daily incoming run cannot accidentally use an administrator identity.

Framework change incoming must carry deterministic merge anchors. Patch content `sha1` is emitted in `patch_diff_facts`; `related_report_run_ids` is used only when the daily or weekly run id is explicitly known. A weekly run id is provenance only and does not make the weekly package a knowledge materialization candidate. Do not create fuzzy report links on the member side.

Framework change packages must also carry two stable read models. `materials/display/patch_view.json` is the human-facing model for member/admin cards and details: it names the material as 补丁包 and provides a human title, problem, solution, result, project/platform/Android version, UI card text and detail sections. `materials/evidence/patch_ai_facts.json` is the AI/admin evidence model for upload validation, queue fallback review, curation review, search indexing, and merge judgement: it provides concrete module, feature domain, patch behavior goal, code anchors, immutable patch assets, verification targets, search usage, search match class, and merge gate inputs. `adapt` and `reference_only` search decisions are reference evidence only and do not imply a merge decision.

Daily and patch packages consume member-side search usage evidence written by `android-knowledge-search`. Daily packages include same-day search evidence when present. Patch packages prefer explicit capture evidence from `android-framework-patch-capture`, then fall back to same-day member search usage records only when the search record matches the current patch feature anchors such as summary, modified files, symbols, resource keys, settings keys, system properties, or framework log keys. Same member and same day are not enough. These values are development evidence, not curation decisions.

Search facts are not enough for a finished patch. `workflow_contract`, not `implementation_origin`, controls the pre-change search gate. A `current_codex_skill` package must run pre-change knowledge search before source edits and record `reuse`, `adapt`, `reference_only`, `not_applicable`, or `not_found`; if no usable knowledge was found, record `not_found` instead of omitting the evidence. A `validated` current-workflow package without that evidence must stay local and fail the upload gate. If the search has hits, local package check must also fail while the usage decision remains `unknown`; the member-side Codex must close the real decision before upload. A capture package that only carries `unknown` search evidence must not override a same-day member search usage record with an explicit decision.

`implementation_origin` records who wrote the code; `workflow_contract` records how the patch entered AKBS. They are independent facts. A manually written change processed through the current Codex + Skill workflow still uses `workflow_contract=current_codex_skill` and must satisfy its search gate. Only a truthful `manual_import` or `historical_import` may preserve an already-implemented patch with `search_before_change.searched=false`; it keeps verification and patch facts for curation but earns no search usage feedback or reuse score. Never change either field merely to bypass a gate.

Project metadata is part of the knowledge loop, not a cosmetic UI field. Daily packages must write traceable project inference evidence when the day's context contains a TVD/TVE/TVA/TVI project model. Patch packages must prefer explicit `--project` or capture package project evidence, and when a patch is related to a known daily package, `--related-report-run-id` lets the patch inherit that daily project context. If no related report is explicit, patch prepare may automatically use the same member's same-day daily package only when that daily context has exactly one TVD/TVE/TVA/TVI project candidate; ambiguous or missing daily context must keep `project=unknown`. A 7-character company model such as `TVE1213` is incomplete by itself; only when the same inference flow already has trusted platform evidence may the plugin rules module complete the platform letter (`mtk -> M`, `rk -> R`, `unisoc -> U`) and then accept the resulting legal model such as `TVE1213M`. TVI is handled separately: an existing eighth character is preserved, while a short TVI model must complete the TVI chip field (`A/X`) instead of the AKBS platform letter (`R/M/U`). Generic labels such as `android16`, `mtk16`, `Camera2`, source folder names, platform, or Android version must not be written as project names. If no traceable project exists, keep `project=unknown` and record the checked sources and limits in `project_inference`; do not invent a project to make the UI look complete.

If project clues disagree, do not choose the first matching value. When explicit `--project`, capture package metadata, source roots, git branch or remote, WSL source-access registry, README/diff text, or related report context contain multiple different TVD/TVE/TVA/TVI project models, keep `project=unknown`, write every candidate into `project_inference.candidates`, record the conflict in `project_inference.limits`, and downgrade any `validated` package to `candidate`.

If a daily package contains multiple raw candidates that normalize to the same company model, such as `TVE1067M1`, `TVE1067M1_H031`, or `TVE1067M1客户描述`, write the normalized model `TVE1067M1` and keep the complete raw candidates in `project_inference`. Do not truncate it to `TVE1067M`. If candidates normalize to different company models, keep `project=unknown` and preserve the ambiguity.

Platform and Android version metadata are also knowledge applicability boundaries. Framework change packages may only write `platform=mtk`, `platform=rk`, `platform=unisoc`, or `platform=unknown`. Patch filenames or capture packages with `sprd` or `u` aliases normalize to `unisoc`; generic or non-standard prefixes must never become a project（project）or platform（platform）fact. Patch asset filenames must use a legal project（project）prefix or a controlled platform Android-version prefix such as `TVE1067M1-`, `mtk15-`, `rk14-`, or `unisoc16-`; any other uncontrolled prefix fails local package validation and the member must recapture from the correct project/platform worktree. A package with unproven project, platform or Android version cannot be uploaded as `validated`; the member-side Skill must collect the missing facts before upload.

Member-side generation and upload gates call the plugin rules module (`android_framework_ops.knowledge_rules`). This module owns project normalization, platform/Android version parsing, no-common-target aggregate package detection, pre-change knowledge search classification, search usage decision closure checks, patch asset pollution basics, package completeness and immutable-patch checks. It decides facts and gate failures, not curation decisions or knowledge validity. Server upload entrypoints do not load this Codex plugin; they independently verify the submitted contract as the final safety boundary.

A patch package can still be preserved locally when project, platform, or Android version metadata is incomplete, but it must not stay `validated` or be uploaded. Even with PASS verification, if one of those boundaries remains `unknown`, downgrade the local package to `candidate`, clear direct reuse hints and record the reason. The member-side Codex must fix the evidence and regenerate one complete `validated` patch package before upload.

Synthetic profiles are for protocol and server testing only. Set `synthetic_data = true` for that temporary profile. In synthetic mode, `daily` and `weekly` generate random synthetic work items instead of reading real Codex sessions or source changes; `patch` can generate a synthetic framework_change package when no `--patch` is provided.

Real daily and weekly generation requires explicit consent for each report run. The current member request to generate that report is the consent event; derive the exact date window from `--date` and pass `--session-consent` plus only the fields needed for that run. Start with `--session-field work_summary`. Add `project_hint` only when local project context is needed, `command_summary` only when command-derived activity is needed, and `patch_discovery` only when patch discovery is needed; `patch_discovery` also requires `project_hint`. Without an explicit current-run request, do not pass consent flags and do not read sessions, create a package, or send HTTP. Consent is not a persistent profile setting and must not be pre-granted by an unattended recurring automation.

## Commands

Prepare a draft package without submitting:

```bash
python3 "scripts/android_knowledge_intake.py" --profile <member_alias> daily --session-consent --session-field work_summary --prepare
python3 "scripts/android_knowledge_intake.py" --profile <member_alias> weekly --session-consent --session-field work_summary --prepare
```

Submit the latest prepared package:

```bash
python3 "scripts/android_knowledge_intake.py" --profile <member_alias> daily --submit-latest
python3 "scripts/android_knowledge_intake.py" --profile <member_alias> weekly --submit-latest
```

Prepare and submit in one run:

```bash
python3 "scripts/android_knowledge_intake.py" --profile <member_alias> daily --session-consent --session-field work_summary --upload
python3 "scripts/android_knowledge_intake.py" --profile <member_alias> weekly --session-consent --session-field work_summary --upload
```

Explicitly replace an existing daily package for the same member and date:

```bash
python3 "scripts/android_knowledge_intake.py" --profile <member_alias> daily --session-consent --session-field work_summary --prepare --replace-daily-run-id 20260629-210000-daily
```

Explicitly replace an existing weekly package for the same member and week:

```bash
python3 "scripts/android_knowledge_intake.py" --profile <member_alias> weekly --session-consent --session-field work_summary --prepare --replace-weekly-run-id 20260618-090102
```

Prepare a Framework change incoming package without generating a report:

```bash
python3 "scripts/android_knowledge_intake.py" --profile <member_alias> patch --prepare --patch /path/to/rk14-frameworks-base@feature.patch --project "TVE8402M" --summary "功能补丁摘要" --status candidate --workflow-contract current_codex_skill
```

Attach a known daily or weekly run explicitly:

```bash
python3 "scripts/android_knowledge_intake.py" --profile <member_alias> patch --prepare --patch-package /path/to/.codex/patch-packages/20260526-120000-patch --summary "功能补丁摘要" --status candidate --related-report-run-id 20260601-210000-daily
```

Use the related daily run id whenever the patch belongs to a work item already described in that day's report. If the run id is omitted, patch prepare can use the same member's same-day daily package as project evidence only when it contains exactly one project candidate. Without an explicit project, capture project, explicit related daily context, or unique same-day daily context, a patch package may remain `project=unknown`; the server will preserve it, but local curation must treat the missing project as a metadata/evidence gap.

When the patch was packaged by `android-framework-patch-capture`, submit the capture package directory so build, verification, and pre-change search evidence are preserved:

```bash
python3 "scripts/android_knowledge_intake.py" --profile <member_alias> patch --prepare --patch-package /path/to/.codex/patch-packages/20260526-120000-patch --project "TVE8402M" --summary "功能补丁摘要" --status validated
```

When the queue reaches `information_required`, read the exact causal `request_id` and complete the same `patch_package_id`. This creates no new business subject or physical source, cannot change patch bytes, and must return the subject in `information_review`:

```bash
python3 "scripts/android_knowledge_intake.py" --profile <member_alias> patch \
  --inspect-information-request <request-id>

python3 "scripts/android_knowledge_intake.py" --profile <member_alias> patch \
  --complete-information-request /path/to/response.json
```

Submit the latest prepared patch package:

```bash
python3 "scripts/android_knowledge_intake.py" --profile <member_alias> patch --submit-latest
```

Check configuration:

```bash
python3 "scripts/android_knowledge_intake.py" doctor
python3 "scripts/android_knowledge_intake.py" --profile <member_alias> doctor
python3 "scripts/android_knowledge_intake.py" --profile <member_alias> doctor --strict --check-remote
```

## Automation

Member-side submission automations may upload a package that already contains valid consent evidence. Real session-reading prepare runs require a fresh explicit member request and must not receive blanket or persistent consent. With that boundary, useful reminders or guarded automations are:

- 21:00 daily prepare reminder: ask the member to authorize this run before generation.
- 22:30 daily submit: submit the latest pending package.
- Saturday 22:00 weekly prepare reminder: ask the member to authorize this run before generation.
- Saturday 22:30 weekly submit.

Before enabling member-side incoming automations, run `doctor --strict --check-remote` for the exact profile used by the automation. Strict doctor must pass before scheduled runs are enabled. It verifies identity, role, allowed modes, submission API, fixed-IP identity contract, Git availability, plugin freshness, and optional remote reachability. Member upload does not use a token or session cookie; residual credential configuration must never be sent. A local knowledge repository worktree is only an optional fallback for offline search; missing local knowledge fallback must warn, not block HTTP upload.

Member profiles submit only through the AKBS HTTP API. Search should use the AKBS member knowledge-search API first and may fall back to a configured local knowledge repository worktree only when the API is unavailable. SSH/local/Git submission is removed from member setup and must not be used.

Synthetic profiles are only for protocol and gray-flow testing. Use `doctor --strict --allow-synthetic` only in tests; real member incoming automations must keep `synthetic_data = false`.

Framework change submission is available when the member-side Codex can identify a clean change, complete evidence and `validated` status. If validation evidence is missing, preserve it locally as `candidate` or `draft`; do not upload it and do not discard the work. Administrator patch contribution remains manual by default.

Prefer `--patch-package` for Framework changes packaged by `android-framework-patch-capture`; it carries one feature README, one or more repository-level patches, build evidence, verification evidence, pre-change knowledge search evidence, implementation origin and workflow contract. Use `--patch` only when directly packaging one standalone patch file into the current incoming protocol. Direct raw patches default to `workflow_contract=current_codex_skill`; importing a patch that was already implemented outside that workflow requires explicit `--workflow-contract manual_import` or `historical_import`. An older capture package that lacks this field also requires an explicit import contract. Multiple raw `--patch` files are rejected; they must first be converted into function-level patch packages by `android-framework-patch-capture`.

Patch packages are function-scoped, not date-scoped. A package may contain multiple repository-level patches only when they implement the same feature across repo-managed Git repositories. Date-bundled summaries such as “今日补丁合集” or one package containing unrelated features must stop before package generation or upload, with no patch-count exception. Split them into separate function-level patch packages.

If intake asks for text, metadata, logs, screenshots or another non-patch fact, Codex reads the exact information request and prepares an `akbs-patch-package-information-completion/v1` response. The client fetches the request again and binds the authoritative patch-set hash; the response cannot define or override that hash. If the request actually requires changing patch bytes, re-running verification against changed code or splitting the feature, stop the completion flow and regenerate a new complete patch package.

## Member First Setup

When a member needs first-time setup, read `references/member-setup-prompt.md` and give the member the copy-paste prompt. The prompt makes Codex perform 插件更新（plugin update）, 当前配置（current configuration）, 服务器上传入口（server upload endpoint） checks, optional local knowledge fallback checks, and `doctor --strict --check-remote` before any daily, weekly, or patch generation.

The intake script also runs a plugin version gate before `daily`, `weekly`, or `patch` `--prepare`, `--upload`, and `--submit-latest`. It checks three versions: the plugin code running the script, the latest installed Codex plugin cache for `android-framework-ops`, and the GitHub marketplace version when reachable. Git checkouts are compared with their configured upstream; when a clean fast-forward update is possible, the script runs it automatically and then re-executes the current command through the updated script. Packaged Codex plugin installs read `.codex-plugin/plugin.json`; when GitHub marketplace has a newer version, the script upgrades the marketplace source, refreshes the plugin cache, and re-executes the current command through the newest cached script. If Codex already installed a newer plugin but this session still runs an older skill cache, the script first tries the same re-exec path. Only when the updated script cannot be located or the loaded Codex skill instructions still cannot refresh should it stop and tell the member to open or restart the Codex session. Do not continue generating incoming packages with a stale plugin or stale session skill cache.

Before daily, weekly or patch package generation and before queue information completion, the skill must confirm that the running plugin, installed plugin cache, session skill cache and remote plugin version agree. If the latest version cannot be confirmed, stop. Every generated package writes source evidence with the current plugin/skill/cache versions and version check. Admin-side validation uses the source version matrix rather than requiring old packages to equal the newest plugin. The server upload entrypoint is the AKBS HTTP API. Strict doctor does not require a local knowledge repository worktree; that worktree is only an optional offline search fallback.

## Configuration

Configuration is loaded from low to high priority:

1. Built-in defaults.
2. This skill's `config.toml`.
3. `$CODEX_HOME/android-knowledge-intake.toml`.
4. `$CODEX_HOME/report/config.toml`.
5. The current repository's nearest `.codex/report.toml`.
6. Environment variables such as `CODEX_REPORT_PROFILE`, `CODEX_REPORT_MEMBER_ALIAS`, `CODEX_REPORT_MEMBER_NAME`, and `CODEX_REPORT_KNOWLEDGE_REPO_WORKTREE`.

Normal member TOML only stores identity and local paths. Server upload is resolved by the AKBS endpoint resolver and uses the AKBS HTTP API. Admin or test environments may override `CODEX_REPORT_AKBS_ENDPOINT_SUBMISSION_API_BASE_URL`; members do not configure or send upload tokens, session cookies, role claims, or client-IP headers. `member_alias` is required before a member API request, and `knowledge_repo_worktree` is optional local fallback for search, not a server endpoint.

Recommended profile config:

```toml
default_profile = "member_alias"

incoming_schema_version = "1"

[paths]
codex_home = "$CODEX_HOME"
out_dir = "$CODEX_HOME/artifacts/android-knowledge-intake"

[profiles.member_alias]
member_alias = "member_alias"
member_name = "成员姓名"
role = "member"
allowed_modes = ["daily", "weekly", "patch"]
knowledge_repo_worktree = "$CODEX_HOME/worktrees/knowledge"

[profiles.admin_alias]
member_alias = "admin_alias"
member_name = "链路测试"
role = "admin"
allowed_modes = ["patch"]
knowledge_repo_worktree = "$CODEX_HOME/worktrees/knowledge"
```

`allowed_modes` is enforced before prepare/upload/submit. For non-member protocol profiles, `daily` and `weekly` must fail.

## Protocol

Read `references/incoming-package-protocol.md` when changing package generation, upload behavior, or AKBS intake failures.

Read `references/patch-package-status-rules.md` before deciding whether a patch package should stay local/report-only, be regenerated, or be uploaded as `validated`.

Read `references/android-framework-patch-rules.md` before generating patch readmes or validating Android Framework patch content.
