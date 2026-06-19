# MVP Runbook

This runbook is the maintainer path for MVP execution and evidence checks.

## Framework boundary note

The wiki-curation agent framework MVP does **not** replace the commands in this
runbook. Agent and skill work should scaffold control-plane routing and thin
wrappers around the existing `scripts/kb/**` entrypoints documented here. The
accepted layering and packaging rule lives in
[`docs/architecture.md`](architecture.md#wiki-curation-framework-mvp-boundary)
and
[`docs/decisions/ADR-007-control-plane-layering-and-packaging.md`](decisions/ADR-007-control-plane-layering-and-packaging.md).

## Post-MVP rollout authority

The authoritative post-MVP rollout **planning** sequence, scope classes, phase
gates, and packaging rules now live in [`docs/ideas/spec.md`](ideas/spec.md).
Use that spec when deciding whether work is **required**, **approval-gated**, or
**optional later-phase**, and before promoting skill-local logic into repo-level
script surfaces. This runbook remains the executable operator path and current
runtime authority for the MVP and ratified framework boundary.

## Lane order and operator handoffs

Maintain the landed lane order from `.github/agents/**`:

1. `knowledgebase-orchestrator`
2. `source-intake-steward`
3. `evidence-verifier`
4. `policy-arbiter`
5. Exactly one policy-cleared downstream persona for the scoped task:
   `synthesis-curator`, `query-synthesist`, or `topology-librarian`

Additional review/maintenance personas (`maintenance-auditor`, `change-patrol`,
`quality-analyst`) may triage or recommend follow-up only after the governance
boundary is understood, and any content-changing action routes back through
`knowledgebase-orchestrator`. Repo support personas (`code-reviewer`,
`test-engineer`, `security-auditor`) help review changes but do not bypass the
wiki governance lane.

## Locality guardrails for customization edits

ADR-028 owns the instruction-locality ladder for `.github/copilot-instructions.md`
and `AGENTS.md`. Current local guardrails are:

- The PostToolUse advisory in `.github/hooks/hooks.json` runs
  `scripts/hooks/locality_postuse_advisory.py` after edit/write tools and warns
  when a Locality 4 file was changed without deciding whether lower-locality
  placement is cheaper.
- `scripts/hooks/check_instructions_applyto_present.py` blocks staged
  `.github/instructions/*.instructions.md` files without non-empty `applyTo:`
  frontmatter so scoped instructions do not silently become always-on context.
- Manual fallback classification lives in
  `.github/skills/audit-knowledgebase-workspace/references/locality-ladder.md`.
  The stronger paired-deletion and commit-message trailer gates remain in the
  open Phase 6 slices (#199/#200).

## Template instantiation (new instances only)

When setting up a fresh copy of this repository from the GitHub template, use
`scripts/init.py` to wipe placeholder content and regenerate skeleton artifacts
before starting real curation work.

```bash
# Interactive (prompts for confirmation):
python3 scripts/init.py --fresh

# Non-interactive (CI-safe; requires INIT_ALLOW_WIPE=1 env var):
INIT_ALLOW_WIPE=1 python3 scripts/init.py --fresh --yes
```

What `--fresh` does:

- Verifies `REPO_ROOT` sentinel files (`pyproject.toml`, `.git`, `AGENTS.md`, `schema/`) are present
- Checks that `wiki/.kb_write.lock` is not held (blocks if it is)
- Wipes 10 content directories: `wiki/analyses/`, `wiki/concepts/`, `wiki/entities/`, `wiki/sources/`, `raw/inbox/`, `raw/processed/`, `raw/assets/`, `raw/rejected/`, `raw/github-sources/`, `raw/drive-sources/`
- Removes stale sibling lock files under `raw/` and `.github/`, including `.github/.customizations.lock` declared by ADR-028 § Customizations lock (but never removes `wiki/.kb_write.lock`, which is checked-and-blocks above)
- Regenerates `raw/processed/SPEC.md` skeleton, a sample inbox source, and stub wiki artifacts
- Runs `pip install -e ".[dev]"` and `pytest tests/` to verify the clean state

**Do not run on a live instance.** This is a destructive reset intended only for
template instances before any real content has been added. See `TEMPLATE.md` for
the full setup guide.

## Phase 0 bootstrap: runtime prerequisites

Make wrapper validation runnable through the same repo-local bootstrap contract
in local and CI environments before later phases depend on it more heavily.

| Surface | Required prerequisites | Bootstrap rule |
|---|---|---|
| Local wrapper validation (`validate-wiki-governance`, `sync-knowledgebase-state --check-only`) | `python3`, `npm`, repo checkout, `wiki/`, pinned `qmd` runtime (`@tobilu/qmd@2.5.1`) | Verify `npm view @tobilu/qmd@2.5.1 dist.integrity` equals `sha512-Ep9ccOj1bNRinfTIszp5UZP8xfi5AJNtmzwWDD4ZVm2YdWVS+rFobWJQovj0HD2uIAFrryvbSpZYeGa3flEO7g==`, install the exact package, run `qmd init`, and mirror runtime outputs into `.qmd/index/` for deterministic preflight checks. |
| CI-2 / CI-3 wrapper validation | `python3`, `npm`, checked-out repo, pinned `qmd` runtime, `.qmd/index` resource | Install `@tobilu/qmd@2.5.1` only after integrity verification, run `qmd init`, and mirror `.qmd/index.sqlite` + `.qmd/index.yml` into `.qmd/index/`; never use a shim binary. |
| Full qmd index/query flow | Pinned authoritative qmd runtime supporting `collection add`, `embed`, and `query` | Use the same pinned package + integrity gate, then run `qmd collection add wiki --name wiki`, preflight, `qmd embed`, and query/persist flows as needed. |

Validation-only bootstrap example (repo root):

```bash
QMD_NPM_PACKAGE="@tobilu/qmd"
QMD_VERSION="2.5.1"
QMD_EXPECTED_INTEGRITY="sha512-Ep9ccOj1bNRinfTIszp5UZP8xfi5AJNtmzwWDD4ZVm2YdWVS+rFobWJQovj0HD2uIAFrryvbSpZYeGa3flEO7g==" # pragma: allowlist secret
QMD_DIST_INTEGRITY="$(npm view "${QMD_NPM_PACKAGE}@${QMD_VERSION}" dist.integrity --registry=https://registry.npmjs.org)"
test "${QMD_DIST_INTEGRITY}" = "${QMD_EXPECTED_INTEGRITY}"

npm install --global "${QMD_NPM_PACKAGE}@${QMD_VERSION}" --registry=https://registry.npmjs.org
qmd init
mkdir -p .qmd/index
cp .qmd/index.sqlite .qmd/index/index.sqlite
cp .qmd/index.yml .qmd/index/index.yml

python3 .github/skills/validate-wiki-governance/logic/validate_wiki_governance.py
python3 .github/skills/sync-knowledgebase-state/logic/sync_knowledgebase_state.py --check-only
```

This bootstrap path is fail-closed by design: integrity mismatch, install
failure, or missing qmd runtime/index resources must stop execution before
wrapper validation proceeds.

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

# 5) qmd preflight
python3 scripts/kb/qmd_preflight.py --repo-root . --required-resource .qmd/index

# 5b) qmd embed
qmd embed

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

# 6b) batch query persistence (Phase 3) — acquires wiki/.kb_write.lock once for all entries
python3 scripts/kb/batch_persist_query.py \
  --batch-file <batch.json> \
  --wiki-root wiki \
  --schema AGENTS.md

# 7) wiki coverage analytics (Phase 4)
# summary mode (read-only):
python3 scripts/reporting/coverage_report.py --mode summary
# persist mode (approval-gated; writes wiki/reports/coverage-report-*.json):
python3 scripts/reporting/coverage_report.py --mode persist --approval approved

# 8) regression/unit/integration workflow checks (≥90% coverage gate enforced in CI-2)
python3 -m pytest tests/ -q --cov=scripts/kb --cov=scripts.validation._runtime_budget --cov-fail-under=90
```

## Wiki search semantic API contract (repo-local)

Issue [#158](https://github.com/wryenmeek/knowledgebase/issues/158) covers the
repo-local search-page integration only. Hosting/deployment/ownership decisions
for a production semantic API endpoint remain in
[#156](https://github.com/wryenmeek/knowledgebase/issues/156).

### Configuration contract

- `wiki/search.md` reads the endpoint from localStorage key
  `kb-semantic-search-endpoint` (set with the in-page **Save endpoint** control).
- Endpoint values must resolve to `http` or `https`.
- Semantic requests always use `POST <base-endpoint>/query`.
- Pagefind behavior remains active in all modes; semantic failures never disable
  Pagefind.

### Request contract (`POST <base-endpoint>/query`)

```json
{
  "query": "search text",
  "limit": 5
}
```

### Response contract (`2xx application/json`)

```json
{
  "results": [
    {
      "title": "Result title",
      "url": "/knowledgebase/concepts/example/",
      "snippet": "Short excerpt from the result.",
      "score": 0.92
    }
  ]
}
```

The `results` array is required. Items may include `title`, `url`, `snippet`,
and `score`.

### Error and fallback contract

- Missing endpoint: semantic lane stays disabled and Pagefind results remain
  available.
- Network failure: semantic lane reports unavailable state and Pagefind results
  remain available.
- Non-2xx HTTP status: semantic lane reports HTTP fallback state and Pagefind
  results remain available.
- Non-JSON `Content-Type`, JSON parse errors, or missing `results` array:
  semantic lane reports contract mismatch and Pagefind results remain available.
- Semantic result rendering must use text nodes (`textContent`) and must not use
  `innerHTML`.

## Framework verification entrypoints

Use these repo-local checks when validating the landed framework artifacts
themselves:

```bash
# fixed governance wrapper over qmd preflight + index + authoritative commit-bound SourceRef lint
python3 .github/skills/validate-wiki-governance/logic/validate_wiki_governance.py

# read-only framework state-sync precheck
python3 .github/skills/sync-knowledgebase-state/logic/sync_knowledgebase_state.py --check-only

# write-capable governed sync after mode-specific checks pass
python3 .github/skills/sync-knowledgebase-state/logic/sync_knowledgebase_state.py --write-index

# primary local test suite (pytest is canonical; see ADR-029)
python3 -m pytest tests/

# fast-path framework suite for files whose unittest migration is deferred
python3 -m unittest tests.kb.test_framework_contracts tests.kb.test_framework_skills tests.kb.test_framework_agents tests.kb.test_framework_references tests.kb.test_framework_write_surface_matrix tests.kb.test_skill_wrappers
```

The unittest command above is a focused compatibility fast path for framework
boundary files that still migrate under the pytest ratchet; prefer
`python3 -m pytest tests/` for broad local verification.

Framework test entrypoints already present under `tests/kb/`:

| Test file | What it verifies |
|---|---|
| `tests/kb/test_framework_contracts.py` | Boundary docs, required execution-surface references, and runbook gate text stay aligned with ADR-007. |
| `tests/kb/test_framework_skills.py` | Framework skill metadata, classifications, and wrapper-path expectations. |
| `tests/kb/test_framework_agents.py` | Persona presence, frontmatter, handoffs, lane ordering, and fail-closed contracts. |
| `tests/kb/test_framework_references.py` | Repo-local link/path resolution for docs, skills, agents, and wrapper entrypoints. |
| `tests/kb/test_framework_write_surface_matrix.py` | `AGENTS.md` write-surface matrix coverage for every current skill-local logic directory and approved repo-level package family. |
| `tests/kb/test_skill_wrappers.py` | Thin wrapper execution order, allowlists, and fail-closed wrapper behavior. |

## Authoritative verification and approval entrypoints

| Coverage lane | Authoritative entrypoint | Approval / operating note |
|---|---|---|
| Primary all-tests suite | `python3 -m pytest tests/` | Canonical local verification command per ADR-029; use before merge unless a narrower debugging loop is explicitly being run. |
| Framework contract suites | `python3 -m unittest tests.kb.test_framework_contracts tests.kb.test_framework_skills tests.kb.test_framework_agents tests.kb.test_framework_references tests.kb.test_framework_write_surface_matrix` | Run whenever framework docs, skills, agents, or the `AGENTS.md` write-surface matrix change. |
| Wrapper behavior suite | `python3 -m unittest tests.kb.test_skill_wrappers` | Confirms the fixed wrapper order, allowlists, and fail-closed execution envelope. |
| Helper surface suites | `python3 -m unittest tests.kb.test_context_import_helpers tests.kb.test_documentation_helpers tests.kb.test_validate_source_registry tests.kb.test_validate_wiki_topology tests.kb.test_harnesses` | Covers skill-local helper contracts without widening repo-write authority. |
| Repo script suites | `python3 -m unittest tests.kb.test_contracts tests.kb.test_sourceref tests.kb.test_ingest tests.kb.test_update_index tests.kb.test_lint_wiki tests.kb.test_qmd_preflight tests.kb.test_persist_query tests.kb.test_write_utils tests.kb.test_batch_persist_query tests.kb.test_coverage_report` | Required when `scripts/kb/**` or approved repo-level helper packages change. |
| Workflow governance suites | `python3 -m unittest tests.kb.test_workflow_yaml_syntax tests.kb.test_ci1_workflow tests.kb.test_ci2_workflow tests.kb.test_ci3_workflow tests.kb.test_ci5_workflow tests.kb.test_ci6_workflow tests.kb.test_ci_permission_asserts tests.kb.test_pages_workflow tests.kb.test_runtime_budget tests.kb.test_runtime_budget_workflows` | Keep CI-1 no-write trusted handoff, CI-2 read-only diagnostics, CI-3 allowlisted writes, CI-5/CI-6 monitor workflows, Pages runtime contract, and runtime-budget gates aligned with workflow YAML. |
| Verification matrix suites | `python3 -m unittest tests.kb.test_unit_verification_matrix tests.kb.test_integration_verification_matrix tests.kb.test_regression_verification_matrix` | Final verification pass for unit, integration, and regression coverage expectations. |
| Broad regression suite | `python3 -m pytest tests/ -q` | Final merge gate after the focused lanes above stay green. |

| Approval lane | Authoritative entrypoint | Required control |
|---|---|---|
| CI-1 no-write trusted handoff | `.github/workflows/ci-1-gatekeeper.yml` on `push` to protected default-branch `raw/inbox/**` changes | Read-only token, inbox-only scope, and handoff-only behavior. |
| CI-2 read-only diagnostics | `.github/workflows/ci-2-analyst-diagnostics.yml` on `push`, `pull_request`, or `workflow_dispatch` | Read-only workflow-level permissions (`actions/checks/contents: read`) plus job-scoped `issues: read` on `analyst-diagnostics`; artifact upload only; no repo mutations. |
| CI-3 allowlisted writes | `.github/workflows/ci-3-pr-producer.yml` from CI-1 handoff, protected manual dispatch, or direct `push` to `main` for CI-3 infrastructure-only validation of `.github/workflows/ci-3-pr-producer.yml` and synthesis skill paths | Allowlisted writes (`wiki/**`, `wiki/index.md`, `wiki/log.md`, `raw/processed/**`, `raw/rejected/**`) plus the ingest cleanup exception for `raw/inbox/**` deletions only when that cleanup is the sole non-inbox change; `batch_persist_query` materializes `wiki/analyses/**` only when written source pages exist; protected-environment approval remains required for manual dispatch; `workflow_dispatch` now hard-blocks when the dispatch commit includes sensitive control-plane paths (`.github/workflows/**`, `.github/skills/**`, `.github/agents/**`, `.github/extensions/**`, `scripts/**`, `schema/**`, `AGENTS.md`, `pyproject.toml`). |

## Verification planning baseline

The matrix in [`docs/ideas/spec.md`](ideas/spec.md#verification-matrix-and-ci-migration-rules)
is the planning authority for post-MVP verification expansion. It does **not**
change today's runtime or CI enforcement. Until a later phase is explicitly
approved, keep the primary pytest command and these existing fast-path MVP
suites green:

- Primary all-tests suite:
  `python3 -m pytest tests/`

- Framework contract suites:
  `python3 -m unittest tests.kb.test_framework_contracts tests.kb.test_framework_skills tests.kb.test_framework_agents tests.kb.test_framework_references tests.kb.test_framework_write_surface_matrix`
- Wrapper behavior suite:
  `python3 -m unittest tests.kb.test_skill_wrappers`
- Helper surface suites:
  `python3 -m unittest tests.kb.test_context_import_helpers tests.kb.test_documentation_helpers tests.kb.test_validate_source_registry tests.kb.test_validate_wiki_topology tests.kb.test_harnesses`
- Repo script suites:
  `python3 -m unittest tests.kb.test_contracts tests.kb.test_sourceref tests.kb.test_ingest tests.kb.test_update_index tests.kb.test_lint_wiki tests.kb.test_qmd_preflight tests.kb.test_persist_query tests.kb.test_write_utils tests.kb.test_batch_persist_query tests.kb.test_coverage_report`
- Workflow governance suites:
  `python3 -m unittest tests.kb.test_workflow_yaml_syntax tests.kb.test_ci1_workflow tests.kb.test_ci2_workflow tests.kb.test_ci3_workflow tests.kb.test_ci5_workflow tests.kb.test_ci6_workflow tests.kb.test_ci_permission_asserts tests.kb.test_pages_workflow tests.kb.test_runtime_budget tests.kb.test_runtime_budget_workflows`
- Verification matrix suites:
  `python3 -m unittest tests.kb.test_unit_verification_matrix tests.kb.test_integration_verification_matrix tests.kb.test_regression_verification_matrix`
- Broad regression suite:
  `python3 -m pytest tests/ -q`

## Wiki processing checkpoint registry (runtime landed; CI wiring/bootstrap pending)

Schema contract, `scripts/kb/contracts.py` constants, the
`analysis_fingerprint()` helper, and the PR3 runtime entrypoint
`scripts/kb/checkpoint_registry.py` are on disk as of the checkpoint
runtime rollout.
The wiki processing checkpoint registry (ADR-026, ADR-027) lands across
four PRs per the Path C-prime plan in
[`docs/ideas/wiki-processing-checkpoint-registry.md`](ideas/wiki-processing-checkpoint-registry.md).
CI-3 wiring and the initial HITL bootstrap remain PR4 work. The
procedures below document the operator path enabled by the runtime and
the remaining CI wiring.

### Manual rescan

A manual rescan recomputes item state and reruns failed/stale entries
under operator control. After preparing a repo-local mutation JSON file
that identifies the batch and item transitions, run from the repo root:

```bash
python3 scripts/kb/checkpoint_registry.py --mutate \
  --input docs/staged/checkpoint-mutation.json \
  --trigger manual_rescan \
  --approval approved
```

`manual_rescan` is the only trigger that can move items between
`skipped` and `pending`. See ADR-026 § State transitions.

### Checkpoint recovery procedure

After a CI-3 partial-failure or fail-closed run, recover with this
sequence:

1. Inspect the operator snapshot at `wiki/status.md`
   for the `## Checkpoint Registry` section. Status publishing now renders
   `Registry: not initialized` until the HITL bootstrap creates the registry;
   after bootstrap it shows the latest `batch_id`, `trigger`, `status`,
   `error_summary`, and item-status counts.
2. Inspect the raw registry at
   `raw/wiki-processing/wiki-processing-checkpoint-registry.json` for
   the failing item's `last_error`, `status`, and `last_attempted_at`
   fields. The registry file does not exist until the PR4 HITL bootstrap
   step seeds it.
3. Resolve the underlying cause (validator failure, write denial, schema
   mismatch, lock contention).
4. Run a manual rescan (above) — `stale` and `failed`
   items are re-claimed by the next batch under deterministic transition
   rules. Requires `scripts/kb/checkpoint_registry.py`.

The registry is the source of truth; `wiki/status.md` is a derived
snapshot.

### Bootstrap dry-run-then-apply sequence

Bootstrap is an explicit mode (never auto-on-first-write). The required
sequence is dry-run, review the reconciliation report, operator
confirmation, then apply:

```bash
# 1. Dry-run bootstrap — emits the reconciliation report without writing
python3 scripts/kb/checkpoint_registry.py --bootstrap

# 2. Review the reconciliation report (item-by-item classification plus
#    any ambiguous cases) printed to stdout.

# 3. Operator confirms the report is correct.

# 4. Apply bootstrap with explicit approval
python3 scripts/kb/checkpoint_registry.py --bootstrap --apply \
  --approval approved
```

Ambiguous or contradictory items are left out of the bootstrap set and
require manual resolution before they can be tracked. See ADR-026 §
Bootstrap and recovery.

### Lock-unavailable: `raw/.wiki-processing-checkpoint.lock`

> **CI wiring pending.** The lock is used by the runtime for approved
> bootstrap and mutation writes. CI-3 starts using it once PR4 wires the
> runtime into the producer workflow.

If the checkpoint script reports
`reason_code=lock_unavailable` for `raw/.wiki-processing-checkpoint.lock`,
do **not** remove the lock blindly. The lock may be held by an active
CI-3 run. First, list active CI-3 runs:

```bash
# Forward-looking runbook step — CI-3 invokes the checkpoint runtime
# once the wiring lands.
gh run list --workflow=ci-3-pr-producer.yml --status in_progress
```

Once the CI-3 wiring lands: if no run is active and the lock is stale
(no in-progress CI-3 job), remove the lock file and retry. If a run is
active, wait for it to complete (lock is typically held for ~1 second
per batch under the single-lock-hold-long pattern; see
`synthesize_combined.py` precedent).
The repo-wide convention for holder-PID tracking is filed as backlog
issue [#183](https://github.com/wryenmeek/knowledgebase/issues/183).

## Exit semantics and failure handling

- **Fail-closed default:** any non-zero exit from preflight/index/lint/tests is a stop signal.
- **Ingest partial success:** `ingest.py` exit **2** means `partial_success` with per-source failures; inspect `per_source[]`, fix failed sources, rerun only failed inputs.
- **Ingest hard failure:** non-zero other than `2` is contract/preflight/write failure (`failed`), including lock contention (`reason_code=lock_unavailable`).
- **Persist policy envelope:** `persist_query.py` can return exit `0` with `status=no_write_policy` (expected no-write outcome) or `status=written`; both are valid automation outcomes.
- **No-write envelope contract:** `no_write_policy` must not mutate repo files (`analysis_path=null`, `index_updated=false`, `log_appended=false`).

## Issue closure evidence policy (security/refactor/testing hardening)

For recently closed issues labeled `security`, `refactor`, `testing`, or
`hardening`, add a deterministic closure-evidence comment in the issue thread
using this template:

```markdown
### Closure evidence
- Implementation reference: <PR URL, commit SHA, or issue/PR reference>
- Key files/surfaces changed:
  - <repo/path/one>
  - <repo/path/two>
- Validation commands:
  - `<exact command 1>`
  - `<exact command 2>`
- Pass/fail summary: PASS|FAIL with concise result details
```

The checker requires the `Closure evidence` heading and all four fields.
Exemptions are only accepted when the issue also carries the maintainer-applied
`closure-evidence-exemption-approved` label.

Automation report (read-only):

```bash
python3 -m scripts.validation.check_issue_closure_evidence \
  --lookback-days 30
```

CI-2 uses forward-only enforcement from the policy cutover timestamp:

```bash
python3 -m scripts.validation.check_issue_closure_evidence \
  --lookback-days 3650 \
  --issue-limit 500 \
  --closed-after 2026-05-25T00:00:00Z
```

Notes:

- `--issue-limit` defaults to `100`; CI-2 sets `500` to reduce false truncation
  failures on larger repositories.
- The cutover value (`2026-05-25T00:00:00Z`) is intentionally aligned with
  `CLOSURE_EVIDENCE_POLICY_START` in
  `.github/workflows/ci-2-analyst-diagnostics.yml`.

Remediation for flagged closures:

1. Post a closure-evidence comment that fills all four template sections.
2. Ensure the implementation reference points to the actual commit/PR used to
   remediate the issue.
3. Include exact validation commands and a PASS/FAIL summary from real runs.
4. Re-run `check_issue_closure_evidence` until `flagged_issue_count` is `0`.

## Runtime budget baselines and remediation

- **Canonical budget source:** `schema/runtime-budgets.json` is the single in-repo source of truth for CI runtime thresholds.
- **Deterministic measurement:** CI-2, CI-3, CI-5, and CI-6 record stage timings in integer seconds (`date -u +%s` start/end deltas) and evaluate them with `scripts/validation/_runtime_budget.py`.
- **Budget fields:** every stage budget entry defines `target_seconds`, `warn_pct`, and `fail_pct`.
- **Severity model:** `ok` when `duration_seconds <= target_seconds`; `warn` when `target_seconds < duration_seconds < fail_seconds`; `fail` when `duration_seconds >= fail_seconds` (`fail_seconds = ceil(target_seconds * (100 + fail_pct) / 100)`).
- **Warn policy detail:** `warn_pct` is preserved in the contract/artifact for budget tuning, but warn gating begins immediately when runtime exceeds `target_seconds`.
- **Fail-closed rule:** any `fail` runtime budget status hard-fails the job after publishing budget artifacts and step summary output.
- **Telemetry hygiene:** runtime artifacts include only workflow/stage IDs, durations, and thresholds. Secrets/tokens are never written to budget outputs.

Runtime-budget outputs:

| CI workflow | Machine-readable output | Human-readable output |
|---|---|---|
| CI-2 (`ci-2-analyst-diagnostics.yml`) | `diagnostics/runtime-metrics.json`, `diagnostics/runtime-budget-report.json` (artifact: `ci2-analyst-diagnostics-*`) | `$GITHUB_STEP_SUMMARY` runtime-budget table |
| CI-3 (`ci-3-pr-producer.yml`) | `ci3-metrics/runtime-metrics.json`, `ci3-metrics/runtime-budget-report.json` (artifact: `ci3-runtime-budget-*`) | `$GITHUB_STEP_SUMMARY` runtime-budget table |
| CI-5 (`ci-5-github-monitor.yml`) | `runtime-metrics/check-drift-runtime-metrics.json`, `runtime-metrics/check-drift-runtime-budget-report.json`; `runtime-metrics/fetch-runtime-metrics.json`, `runtime-metrics/fetch-runtime-budget-report.json`; `runtime-metrics/classify-runtime-metrics.json`, `runtime-metrics/classify-runtime-budget-report.json`; `runtime-metrics/synthesize-runtime-metrics.json`, `runtime-metrics/synthesize-runtime-budget-report.json` | `$GITHUB_STEP_SUMMARY` runtime-budget table |
| CI-6 (`ci-6-google-drive-monitor.yml`) | `runtime-metrics/check-drift-runtime-metrics.json`, `runtime-metrics/check-drift-runtime-budget-report.json`; `runtime-metrics/fetch-runtime-metrics.json`, `runtime-metrics/fetch-runtime-budget-report.json`; `runtime-metrics/classify-runtime-metrics.json`, `runtime-metrics/classify-runtime-budget-report.json`; `runtime-metrics/synthesize-runtime-metrics.json`, `runtime-metrics/synthesize-runtime-budget-report.json`; `runtime-metrics/advance-cursor-runtime-metrics.json`, `runtime-metrics/advance-cursor-runtime-budget-report.json` | `$GITHUB_STEP_SUMMARY` runtime-budget table |

Remediation playbook:

1. **WARN result:** inspect the stage row(s) in step summary and the runtime-budget JSON report, then optimize the slow stage or split work to reduce duration.
2. **FAIL result:** treat as fail-closed; do not bypass. Resolve stage slowness first, rerun, and confirm status returns to `ok`/`warn`.
3. **Threshold updates:** change `schema/runtime-budgets.json` in a reviewed PR with rationale tied to measured runtime trends.

## High-risk schema/topology baseline gate

Use this narrow manual gate only for schema contract edits, namespace/topology
moves, mass page rewrites, or ingest-pipeline refactors. MVP does **not** add a
new `scripts/validation/*` snapshot tree for this check; use the existing
deterministic surfaces plus git diff review.

```bash
# 1) run the fixed governance gate first
python3 .github/skills/validate-wiki-governance/logic/validate_wiki_governance.py

# 2) capture the targeted baseline scope before editing high-risk files
git --no-pager status --short --untracked-files=all -- schema wiki .github/skills .github/agents docs/architecture.md docs/decisions/ADR-007-control-plane-layering-and-packaging.md

# 3) after the change, rerun the focused framework gates
python3 -m unittest tests.kb.test_framework_contracts tests.kb.test_framework_skills tests.kb.test_framework_agents tests.kb.test_framework_references tests.kb.test_framework_write_surface_matrix tests.kb.test_skill_wrappers
python3 scripts/kb/update_index.py --wiki-root wiki
python3 scripts/kb/lint_wiki.py --wiki-root wiki --strict
```

- Review only expected diffs under `schema/**`, affected `.github/skills/**`,
  affected `.github/agents/**`, targeted `wiki/**`, and `wiki/index.md`.
- Block merge on unexpected path churn or any governance/test failure.

## CI-1 governance prerequisites (trusted-trigger model)

- **Protected default branch is required:** CI-1 checks `github.ref_protected` and rejects with `reject:trusted_trigger_model:ref_not_protected` when false.
- **Tiered path filter with benign allowlist:** pushes may include benign non-inbox paths (`docs/**`, `tests/**`, `wiki/pages/**`, `wiki/sources/**`, `README.md`, `LICENSE*`) alongside `raw/inbox/**` without rejection. Deletion-only `raw/inbox/**` cleanup emitted by CI-3 is treated as a no-op only when it is the sole non-inbox change; any additional non-inbox path still routes through the normal sensitive/benign checks. Paths outside both the inbox and the benign allowlist are treated as sensitive control-plane paths and rejected with `reject:path_filter:sensitive_control_plane_path:*`.
- **Operational guidance:** keep CI-1-triggering commits free of sensitive control-plane paths (`.github/workflows/**`, `scripts/**`, `AGENTS.md`, `pyproject.toml`, etc.); benign documentation or test changes bundled with inbox files are allowed.
- **If branch protection is not yet available:** use the documented fallback/manual path until branch protection is configured.

## CI fallback/manual path summary (CI-1..CI-6)

| CI | Normal role | If automation is unavailable/fails |
|---|---|---|
| **CI-1** (`.github/workflows/ci-1-gatekeeper.yml`) | trusted-trigger gatekeeper/handoff for `raw/inbox/**` | run local ingest → update_index → lint; open/update PR manually; keep fail-closed behavior and required checks. |
| **CI-2** (`.github/workflows/ci-2-analyst-diagnostics.yml`) | read-only diagnostics (`validate_wiki_governance`, `check_doc_freshness`, `content_quality_report`, `check_issue_closure_evidence` with forward-only cutover, `lint_wiki --strict`, dependency audit, secret scan, and test suite); triggers on `pull_request`, `push` to `main`, and `workflow_dispatch` | run the same diagnostics locally (`python3 .github/skills/validate-wiki-governance/logic/validate_wiki_governance.py --quiet`, `python3 -m scripts.validation.check_doc_freshness --scope wiki --path wiki/concepts --path wiki/entities --path wiki/analyses --as-of "$(date -u +%Y-%m-%d)" --max-age-days 90 --failures-only`, `python3 scripts/reporting/content_quality_report.py --mode summary --path wiki --failures-only`, `python3 -m scripts.validation.check_issue_closure_evidence --lookback-days 3650 --issue-limit 500 --closed-after 2026-05-25T00:00:00Z`, `python3 scripts/kb/lint_wiki.py --wiki-root wiki --strict`, `python -m pip install --quiet 'pip>=26.1' pip-audit && pip-audit --desc on --ignore-vuln CVE-2026-3219`, `gitleaks detect --source . --config .gitleaks.toml --redact --no-banner`, `python3 -m pytest tests/ -q --cov=scripts/kb --cov=scripts.validation._runtime_budget --cov-fail-under=90`), attach findings to PR/issue; workflow-level permissions stay `actions/checks/contents: read` with `issues: read` scoped to the `analyst-diagnostics` job; no repo-write automation needed. |
| **CI-4** (`.github/workflows/ci-4-framework-writer.yml`) | framework-writer: staged agent-generated content for `docs/**` and `.github/skills/**`; `workflow_dispatch` only; approval-gated | trigger `workflow_dispatch` manually after generating staged content; requires `ci4-framework-approval` environment gating; only allowlisted paths (`docs/**`, `.github/skills/**`) may be written. |
| **CI-5** (`.github/workflows/ci-5-github-monitor.yml`) | GitHub source monitor: daily schedule (cron `30 6 * * *`, 06:30 UTC) + `repository_dispatch` (type `upstream-source-updated`) + drift detection (read-only) + PR-producing fetch/synthesize path; repository_dispatch now fail-closes unless actor is trusted (`CI5_TRUSTED_DISPATCH_ACTORS`) and minimal payload contract fields are valid (`source_kind=github`, `delivery_id`, `upstream_repo`); optional `registry_path` hints from `repository_dispatch` payload or `workflow_dispatch` input run targeted mode only when allowlisted (`raw/github-sources/*.source-registry.json` + existing file), otherwise CI-5 logs explicit full-scan fallback diagnostics, writes fallback telemetry (`runtime-metrics/fallback-telemetry.json`), and emits warning annotations for `repository_dispatch` invalid-hint fallback (escalated on rerun attempts for repeated invalid hints); writes `raw/assets/**`, `raw/github-sources/**`, bounded `wiki/**` | run `scripts/github_monitor/check_drift.py` and `classify_drift.py` locally to inspect drift; run `fetch_content.py` and `synthesize_diff.py` locally with `--approval approved`; open PR for any changes. See ADR-015 and ADR-012 for governance rules. |
| **CI-6** (`.github/workflows/ci-6-google-drive-monitor.yml`) | Google Drive source monitor: weekly schedule (cron `0 8 * * 1`, Mon 08:00 UTC) + `repository_dispatch` (type `drive-source-updated`) + drift detection (read-only) + approval-gated fetch/synthesize path; workflow-level concurrency key is `ci-6-drive-monitor-${{ github.ref }}-${{ github.event.client_payload.channel_id || 'none' }}-${{ github.event.client_payload.resource_id || 'none' }}-${{ github.event.client_payload.change_id || 'none' }}-${{ github.event.client_payload.file_id || 'none' }}` and manual `workflow_dispatch` runs can scope to `inputs.registry_path`; writes`raw/assets/**`,`raw/drive-sources/**`, bounded`wiki/**` | run `scripts/drive_monitor/check_drift.py` and `classify_drift.py` locally to inspect drift; run `fetch_content.py` and `synthesize_diff.py` locally with `--approval approved`; advance cursor with `advance_cursor.py --approval approved`. See ADR-021 for governance rules. |

- **CI-3 manual dispatch note:** `maintainer_approved` remains a required attestation input for `workflow_dispatch`, manual runs are gated by protected-environment reviewer approval (`ci3-manual-approval`), and preflight hard-blocks dispatch commits that include sensitive control-plane paths (`.github/workflows/**`, `.github/skills/**`, `.github/agents/**`, `.github/extensions/**`, `scripts/**`, `schema/**`, `AGENTS.md`, `pyproject.toml`).

## Webhook relay operations for CI-5 and CI-6 (manual provisioning)

> **Scope boundary:** This repository now includes relay logic and tests only.
> Provisioning/deployment (GitHub App registration, Cloud Run service, Drive
> watch channel lifecycle, DNS/TLS, IAM) remains a maintainer-operated manual
> step.

### Required secrets and setup prerequisites

| Relay | Required secrets/config | Manual prerequisites |
|---|---|---|
| GitHub push relay (`upstream-source-updated`) | `GITHUB_WEBHOOK_SECRET` (used to validate `X-Hub-Signature-256`), `DISPATCH_TARGET_OWNER`, `DISPATCH_TARGET_REPO`, `DISPATCH_TOKEN` (least-privilege token that can call `POST /repos/{owner}/{repo}/dispatches`) | Register/install GitHub App on monitored upstream repos, subscribe to `push` events, configure webhook URL/secret. |
| Drive relay (`drive-source-updated`) | `DRIVE_CHANNEL_TOKEN_SECRET` (used to validate signed channel token context), `DISPATCH_TARGET_OWNER`, `DISPATCH_TARGET_REPO`, `DISPATCH_TOKEN` | Create/renew Drive watch channels manually, set channel token using `build_drive_channel_token(...)`, and point Google notifications at the relay HTTPS endpoint. |

Additional runtime prerequisite for both relays:

- The relay runtime must have a checkout/snapshot of this repository available at
  startup so it can read source registries at:
  `raw/github-sources/*.source-registry.json` and
  `raw/drive-sources/*.source-registry.json`.

### Stable `repository_dispatch` payload contracts

- `event_type: upstream-source-updated` payload fields:
  `source_kind` (`"github"`), `registry_path`, `upstream_repo`, `upstream_ref`,
  `upstream_after_sha`, `delivery_id`, `observed_at` (ISO-8601), `changed_paths`
- `event_type: drive-source-updated` payload fields:
  `source_kind` (`"drive"`), `alias`, `registry_path`, `file_id`, `change_id`,
  `channel_id`, `resource_id`, `delivery_id`, `observed_at` (ISO-8601)

### Relay behavior guarantees

- GitHub relay validates `X-Hub-Signature-256` (HMAC SHA-256) and fails closed
  on signature mismatch.
- GitHub relay enforces an upstream source allowlist by dispatching only when the
  push source repo matches a monitored registry and changed paths intersect active
  or uninitialized tracked entries.
- GitHub relay only dispatches when changed push paths intersect monitored
  registry entry paths for that upstream `owner/repo`.
- GitHub relay suppresses replayed deliveries (`X-GitHub-Delivery`) with a TTL
  cache and returns `replay_suppressed` on duplicates.
- Drive relay validates signed channel token context (including optional
  channel/resource expectations) and registry alias/path, and fails closed on
  mismatches.
- Drive relay dispatches only for relevant lifecycle states and suppresses
  replays using dedupe key
  `X-Goog-Channel-ID + X-Goog-Resource-ID + change_id + file_id`.
- Replay suppression is best-effort unless you back relay caches with a shared
  store; the built-in cache is process-local.
- Drive lifecycle handling is explicit: notifications with
  `X-Goog-Channel-Expiration` in the past are ignored (`channel_expired`), and
  `sync`/`heartbeat` notifications remain ignored; if expiration is within one
  hour they return `channel_renewal_due`. When no expiration header is present,
  relay behavior is deterministic: process relevant states normally and ignore
  `sync`/`heartbeat` as `resource_state_ignored`.

### Minimal handler wiring (example)

```python
from pathlib import Path
from scripts.github_monitor._relay import (
    GitHubApiDispatchClient as GitHubDispatchClient,
    relay_github_push_event,
)
from scripts.drive_monitor._relay import (
    InMemoryDriveReplayCache,
    GitHubApiDispatchClient as DriveDispatchClient,
    relay_drive_notification,
)

REPO_ROOT = Path(".").resolve()
drive_replay_cache = InMemoryDriveReplayCache()

# GitHub webhook request:
# result = relay_github_push_event(
#   repo_root=REPO_ROOT,
#   headers=request.headers,
#   body=request.get_data(),
#   webhook_secret=os.environ["GITHUB_WEBHOOK_SECRET"],
#   dispatch_client=GitHubDispatchClient(...),
# )

# Drive webhook request:
# result = relay_drive_notification(
#   repo_root=REPO_ROOT,
#   headers=request.headers,
#   token_secret=os.environ["DRIVE_CHANNEL_TOKEN_SECRET"],
#   dispatch_client=DriveDispatchClient(...),
#   replay_cache=drive_replay_cache,
# )
```

Example service run commands (for the maintainer-owned HTTP wrapper modules):

- local/dev (GitHub): `python -m scripts.github_monitor.relay_http --host 0.0.0.0 --port 8080`
- container/Cloud Run entrypoint (GitHub): `gunicorn -b :${PORT:-8080} scripts.github_monitor.relay_http:app`
- local/dev (Drive): `python -m scripts.drive_monitor.relay_http --host 0.0.0.0 --port 8080`
- container/Cloud Run entrypoint (Drive): `gunicorn -b :${PORT:-8080} scripts.drive_monitor.relay_http:app`

Suggested HTTP response mapping from relay result:

- `status=dispatched` → `202 Accepted`
- `status=ignored` (non-relevant event/replay) → `202 Accepted`
- `status=rejected` (invalid signature/token/headers/body) → `400 Bad Request`
- GitHub relay oversized request body (`reason=request_body_too_large`) → `413 Payload Too Large`
- `status=failed` (dispatch transport failure) → `502 Bad Gateway` / retryable `5xx`

## Support and infrastructure workflows

| Workflow | Trigger | Purpose | Manual equivalent |
|---|---|---|---|
| `pre-commit.yml` | `push` (all branches), `pull_request` to main | Runs all pre-commit hooks in CI so governance guardrails are verified even when local hooks are skipped | `pre-commit run --all-files` |
| `pages.yml` | `push` to main (`wiki/**`, `mkdocs.yml`, `.github/workflows/pages.yml`), `workflow_dispatch` | Builds MkDocs Material site from `wiki/`, installs pinned qmd runtime with integrity verification, runs `qmd collection add wiki --name wiki`, gates on qmd preflight before `qmd embed`, persists `.qmd/index` artifact for downstream query consumers, installs pinned Pagefind runtime with integrity verification, runs Pagefind indexing, and deploys via `actions/deploy-pages` (OIDC, no PAT required; requires Pages source set to GitHub Actions in repo Settings → Pages) | `mkdocs build --strict && qmd collection add wiki --name wiki && python3 scripts/kb/qmd_preflight.py --repo-root . && qmd embed && pagefind --site site` then upload `.qmd/index` (artifact) and `site/` (Pages artifact) |
| `wiki-freshness.yml` | Weekly schedule (cron `30 3 * * 1`, Mon 03:30 UTC), `workflow_dispatch` | Advisory freshness check on wiki pages; detects content that may be stale | (1) `python3 -m scripts.validation.check_doc_freshness --scope wiki --as-of "$(date -u +%Y-%m-%d)" --max-age-days 90 --failures-only > freshness-reports/wiki-freshness.json`<br>(2) annotate stale pages as `::warning` annotations<br>(3) `python3 -m scripts.validation.classify_stale --freshness-report freshness-reports/wiki-freshness.json --output freshness-reports/freshness-routing.json --afk-threshold-days 180`<br>(4) advisory governance signal sweep via `validate_wiki_governance.py --mode signal` |
| `github-customizations-freshness.yml` | `push` to `.github/**`, weekly schedule (cron `0 4 * * 1`, Mon 04:00 UTC), `workflow_dispatch` | Validates `.github/` customizations (skills, agents, hooks) are fresh and internally consistent; **has write side effects** — opens a repair PR (`contents: write`, `pull-requests: write`) for auto-fixable drift and creates a GitHub Issue (`issues: write`) for ambiguous drift that requires human review | `python3 -m scripts.kb.github_customizations_freshness --output drift-report.json` |
| `fleet-plan.yml` | Daily schedule (cron `0 6 * * *`, 06:00 UTC), `workflow_dispatch` | Fleet phase 1: creates a Jules planning session for open issues; stores the pending session ID in the `fleet-state` branch | `cd scripts/fleet && bun run fleet-plan.ts` |
| `fleet-dispatch.yml` | `pull_request` opened/reopened | Fleet phase 2: detects Jules planning PRs via `fleet-state` pending session; merges the planning PR and dispatches per-issue task sessions. Fail-closed preflight enforces `FLEET_PENDING_DATE` format (`YYYY_MM_DD`) and rejects path-escaping values. | `cd scripts/fleet && bun run fleet-dispatch.ts` |
| `fleet-merge.yml` | `workflow_run` (CI-2 completes), `workflow_dispatch` | Event-driven sequential merge of Jules-authored PRs: fires when CI-2 passes on a fleet PR head SHA → update branch → squash merge; re-dispatches on conflict. Manual `workflow_dispatch` sweeps all open fleet PRs with currently passing CI. Fail-closed preflight enforces `FLEET_PENDING_DATE` format (`YYYY_MM_DD`) and merge fails closed when zero check runs exist unless `FLEET_ALLOW_NO_CHECKS=true`. | `cd scripts/fleet && bun run fleet-merge.ts` |
| `copilot-setup-steps.yml` | `workflow_dispatch`, `push`/`pull_request` on `.github/workflows/copilot-setup-steps.yml` and `scripts/fleet/**` | Configures Copilot cloud agent environment with Python 3.12, Bun, and all project dependencies; enforces fleet Bun tests/build on workflow-triggered runs | Push workflow or `scripts/fleet/**` changes to default branch; runs automatically when Copilot cloud agent starts a session |

### Fleet mutation troubleshooting (`FAILED_PRECONDITION`)

- Fleet mutation entrypoints (`fleet-plan.ts`, `fleet-dispatch.ts`, `fleet-merge.ts`) now fail closed with bounded retries and a `sanitized_error_envelope` that includes `classification`, `hint`, and `root_cause_path`.
- Retry policy is deterministic: retryable classes (`failed_precondition`, `rate_limit`, `network`) back off in bounded steps and hard-fail after `FLEET_MUTATION_MAX_ATTEMPTS` (default `3`, max `5`).
- Non-retryable classes (`auth`, `permission`) fail immediately after preflight diagnostics; there is no permissive fallback path.
- Preflight checks validate `JULES_API_KEY`, `GITHUB_TOKEN`, repo format (`owner/repo`), base-branch format, base-branch visibility in local/origin refs, retry bounds, and fleet date format (`FLEET_PENDING_DATE` must be `YYYY_MM_DD`) before any Jules mutation call.
- Local validation commands:
  - `cd scripts/fleet && bun test`
  - `cd scripts/fleet && bun build fleet-analyze.ts fleet-plan.ts fleet-dispatch.ts fleet-merge.ts --target bun --outdir dist`

## Milestone evidence mapping (M0..M4)

| Gate | Concrete evidence in this repo |
|---|---|
| **M0: terminology/assumptions freeze** | `raw/processed/SPEC.md` (Assumptions/Terminology sections) + `tests/kb/test_contracts.py` (canonical policy IDs, token profiles, reason/envelope constants). |
| **M1: interface executability** | `scripts/kb/ingest.py`, `update_index.py`, `lint_wiki.py`, `qmd_preflight.py`, `persist_query.py`; validated by `tests/kb/test_ingest.py`, `test_update_index.py`, `test_lint_wiki.py`, `test_qmd_preflight.py`, `test_persist_query.py`. |
| **M2: security/automation enforcement** | `.github/workflows/ci-1-gatekeeper.yml`, `ci-2-analyst-diagnostics.yml`, `ci-3-pr-producer.yml`; enforced by `tests/kb/test_ci1_workflow.py`, `test_ci2_workflow.py`, `test_ci3_workflow.py`, `test_ci_permission_asserts.py`. |
| **M3: verification readiness** | `raw/processed/SPEC.md` Verification Matrix + `tests/kb/test_unit_verification_matrix.py`, `test_integration_verification_matrix.py`, `test_regression_verification_matrix.py`. |
| **M4: pre-implementation go/no-go (complete)** | `raw/processed/SPEC.md` Implementation-ready milestone gates + Final Pre-Implementation Ambiguity Review Checklist, plus this runbook (`docs/mvp-runbook.md`) as executable operator evidence. MVP framework is implemented; post-MVP phase governance lives in `docs/ideas/spec.md` and ADR-015 through ADR-021. |
