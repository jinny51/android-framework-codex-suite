# Android Knowledge V2 Rebuild Implementation Plan

**Goal:** Rebuild the Android team knowledge system around V2 knowledge events, evidence, patch analysis, generated views, and plugin-marketplace member workflows.

**Architecture:** The server knowledge repository remains the authority. `knowledge-events/` becomes the durable source of truth; `daily/`, `weekly/`, `patches/by-id/`, `index/`, and `site/` become generated views. Member and maintainer tools come from the `android-framework-ops` Codex marketplace plugin.

**Tech Stack:** Python 3 standard library, Git, JSON/JSONL, SQLite, existing static HTML/CSS/JS site, Codex marketplace plugin skills.

---

## Current Paths

Android Framework Codex suite plugin source:

```text
<android-framework-codex-suite checkout root>
```

Use the checkout of `github.com/jinny51/android-framework-codex-suite` that contains `manifests/android-framework-ops.toml`. Local parent directory names are not part of the architecture.

Knowledge administrator worktree:

```text
/mnt/c/Users/jinny/Documents/Codex/worktrees/knowledge-jinny
```

Knowledge test worktree:

```text
/mnt/c/Users/jinny/Documents/Codex/worktrees/knowledge-test
```

Server authority:

```text
test35:/home/test35/work/knowledge
test35:/home/test35/work/knowledge/remote.git
test35:/home/test35/work/knowledge/worktree
```

Do not base this design on legacy local sync paths or member-local skill directories. Those may exist for compatibility or unrelated maintenance, but they are not the Android Framework main-chain distribution model.

## Scope Split

This rebuild is too large for one code batch. Execute it in phases:

1. V2 schema and patch analysis foundation.
2. Incoming V2 normalization and generated daily/weekly compatibility views.
3. Historical V2 migration with patch-content analysis.
4. Index and search redesign around events and evidence.
5. Site UI redesign around events, patch assets, evidence, and quality.
6. Plugin workflow updates for marketplace-installed `android-framework-ops`.
7. Simulated gray testing, then real member gray testing.

Each phase must be independently testable and commit-worthy.

## Files By Responsibility

### Knowledge Server Repository

Create or modify these files in `/mnt/c/Users/jinny/Documents/Codex/worktrees/knowledge-jinny`:

```text
docs/knowledge-v2-schema.md
docs/knowledge-v2-migration-report-template.md
scripts/knowledge_pipeline/patch_analysis.py
scripts/knowledge_pipeline/incoming_v2.py
scripts/knowledge_pipeline/normalize_v2.py
scripts/process_incoming.py
scripts/import_history_staging.py
scripts/build_index.py
site/index.html
site/patches.html
site/reports.html
site/symbols.html
tests/test_patch_analysis_v2.py
tests/test_incoming_v2_validation.py
tests/test_v2_materialized_views.py
tests/test_historical_v2_migration.py
tests/test_build_index_v2_analysis.py
tests/fixtures/patch_analysis/
tests/fixtures/incoming_v2/
```

### Plugin Source Repository

Create or modify these files in the `android-framework-codex-suite` checkout:

```text
docs/knowledge-v2-architecture.md
plugins/android-framework-ops/skills/android-knowledge-intake/SKILL.md
plugins/android-framework-ops/skills/android-knowledge-intake/references/incoming-package-protocol.md
plugins/android-framework-ops/skills/android-knowledge-intake/scripts/android_knowledge_intake.py
plugins/android-framework-ops/skills/android-knowledge-intake/tests/test_patch_capture_ingest.py
plugins/android-framework-ops/skills/android-framework-patch-capture/SKILL.md
plugins/android-framework-ops/skills/android-framework-patch-capture/references/package-contract.md
plugins/android-framework-ops/skills/android-framework-patch-capture/scripts/capture_framework_patch.py
plugins/android-framework-ops/skills/android-framework-patch-capture/tests/test_capture_framework_patch.py
plugins/android-framework-ops/skills/android-knowledge-search/SKILL.md
plugins/android-framework-ops/skills/android-knowledge-search/references/search-contract.md
plugins/android-framework-ops/skills/android-knowledge-search/scripts/android_knowledge_search.py
plugins/android-framework-ops/skills/android-knowledge-search/tests/test_android_knowledge_search_v2.py
plugins/android-framework-ops/skills/android-framework-change-workflow/SKILL.md
plugins/android-framework-ops/skills/android-framework-change-workflow/references/requirements-implementation.md
```

## Phase 1: Freeze V2 Schema And Quality Contract

**Files:**

- Modify: `docs/knowledge-v2-architecture.md`
- Create: `/mnt/c/Users/jinny/Documents/Codex/worktrees/knowledge-jinny/docs/knowledge-v2-schema.md`

- [ ] **Step 1: Copy the final architecture decisions into the server repo schema doc**

  The server schema doc must define:

  ```text
  source.origin: incoming, maintainer_manual, historical_import, synthetic_test
  package_kind: daily_trace, weekly_trace, session_trace, framework_change, patch_contribution, reuse_decision
  channel: light, strict
  quality: imported, trace, candidate, validated, released, buggy
  evidence kinds: source, codex_sessions, historical_source, legacy_archive, legacy_readme, patch_diff_facts, patch_problem_inference, risk_surface, changed_files, search_before_change, verification_result, device_verification, equivalent_verification, package_check
  ```

- [ ] **Step 2: Record the hard validation rules**

  Add these rules to `docs/knowledge-v2-schema.md`:

  ```text
  light events may use imported, trace, candidate.
  strict events may use imported, candidate, validated, released, buggy.
  validated requires PASS device verification or accepted equivalent verification evidence.
  imported historical patches must not be upgraded by inference alone.
  patch-derived facts and patch-derived inferences must remain separate.
  ```

- [ ] **Step 3: Verify the schema doc has no unresolved markers**

  Run:

  ```bash
  python3 - <<'PY'
  from pathlib import Path

  needles = ["T" + "BD", "TO" + "DO", "FIX" + "ME", "?" + "?", "place" + "holder", "待" + "定", "待" + "补"]
  text = Path("docs/knowledge-v2-schema.md").read_text(encoding="utf-8")
  hits = [(needle, text.find(needle)) for needle in needles if needle in text]
  if hits:
      raise SystemExit(f"unresolved markers found: {hits}")
  PY
  ```

  Expected: no output and exit code 0.

## Phase 2: Add Deterministic Patch Analysis

**Files:**

- Create: `/mnt/c/Users/jinny/Documents/Codex/worktrees/knowledge-jinny/scripts/knowledge_pipeline/patch_analysis.py`
- Create: `/mnt/c/Users/jinny/Documents/Codex/worktrees/knowledge-jinny/tests/test_patch_analysis_v2.py`
- Create: `/mnt/c/Users/jinny/Documents/Codex/worktrees/knowledge-jinny/tests/fixtures/patch_analysis/frameworks-base-focus.patch`

- [ ] **Step 1: Add the fixture patch**

  The fixture patch should modify at least:

  ```text
  frameworks/base/services/core/java/com/android/server/wm/ActivityTaskManagerService.java
  frameworks/base/services/core/java/com/android/server/wm/WindowState.java
  ```

  Include added lines that mention focus handling, resumed activity, and a log tag. The test fixture must be small and synthetic so it can be committed safely.

- [ ] **Step 2: Write tests for direct facts**

  `tests/test_patch_analysis_v2.py` must assert that `analyze_patch_text()` returns:

  ```text
  modified_files includes both fixture files
  modules includes WindowManager
  symbols includes class or method-like names found in hunk headers when present
  framework_log_keys includes added log tags when present
  ```

- [ ] **Step 3: Write tests for inference output shape**

  The same test file must assert that inference evidence contains:

  ```text
  kind = patch_problem_inference
  confidence = low, medium, or high
  inferred_keywords includes focus and WindowManager for the fixture
  basis is non-empty
  limits is non-empty
  ```

- [ ] **Step 4: Implement `patch_analysis.py`**

  Implement deterministic analysis only:

  ```text
  parse diff file headers for modified files
  parse hunk headers and changed lines for rough symbols
  map known paths to modules such as WindowManager, ActivityTaskManager, PackageManager, SystemUI, Launcher, Power, Input
  extract obvious log tags, Settings keys, SystemProperties keys, resource keys
  generate conservative keywords and risk surface from modified files and modules
  ```

  Do not call network services or require an LLM in the server hook.

- [ ] **Step 5: Run the focused tests**

  Run:

  ```bash
  python3 -m unittest tests.test_patch_analysis_v2
  ```

  Expected: all tests pass.

## Phase 3: Accept Patch Analysis Evidence In Incoming V2

**Files:**

- Modify: `/mnt/c/Users/jinny/Documents/Codex/worktrees/knowledge-jinny/scripts/knowledge_pipeline/incoming_v2.py`
- Modify: `/mnt/c/Users/jinny/Documents/Codex/worktrees/knowledge-jinny/tests/test_incoming_v2_validation.py`
- Modify fixtures under: `/mnt/c/Users/jinny/Documents/Codex/worktrees/knowledge-jinny/tests/fixtures/incoming_v2/`

- [ ] **Step 1: Expand accepted quality values**

  Update validation so:

  ```text
  light qualities: imported, trace, candidate
  strict qualities: imported, candidate, validated, released, buggy
  ```

- [ ] **Step 2: Validate inference evidence shape**

  For `patch_problem_inference` and `risk_surface`, require the evidence payload to include:

  ```text
  confidence
  basis
  limits
  ```

  `basis` and `limits` must be non-empty arrays.

- [ ] **Step 3: Validate patch facts are present or derivable**

  For every patch item, validation must pass when either:

  ```text
  patch.facts.modified_files is non-empty
  ```

  or:

  ```text
  server-side patch analysis can derive modified_files from the patch diff
  ```

- [ ] **Step 4: Add regression tests**

  Add tests for:

  ```text
  imported strict patch contribution passes without verification
  validated strict patch contribution fails without PASS verification
  inference evidence fails when confidence is missing
  inference evidence fails when basis is empty
  inference evidence fails when limits is empty
  ```

- [ ] **Step 5: Run validation tests**

  Run:

  ```bash
  python3 -m unittest tests.test_incoming_v2_validation
  ```

  Expected: all tests pass.

## Phase 4: Normalize V2 Events And Materialize Compatibility Views

**Files:**

- Modify: `/mnt/c/Users/jinny/Documents/Codex/worktrees/knowledge-jinny/scripts/knowledge_pipeline/normalize_v2.py`
- Modify: `/mnt/c/Users/jinny/Documents/Codex/worktrees/knowledge-jinny/scripts/process_incoming.py`
- Create: `/mnt/c/Users/jinny/Documents/Codex/worktrees/knowledge-jinny/tests/test_v2_materialized_views.py`

- [ ] **Step 1: Preserve event authority**

  `normalize_v2_package()` must always write the authoritative event to:

  ```text
  knowledge-events/YYYYMMDD/member_alias/event_id/event.json
  ```

- [ ] **Step 2: Generate daily and weekly views from V2 report events**

  Add materialization rules:

  ```text
  daily_trace with reports -> daily/YYYYMMDD/member_alias/<title>.md and sidecar metadata
  weekly_trace with reports -> weekly/YYYYMMDD-YYYYMMDD/member_alias/<title>.md and sidecar metadata
  ```

  Each generated report must include or sidecar-record:

  ```text
  event_id
  source.origin
  schema_version
  quality
  ```

- [ ] **Step 3: Generate patch metadata with analysis summaries**

  `patches/by-id/<patch_id>/metadata.json` must include:

  ```text
  event_id
  package_id
  source.origin
  quality
  patch_diff_facts summary when available
  patch_problem_inference summary when available
  confidence and limits for inferred fields
  ```

- [ ] **Step 4: Add materialization tests**

  Tests must prove:

  ```text
  V2 daily_trace produces daily output
  V2 weekly_trace produces weekly output
  V2 framework_change produces patch metadata with event linkage
  deleting generated daily/weekly/patch output and rerunning normalization recreates it
  ```

- [ ] **Step 5: Run focused tests**

  Run:

  ```bash
  python3 -m unittest tests.test_v2_materialized_views tests.test_incoming_v2_validation
  ```

  Expected: all tests pass.

## Phase 5: Rebuild Historical Data Into V2 Events

**Files:**

- Modify: `/mnt/c/Users/jinny/Documents/Codex/worktrees/knowledge-jinny/scripts/import_history_staging.py`
- Create: `/mnt/c/Users/jinny/Documents/Codex/worktrees/knowledge-jinny/tests/test_historical_v2_migration.py`
- Create: `/mnt/c/Users/jinny/Documents/Codex/worktrees/knowledge-jinny/docs/knowledge-v2-migration-report-template.md`

- [ ] **Step 1: Add a dry-run V2 migration mode**

  Add a mode that writes to a temporary or caller-provided output root:

  ```bash
  python3 scripts/import_history_staging.py --v2 --dry-run --output /tmp/android-knowledge-v2-preview
  ```

  The command must not modify current `daily/`, `weekly/`, `patches/`, `index/`, or `site/`.

- [ ] **Step 2: Generate deterministic event IDs**

  Event IDs must be stable from:

  ```text
  source origin identity
  member
  date or week key
  patch content hash when a patch exists
  report row ID or archive member path when available
  ```

- [ ] **Step 3: Analyze every historical patch with available content**

  For every historical patch file, migration must emit:

  ```text
  patch_diff_facts evidence
  patch_problem_inference evidence
  risk_surface evidence
  ```

  If the patch cannot be parsed, emit a `quality_issue` row instead of failing the whole migration.

- [ ] **Step 4: Keep inference honest**

  Historical inference evidence must include:

  ```text
  source_patch
  confidence
  basis
  limits
  ```

  Historical events without modern verification remain `quality=imported`.

- [ ] **Step 5: Produce a migration report**

  The report must include:

  ```text
  source daily rows
  source weekly rows
  source archives
  generated events
  generated reports
  generated patches
  generated evidence
  duplicate patch sources
  parse failures
  validation failures
  ```

- [ ] **Step 6: Run historical migration tests**

  Run:

  ```bash
  python3 -m unittest tests.test_historical_v2_migration
  ```

  Expected: all tests pass.

## Phase 6: Rebuild Indexes Around Events And Evidence

**Files:**

- Modify: `/mnt/c/Users/jinny/Documents/Codex/worktrees/knowledge-jinny/scripts/build_index.py`
- Create: `/mnt/c/Users/jinny/Documents/Codex/worktrees/knowledge-jinny/tests/test_build_index_v2_analysis.py`

- [ ] **Step 1: Index patch-derived facts**

  `build_index.py` must add patch-derived fields to patch, evidence, symbol, and event rows:

  ```text
  modified_files
  modules
  symbols
  framework_log_keys
  system_properties
  settings_keys
  resource_keys
  ```

- [ ] **Step 2: Index patch-derived inferences**

  Index these fields with explicit inference labels:

  ```text
  inferred_problem
  inferred_solution
  inferred_keywords
  risk_surface
  inference_confidence
  inference_basis
  inference_limits
  ```

- [ ] **Step 3: Extend SQLite schema**

  The SQLite output must support querying:

  ```text
  knowledge_events by package_kind, origin, quality, member, date
  evidence by kind, event_id, result, confidence
  patches by patch_id, event_id, quality, module, modified_file
  symbols by symbol, file, module, event_id, patch_id
  ```

- [ ] **Step 4: Add search regression tests at index level**

  Tests must prove an old patch without a strong readme is findable by:

  ```text
  modified file
  module
  inferred keyword
  risk surface
  ```

- [ ] **Step 5: Run index tests**

  Run:

  ```bash
  python3 -m unittest tests.test_build_index_v2_analysis tests.test_incoming_v2_validation
  ```

  Expected: all tests pass.

## Phase 7: Update Plugin Workflows For Marketplace Distribution

**Files:**

- Modify: `plugins/android-framework-ops/skills/android-knowledge-intake/references/incoming-package-protocol.md`
- Modify: `plugins/android-framework-ops/skills/android-framework-patch-capture/references/package-contract.md`
- Modify: `plugins/android-framework-ops/skills/android-framework-change-workflow/SKILL.md`
- Modify: `plugins/android-framework-ops/skills/android-knowledge-search/references/search-contract.md`

- [ ] **Step 1: Remove old distribution assumptions**

  Android Framework main-chain docs must refer to:

  ```text
  GitHub marketplace source: jinny51/android-framework-codex-suite
  plugin: android-framework-ops
  installed skills from Codex plugin cache
  ```

  They must not require:

  ```text
  legacy local sync paths
  member-local skill directory synchronization
  any non-marketplace distribution chain
  ```

- [ ] **Step 2: Make `--patch-package` the recommended path**

  `android-knowledge-intake` docs must state:

  ```text
  android-framework-patch-capture -> .codex/patch-packages/<run-id> -> android-knowledge-intake --patch-package <package> --schema-version 2.0
  ```

  `--patch` remains legacy/manual compatibility only.

- [ ] **Step 3: Require search-before-change evidence**

  `android-framework-change-workflow` must say Framework implementation starts with `android-knowledge-search` unless the user explicitly scopes the task as non-Framework or search is impossible.

- [ ] **Step 4: Require patch analysis output in capture packages**

  Patch-capture packages should include:

  ```text
  evidence/patch-diff-facts.json
  evidence/patch-problem-inference.json
  evidence/risk-surface.json
  ```

  The capture skill may generate richer inference than the server hook because it runs inside a Codex session.

- [ ] **Step 5: Validate plugin layout**

  Run:

  ```bash
  scripts/validate_plugins.sh
  ```

  Expected: successful validation.

## Phase 8: Redesign Site Around Workbench Views

**Files:**

- Modify: `/mnt/c/Users/jinny/Documents/Codex/worktrees/knowledge-jinny/site/index.html`
- Modify: `/mnt/c/Users/jinny/Documents/Codex/worktrees/knowledge-jinny/site/patches.html`
- Modify: `/mnt/c/Users/jinny/Documents/Codex/worktrees/knowledge-jinny/site/reports.html`
- Modify: `/mnt/c/Users/jinny/Documents/Codex/worktrees/knowledge-jinny/site/symbols.html`
- Modify generated payload code in: `/mnt/c/Users/jinny/Documents/Codex/worktrees/knowledge-jinny/scripts/build_index.py`

- [ ] **Step 1: Define top-level views**

  The site must present:

  ```text
  Overview
  Knowledge Events
  Patch Assets
  Reports
  Evidence
  Members
  Quality Issues
  ```

- [ ] **Step 2: Expose source and quality visibly**

  Every event and patch result must show:

  ```text
  source.origin
  quality
  package_kind
  member
  date
  validation state
  ```

- [ ] **Step 3: Label facts and inferences separately**

  UI must visibly separate:

  ```text
  direct patch facts
  inferred problem
  inferred solution
  inferred keywords
  inference confidence
  inference limits
  verification evidence
  ```

- [ ] **Step 4: Keep search inputs stable under Chinese IME**

  Any UI rewrite must preserve the existing IME-safe behavior:

  ```text
  do not rebuild the active input during composition
  debounce result rendering
  refresh result containers instead of remounting the whole search form
  ```

- [ ] **Step 5: Browser-check the generated site**

  Start a local static server from the knowledge test worktree after generation:

  ```bash
  python3 -m http.server 8765
  ```

  Verify desktop and mobile widths for:

  ```text
  no overlapping text
  search input works with Chinese text
  patch asset detail shows inference labels
  event detail links to evidence and generated patch metadata
  ```

## Phase 9: Simulated Gray Test Before Real Members

**Files:**

- Use: `/mnt/c/Users/jinny/Documents/Codex/worktrees/knowledge-test`
- Use or create fixtures under: `/mnt/c/Users/jinny/Documents/Codex/worktrees/knowledge-test/incoming/`

- [ ] **Step 1: Create synthetic member packages**

  Create at least:

  ```text
  incoming/20260526/testuser/20260526-210000-daily-trace/
  incoming/20260526/testuser/20260526-211000-weekly-trace/
  incoming/20260526/testuser/20260526-212000-framework-change-candidate/
  incoming/20260526/testuser/20260526-213000-framework-change-validated/
  incoming/20260526/testuser/20260526-214000-historical-like-imported-patch/
  ```

- [ ] **Step 2: Process simulated incoming**

  Run:

  ```bash
  python3 scripts/process_incoming.py
  python3 scripts/build_index.py
  ```

  Expected:

  ```text
  server-result.json written for each package
  knowledge-events generated
  daily/weekly compatibility views generated
  patches/by-id generated
  indexes generated
  site payload generated
  ```

- [ ] **Step 3: Compare counts**

  Compare against the current historical baseline:

  ```text
  members: 14
  reports: 3879
  patches: 1649
  readmes: 1649
  patch_readmes: 1649
  archives: 147
  symbols: 7754
  issues: 0
  ```

  The test should explain expected differences instead of requiring exact equality during V2 preview.

- [ ] **Step 4: Search simulated data**

  Verify search hits for:

  ```text
  member alias
  modified file
  inferred keyword
  package_kind
  source.origin
  quality
  validation evidence
  ```

- [ ] **Step 5: Decide real gray scope**

  Real member gray testing may start only after:

  ```text
  simulated incoming passes
  generated views rebuild cleanly
  search finds historical imported and new incoming data through the same CLI/site
  UI labels imported/candidate/validated clearly
  rollback plan is documented
  ```

## Verification Matrix

Run these before claiming the rebuild phase is complete:

```bash
python3 -m unittest tests.test_patch_analysis_v2
python3 -m unittest tests.test_incoming_v2_validation
python3 -m unittest tests.test_v2_materialized_views
python3 -m unittest tests.test_historical_v2_migration
python3 -m unittest tests.test_build_index_v2_analysis
python3 scripts/process_incoming.py
python3 scripts/build_index.py
```

For plugin changes:

```bash
scripts/validate_plugins.sh
python3 plugins/android-framework-ops/skills/android-framework-patch-capture/tests/test_capture_framework_patch.py
python3 plugins/android-framework-ops/skills/android-knowledge-intake/tests/test_patch_capture_ingest.py
python3 plugins/android-framework-ops/skills/android-knowledge-search/tests/test_android_knowledge_search_v2.py
```

## Commit Boundaries

Use small commits after reviewable phases:

```text
docs: define android knowledge v2 schema
knowledge: add v2 patch analysis facts
knowledge: materialize v2 report views
knowledge: rebuild historical data as v2 events
knowledge: index v2 patch analysis evidence
site: expose v2 events evidence and patch quality
ops: align framework skills with knowledge v2
```

Do not commit generated historical rebuild output until the dry-run migration report has been reviewed.
