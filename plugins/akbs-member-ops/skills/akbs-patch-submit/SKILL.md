---
name: akbs-patch-submit
description: "Use when an AKBS member needs to preflight a capture or read, check, prepare, or submit an Android change package. Supports real legacy Framework change v1 submission, read-only capture-v2 adaptation preflight, and local generic Android change v2 handling; adapter materialization and v2 server submission remain fail-closed while their contracts are disabled."
---

# AKBS Patch Submit

Use this member-facing Skill for Android change packages across application,
platform, native, HAL, kernel, device, and build layers. It owns
`scripts/akbs_patch_submit.py` and has three deliberately separate contract routes.

## Active Install Family

Before reading/checking/preparing a package, preflighting a capture, creating an
archive, or making any server request, run:

```bash
python3 "../akbs-member-setup/scripts/akbs_member_setup.py" preflight-install-family
```

Only a true parser `--help` request may bypass it; a literal `--help` after `--` is
business input and must not bypass the gate. Continue only on exit 0 with JSON
`status=PASS`.

## Contract dispatch

- Legacy `knowledge-incoming-package/1/framework_change` remains readable,
  checkable, and genuinely submittable through the internal incoming v1 kernel.
- Generic `akbs-android-change-package-v2/2/android_change` supports strict local
  read, check, and byte-preserving prepare.
- `android-patch-capture-package-v2/2.0/android_change_capture` is a distinct
  source contract. It supports only explicit `android-change-v2 adapt-capture`
  preflight in Phase 2 and cannot be passed directly to `prepare`.
- Android change v2 server qualification and writer activation are not available.
  A v2 submit attempt fails locally before config loading, plugin freshness
  network access, archive creation, POST, receipt writing, or v1 fallback.
- Every v2 read/check/prepare/submit/adapt-capture action first requires an authoritative,
  target-only active plugin inventory. Missing, malformed, ambiguous, or mixed
  inventory fails closed; `--help` remains available without a business gate.
- Never translate a v2 package or an `android_change_capture` into
  `framework_change` merely to make upload available.

The v2 client outputs are untrusted inputs. The local checker validates schema,
the frozen evidence-profile hash, qualification-input hash, file hashes and sizes,
archive inventory, component bindings, and required evidence groups. A PASS means
`client_semantic_coherence_valid`; it never means server-qualified. Because the
versioned adapter input contracts and server implementations are not frozen, this
Skill never manufactures adapter PASS rows.
Each v2 component must provide the contract's canonical `layer`, `type`,
`partition`, and `ownership` facets. Legacy `change_domain` is not a v2 facet and
is rejected rather than used to infer any canonical value.

## Generic Android change v2

Preflight a validated multi-component capture without network or file writes:

```bash
python3 "scripts/akbs_patch_submit.py" android-change-v2 adapt-capture /path/to/capture
```

The Phase 2 result is intentionally non-zero with `status=BLOCKED` and
`reason_code=android_change_v2_adapter_contracts_unavailable`. The preflight
strictly checks the bundled, hash-pinned Draft 2020-12 capture schema before the
capture's semantic identity and declared/effective
validated status chain, local-only authority, every regular file against the
manifest SHA-256 inventory, patch SHA-1 bytes, `components[]`,
`primary_component_id`, repository and patch `component_ids[]`, evidence and
qualification bindings. It emits their hashes and structured gaps to stdout,
but creates no canonical v2 package, client-adapter output, receipt, or PASS.
Only after Phase 4 activates the per-group versioned adapter input contracts may
the adapter create a new hash-bound target artifact for `check` and `prepare`.

Read only the manifest identity and component layers:

```bash
python3 "scripts/akbs_patch_submit.py" android-change-v2 read /path/to/package
```

Check the complete directory, including exact file inventory and hashes:

```bash
python3 "scripts/akbs_patch_submit.py" android-change-v2 check /path/to/package
```

After a successful check, preserve the exact package bytes under
`$CODEX_HOME/artifacts/akbs-member-ops/android-change-v2/pending/`:

```bash
python3 "scripts/akbs_patch_submit.py" android-change-v2 prepare /path/to/package
```

The following command is an explicit writer-off probe and currently returns a
non-zero result with `reason_code=android_change_v2_writer_off` and zero submission
side effects:

```bash
python3 "scripts/akbs_patch_submit.py" android-change-v2 submit /path/to/package
```

## Legacy Framework change v1

Prepare a validated v1 package only from a legacy v1-compatible Framework capture:

```bash
python3 "scripts/akbs_patch_submit.py" --profile <member_alias> --prepare \
  --patch-package /path/to/capture \
  --project "TVE8402M" --platform rk --android-version 14 \
  --summary "功能补丁摘要" --status validated
```

Submit the latest v1 pending package through the real incoming HTTP route:

```bash
python3 "scripts/akbs_patch_submit.py" --profile <member_alias> --submit-latest
```

Queue information completion remains attached to the same server-assigned
`patch_package_id`. Read a request with `--inspect-information-request <request-id>`
and answer it with `--complete-information-request /path/to/response.json`.
Patch bytes and their hash stay immutable; completion may add only the allowed
text, fields, and non-patch attachments bound to that causal `request_id`.

## Boundaries

- Use `$android-patch-capture` when source changes or recapture are required,
  then run the explicit `adapt-capture` preflight. Do not feed that capture
  directory directly to `prepare` and do not route it through v1.
- Use `$akbs-knowledge-search` before implementation and record the honest reuse
  decision; search evidence is not a curation merge decision.
- Keep one functional goal per package and never upgrade incomplete evidence by
  prose or by relabeling the package contract.
- Do not decide new-case or merge outcomes. Administrator curation owns those
  decisions after intake.
- The deprecated `$android-framework-patch-intake` and
  `android_knowledge_intake.py ... patch` surfaces are compatibility-only thin
  forwarders for v1-era calls.
