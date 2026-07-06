# Capability Capture

Use this reference only at the end of an `android-windows-source-access` task when deciding whether to surface reusable source-access learning. Default behavior is to say nothing about capability capture.

## Trigger

Append a `Skill 改进建议` only when the completed task produced at least one reusable outcome:

- a repeatable Windows SMB drive or UNC mapping workflow, restore sequence, check, or judgment rule
- a diagnostic pattern for SMB, SSH, credentials, mapped drives, UNC paths, registry files, remote source identity, or local artifact-pickup failures
- a verification method that prevents wrong mappings, wrong local paths, stale registry use, credential leakage, or platform/project misclassification
- a skill gap that caused rework, unclear decisions, or temporary logic
- a high-risk pitfall that could later cause build failure, deploy failure, data loss, credential exposure, or misjudgment
- a problem pattern that appeared for the second time
- an explicit user instruction such as "记住这个", "以后都这样", or "记录一下"
- a new generic script, stable command sequence, or reusable artifact/mapping check

Do not append a candidate for routine success, one-off project facts, private paths, temporary server state, raw logs, credentials, or unverified guesses.

## Scoring

Internally score the candidate before mentioning it:

- `Reuse`: Will this apply across future Windows source mapping or recovery tasks?
- `Risk`: Would forgetting it create meaningful mapping, credential, build/deploy handoff, or data risk?
- `Novelty`: Is it missing or under-specified in the current skill?
- `Confidence`: Is it backed by this task's evidence?

Only surface a candidate when `Reuse` is high and at least one of `Risk` or `Novelty` is meaningful, with medium or high `Confidence`. When unsure, omit it.

## Strong Suggestion Cases

It is acceptable to say "我建议固化到 skill" only when one of these is true:

- the same pitfall appeared for the second time
- a skill gap caused obvious rework
- the lesson affects high-risk mapping safety, credential handling, registry recovery, or build/deploy handoff behavior
- a generic script or stable command sequence was added
- the user explicitly asked future runs to follow the rule

Still wait for explicit user confirmation before editing the skill.

## Focus Areas

Prefer candidates about:

- Windows SMB drive and UNC mapping shapes
- account-level registry and credential-file behavior
- remote path normalization and source-based platform/project recognition
- local artifact-pickup-only boundaries
- SSH reachability and remote source marker checks
- checks that prevent using Windows SMB mapped paths for source search, source edits, git, repo, or builds
- UTF-8 and PowerShell parsing rules that prevent recurring Windows-side failures

Avoid candidates about:

- concrete private credentials
- one-time machine IP, drive letter, device state, or temporary server state
- specific private paths except anonymized examples
- raw logs or large command output
- guesses that were not verified

## Output Format

Append only when triggered, at the very end of the final report:

```text
Skill 改进建议:
- 模式: <可复用的能力/经验>
- 建议存放: <SKILL.md、references/file.md、scripts/script.ps1，或新建 reference>
- 原因: <为什么未来会复用，或为什么忘记会有风险>
- 依据完整度: high|medium|low
- 是否固化: 等用户明确确认后再修改 skill。
```

Keep it short. One candidate is usually enough; use multiple only when the task produced clearly distinct reusable capabilities.
