# Issue Analysis: wryenmeek/knowledgebase

> Analyzed 1 issues on 2026-08-15T06:34:40.003Z

## Executive Summary

One root cause was identified corresponding to a feature request for automated near-expiry freshness checks (#560). The issue can be fully addressed by adding a `--near-expiry-days` option to the existing `check_doc_freshness.py` script and running a new near-expiry check step in the `.github/workflows/wiki-freshness.yml` CI workflow.

## Root Cause Analysis

### RC-1: Missing automated near-expiry refresh notifications

**Related issues:** #560
**Severity:** Medium
**Files involved:** `scripts/validation/check_doc_freshness.py`, `tests/kb/test_check_doc_freshness.py`, `.github/workflows/wiki-freshness.yml`, `docs/architecture.md`, `docs/mvp-runbook.md`

#### Diagnosis

The existing `check_doc_freshness.py` script computes document age and triggers a failure only when the age strictly exceeds `max_age_days`:

```python
# scripts/validation/check_doc_freshness.py:284-292
    if age_days > max_age_days:
        return FreshnessFileResult(
            path=relative_path,
            status=STATUS_FAIL,
            reason_code=REASON_CODE_STALE_DOCUMENT,
            message=f"document exceeds freshness threshold ({age_days}d > {max_age_days}d). FIX: update page content and set updated_at: <today's date> in the YAML frontmatter.",
            updated_at=updated_at_date.isoformat(),
            age_days=age_days,
        )
```

It doesn't provide any warning when a page approaches expiry (e.g., within 14 days), nor is this handled by the scheduled jobs. Because of this, document maintainers only find out pages are stale once they have already violated the freshness SLA.

#### Proposed Solution

Add near-expiry tracking to `check_doc_freshness.py`:
1. Add a new `REASON_CODE_NEAR_EXPIRY = "near_expiry"` constant in `check_doc_freshness.py`.
2. Add a `_normalize_near_expiry_days(near_expiry_days, *, max_age_days)` helper, modeled on the existing `_normalize_max_age_days`, that returns `None` unchanged and otherwise raises `ValueError` unless `0 <= near_expiry_days <= max_age_days`. A negative value would silently suppress warnings; a value greater than `max_age_days` would mark every non-stale document as near expiry — both must fail closed as `REASON_CODE_INVALID_INPUT` (reusing the same `try/except ValueError` block in `run_freshness` that already validates `max_age_days`), not as a misleading per-file result.
3. Modify `_check_file`, `run_freshness`, and the CLI (`--near-expiry-days`) to accept and normalize the near-expiry window size (e.g., 14 days).
4. In `run_cli`, explicitly pass the parsed flag through: `near_expiry_days=args.near_expiry_days` must be added to the existing `run_freshness(...)` call — the wiring is not implicit or default-driven.
5. Inside `_check_file`, extend the *existing* `if age_days > max_age_days:` statement with an `elif` branch (prose and code must describe the same single `if`/`elif` chain) right before returning `STATUS_PASS`:
```python
    if age_days > max_age_days:
        return FreshnessFileResult(
            path=relative_path,
            status=STATUS_FAIL,
            reason_code=REASON_CODE_STALE_DOCUMENT,
            message=f"document exceeds freshness threshold ({age_days}d > {max_age_days}d). FIX: update page content and set updated_at: <today's date> in the YAML frontmatter.",
            updated_at=updated_at_date.isoformat(),
            age_days=age_days,
        )
    elif near_expiry_days is not None and age_days >= (max_age_days - near_expiry_days):
        remaining_days = max(0, max_age_days - age_days)
        return FreshnessFileResult(
            path=relative_path,
            status=STATUS_FAIL,
            reason_code=REASON_CODE_NEAR_EXPIRY,
            message=f"document is approaching freshness threshold ({age_days}d old, expires in {remaining_days}d). Note: age_days == max_age_days is classified near-expiry (not stale) here because the stale branch above uses a strict '>' comparison. PROACTIVE FIX: update page content and set updated_at: <today's date>.",
            updated_at=updated_at_date.isoformat(),
            age_days=age_days,
        )
```
   `remaining_days` uses `max(0, ...)` so the message never reports a negative number of remaining days. The `age_days == max_age_days` boundary case is explicitly documented as falling into the `elif` (near-expiry), not the `if` (stale), branch.
6. In `.github/workflows/wiki-freshness.yml`, add two new steps before "Upload freshness report artifact" to emit warnings for near-expiry pages (using `max_age_days=90` and `near_expiry_days=14`). Since they return `STATUS_FAIL`, the existing `Fail on stale wiki pages` step in blocking mode would fail if we reuse `steps.freshness`. So we should run near-expiry as a standalone step:

```yaml
      - name: Run wiki near-expiry check
        continue-on-error: true
        run: |
          set -euo pipefail
          mkdir -p freshness-reports
          python3 scripts/validation/check_doc_freshness.py \
            --scope wiki \
            --as-of "$(date -u +%Y-%m-%d)" \
            --max-age-days 90 \
            --near-expiry-days 14 \
            --failures-only \
            > freshness-reports/wiki-near-expiry.json

      - name: Annotate near-expiry pages
        if: always()
        run: |
          set -euo pipefail
          report_path="freshness-reports/wiki-near-expiry.json"
          if [[ ! -s "$report_path" ]]; then
            echo "No near-expiry report generated (missing or empty file); skipping annotation."
            exit 0
          fi
          python3 <<'PY'
          import json
          import sys

          report_path = "freshness-reports/wiki-near-expiry.json"
          try:
              with open(report_path, encoding="utf-8") as f:
                  report = json.load(f)
          except (OSError, json.JSONDecodeError) as exc:
              print(f"::warning::Could not parse near-expiry report ({exc}); skipping annotation.")
              sys.exit(0)

          for entry in report.get("files", []):
              if entry.get("reason_code") == "near_expiry":
                  path = entry.get("path", "unknown")
                  msg = entry.get("message", "near expiry")
                  print(f"::warning file={path}::{msg}")
          PY
```
   The annotation step uses a heredoc (`python3 <<'PY' ... PY`) rather than a `python3 -c '...'` one-liner: the one-liner is fragile against quoting/indentation and cannot cleanly guard missing, empty, or malformed report JSON. The heredoc's shell `-s` check (missing/empty file) plus the `try/except (OSError, json.JSONDecodeError)` (malformed JSON) both log a warning and exit 0 instead of failing the step.
7. In `docs/architecture.md`, add a `freshness_near_expiry_days` row (value `14`) to the "Governed constants" table alongside `freshness_stale_days` and `freshness_afk_threshold_days`, documenting the rationale for the proactive-warning window relative to the 90-day stale threshold — governance-affecting configuration values require documented rationale per that section, and the dispatched task now owns this file so the constant isn't left undocumented.
8. In `docs/mvp-runbook.md`, update the `wiki-freshness.yml` workflow table row (which currently enumerates the stale-check, annotate, classify-stale, and governance-signal-sweep steps) to add the two new near-expiry steps (`Run wiki near-expiry check`, `Annotate near-expiry pages`) so the operator-facing table remains a complete description of the workflow. Also add the equivalent local-repro `check_doc_freshness` command with `--near-expiry-days 14` next to the existing documented `--max-age-days 90 --failures-only` invocation, so operators can reproduce the near-expiry warning locally.

#### Test Plan

1. Verify `test_check_doc_freshness.py` accurately flags pages nearing expiry but not fully stale, including the `age_days == max_age_days` boundary (near-expiry, not stale).
2. Verify standard tests still pass when `--near-expiry-days` is unset.
3. Verify `--near-expiry-days` values outside `[0, max_age_days]` (negative or greater than `max_age_days`) return `REASON_CODE_INVALID_INPUT`.
4. Verify the remaining-days message never reports a negative value.
5. Validate GitHub workflow syntax with `actionlint`.

---

## Task Plan

| # | Task | Root Cause | Issues | Files | Risk |
|---|------|-----------|--------|-------|------|
| 1 | Add automated near-expiry refresh tracking | RC-1 | #560 | `scripts/validation/check_doc_freshness.py`, `tests/kb/test_check_doc_freshness.py`, `.github/workflows/wiki-freshness.yml`, `docs/architecture.md`, `docs/mvp-runbook.md` | Medium |

## File Ownership Matrix

| File | Task | Change Type |
|------|------|-------------|
| `scripts/validation/check_doc_freshness.py` | 1 | Modify |
| `tests/kb/test_check_doc_freshness.py` | 1 | Modify |
| `.github/workflows/wiki-freshness.yml` | 1 | Modify |
| `docs/architecture.md` | 1 | Modify |
| `docs/mvp-runbook.md` | 1 | Modify |
