---
name: android-framework-patch-intake
description: "Use when generating, checking, submitting, or completing queue information for one validated Android Framework patch package through AKBS incoming. Do not use for daily reports, weekly reports, or knowledge curation decisions."
---

# Android Framework Patch Intake

Use this member-facing skill for one complete Android Framework 补丁包. It takes a real Framework change or an `android-framework-patch-capture` result and produces one `framework_change` incoming package.

This skill calls the shared member intake kernel in `android-knowledge-intake/scripts/android_knowledge_intake.py` with `patch` mode. Member identity, endpoint resolution, source-version evidence, package validation and upload remain shared with daily and weekly intake.

## Responsibility

The member-side Skill is the primary completeness gate. Before upload it must collect and validate:

- one common functional goal;
- traceable project, platform and Android version;
- clean, immutable patch assets;
- problem, solution, code anchors and applicability;
- PASS build plus device or accepted equivalent verification;
- honest knowledge-search usage facts.

Only a `validated` package enters the server queue. `candidate`, `draft`, `failed` and `blocked` work stays local or in report context until it becomes a complete patch package.

AKBS no longer creates or uploads 原始包、补证包 or 逻辑包. The patch package is the only current business identity.

## Queue fallback

The administrator-side intake Skill independently checks the queued package as a safety fallback:

- complete: admit the same patch package;
- metadata, explanation, log, screenshot or other non-patch evidence missing: ask the member to complete the existing patch package;
- patch bytes must change, the functional goal must split, or the package cannot be trusted: reject intake and ask for a newly generated patch package.

Queue completion never creates another package key. The patch file set and its hash are immutable. Codex may add text, fields or non-patch attachments only after reading the exact open request. Curation starts only after intake admission and decides `new knowledge` or `planned merge`.

## Commands

Generate or submit one complete patch package:

```bash
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> patch --prepare \
  --patch-package /path/to/.codex/patch-packages/<run-id> \
  --project "TVE8402M" \
  --summary "功能补丁摘要" \
  --status validated

python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> patch --submit-latest
```

Read an open queue information request:

```bash
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> patch \
  --inspect-information-request <request-id>
```

Submit a reviewed response for the same patch package:

```bash
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> patch \
  --complete-information-request /path/to/response.json
```

The response uses `schema=akbs-patch-package-information-completion/v1`, the exact `request_id`, optional human `statement`, optional allowed `fields`, and optional non-patch attachments with `relative_path` plus local `source_path`. The client reads the server request again and binds the authoritative patch-set hash itself; callers cannot override it.

## Boundaries

- Use `android-framework-patch-capture` when source changes or patch recapture are required.
- Do not turn an incomplete or mixed-function change into an upload merely by adding prose.
- Do not create a second package to add evidence.
- Do not modify patch files during queue completion.
- Do not decide knowledge merge/new-case outcomes; those belong to administrator curation after intake.
- `adapt` and `reference_only` search decisions are reference evidence, not merge decisions.
