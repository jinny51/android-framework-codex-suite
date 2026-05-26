# Capability Capture

Use this reference only while preparing the final report after a task that may have produced reusable build/deploy executor knowledge.

## Default

Do not output a capture summary by default. Do not automatically modify `SKILL.md`, references, or scripts. Persist only after the user explicitly confirms.

## Trigger Conditions

Consider a capture only when at least one applies:

- A reusable step, command sequence, check, or decision rule was discovered.
- The current skill did not cover a case, causing rework or temporary judgment.
- A high-risk pitfall appeared where forgetting it could cause build failure, deploy failure, device instability, data loss, or false verification.
- The same problem pattern appeared for the second time.
- The user explicitly says to remember it, do it this way in the future, or capture it.
- A general script, stable command sequence, or reusable artifact check was written or proven.

Strongly recommend persistence, while still waiting for confirmation, when one applies:

- The same pitfall appeared for the second time.
- A skill gap caused clear rework.
- The pattern affects high-risk build/deploy/verification handoff paths.
- A general script or stable command sequence was added.
- The user explicitly asked future work to follow this rule.

## Scoring

Internally score before output:

- `Reuse`: Will this apply across future Android build/deploy tasks?
- `Risk`: Would forgetting it create build, deploy, device, data, or verification risk?
- `Novelty`: Is it missing from the current skill or project memory model?
- `Confidence`: Is there enough evidence from this task?

Output a candidate only when `Reuse` is true, at least one of `Risk` or `Novelty` is meaningful, and `Confidence` is medium or high. Use low confidence only when the user explicitly asks to capture an emerging idea.

## Preferred Capture Areas

Favor patterns about:

- remote build profiles, module selection, and profile repair
- artifact names, locations, freshness checks, and artifact-not-effective diagnosis
- artifact-to-device destination mapping
- push, remount, reboot, wait-boot, and process restart strategy
- build failure signatures and focused diagnosis entry points
- device delivery evidence and executor handoff evidence
- missing executor scripts or reusable command sequences

## Do Not Capture

Never capture:

- one-time project facts
- private local or remote paths, server names, IPs, usernames, device serials, or credentials
- raw build logs, logcat, dumpsys, screenshots, recordings, or large command output
- temporary device state
- unverified guesses
- feature-specific framework behavior requirements that belong in the active conversation or `android-framework-change-workflow`

Generalize sensitive examples before proposing persistence.

## Store-In Guidance

- `SKILL.md`: core executor workflow rule, boundary, trigger, or output contract.
- `references/<topic>.md`: nuanced failure pattern, diagnosis checklist, deploy/restart guidance, or decision table.
- `scripts/<name>.sh`: stable command sequence or deterministic check that should be reused.
- New reference: use when a pattern cluster is useful but too detailed for `SKILL.md`.

## Output Format

Append only when triggered, at the very end of the final report. Use Chinese labels by default:

```text
Skill 改进建议:
- 模式: <可复用的能力/经验>
- 建议存放: <SKILL.md、references/file.md、scripts/script.sh，或新建 reference>
- 原因: <为什么未来会复用，或为什么忘记会有风险>
- 置信度: high|medium|low
- 是否固化: 等用户明确确认后再修改 skill。
```

Keep it short. One candidate is usually enough; use multiple only when the task produced clearly distinct reusable capabilities.
