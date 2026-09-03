---
name: jinny-android-coding-practices
description: "Use only when android-change-workflow explicitly resolved the Jinny coding capability. Return a coding-policy-decision-v1 with optional non-conflicting naming or review recommendations; never modify source or relax android-change-policy."
---

# Jinny Android Coding Practices

This is a decision-only optional provider Skill. The controller supplies `run_id`,
`stage_id`, `context_sha256`, `core_policy_sha256`, workflow action, component layer,
and the bounded scope. Return only `coding-policy-decision-v1`.

Never edit source, spawn a worker, acquire a lock, run a side effect, upload, accept a
Gate, or announce final acceptance. Never return an override or exception to
`android-change-policy`; recommendations are additive only.

Use `scripts/jinny_coding_policy.py` to produce the bound decision. It computes the
installed provider manifest SHA-256 itself. The controller must validate the result
against its packaged `coding-policy-decision-v1` schema before applying it.

The bounded advisory is part of this hash-bound Skill, rather than an unbound runtime
reference. Recommend `legacy_jinny_style` only when the selected provider configuration
and current request make it applicable:

- helper methods may use a suffix derived from the controller-resolved `member_alias`;
- two or more feature helpers may be grouped in a same-package alias-derived `Utils` type;
- review or project conventions must be concrete and non-conflicting.

Never hardcode an example person's alias. Mandatory identity, paired markers, domain
safety, resources, evidence, and historical-author behavior come only from the canonical
policy. Every returned rule uses `effect=recommend`.
