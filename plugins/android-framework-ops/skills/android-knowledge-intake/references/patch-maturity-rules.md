# Patch Maturity Rules

Daily work is always recorded. Patch upload is maturity-based.

## Status

- `draft`: unfinished or unverified; process evidence only, not recommended for reuse.
- `candidate`: implemented, waiting for device/customer validation.
- `validated`: compiled and verified; can be reused with caveats.
- `released`: delivered or merged; preferred reuse candidate.
- `buggy`: known bug; retained for history but not recommended.

## Default Policy

- No patch or only messy local experiment: record work, do not upload patch.
- Patch without validation evidence: upload as `draft` with `reusable=false`.
- Patch with compile or verification evidence: upload as `candidate` or `validated`.
- Patch with known failure: upload as `buggy` only if it is useful as process evidence.

## Evidence Keywords

Treat these as validation signals when found in Codex sessions:

- 编译通过
- 验证通过
- 已验证
- 已交付
- 已合入
- 客户复测通过

