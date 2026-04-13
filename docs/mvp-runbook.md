# MVP Runbook (Task 15 / M4)

This runbook is the maintainer path for MVP execution and evidence checks.

## Local execution flow (repo root)

```bash
# 1) ingest (single source)
python3 scripts/kb/ingest.py \
  --source raw/inbox/<source-file>.md \
  --batch-policy continue_and_report_per_source \
  --wiki-root wiki \
  --schema AGENTS.md \
  --report-json

# 1b) ingest (batch manifest)
python3 scripts/kb/ingest.py \
  --sources-manifest raw/inbox/<manifest>.txt \
  --batch-policy continue_and_report_per_source \
  --wiki-root wiki \
  --schema AGENTS.md \
  --report-json

# 2) rebuild wiki index
python3 scripts/kb/update_index.py --wiki-root wiki --write

# 3) strict wiki lint (read-only)
python3 scripts/kb/lint_wiki.py --wiki-root wiki --strict

# 4) qmd index/query bootstrap
qmd collection add wiki --name wiki
qmd embed

# 5) qmd preflight
python3 scripts/kb/qmd_preflight.py --repo-root . --required-resource .qmd/index

# 6) query + policy-gated persist
qmd query "<query>"
python3 scripts/kb/persist_query.py \
  --query "<query>" \
  --result-summary "<summary>" \
  --confidence 4 \
  --source "<SourceRef-1>" \
  --source "<SourceRef-2>" \
  --wiki-root wiki \
  --schema AGENTS.md \
  --result-json

# 7) regression/unit/integration workflow checks
python3 -m unittest discover -s tests -p "test_*.py"
```

## Exit semantics and failure handling

- **Fail-closed default:** any non-zero exit from preflight/index/lint/tests is a stop signal.
- **Ingest partial success:** `ingest.py` exit **2** means `partial_success` with per-source failures; inspect `per_source[]`, fix failed sources, rerun only failed inputs.
- **Ingest hard failure:** non-zero other than `2` is contract/preflight/write failure (`failed`), including lock contention (`reason_code=lock_unavailable`).
- **Persist policy envelope:** `persist_query.py` can return exit `0` with `status=no_write_policy` (expected no-write outcome) or `status=written`; both are valid automation outcomes.
- **No-write envelope contract:** `no_write_policy` must not mutate repo files (`analysis_path=null`, `index_updated=false`, `log_appended=false`).

## CI-1 governance prerequisites (trusted-trigger model)

- **Protected default branch is required:** CI-1 checks `github.ref_protected` and rejects with `reject:trusted_trigger_model:ref_not_protected` when false.
- **Strict inbox-only scope is required:** pushes that include `raw/inbox/**` plus non-inbox paths are rejected with `reject:path_filter:outside_raw_inbox:*`.
- **Operational guidance:** keep CI-1-triggering commits scoped to `raw/inbox/**`; apply broader repository changes in separate commits/PRs.
- **If branch protection is not yet available:** use the documented fallback/manual path until branch protection is configured.

## CI fallback/manual path summary (CI-1..CI-3)

| CI | Normal role | If automation is unavailable/fails |
|---|---|---|
| **CI-1** (`.github/workflows/ci-1-gatekeeper.yml`) | trusted-trigger gatekeeper/handoff for `raw/inbox/**` | run local ingest → update_index → lint; open/update PR manually; keep fail-closed behavior and required checks. |
| **CI-2** (`.github/workflows/ci-2-analyst-diagnostics.yml`) | read-only diagnostics (`lint_wiki --strict` + test suite) | run the same diagnostics locally (`lint_wiki`, `unittest discover`), attach findings to PR/issue; no repo-write automation needed. |
| **CI-3** (`.github/workflows/ci-3-pr-producer.yml`) | write-capable PR producer after trusted handoff/manual approval | execute the local sequence in this runbook, commit only allowlisted paths (`wiki/**`, `raw/processed/**`), and open/update PR manually through normal approvals/checks. Manual dispatch runs additionally require protected-environment reviewer approval (`ci3-manual-approval`). |

- **CI-3 manual dispatch note:** `maintainer_approved` remains a required attestation input for `workflow_dispatch`, and manual runs are gated by protected-environment reviewer approval (`ci3-manual-approval`) for authoritative control.

## Milestone evidence mapping (M0..M4)

| Gate | Concrete evidence in this repo |
|---|---|
| **M0: terminology/assumptions freeze** | `raw/inbox/SPEC.md` (Assumptions/Terminology sections) + `tests/kb/test_contracts.py` (canonical policy IDs, token profiles, reason/envelope constants). |
| **M1: interface executability** | `scripts/kb/ingest.py`, `update_index.py`, `lint_wiki.py`, `qmd_preflight.py`, `persist_query.py`; validated by `tests/kb/test_ingest.py`, `test_update_index.py`, `test_lint_wiki.py`, `test_qmd_preflight.py`, `test_persist_query.py`. |
| **M2: security/automation enforcement** | `.github/workflows/ci-1-gatekeeper.yml`, `ci-2-analyst-diagnostics.yml`, `ci-3-pr-producer.yml`; enforced by `tests/kb/test_ci1_workflow.py`, `test_ci2_workflow.py`, `test_ci3_workflow.py`, `test_ci_permission_asserts.py`. |
| **M3: verification readiness** | `raw/inbox/SPEC.md` Verification Matrix + `tests/kb/test_unit_verification_matrix.py`, `test_integration_verification_matrix.py`, `test_regression_verification_matrix.py`. |
| **M4: pre-implementation go/no-go** | `raw/inbox/SPEC.md` Implementation-ready milestone gates + Final Pre-Implementation Ambiguity Review Checklist, plus this runbook (`docs/mvp-runbook.md`) as executable operator evidence. |
