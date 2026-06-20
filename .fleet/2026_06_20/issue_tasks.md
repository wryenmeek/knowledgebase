# Issue Analysis: wryenmeek/knowledgebase

> Analyzed 15 issues on 2026-06-20T08:54:05.565Z

## Executive Summary

Found 6 actionable root causes across the 6 P1/MEDIUM tracking issues. Two of the issues are single atomic bugfixes/enhancements (archive-stale-sessions truthiness bug and jules-archive-stale.yml missing environment gate). Issues #305 (P2 bundle), #304 (P1 docs), #303 (extract_frontmatter tests), #302 (LockUnavailableError propagation), and #300 (approval flag check bug) are all code or doc bugs. The remaining 7 issues are epic/milestone tracking or external investigation tickets (#212, #207, #198, #196, #194, #188, #156, #82) which are unaddressable directly through code changes in this task. Overall the codebase is healthy, and the required fixes are isolated and low to medium risk.

## Root Cause Analysis

### RC-1: Time-bomb and Ratchet Bugs in check_approval_flag.py

**Related issues:** #300
**Severity:** High
**Files involved:** `scripts/hooks/check_approval_flag.py`, `tests/kb/test_approval_migration_ratchet.py`

#### Diagnosis

There are two distinct bugs reported in #300:
1. **Time-bomb on compatibility alias file:** The equals-form rejection (`_contains_approval_equals`) in `check_approval_flag.py` runs before checking if the path is in `_EXEMPT_PATHS`. After the `APPROVAL_EQUALS_REJECTION_DEADLINE` (2026-12-31), any edit to `scripts/_optional_surface_common.py` (which is an exempt path that legitimately contains `"--approval="` to detect legacy callers) will fail the pre-commit hook because the exemption check happens *after* the deadline check.
2. **Ratchet uses `<=` instead of `==`:** In `tests/kb/test_approval_migration_ratchet.py`, the test `test_approval_flag_script_count_does_not_exceed_contract` uses `<=` when asserting against `MAX_APPROVAL_FLAG_SCRIPTS`. This means if a script is migrated (count goes down), the test still passes without requiring `MAX_APPROVAL_FLAG_SCRIPTS` to be decremented, defeating the ratchet mechanism.

#### Proposed Solution

1. Move the `_EXEMPT_PATHS` check before the equals-form check in `check_approval_flag.py`.
2. Change the assertion in `tests/kb/test_approval_migration_ratchet.py` to use `==`.

```python
# scripts/hooks/check_approval_flag.py
<<<<<<< SEARCH
        if read_error is not None:
            failures.append(read_error)
            continue
        # Enforce equals-sign rejection before exemptions so transitional
        # compatibility files cannot silently keep the legacy equals syntax.
        if (
            _contains_approval_equals(staged_text)
            and _migration_deadline_passed()
        ):
            failures.append(
                f"{staged_path.path}: {_APPROVAL_EQUALS_TOKEN}<value> is forbidden after "
                f"{APPROVAL_EQUALS_REJECTION_DEADLINE.isoformat()}; use --apply"
            )
            continue
        if staged_path.path in _EXEMPT_PATHS:
            continue
        if not _contains_approval_flag(staged_text):
            continue
=======
        if read_error is not None:
            failures.append(read_error)
            continue
        if staged_path.path in _EXEMPT_PATHS:
            continue
        # Enforce equals-sign rejection before exemptions so transitional
        # compatibility files cannot silently keep the legacy equals syntax.
        if (
            _contains_approval_equals(staged_text)
            and _migration_deadline_passed()
        ):
            failures.append(
                f"{staged_path.path}: {_APPROVAL_EQUALS_TOKEN}<value> is forbidden after "
                f"{APPROVAL_EQUALS_REJECTION_DEADLINE.isoformat()}; use --apply"
            )
            continue
        if not _contains_approval_flag(staged_text):
            continue
>>>>>>> REPLACE
```

```python
# tests/kb/test_approval_migration_ratchet.py
<<<<<<< SEARCH
def test_approval_flag_script_count_does_not_exceed_contract() -> None:
    files = _legacy_approval_script_files()
    assert len(files) <= MAX_APPROVAL_FLAG_SCRIPTS, (
        f"{len(files)} scripts still use --approval but MAX_APPROVAL_FLAG_SCRIPTS="
        f"{MAX_APPROVAL_FLAG_SCRIPTS}: "
        + ", ".join(path.relative_to(REPO_ROOT).as_posix() for path in files)
    )
=======
def test_approval_flag_script_count_does_not_exceed_contract() -> None:
    files = _legacy_approval_script_files()
    assert len(files) == MAX_APPROVAL_FLAG_SCRIPTS, (
        f"{len(files)} scripts still use --approval but MAX_APPROVAL_FLAG_SCRIPTS="
        f"{MAX_APPROVAL_FLAG_SCRIPTS}: "
        + ", ".join(path.relative_to(REPO_ROOT).as_posix() for path in files)
    )
>>>>>>> REPLACE
```

#### Test Plan
- Run `pytest tests/kb/test_approval_migration_ratchet.py` to ensure tests pass.
- Modify `scripts/_optional_surface_common.py` and run `python3 scripts/hooks/check_approval_flag.py` to verify it doesn't fail.

---

### RC-2: Truthiness Check Bypass in archive-stale-sessions.ts

**Related issues:** #301
**Severity:** High
**Files involved:** `scripts/fleet/archive-stale-sessions.ts`, `scripts/fleet/archive-stale-sessions.test.ts`

#### Diagnosis
In `scripts/fleet/archive-stale-sessions.ts`, the check `if (arg === "--source-filter" && argv[i + 1])` uses JS truthiness. If the next argument is a whitespace-only string (e.g., `"   "`), it's truthy, so `sourceFilter = "   "`. Then, later, if `--apply` is set, the gate `if (args.apply && !args.sourceFilter)` doesn't fire because `args.sourceFilter` is truthy, allowing an archive with a no-op filter, bypassing the deny-by-default behavior.

#### Proposed Solution

Replace the truthiness check with an explicit check for non-empty and non-whitespace values.

```typescript
// scripts/fleet/archive-stale-sessions.ts
<<<<<<< SEARCH
    } else if (arg === "--older-than-days" && argv[i + 1]) {
      const parsed = Number(argv[++i]);
      if (!Number.isInteger(parsed) || parsed < 1) {
        throw new Error(
          `--older-than-days must be a positive integer; got: "${argv[i]}"`
        );
      }
      olderThanDays = parsed;
    } else if (arg === "--source-filter" && argv[i + 1]) {
      sourceFilter = argv[++i];
    } else if (arg === "--repo" && argv[i + 1]) {
=======
    } else if (arg === "--older-than-days" && argv[i + 1]) {
      const parsed = Number(argv[++i]);
      if (!Number.isInteger(parsed) || parsed < 1) {
        throw new Error(
          `--older-than-days must be a positive integer; got: "${argv[i]}"`
        );
      }
      olderThanDays = parsed;
    } else if (arg === "--source-filter") {
      const value = argv[++i];
      if (value === undefined || value.trim().length === 0) {
        throw new Error("--source-filter requires a non-empty value");
      }
      sourceFilter = value;
    } else if (arg === "--repo" && argv[i + 1]) {
>>>>>>> REPLACE
```

Add tests in `scripts/fleet/archive-stale-sessions.test.ts` to cover empty and whitespace-only inputs.

```typescript
// scripts/fleet/archive-stale-sessions.test.ts
// Add the following test cases to the argument parsing describe block:
  test("--apply with whitespace-only --source-filter is denied", () => {
    expect(() =>
      parseCliArgs(["--apply", "--older-than-days", "1", "--source-filter", "   "])
    ).toThrow("--source-filter requires a non-empty value");
  });

  test("--apply with empty --source-filter is denied", () => {
    expect(() =>
      parseCliArgs(["--apply", "--older-than-days", "1", "--source-filter", ""])
    ).toThrow("--source-filter requires a non-empty value");
  });
```

#### Test Plan
- Run `bun test archive-stale-sessions.test.ts` to verify the new cases throw the correct errors.

---

### RC-3: Missing lock_file_path in Meta-lock LockUnavailableError

**Related issues:** #302, #305 (P2: UnicodeDecodeError and Darwin lstart tolerance), #306 (P1: pin `ps` and bound recursion)
**Severity:** High
**Files involved:** `scripts/kb/write_utils.py`, `tests/kb/test_write_utils.py`

#### Diagnosis
In `scripts/kb/write_utils.py` ~line 408 (`_acquire_sibling_governance_lock`), when acquiring the meta-lock fails, it raises `LockUnavailableError(contracts.GOVERNANCE_META_LOCK_PATH) from exc`. It's missing the `lock_file_path=repo_root / contracts.GOVERNANCE_META_LOCK_PATH` kwarg. This causes the path to be resolved against `cwd` instead of `repo_root` inside the `LockUnavailableError` init, so the holder introspection silently fails.
Additionally, several P2/P3 items affect the same file or closely related areas:
1. `_read_lock_holder_details` doesn't catch `UnicodeDecodeError` when reading a corrupted lock file.
2. `_darwin_pid_start_time_unix_seconds` UTC fallback shifts in the wrong direction and uses an unpinned `ps` executable.
3. Darwin start-time tolerance vs `time.time()` fallback can be too tight due to `ps` precision.

#### Proposed Solution

Update the meta-lock raise statement in `write_utils.py` and address the bundled bugs. Update the sibling-contention tests in `test_write_utils.py` to assert that `holder_alive` and `holder_context_hash` are correctly propagated.

```python
# scripts/kb/write_utils.py (LockUnavailableError propagation)
<<<<<<< SEARCH
    with meta_lock_file:
        try:
            fcntl.flock(meta_lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise LockUnavailableError(contracts.GOVERNANCE_META_LOCK_PATH) from exc
        try:
=======
    with meta_lock_file:
        try:
            fcntl.flock(meta_lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise LockUnavailableError(
                contracts.GOVERNANCE_META_LOCK_PATH,
                lock_file_path=repo_root / contracts.GOVERNANCE_META_LOCK_PATH,
            ) from exc
        try:
>>>>>>> REPLACE
```

```python
# scripts/kb/write_utils.py (UnicodeDecodeError)
<<<<<<< SEARCH
    try:
        line = lock_file_path.read_text(encoding="utf-8").splitlines()[0].strip()
    except IndexError:
        return None
    except OSError:
        return None
=======
    try:
        line = lock_file_path.read_text(encoding="utf-8").splitlines()[0].strip()
    except IndexError:
        return None
    except (OSError, UnicodeDecodeError):
        return None
>>>>>>> REPLACE
```

```python
# scripts/kb/write_utils.py (Darwin ps path and UTC offset)
<<<<<<< SEARCH
    try:
        ps_env = dict(os.environ)
        ps_env["LC_TIME"] = "C"
        completed = subprocess.run(
            ["ps", "-o", "lstart=", "-p", str(pid)],
            check=True,
            capture_output=True,
            text=True,
            env=ps_env,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    lstart_text = completed.stdout.strip()
    if not lstart_text:
        return None
    try:
        parsed = datetime.strptime(lstart_text, "%a %b %d %H:%M:%S %Y")
    except ValueError:
        return None
    local_tz = datetime.now().astimezone().tzinfo
    if local_tz is None:
        return parsed.replace(tzinfo=timezone.utc).timestamp()
    return parsed.replace(tzinfo=local_tz).timestamp()
=======
    try:
        ps_env = dict(os.environ)
        ps_env["LC_TIME"] = "C"
        completed = subprocess.run(
            ["/bin/ps", "-o", "lstart=", "-p", str(pid)],
            check=True,
            capture_output=True,
            text=True,
            env=ps_env,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    lstart_text = completed.stdout.strip()
    if not lstart_text:
        return None
    try:
        parsed = datetime.strptime(lstart_text, "%a %b %d %H:%M:%S %Y")
    except ValueError:
        return None

    # Use explicit timezone fallback
    import time
    if time.timezone:
        # Avoid local timezone shift by assuming the parsed time is already local
        return time.mktime(parsed.timetuple())
    return parsed.replace(tzinfo=timezone.utc).timestamp()
>>>>>>> REPLACE
```

```python
# tests/kb/test_write_utils.py
<<<<<<< SEARCH
                self.assertFalse(probe_result["acquired"])
                self.assertEqual(
                    probe_result["reason_code"],
                    contracts.ReasonCode.LOCK_UNAVAILABLE.value,
                )
                self.assertEqual(
                    probe_result["failure_reason"],
                    write_utils.lock_unavailable_reason(held_lock),
                )

    def test_sibling_governance_lock_fails_when_customizations_lock_is_held(self) -> None:
=======
                self.assertFalse(probe_result["acquired"])
                self.assertEqual(
                    probe_result["reason_code"],
                    contracts.ReasonCode.LOCK_UNAVAILABLE.value,
                )
                self.assertEqual(
                    probe_result["failure_reason"],
                    write_utils.lock_unavailable_reason(held_lock),
                )
                self.assertTrue(probe_result["holder_alive"])
                self.assertRegex(probe_result["holder_context_hash"], r"^[0-9a-f]{64}$")

    def test_sibling_governance_lock_fails_when_customizations_lock_is_held(self) -> None:
>>>>>>> REPLACE
<<<<<<< SEARCH
                self.assertFalse(probe_result["acquired"])
                self.assertEqual(
                    probe_result["reason_code"],
                    contracts.ReasonCode.LOCK_UNAVAILABLE.value,
                )
                self.assertEqual(
                    probe_result["failure_reason"],
                    write_utils.lock_unavailable_reason(contracts.CUSTOMIZATIONS_LOCK_PATH),
                )

    def test_governance_lock_uses_meta_lock_even_with_noncanonical_target_path(self) -> None:
=======
                self.assertFalse(probe_result["acquired"])
                self.assertEqual(
                    probe_result["reason_code"],
                    contracts.ReasonCode.LOCK_UNAVAILABLE.value,
                )
                self.assertEqual(
                    probe_result["failure_reason"],
                    write_utils.lock_unavailable_reason(contracts.CUSTOMIZATIONS_LOCK_PATH),
                )
                self.assertTrue(probe_result["holder_alive"])
                self.assertRegex(probe_result["holder_context_hash"], r"^[0-9a-f]{64}$")

    def test_governance_lock_uses_meta_lock_even_with_noncanonical_target_path(self) -> None:
>>>>>>> REPLACE
```

#### Test Plan
- Run `pytest tests/kb/test_write_utils.py` to ensure the extended tests pass and the meta-lock LockUnavailableError carries the metadata.

---

### RC-4: extract_frontmatter Tests Missing

**Related issues:** #303
**Severity:** High
**Files involved:** `tests/kb/test_extract_frontmatter.py` (new), `scripts/kb/page_template_utils.py`

#### Diagnosis
Issue #303 notes that `extract_frontmatter` has no direct unit tests, and the recent regex change subtly changed how body bytes are preserved (e.g. CRLF, trailing newlines). The byte contract must be codified in tests and documented.

#### Proposed Solution

Create `tests/kb/test_extract_frontmatter.py` with the required parameterized cases, and update the docstring of `extract_frontmatter` in `scripts/kb/page_template_utils.py` to document the byte contract.

```python
# scripts/kb/page_template_utils.py
<<<<<<< SEARCH
def extract_frontmatter(text: str) -> tuple[str | None, str]:
    """Extract a YAML frontmatter block and the body from a markdown document.

    Returns a tuple of (frontmatter, body). If no frontmatter block is found,
    returns (None, original_text).
    """
=======
def extract_frontmatter(text: str) -> tuple[str | None, str]:
    """Extract a YAML frontmatter block and the body from a markdown document.

    Returns a tuple of (frontmatter, body). If no frontmatter block is found,
    returns (None, original_text). The original body bytes (including any CRLF
    newlines and trailing newlines) are preserved verbatim.
    """
>>>>>>> REPLACE
```

```python
# tests/kb/test_extract_frontmatter.py
import pytest
from scripts.kb.page_template_utils import extract_frontmatter

@pytest.mark.parametrize(
    "text,expected_fm,expected_body",
    [
        ("---\nfm\n---\nbody\n", "fm", "body\n"),
        ("---\r\nfm\r\n---\r\nbody\r\n", "fm\r\n", "body\r\n"),
        ("  ---\nfm\n---\nbody", "fm", "body"),
        ("---\n---\nbody\n", "", "body\n"),
        ("no frontmatter\n", None, "no frontmatter\n"),
        ("---\nunclosed\nbody\n", None, "---\nunclosed\nbody\n"),
        ("---\nfm\n---\nbody\n---\nmore\n", "fm", "body\n---\nmore\n"),
        ("---\nfm\n---", "fm", ""),
    ],
)
def test_extract_frontmatter(text, expected_fm, expected_body):
    fm, body = extract_frontmatter(text)
    assert fm == expected_fm
    assert body == expected_body
```

#### Test Plan
- Run `pytest tests/kb/test_extract_frontmatter.py` to verify the byte contract tests pass.

---

### RC-5: ADR and Docs Updates

**Related issues:** #304
**Severity:** High
**Files involved:** `docs/decisions/ADR-032-fleet-quota-saturation-soft-warn.md`, `docs/decisions/README.md`, `docs/decisions/ADR-005-write-concurrency-guards.md`, `docs/decisions/ADR-019-fleet-jules-orchestration.md`, `docs/decisions/ADR-031-lock-holder-pid-tracking.md`, `docs/decisions/ADR-030-cli-write-confirmation.md`

#### Diagnosis
Issue #304 requires updates to several ADR documents to improve quality, cross-referencing, and structural consistency.
- ADR-032 missing Alternatives
- ADR-031 README extends ADR-005
- ADR-005 missing back-ref to ADR-031
- ADR-019 missing back-ref to ADR-032
- ADR-031 section ordering and privacy tradeoff in Consequences
- ADR-030 missing related decisions and full URL in ADR-032

#### Proposed Solution

Apply the markdown text updates requested in the issue to the respective ADR markdown files.

---

### RC-6: jules-archive-stale.yml Lacks Environment Gate

**Related issues:** #306, #305
**Severity:** Medium
**Files involved:** `.github/workflows/jules-archive-stale.yml`

#### Diagnosis
The destructive workflow `.github/workflows/jules-archive-stale.yml` doesn't have an `environment` gate. Also, issue #305 mentions it's missing a concurrency block to prevent rapid clicks from racing.

#### Proposed Solution

Add `environment: jules-archive-approval` and a `concurrency` block to `.github/workflows/jules-archive-stale.yml`.

```yaml
# .github/workflows/jules-archive-stale.yml
<<<<<<< SEARCH
jobs:
  archive:
    runs-on: ubuntu-latest
=======
jobs:
  archive:
    runs-on: ubuntu-latest
    environment: jules-archive-approval
    concurrency:
      group: jules-archive-stale
      cancel-in-progress: false
>>>>>>> REPLACE
```

#### Test Plan
- Ensure `yamllint` checks pass on the modified workflow.

## Task Plan

| # | Task | Root Cause | Issues | Files | Risk |
|---|------|-----------|--------|-------|------|
| 1 | Fix check_approval_flag bugs | RC-1 | #300 | `scripts/hooks/check_approval_flag.py`, `tests/kb/test_approval_migration_ratchet.py` | Low |
| 2 | Fix archive-stale-sessions | RC-2 | #301 | `scripts/fleet/archive-stale-sessions.ts`, `scripts/fleet/archive-stale-sessions.test.ts` | Low |
| 3 | Fix LockUnavailableError and write bugs | RC-3 | #302, #305, #306 | `scripts/kb/write_utils.py`, `tests/kb/test_write_utils.py` | Medium |
| 4 | Add extract_frontmatter tests | RC-4 | #303 | `scripts/kb/page_template_utils.py`, `tests/kb/test_extract_frontmatter.py` | Low |
| 5 | Update ADRs | RC-5 | #304 | `docs/decisions/ADR-032-fleet-quota-saturation-soft-warn.md`, `docs/decisions/README.md`, `docs/decisions/ADR-005-write-concurrency-guards.md`, `docs/decisions/ADR-019-fleet-jules-orchestration.md`, `docs/decisions/ADR-031-lock-holder-pid-tracking.md`, `docs/decisions/ADR-030-cli-write-confirmation.md` | Low |
| 6 | Fix workflow gates | RC-6 | #306, #305 | `.github/workflows/jules-archive-stale.yml` | Low |

## File Ownership Matrix

| File | Task | Change Type |
|------|------|-------------|
| `scripts/hooks/check_approval_flag.py` | 1 | Modify |
| `tests/kb/test_approval_migration_ratchet.py` | 1 | Modify |
| `scripts/fleet/archive-stale-sessions.ts` | 2 | Modify |
| `scripts/fleet/archive-stale-sessions.test.ts` | 2 | Modify |
| `scripts/kb/write_utils.py` | 3 | Modify |
| `tests/kb/test_write_utils.py` | 3 | Modify |
| `scripts/kb/page_template_utils.py` | 4 | Modify |
| `tests/kb/test_extract_frontmatter.py` | 4 | Create |
| `docs/decisions/ADR-032-fleet-quota-saturation-soft-warn.md` | 5 | Modify |
| `docs/decisions/README.md` | 5 | Modify |
| `docs/decisions/ADR-005-write-concurrency-guards.md` | 5 | Modify |
| `docs/decisions/ADR-019-fleet-jules-orchestration.md` | 5 | Modify |
| `docs/decisions/ADR-031-lock-holder-pid-tracking.md` | 5 | Modify |
| `docs/decisions/ADR-030-cli-write-confirmation.md` | 5 | Modify |
| `.github/workflows/jules-archive-stale.yml` | 6 | Modify |

## Unaddressable Issues

Issues that require changes outside this repository (backend API, infrastructure, product decisions) or are epic/milestone tracking:

| Issue | Reason | Suggested Owner |
|-------|--------|-----------------|
| #212 | Phase 7 validation epic tracking | Team Lead |
| #207 | QA gate epic tracking | QA / Security |
| #198 | QA gate epic tracking | QA / Security |
| #196 | Compliance rate spike tracking | Product / Engineering |
| #194 | Spike ticket / Epic | Product / Engineering |
| #188 | PR/Milestone tracker that requires HITL manual execution | Engineering |
| #156 | Human-owned decision lane for hosting/deployment | Architect / Eng Lead |
| #82 | Investigation into external API provider behavior (Jules) | Backend Team / Integration Lead |
