---
name: android-knowledge-merge-review
description: "Use when an AKBS member needs to list, inspect, compare, analyze, or explicitly dispute a server-provided knowledge merge confirmation. Do not use for ordinary knowledge search, administrator curation decisions, or patch submission."
---

# Android Knowledge Merge Review

Use this skill for the member side of an existing AKBS merge-confirmation event. The
server-provided `confirmation_id` is the causal event identifier;
`patch_package_id` remains the patch business subject and `package_key` remains source
provenance only.

Read-only actions are `list`, `detail`, `target`, `compare`, and `analyze`. They must use
the member merge-confirmation API and must fail clearly when it is unavailable. Never
replace a failed server read with local knowledge search or fabricate merge evidence.

`dispute` is an external write. Send it only when the user explicitly asks to submit an
objection, `--send-dispute` is present, and a reason or member assessment is supplied.
Reading or analyzing a confirmation does not authorize a dispute.

## Commands

```bash
python3 "scripts/android_knowledge_merge_review.py" list

python3 "scripts/android_knowledge_merge_review.py" analyze \
  --confirmation-id <confirmation_id>

python3 "scripts/android_knowledge_merge_review.py" dispute \
  --confirmation-id <confirmation_id> \
  --send-dispute \
  --dispute-reason "目标知识没有覆盖当前补丁的功能目标"
```

The existing `android-knowledge-search --merge-confirmation ...` commands remain as
backward-compatible entrypoints. This Skill is the user-facing owner of the merge-review
intent; it does not decide whether AKBS creates or merges knowledge.
