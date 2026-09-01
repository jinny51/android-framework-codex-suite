---
name: android-change-policy
description: "Use when implementing, modifying, reviewing, importing, or packaging Android changes that are archived as patches. Enforces the canonical member-bound attribution contract for all Android change domains and the Framework logging, debug-property, resource, and feature-material overlay only for Framework changes."
---

# Android Change Policy

Use this skill as the public entrypoint to the core plugin's canonical engineering
change policy. It is a policy layer, not a second change workflow and not a patch
packager.

## Required Contract

Before editing or judging Android source, read both files completely:

- `../../contracts/android-change-policy/v1/README.md`
- `../../contracts/android-change-policy/v1/policy.json`

The JSON contract is authoritative. Do not reproduce or reinterpret it in another
Skill, project note, prompt, or generated evidence file.

## Apply the Correct Layer

- Apply `universal_patch_archive` to every Android change that will be preserved as
  patches.
- Apply the `framework` overlay only when the changed code belongs to the Framework
  domain. Do not impose FrameworkLog or Framework debug-property rules on App, HAL,
  native, kernel, driver, device, or build code.
- Apply `legacy_jinny_style` only when the user explicitly requests the old Jinny
  naming preference. It is advisory and cannot replace mandatory core rules.

## Identity and Markers

Select an existing member profile, normally through `android-member-setup`. Resolve
the identity only from that profile's `member_alias`; never derive it from Git author,
an example name, an invented alias, or a ticket number.

For new Codex-authored code in files that support slash line comments, add the markers
while implementing the change:

```text
//<member_alias> <yyyyMMdd>@{
...
//<member_alias> <yyyyMMdd>@}
```

Use a pair even for one changed line. Opening and closing alias/date values must match,
and the date must be a real calendar date. Do not insert `//` into XML, shell,
properties, make, or another syntax that does not support it. Until a versioned
comment adapter exists, record that file as not applicable to the slash-marker check;
do not break its syntax.

## Source Origin

- `codex`: every applicable changed file uses the current profile's paired marker.
- `mixed`: preserve historical markers and add at least one paired marker for the
  current member's Codex-authored part.
- `manual`, `external`, or `historical`: preserve original authorship. Legacy markers
  may be observed for compatibility; never rewrite them to the submitting member.

Do not invent missing identity or requirement metadata. A manual or historical local
draft with missing markers may remain `WARN`; it is not policy-compliant and cannot be
upgraded by wording alone.

## Workflow Boundary

Apply policy during implementation. `android-framework-patch-capture` verifies the
same contract per changed file and writes versioned `coding-standard-check.json`
evidence. Raw patch intake runs the same canonical parser before creating an incoming
directory. Do not hand-edit generated evidence to turn a failure into a pass.
