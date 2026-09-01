---
name: android-member-setup
description: "Use when an Android engineering member needs first setup, profile configuration guidance, doctor checks, plugin/cache freshness diagnosis, or endpoint health verification. Do not use for daily/weekly generation, patch submission, knowledge search, or curation."
---

# Android Member Setup

Use this Skill for member identity and local client readiness. It owns first-setup
guidance, the selected `member_alias`/`member_name` profile, doctor checks, plugin and
session-cache freshness, and AKBS endpoint health. It does not generate or submit daily,
weekly, or patch packages.

For first setup, read the existing canonical prompt at
`../android-knowledge-intake/references/member-setup-prompt.md`. That shared-kernel
location remains the single source; do not duplicate member configuration rules.

Run strict doctor for the exact member profile before enabling report or patch automation:

```bash
python3 "scripts/android_member_setup.py" doctor \
  --profile <member_alias> \
  --strict \
  --check-remote
```

The member profile supplies `member_alias`; do not derive it from Git author, invent an
alias, or ask ordinary members to configure server tokens, cookies, roles, database
paths, or client-IP headers. `android-knowledge-intake` remains the backward-compatible
CLI and shared incoming v1 kernel.
