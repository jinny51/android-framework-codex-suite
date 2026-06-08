# Patch Package Status Rules

Daily work is always recorded. Framework change upload is package-status based. These statuses describe the member-side incoming package and its evidence quality; they are not curation decisions and do not decide whether anything enters the knowledge repository.

## Status

- `validated`: clear scope, clean diff, build pass, and device or accepted equivalent verification pass.
- `candidate`: clear implementation evidence, but validation or acceptance evidence is incomplete.
- `draft`: partial or WIP implementation evidence.
- `failed`: failed implementation or failed verification retained as negative evidence.
- `blocked`: blocked work retained with cause, checked paths, and missing external condition.

## Default Policy

- No completed patch: record daily/weekly trace with `work_findings`.
- Clear patch without validation evidence: upload as `candidate` or `draft`.
- Patch with build and accepted device/equivalent verification: upload as `validated`.
- Known failure: upload as `failed` when it helps future AI avoid repeating the path.
- Blocked work: record as `blocked` when the missing condition is explicit.
- Stop patch upload only for sensitive material, mixed unrelated diffs, unclear task boundaries, or high-risk misleading reuse hints.

The user's local curation maintainer skill later reads the database repository and knowledge repository to produce the curation decision.

## Evidence Keywords

Treat these as validation signals when found in Codex sessions:

- 编译通过
- 验证通过
- 已验证
- 已交付
- 已合入
- 客户复测通过
