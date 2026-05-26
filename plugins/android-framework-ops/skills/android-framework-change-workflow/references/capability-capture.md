# Capability Capture

Read this near final reporting only when the task may have produced reusable framework engineering capability. Do not use it for ordinary task outcomes.

## Default

Do not summarize or persist capability by default. Most completed tasks should end with the normal final report only.

Do not automatically modify this skill, references, or scripts unless the user explicitly confirms persistence.

## Trigger Threshold

Propose capture only when the task produced reusable process knowledge, not one-off project facts.

Trigger when one or more are true:

- A reusable diagnosis path, implementation pattern, verification path, failure recovery pattern, command sequence, or script idea emerged.
- Existing skill guidance was missing or weak and caused extra investigation, rework, or risk.
- A high-risk framework pitfall was found, such as artifact mismatch, overlay priority, SystemUI restart path, Binder identity, handler/thread context, lock ordering, user/profile scope, boot phase, watchdog, or system_server crash behavior.
- The same requirement, issue, or verification pattern appeared again.
- A generic script, stable command pattern, or artifact check would reduce future mistakes.
- The user explicitly says to remember, reuse, summarize, solidify, or make this the future rule.

Do not trigger for:

- Straightforward edits that followed existing guidance.
- Project-specific facts, private paths, machine names, credentials, raw logs, or temporary device state.
- Unverified guesses or one-off workarounds.
- Routine build/deploy success with no new reusable lesson.

## Scoring

Use this internal score before showing a candidate:

- **Reuse**: likely to help future Android framework tasks.
- **Risk**: forgetting it could cause misdiagnosis, crash, boot/deploy failure, or bad verification.
- **Novelty**: current skill does not already cover it well.
- **Confidence**: conclusion is supported by source, logs, build/deploy evidence, or device verification.

Show a candidate only when `Reuse` is high and at least one of `Risk` or `Novelty` is meaningful, with medium or high confidence.

## Strong Recommendation

Say "I recommend persisting this to the skill" only when one of these is true:

- The same pitfall appeared more than once.
- A skill gap caused clear rework or a wrong first path.
- The lesson concerns high-risk framework mechanisms or delivery/verification paths.
- A generic script or stable command sequence was created.
- The user explicitly asked for future behavior.

Still wait for explicit confirmation before editing the skill.

## Candidate Format

When triggered, append this compact section to the final report:

```text
Skill 改进建议:
- 模式: <可复用的能力/经验>
- 建议存放: <SKILL.md、references/某文件、scripts/某脚本，或新建 reference>
- 原因: <为什么未来会复用/不记会有风险>
- 置信度: high/medium/low
- 是否固化: 等用户确认后再修改 skill。
```

Keep it short. One strong candidate is better than several weak ones.
