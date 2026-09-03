---
name: android-knowledge-intake
description: "Deprecated compatibility router for the internal AKBS incoming v1 kernel. Use only for an existing doctor, daily, weekly, or patch CLI invocation."
---

# Android Knowledge Intake Compatibility

`scripts/android_knowledge_intake.py` forwards unchanged arguments and exit status to
`internal/incoming-v1/scripts/akbs_member_intake.py`. It recognizes only the frozen
incoming v1 `doctor`, `daily`, `weekly`, and `patch` routes; unknown business actions
fail closed. Use `$akbs-member-setup`, `$akbs-daily-report`, `$akbs-weekly-report`, or
`$akbs-patch-submit` for new work.

Do not add implementation modules, configuration writers, or a second incoming kernel
to this compatibility Skill.
