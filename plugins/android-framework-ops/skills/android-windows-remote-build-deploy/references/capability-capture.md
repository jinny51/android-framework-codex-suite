# Capability Capture

Use this reference only while preparing the final report after an `android-windows-remote-build-deploy` task that may have produced reusable Windows-native remote build/deploy executor knowledge.

## Default

Do not output a capture summary by default. Do not automatically modify `SKILL.md`, references, or scripts. Persist only after the user explicitly confirms.

## Trigger Conditions

Consider a capture only when at least one applies:

- A reusable remote SSH/session step, command sequence, check, or decision rule was discovered.
- The current skill did not cover a case, causing rework or temporary judgment.
- A high-risk pitfall appeared where forgetting it could cause source corruption, build failure, deploy failure, device instability, data loss, or false verification.
- The same problem pattern appeared for the second time.
- The user explicitly says to remember it, do it this way in the future, or capture it.
- A general PowerShell helper, remote Bash payload, stable command sequence, or reusable artifact check was written or proven.

Strongly recommend persistence, while still waiting for confirmation, when one applies:

- the same pitfall appeared for the second time
- a skill gap caused clear rework
- the pattern affects high-risk source operation, build/deploy, device, or verification handoff paths
- a general script or stable command sequence was added
- the user explicitly asked future work to follow this rule

## Scoring

Internally score before output:

- `Reuse`: Will this apply across future Windows-native Android remote build/deploy tasks?
- `Risk`: Would forgetting it create source, build, deploy, device, data, or verification risk?
- `Novelty`: Is it missing from the current skill or project memory model?
- `Confidence`: Is there enough evidence from this task?

Output a candidate only when `Reuse` is true, at least one of `Risk` or `Novelty` is meaningful, and `Confidence` is medium or high. Use low confidence only when the user explicitly asks to capture an emerging idea.

## Preferred Capture Areas

Favor patterns about:

- persistent remote `tmux` sessions and command-log recovery
- Windows PowerShell to remote Linux SSH boundaries
- UTF-8 no-BOM stdin/stdout handling for remote shell payloads
- remote-only source search/read/write/patch/git/repo/build rules
- remote build profiles, module selection, and profile repair
- artifact names, locations, freshness checks, and artifact-not-effective diagnosis
- Windows SMB mapping as artifact-pickup-only
- local `adb.exe` push, remount, reboot, wait-boot, and process restart strategy
- build failure signatures and focused diagnosis entry points
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
- `scripts/<name>.ps1`: stable Windows-local helper or deterministic check that should be reused.
- `scripts/<name>.sh`: remote Linux payload executed only through SSH or the persistent remote session.
- New reference: use when a pattern cluster is useful but too detailed for `SKILL.md`.

## Output Format

Append only when triggered, at the very end of the final report. Use Chinese labels by default:

```text
Skill 改进建议:
- 模式: <可复用的能力/经验>
- 建议存放: <SKILL.md、references/file.md、scripts/script.ps1，或新建 reference>
- 原因: <为什么未来会复用，或为什么忘记会有风险>
- 置信度: high|medium|low
- 是否固化: 等用户明确确认后再修改 skill。
```

Keep it short. One candidate is usually enough; use multiple only when the task produced clearly distinct reusable capabilities.
