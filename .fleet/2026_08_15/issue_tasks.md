# Issue Analysis: wryenmeek/knowledgebase

> Analyzed 1 issues on 2026-08-15T06:34:40.003Z

## Executive Summary

One root cause was identified corresponding to a feature request for automated near-expiry freshness checks (#560). The issue can be fully addressed by adding a `--near-expiry-days` option to the existing `check_doc_freshness.py` script and running a new near-expiry check step in the `.github/workflows/wiki-freshness.yml` CI workflow.

## Root Cause Analysis

### RC-1: Missing automated near-expiry refresh notifications

**Related issues:** #560
**Severity:** Medium
**Files involved:** `scripts/validation/check_doc_freshness.py`, `tests/kb/test_check_doc_freshness.py`, `.github/workflows/wiki-freshness.yml`

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
1. Modify `_check_file`, `run_freshness`, and the CLI (`--near-expiry-days`) to accept a near expiry window size (e.g., 14 days).
2. Add a new `REASON_CODE_NEAR_EXPIRY = "near_expiry"` constant in `check_doc_freshness.py`.
3. Inside `_check_file`, add an `elif` condition right before returning `STATUS_PASS`:
```python
    if near_expiry_days is not None and age_days >= (max_age_days - near_expiry_days):
        return FreshnessFileResult(
            path=relative_path,
            status=STATUS_FAIL,
            reason_code=REASON_CODE_NEAR_EXPIRY,
            message=f"document is approaching freshness threshold ({age_days}d old, expires in {max_age_days - age_days}d). PROACTIVE FIX: update page content and set updated_at: <today's date>.",
            updated_at=updated_at_date.isoformat(),
            age_days=age_days,
        )
```
4. In `.github/workflows/wiki-freshness.yml`, add two new steps before "Upload freshness report artifact" to emit warnings for near-expiry pages (using `max_age_days=90` and `near_expiry_days=14`). Since they return `STATUS_FAIL`, the existing `Fail on stale wiki pages` step in blocking mode would fail if we reuse `steps.freshness`. So we should run near-expiry as a standalone step:

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
          if [[ ! -f freshness-reports/wiki-near-expiry.json ]]; then
            echo "No near-expiry report generated."
            # Note: Do not use exit inside python block directly if it crashes run_in_bash_session.
            # Using sys.exit is fine.
          fi
          python3 -c '
          import json, sys
          with open("freshness-reports/wiki-near-expiry.json") as f:
              report = json.load(f)
          for entry in report.get("files", []):
              if entry.get("reason_code") == "near_expiry":
                  path = entry.get("path", "unknown")
                  msg = entry.get("message", "near expiry")
                  print(f"::warning file={path}::{msg}")
          '
```

#### Test Plan

1. Verify `test_check_doc_freshness.py` accurately flags pages nearing expiry but not fully stale.
2. Verify standard tests still pass when `--near-expiry-days` is unset.
3. Validate GitHub workflow syntax with `actionlint`.

---

## Task Plan

| # | Task | Root Cause | Issues | Files | Risk |
|---|------|-----------|--------|-------|------|
| 1 | Add automated near-expiry refresh tracking | RC-1 | #560 | `scripts/validation/check_doc_freshness.py`, `tests/kb/test_check_doc_freshness.py`, `.github/workflows/wiki-freshness.yml` | Medium |

## File Ownership Matrix

| File | Task | Change Type |
|------|------|-------------|
| `scripts/validation/check_doc_freshness.py` | 1 | Modify |
| `tests/kb/test_check_doc_freshness.py` | 1 | Modify |
| `.github/workflows/wiki-freshness.yml` | 1 | Modify |
