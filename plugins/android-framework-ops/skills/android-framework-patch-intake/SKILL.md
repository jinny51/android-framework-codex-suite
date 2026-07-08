---
name: android-framework-patch-intake
description: "Use when generating, replacing, checking, or submitting Android Framework original patch packages, evidence supplement packages, or patch asset correction packages through AKBS incoming. Do not use for daily reports, weekly reports, or knowledge curation decisions."
---

# Android Framework Patch Intake

Use this member-facing skill for 原始补丁包、补证包、替换包 and 补丁资产修正 package submission. It takes a real Framework change or an `android-framework-patch-capture` package and produces a `framework_change` incoming package.

This skill is an entrypoint, not a separate upload implementation. It routes to the shared member intake kernel in `android-knowledge-intake/scripts/android_knowledge_intake.py` with `patch` mode, so member identity, server submission, manifest protocol, replacement metadata, plugin version gate, session cache gate, local validation, project/platform/Android version checks, and supplement relationship checks remain shared with daily and weekly intake.

## Boundary

- Owns member-side `framework_change` incoming generation, original patch package upload, evidence supplement package upload, replacement metadata, `materials/display/patch_view.json`, and `materials/evidence/patch_ai_facts.json`.
- Uses `android-framework-patch-capture` for real feature capture when there are source changes or patch asset corrections.
- Does not generate daily reports, weekly reports, administrator summaries, curation decisions, database writes, knowledge repository writes, or UI changes.

## Rules

Ordinary patch packages and evidence supplements must be `validated`: function boundary is clear, project/platform/Android version are traceable, patch assets are clean, and build plus device or accepted equivalent verification passed.

补证包（evidence supplement package） must link to the original package with `--supplement-for-package-key`. Do not wrap a supplement around another supplement. If the original package is a no-common-target aggregate package or date-bundled patch set, split and upload new function-level original packages instead.

`adapt` and `reference_only` search decisions are reference evidence only. They must not imply a merge decision. Curation decisions belong to the admin-side local skill.

## Commands

```bash
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> patch --prepare \
  --patch-package /path/to/.codex/patch-packages/<run-id> \
  --project "TVE8402M" \
  --summary "功能补丁摘要" \
  --status validated

python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> patch --submit-latest
```

Evidence supplement example:

```bash
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> patch --prepare \
  --patch-package /path/to/.codex/patch-packages/<run-id> \
  --project "TVE1067M" \
  --platform mtk \
  --android-version 16 \
  --summary "补充验证证据" \
  --status validated \
  --supplement-for-package-key 20260612/lincong/20260612-172836-patch \
  --supplement-reason "补充验证证据"
```

Lightweight field correction example for project/platform/Android version gaps:

```bash
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> patch --prepare \
  --supplement-for-package-key 20260702/lincong/20260702-193308-patch \
  --supplement-mode field_correction \
  --corrected-field project=TVI3315A \
  --corrected-field platform=rk \
  --corrected-field android_version=14 \
  --correction-reason "管理端提示项目名缺失，按成员可追溯字段补证" \
  --summary "补充 TVI3315A 项目字段" \
  --status validated
```

Field correction packages do not include patch diff, verification, search evidence, `patch_ai_facts`, material name, or material summary. Supplements inherit the target original package material identity. If the material name or material summary is wrong, regenerate a replacement original package instead of using field correction. If the missing item is verification, patch asset, local-check, `patch_ai_facts`, or polluted diff, rerun `android-framework-patch-capture` from a clean source tree and submit an asset correction supplement.
