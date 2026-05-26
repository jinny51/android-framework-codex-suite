# Capability Capture

Use this reference only at the end of an `android-wsl-source-access` task when
deciding whether to surface a reusable learning. Default behavior is to say
nothing about capability capture.

## Trigger

Append a `Skill 改进建议` only when the completed task produced at
least one of these reusable outcomes:

- a repeatable mount or restore workflow, command sequence, check, or judgment rule
- a diagnostic pattern for Samba/CIFS, SSH, sudo, credentials, network, source-root recognition, project registry, or reboot recovery failures
- a verification method that prevents wrong mounts, wrong local paths, hidden files, stale registry use, or platform/project misclassification
- a skill gap that caused rework, unclear decisions, or temporary logic
- a high-risk pitfall that could later cause build failure, deploy failure, device trouble, data loss, credential exposure, or misjudgment
- a problem pattern that appeared for the second time
- an explicit user instruction such as "记住这个", "以后都这样", or "记录一下"
- a new generic script, stable command sequence, or reusable artifact check

Do not append a candidate for routine success, one-off project facts, private
paths, temporary device/server state, raw logs, credentials, or unverified
guesses.

## Scoring

Internally score the candidate before mentioning it:

- `Reuse`: Will this apply across future mount/recovery tasks?
- `Risk`: Would forgetting it create meaningful risk?
- `Novelty`: Is it missing or under-specified in the current skill?
- `Confidence`: Is it backed by this task's evidence?

Only surface a candidate when `Reuse` is high and at least one of `Risk` or
`Novelty` is meaningful, with medium or high `Confidence`. When unsure, omit it.

## Strong Suggestion Cases

It is acceptable to say "我建议固化到 skill" only when one of these is true:

- the same pitfall appeared for the second time
- a skill gap caused obvious rework
- the lesson affects high-risk delivery, verification, mount safety, credentials, or recovery behavior
- a generic script or stable command sequence was added
- the user explicitly asked future runs to follow the rule

Still wait for explicit user confirmation before editing the skill.

## Focus Areas

Prefer candidates about:

- project-level mount and restore shapes
- Samba/CIFS options and share discovery or creation rules
- remote path normalization and source-based platform/project recognition
- remembered project registry behavior
- reboot/Codex-restart recovery
- local/remote sudo, SSH, network, password, and credential failure signatures
- checks that prevent parent-share mounts, wrong local folders, or hiding local files

Avoid candidates about:

- concrete private credentials
- one-time machine IP or device state
- specific private paths except anonymized examples
- raw logs or large command output
- guesses that were not verified

## 最终报告块

触发时，在最终报告末尾追加这个固定块：

```text
Skill 改进建议:
- 模式: <可复用的能力/经验>
- 建议存放: <SKILL.md、references/某文件、scripts/某脚本，或新建 reference>
- 原因: <为什么未来会复用/不记会有风险>
- 置信度: high/medium/low
- 是否固化: 等用户确认后再修改 skill。
```

保持简短。不要包含凭据、原始 log、一次性机器状态或一次性项目事实。
