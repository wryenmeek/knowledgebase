# MVP Runbook (Task 15 / M4)

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

## Phase 0 bootstrap: runtime prerequisites

Make wrapper validation runnable through the same repo-local bootstrap contract
in local and CI environments before later phases depend on it more heavily.

| Surface | Required prerequisites | Bootstrap rule |
|---|---|---|
| Local wrapper validation (`validate-wiki-governance`, `sync-knowledgebase-state --check-only`) | `python3`, repo checkout, `wiki/`, `qmd` on `PATH`, `.qmd/index` | Prefer the authoritative qmd runtime when available. If only wrapper validation is needed, use a repo-local validation shim plus `mkdir -p .qmd/index` so preflight stays deterministic and fail-closed without introducing non-repo state. |
| CI-2 / CI-3 wrapper validation | `python3`, checked-out repo, repo-local `qmd` shim, `.qmd/index` directory | Bootstrap a repo-local `qmd` shim inside the workflow workspace and prepend it to `PATH`; never depend on a machine-global install. |
| Full qmd index/query flow | Authoritative qmd runtime that supports `collection add`, `embed`, and `query` | Remains the operator/manual path below. CI bootstrap only satisfies current wrapper-preflight needs; authoritative qmd packaging/version pinning stays in the post-MVP verification story until a later phase ratifies it. |

Validation-only bootstrap example (repo root):

```bash
mkdir -p .ci-bin .qmd/index
cat > .ci-bin/qmd <<'EOF'
#!/usr/bin/env sh
set -eu
exit 0
EOF
chmod +x .ci-bin/qmd

PATH="$PWD/.ci-bin:$PATH" \
  python3 .github/skills/validate-wiki-governance/logic/validate_wiki_governance.py

PATH="$PWD/.ci-bin:$PATH" \
  python3 .github/skills/sync-knowledgebase-state/logic/sync_knowledgebase_state.py --check-only
```

This shim is intentionally scoped to wrapper validation only. Use the
authoritative qmd runtime for `qmd collection add`, `qmd embed`, and
`qmd query`; do not treat the shim as a substitute for real indexing/query
coverage.

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
python3 -m pytest tests/ -q
```

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

# focused framework test suite, including wrapper-boundary coverage
python3 -m unittest tests.kb.test_framework_contracts tests.kb.test_framework_skills tests.kb.test_framework_agents tests.kb.test_framework_references tests.kb.test_framework_write_surface_matrix tests.kb.test_skill_wrappers
```

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
| Framework contract suites | `python3 -m unittest tests.kb.test_framework_contracts tests.kb.test_framework_skills tests.kb.test_framework_agents tests.kb.test_framework_references tests.kb.test_framework_write_surface_matrix` | Run whenever framework docs, skills, agents, or the `AGENTS.md` write-surface matrix change. |
| Wrapper behavior suite | `python3 -m unittest tests.kb.test_skill_wrappers` | Confirms the fixed wrapper order, allowlists, and fail-closed execution envelope. |
| Helper surface suites | `python3 -m unittest tests.kb.test_context_import_helpers tests.kb.test_documentation_helpers tests.kb.test_validate_source_registry tests.kb.test_validate_wiki_topology tests.kb.test_harnesses` | Covers skill-local helper contracts without widening repo-write authority. |
| Repo script suites | `python3 -m unittest tests.kb.test_contracts tests.kb.test_sourceref tests.kb.test_ingest tests.kb.test_update_index tests.kb.test_lint_wiki tests.kb.test_qmd_preflight tests.kb.test_persist_query tests.kb.test_write_utils` | Required when `scripts/kb/**` or approved repo-level helper packages change. |
| Workflow governance suites | `python3 -m unittest tests.kb.test_workflow_yaml_syntax tests.kb.test_ci1_workflow tests.kb.test_ci2_workflow tests.kb.test_ci3_workflow tests.kb.test_ci_permission_asserts` | Keep CI-1 no-write trusted handoff, CI-2 read-only diagnostics, and CI-3 allowlisted writes aligned with workflow YAML. |
| Verification matrix suites | `python3 -m unittest tests.kb.test_unit_verification_matrix tests.kb.test_integration_verification_matrix tests.kb.test_regression_verification_matrix` | Final verification pass for unit, integration, and regression coverage expectations. |
| Broad regression suite | `python3 -m pytest tests/ -q` | Final merge gate after the focused lanes above stay green. |

| Approval lane | Authoritative entrypoint | Required control |
|---|---|---|
| CI-1 no-write trusted handoff | `.github/workflows/ci-1-gatekeeper.yml` on `push` to protected default-branch `raw/inbox/**` changes | Read-only token, inbox-only scope, and handoff-only behavior. |
| CI-2 read-only diagnostics | `.github/workflows/ci-2-analyst-diagnostics.yml` on `push`, `pull_request`, or `workflow_dispatch` | Read-only permissions plus artifact upload only; no repo mutations. |
| CI-3 allowlisted writes | `.github/workflows/ci-3-pr-producer.yml` from CI-1 handoff or protected manual dispatch | Allowlisted writes only (`wiki/**`, `wiki/index.md`, `wiki/log.md`, `raw/processed/**`) plus protected-environment approval for manual dispatch. |

## Verification planning baseline

The matrix in [`docs/ideas/spec.md`](ideas/spec.md#verification-matrix-and-ci-migration-rules)
is the planning authority for post-MVP verification expansion. It does **not**
change today's runtime or CI enforcement. Until a later phase is explicitly
approved, keep these existing MVP suites green:

- Framework contract suites:
  `python3 -m unittest tests.kb.test_framework_contracts tests.kb.test_framework_skills tests.kb.test_framework_agents tests.kb.test_framework_references tests.kb.test_framework_write_surface_matrix`
- Wrapper behavior suite:
  `python3 -m unittest tests.kb.test_skill_wrappers`
- Helper surface suites:
  `python3 -m unittest tests.kb.test_context_import_helpers tests.kb.test_documentation_helpers tests.kb.test_validate_source_registry tests.kb.test_validate_wiki_topology tests.kb.test_harnesses`
- Repo script suites:
  `python3 -m unittest tests.kb.test_contracts tests.kb.test_sourceref tests.kb.test_ingest tests.kb.test_update_index tests.kb.test_lint_wiki tests.kb.test_qmd_preflight tests.kb.test_persist_query tests.kb.test_write_utils`
- Workflow governance suites:
  `python3 -m unittest tests.kb.test_workflow_yaml_syntax tests.kb.test_ci1_workflow tests.kb.test_ci2_workflow tests.kb.test_ci3_workflow tests.kb.test_ci_permission_asserts`
- Verification matrix suites:
  `python3 -m unittest tests.kb.test_unit_verification_matrix tests.kb.test_integration_verification_matrix tests.kb.test_regression_verification_matrix`
- Broad regression suite:
  `python3 -m pytest tests/ -q`

## Exit semantics and failure handling

- **Fail-closed default:** any non-zero exit from preflight/index/lint/tests is a stop signal.
- **Ingest partial success:** `ingest.py` exit **2** means `partial_success` with per-source failures; inspect `per_source[]`, fix failed sources, rerun only failed inputs.
- **Ingest hard failure:** non-zero other than `2` is contract/preflight/write failure (`failed`), including lock contention (`reason_code=lock_unavailable`).
- **Persist policy envelope:** `persist_query.py` can return exit `0` with `status=no_write_policy` (expected no-write outcome) or `status=written`; both are valid automation outcomes.
- **No-write envelope contract:** `no_write_policy` must not mutate repo files (`analysis_path=null`, `index_updated=false`, `log_appended=false`).

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
- **Strict inbox-only scope is required:** pushes that include `raw/inbox/**` plus non-inbox paths are rejected with `reject:path_filter:outside_raw_inbox:*`.
- **Operational guidance:** keep CI-1-triggering commits scoped to `raw/inbox/**`; apply broader repository changes in separate commits/PRs.
- **If branch protection is not yet available:** use the documented fallback/manual path until branch protection is configured.

## CI fallback/manual path summary (CI-1..CI-3)

| CI | Normal role | If automation is unavailable/fails |
|---|---|---|
| **CI-1** (`.github/workflows/ci-1-gatekeeper.yml`) | trusted-trigger gatekeeper/handoff for `raw/inbox/**` | run local ingest → update_index → lint; open/update PR manually; keep fail-closed behavior and required checks. |
| **CI-2** (`.github/workflows/ci-2-analyst-diagnostics.yml`) | read-only diagnostics (`lint_wiki --strict` + test suite) | run the same diagnostics locally (`lint_wiki`, `pytest tests/`), attach findings to PR/issue; no repo-write automation needed. |
| **CI-3** (`.github/workflows/ci-3-pr-producer.yml`) | write-capable PR producer after trusted handoff/manual approval | execute the local sequence in this runbook, commit only allowlisted paths (`wiki/**`, `raw/processed/**`), and open/update PR manually through normal approvals/checks. Manual dispatch runs additionally require protected-environment reviewer approval (`ci3-manual-approval`). |

- **CI-3 manual dispatch note:** `maintainer_approved` remains a required attestation input for `workflow_dispatch`, and manual runs are gated by protected-environment reviewer approval (`ci3-manual-approval`) for authoritative control.

## Milestone evidence mapping (M0..M4)

| Gate | Concrete evidence in this repo |
|---|---|
| **M0: terminology/assumptions freeze** | `raw/processed/SPEC.md` (Assumptions/Terminology sections) + `tests/kb/test_contracts.py` (canonical policy IDs, token profiles, reason/envelope constants). |
| **M1: interface executability** | `scripts/kb/ingest.py`, `update_index.py`, `lint_wiki.py`, `qmd_preflight.py`, `persist_query.py`; validated by `tests/kb/test_ingest.py`, `test_update_index.py`, `test_lint_wiki.py`, `test_qmd_preflight.py`, `test_persist_query.py`. |
| **M2: security/automation enforcement** | `.github/workflows/ci-1-gatekeeper.yml`, `ci-2-analyst-diagnostics.yml`, `ci-3-pr-producer.yml`; enforced by `tests/kb/test_ci1_workflow.py`, `test_ci2_workflow.py`, `test_ci3_workflow.py`, `test_ci_permission_asserts.py`. |
| **M3: verification readiness** | `raw/processed/SPEC.md` Verification Matrix + `tests/kb/test_unit_verification_matrix.py`, `test_integration_verification_matrix.py`, `test_regression_verification_matrix.py`. |
| **M4: pre-implementation go/no-go** | `raw/processed/SPEC.md` Implementation-ready milestone gates + Final Pre-Implementation Ambiguity Review Checklist, plus this runbook (`docs/mvp-runbook.md`) as executable operator evidence. |
