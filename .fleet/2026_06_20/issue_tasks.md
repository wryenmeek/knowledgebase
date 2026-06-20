# Issue Analysis: wryenmeek/knowledgebase

> Analyzed 16 issues on 2026-06-20T05:26:39.507361+00:00

## Executive Summary

Found 8 addressable root causes that can be resolved via automated PR generation, and 8 unaddressable issues requiring human intervention or external access.

## Root Cause Analysis

### RC-rc-8-format: .jules/bolt.md format inconsistency

**Related issues:** #305
**Severity:** low
**Files involved:** .jules/bolt.md

#### Diagnosis
**Code path:** `.jules/bolt.md`

**Mechanism:** The file mixes older elaborated learning formats with the new exact format `## YYYY-MM-DD - [Title]\n**Learning:** [Insight]\n**Action:** [How to apply next time]`.

**Root cause:** Lack of enforcement for exact memory formatting.

#### Proposed Solution
**Proposed implementation:** Reformat all older entries to match the canonical format.

**Integration Points:**
`.jules/bolt.md`

#### Test Plan
Verify the markdown file strictly complies with the regex `^## \d{4}-\d{2}-\d{2} - \[.+\]\n\*\*Learning:\*\* .+\n\*\*Action:\*\* .+$` for every block.

#### Edge Cases and Risks
Line breaks inside `Learning` or `Action` values might break simple regex validations, but manual formatting should safely preserve markdown paragraphs.

---

### RC-rc-1-workflows: jules-archive-stale.yml missing environment and concurrency gate

**Related issues:** #306, #305
**Severity:** medium
**Files involved:** .github/workflows/jules-archive-stale.yml

#### Diagnosis
**Code path:** `.github/workflows/jules-archive-stale.yml:57-61`

**Mechanism:**
The destructive `jules-archive-stale.yml` workflow lacks an `environment:` approval gate for the `archive` job. Additionally, it lacks a `concurrency:` block, meaning two rapid manual runs can race to mass-archive sessions.
```yaml
  archive:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
```

**Root cause:** Missing workflow-level environment gate and concurrency grouping for a destructive script.

#### Proposed Solution
**Proposed implementation:** Add `environment: jules-archive-approval` to the `archive` job, and `concurrency: group: jules-archive-stale, cancel-in-progress: false` to the workflow level.

**Integration Points:**
`.github/workflows/jules-archive-stale.yml:57-61`

#### Test Plan
1. Parse the YAML file and assert `environment: jules-archive-approval` is present under the `archive` job.
2. Assert the concurrency block is present at the top level of the file.

#### Edge Cases and Risks
YAML parsing issues could occur if the file is poorly formatted, but standard git diff patching should handle this safely. Assuming `jules-archive-approval` environment exists in settings.

---

### RC-rc-6-adr-polish: ADR documentation quality polish

**Related issues:** #304, #305
**Severity:** medium
**Files involved:** docs/decisions/ADR-032-fleet-quota-saturation-soft-warn.md, docs/decisions/README.md, docs/decisions/ADR-005-write-concurrency-guards.md, docs/decisions/ADR-019-fleet-jules-orchestration.md, docs/decisions/ADR-031-lock-holder-pid-tracking.md, docs/decisions/ADR-030-cli-write-confirmation.md

#### Diagnosis
**Code path:** `docs/decisions/ADR-032-fleet-quota-saturation-soft-warn.md` and others.

**Mechanism:** ADRs lack standard sections:
- ADR-032 lacks `## Alternatives considered`
- ADR-031 in README does not state `extends ADR-005`
- ADR-005 lacks `## Related decisions` backref to ADR-031
- ADR-019 lacks backref to ADR-032
- ADR-030 lacks backref to ADR-022 and ADR-005
- `wryenmeek/hot-springs-island#595` shorthand url dead-ends.

**Root cause:** Documentation process missed connecting back-references and alternative considerations.

#### Proposed Solution
**Proposed implementation:** Add the missing headers, full URLs, and references explicitly to each file.

**Integration Points:**
`docs/decisions/ADR-032-fleet-quota-saturation-soft-warn.md` and others.

#### Test Plan
Validate the Markdown files to ensure the sections are present and links are correctly formatted.

#### Edge Cases and Risks
None, text only.

---

### RC-rc-7-diagnostics: extractStatusCode gRPC code confusion and handleMergeFatal test

**Related issues:** #305
**Severity:** medium
**Files involved:** scripts/fleet/github/mutation-diagnostics.ts

#### Diagnosis
**Code path:** `scripts/fleet/github/mutation-diagnostics.ts:284`

**Mechanism:** `extractStatusCode` reads `record.code` blindly as a number. For gRPC errors, this is `9`, which is mapped as `statusCode = 9`, colliding with HTTP space potentially. Additionally, `handleMergeFatal` quota_saturation path is untested.

**Root cause:** extractStatusCode assumes `.code` is always an HTTP status. Test coverage gap for quota saturation in merge fatal handler.

#### Proposed Solution
**Proposed implementation:** Extract grpc error into `grpcCode` rather than blindly casting `record.code` as HTTP code. Add tests for `handleMergeFatal` quota saturation.

**Integration Points:**
`scripts/fleet/github/mutation-diagnostics.ts:284`

#### Test Plan
Ensure `extractStatusCode` correctly separates gRPC from HTTP codes in `mutation-diagnostics.test.ts`. Verify the new `fleet-entrypoint-fatal.test.ts` block runs successfully.

#### Edge Cases and Risks
Errors might have overlapping properties; verify `record.code` safely defaults.

---

### RC-rc-2-frontmatter: extract_frontmatter lacks tests and byte contract documentation

**Related issues:** #303
**Severity:** high
**Files involved:** scripts/kb/page_template_utils.py

#### Diagnosis
**Code path:** `scripts/kb/page_template_utils.py:135-146`
**Mechanism:** The regex `_FRONTMATTER_BLOCK_RE` was introduced recently but lacks tests covering the body byte contract, notably CRLF mapping.
```python
        if fm.endswith("\r\n"):
            fm = fm[:-2]
        elif fm.endswith("\n"):
            fm = fm[:-1]
        body = text[match.end():]
```
**Root cause:** The extraction byte parity behavior is not documented nor tested, introducing regression risks.

#### Proposed Solution
**Proposed implementation:** Document the byte contract in the docstring. Add comprehensive unit tests in `tests/kb/test_extract_frontmatter.py` covering LF, CRLF, unclosed, empty frontmatter etc.

**Integration Points:**
`scripts/kb/page_template_utils.py:135-146`

#### Test Plan
Test cases in `tests/kb/test_extract_frontmatter.py`:
1. Happy LF: `---\nfm\n---\nbody\n` -> `('fm', 'body\n')`
2. Happy CRLF: `---\r\nfm\r\n---\r\nbody\r\n` -> `('fm', 'body\r\n')`
3. Empty frontmatter: `---\n---\nbody\n` -> `('', 'body\n')`
4. No frontmatter pass-through returns `(None, original_text)`
5. Unclosed delim returns `(None, original_text)`
6. `---` in mid-body does not re-trigger.

#### Edge Cases and Risks
Regex may be slow on huge files, but testing must ensure `extract_frontmatter` matches exactly the byte contract established by prior implementation without memory leaks.

---

### RC-rc-3-write-utils: write_utils lock holder issues and test coverage gaps

**Related issues:** #302, #305
**Severity:** high
**Files involved:** scripts/kb/write_utils.py

#### Diagnosis
**Code path:** `scripts/kb/write_utils.py:402`, `300`, `279`, `319`

**Mechanism:**
1. At line 402, `LockUnavailableError(contracts.GOVERNANCE_META_LOCK_PATH)` does not pass `lock_file_path=...`, falling back to `cwd` resolution, failing holder introspection when not in root.
2. `_read_lock_holder_details` doesn't catch `UnicodeDecodeError`.
3. `_darwin_pid_start_time_unix_seconds` fallback at line 279 returns `time.time()`, shifting by local UTC offset since ps is local time.
4. `_linux_pid_start_time_unix_seconds` and `_holder_process_is_alive` error branches (like EPERM) are completely untested.

**Root cause:** Flawed lock metadata introspection and gaps in testing error branches.

#### Proposed Solution
**Proposed implementation:** Pass `lock_file_path` to `LockUnavailableError` meta lock, catch `UnicodeDecodeError`, fix Darwin time fallback. Extend tests in `test_write_utils.py` to cover `_linux_pid_start_time_unix_seconds` parser and `PermissionError` paths in `_holder_process_is_alive`.

**Integration Points:**
`scripts/kb/write_utils.py:402`, `300`, `279`, `319`

#### Test Plan
1. Assert `holder_alive` and `holder_context_hash` in `test_sibling_governance_lock_fails_when_customizations_lock_is_held`.
2. Mock `os.kill` to raise `PermissionError` and `OSError` with `errno.EPERM` to ensure `_holder_process_is_alive` returns `True`.
3. Mock `os.kill` to raise `OSError` with unknown errno to ensure it returns `None`.
4. Mock `Path.read_text` for `/proc/pid/stat` to cover Linux stat parsing edge cases.

#### Edge Cases and Risks
Darwin time fallback using `time.time()` was problematic; returning `None` instead disables start-time verification fallback safely. `os.kill` mock tests must clean up patches to avoid polluting other tests.

---

### RC-rc-4-archive-cli: archive-stale-sessions CLI arg parsing bugs

**Related issues:** #301, #305
**Severity:** high
**Files involved:** scripts/fleet/archive-stale-sessions.ts

#### Diagnosis
**Code path:** `scripts/fleet/archive-stale-sessions.ts:121`

**Mechanism:**
```typescript
} else if (arg === "--source-filter" && argv[i + 1]) {
```
Empty or whitespace strings bypass validation because an empty string is falsy but whitespace is truthy, bypassing the explicit apply gate logic later.

**Root cause:** Flawed logic relying on JS truthiness instead of explicit trimming and length checking. Also, order-dependent overrides were untested.

#### Proposed Solution
**Proposed implementation:** Explicitly check for undefined or whitespace-only values when parsing `--source-filter`. Add test coverage for order-dependent overrides.

**Integration Points:**
`scripts/fleet/archive-stale-sessions.ts:121`

#### Test Plan
1. Invoke `parseCliArgs` with `--source-filter "   " --apply` and expect Error to be thrown.
2. Invoke with `--source-filter ""` and expect Error.
3. Test `--repo all --source-filter X` and verify `sourceFilter` is `X` and `repoAll` is `true` independent of argument order.

#### Edge Cases and Risks
Ensure argument index `i` is properly incremented when reading the value. Unhandled arguments might throw, which is expected.

---

### RC-rc-5-approval-hooks: check_approval_flag.py and alias bugs & test coverage

**Related issues:** #300, #305
**Severity:** high
**Files involved:** scripts/hooks/check_approval_flag.py, scripts/_optional_surface_common.py

#### Diagnosis
**Code path:** `scripts/hooks/check_approval_flag.py:271-277`, `tests/kb/test_approval_migration_ratchet.py:31`

**Mechanism:**
1. The deadline check fires before the exemption check, causing the alias script to be rejected after the deadline.
2. The ratchet test checks `len(files) <= MAX_APPROVAL_FLAG_SCRIPTS` instead of `==`.
3. `_contains_approval_flag` has false positives for substrings.
4. Payload-path gating and BEFORE deadline equality check are untested.
5. `normalize_apply_alias` lacks alias coverage matrix testing.

**Root cause:** Logic order bug for exemptions, weak `<=` assertion, and missing test coverage for edge paths.

#### Proposed Solution
**Proposed implementation:** Move exemption check above equals-form check, change `<=` to `==` in `test_approval_migration_ratchet.py`, and remove dead code in `normalize_apply_alias`. Add tests for payload-path gating and alias matrix.

**Integration Points:**
`scripts/hooks/check_approval_flag.py:271-277`, `tests/kb/test_approval_migration_ratchet.py:31`

#### Test Plan
1. Assert `test_approval_flag_script_count_does_not_exceed_contract` uses `==`.
2. Ensure alias file changes pass the hook by moving the exemption check higher.
3. Test `_payload_script_paths` failure short-circuit and `env` var precedence.
4. Add matrix-style test iterating `EXPECTED_WRITE_SURFACE_MATRIX_ROWS` for `--apply` aliases.

#### Edge Cases and Risks
Exemptions bypassing the deadline check must only apply to `_EXEMPT_PATHS` (the alias script itself).

---

## Task Plan

| # | Task | Root Cause | Issues | Files | Risk |
|---|------|-----------|--------|-------|------|
| 1 | .jules/bolt.md format inconsistency | rc-8-format | #305 | .jules/bolt.md | low |
| 2 | jules-archive-stale.yml missing environment and concurrency gate | rc-1-workflows | #306, #305 | .github/workflows/jules-archive-stale.yml | medium |
| 3 | ADR documentation quality polish | rc-6-adr-polish | #304, #305 | docs/decisions/ADR-032-fleet-quota-saturation-soft-warn.md, docs/decisions/README.md, docs/decisions/ADR-005-write-concurrency-guards.md, docs/decisions/ADR-019-fleet-jules-orchestration.md, docs/decisions/ADR-031-lock-holder-pid-tracking.md, docs/decisions/ADR-030-cli-write-confirmation.md | medium |
| 4 | extractStatusCode gRPC code confusion and handleMergeFatal test | rc-7-diagnostics | #305 | scripts/fleet/github/mutation-diagnostics.ts | medium |
| 5 | extract_frontmatter lacks tests and byte contract documentation | rc-2-frontmatter | #303 | scripts/kb/page_template_utils.py | high |
| 6 | write_utils lock holder issues and test coverage gaps | rc-3-write-utils | #302, #305 | scripts/kb/write_utils.py | high |
| 7 | archive-stale-sessions CLI arg parsing bugs | rc-4-archive-cli | #301, #305 | scripts/fleet/archive-stale-sessions.ts | high |
| 8 | check_approval_flag.py and alias bugs & test coverage | rc-5-approval-hooks | #300, #305 | scripts/hooks/check_approval_flag.py, scripts/_optional_surface_common.py | high |

## File Ownership Matrix

| File | Task | Change Type |
|------|------|-------------|
| .jules/bolt.md | rc-8-format | Modify/Create |
| .github/workflows/jules-archive-stale.yml | rc-1-workflows | Modify/Create |
| docs/decisions/ADR-032-fleet-quota-saturation-soft-warn.md | rc-6-adr-polish | Modify/Create |
| docs/decisions/README.md | rc-6-adr-polish | Modify/Create |
| docs/decisions/ADR-005-write-concurrency-guards.md | rc-6-adr-polish | Modify/Create |
| docs/decisions/ADR-019-fleet-jules-orchestration.md | rc-6-adr-polish | Modify/Create |
| docs/decisions/ADR-031-lock-holder-pid-tracking.md | rc-6-adr-polish | Modify/Create |
| docs/decisions/ADR-030-cli-write-confirmation.md | rc-6-adr-polish | Modify/Create |
| scripts/fleet/github/mutation-diagnostics.ts | rc-7-diagnostics | Modify/Create |
| scripts/fleet/github/mutation-diagnostics.test.ts | rc-7-diagnostics | Modify/Create |
| scripts/fleet/fleet-entrypoint-fatal.test.ts | rc-7-diagnostics | Modify/Create |
| scripts/kb/page_template_utils.py | rc-2-frontmatter | Modify/Create |
| tests/kb/test_extract_frontmatter.py | rc-2-frontmatter | Modify/Create |
| scripts/kb/write_utils.py | rc-3-write-utils | Modify/Create |
| tests/kb/test_write_utils.py | rc-3-write-utils | Modify/Create |
| scripts/fleet/archive-stale-sessions.ts | rc-4-archive-cli | Modify/Create |
| scripts/fleet/archive-stale-sessions.test.ts | rc-4-archive-cli | Modify/Create |
| scripts/hooks/check_approval_flag.py | rc-5-approval-hooks | Modify/Create |
| scripts/_optional_surface_common.py | rc-5-approval-hooks | Modify/Create |
| tests/kb/test_approval_migration_ratchet.py | rc-5-approval-hooks | Modify/Create |
| tests/kb/test_contracts.py | rc-5-approval-hooks | Modify/Create |
| tests/kb/test_optional_surface_scripts.py | rc-5-approval-hooks | Modify/Create |
| tests/kb/test_check_approval_flag.py | rc-5-approval-hooks | Modify/Create |

## Unaddressable Issues

Issues that require changes outside this repository (backend API, infrastructure, product decisions):

| Issue | Reason | Suggested Owner |
|-------|--------|-----------------|
| #212 | Requires human-in-the-loop Phase 7 validation by comparing fresh VS Code Copilot Chat session with CLI session. | QA Engineer / Operator |
| #207 | Requires adversarial QA gate validating the read-only classifier with manual audit of findings. | QA Engineer / Operator |
| #198 | Requires human adversarial QA gate and cross-functional review chain (code-reviewer, security-auditor, solutions-architect). | QA Engineer / Security Auditor |
| #196 | Requires manual phase 1.5 spike to empirically measure agent compliance rate via manual CLI session and VS Code Copilot Chat. | QA Engineer |
| #194 | Requires manual phase 0 spike with fresh CLI 1.0.60 session to validate hook firing and override behavior. | QA Engineer |
| #188 | Requires HITL operator step to review reconciliation report and approve bootstrap application (--approval approved). | HITL Operator |
| #156 | Requires human decision for deployment platform, operational ownership model, and security controls for semantic query API. | Solutions Architect / Tech Lead |
| #82 | Requires external investigation of JULES_API_KEY entitlement, account/project linkage, and provider-side preconditions. | Platform Engineer |
