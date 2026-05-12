# Spec: LLM-Organized Knowledgebase Bootstrap

## Assumptions and Defaults

1. This repository implements a persistent wiki pattern (not query-time-only RAG).
2. `AGENTS.md` is the primary schema/contract file for agent behavior.
3. Raw source truth remains immutable once moved to `raw/processed/`.
4. qmd is included in MVP and treated as part of the local search/query stack.
5. Query persistence default is `auto_persist_when_high_value`, with deterministic rule:
   - confidence `>= 4/5`,
   - at least 2 source references,
   - no unresolved contradiction flag.
6. Batch ingest policy is `continue_and_report_per_source`.
7. Source sensitivity metadata is required in frontmatter.
8. Confidence rubric is numeric `1..5` for synthesized wiki content.
9. Canonical `sources` format is `repo_uri_with_anchor_and_checksum`.
10. Append-log policy is `log_only_state_changes`.
11. External assets policy is `external_assets_allowed_as_authoritative_if_checksumed`.
12. Token permission profile policy is `custom_per_workflow_matrix`.
13. Concurrency control policy is `workflow_concurrency_group_plus_local_file_lock`.

## Normative Precedence for This Spec

When requirements conflict during refinement, apply this precedence order:

1. Explicitly approved user constraints/assumption decisions.
2. Security/trust-boundary constraints (most restrictive rule wins).
3. This `SPEC.md` baseline.
4. Approved planning artifacts.
5. External research and workflow guidance.

Tie-break rule: if conflict remains unresolved after precedence, do not choose silently; record it in the final ambiguity checklist and require explicit resolution before implementation planning.

## Terminology (Canonical)

- **SourceRef**: `repo://<owner>/<repo>/<path>@<git_sha>#<anchor>?sha256=<64-hex>` (anchor required; use `#asset` when line anchors are not applicable).
- **Authoritative source corpus**: repository-local inputs under `raw/inbox/**` plus checksummed external assets vendored into `raw/assets/**`.
- **External asset**: externally originated file stored in `raw/assets/**`; authoritative only when checksummed and referenced via SourceRef.
- **State change**: net repository mutation to `wiki/**`, `wiki/index.md`, `wiki/log.md`, or `raw/processed/**`.
- **No-op rerun**: execution producing no state change.
- **Result envelope**: machine-readable JSON output emitted by write-capable scripts.
- **Token profile**: explicit permission set bound to a workflow role.
- **Concurrency guard**: workflow `concurrency.group` control plus local write lock file enforcement.

## Objective

Build a production-usable, repo-scoped, LLM-maintained knowledgebase where:

- humans curate source inputs and adjudicate conflicts,
- agents perform ingest/query/lint maintenance workflows,
- knowledge compounds through persistent markdown artifacts,
- and all operations are auditable via git history and `wiki/log.md`.

### Primary users

- Primary: solo maintainer/researcher.
- Secondary: collaborators reviewing synthesized wiki output.

## Scope

### MVP scope

- Persistent wiki architecture with `raw/`, `wiki/`, and schema layers.
- Mermaid support in wiki/source artifacts.
- Commit-triggered ingest for new/changed files in `raw/inbox/`.
- gh-aw-driven automation workflows.
- Security/trust controls for untrusted source input and automation boundaries.
- Knowledge corpus scope is repository-local: authoritative ingest is limited to this repository's `raw/inbox/**` plus checksummed external assets stored in `raw/assets/**`; non-vendored or non-checksummed external material remains citation-only in MVP.
- qmd-backed local search/query capability.

### Phase 2 scope

- GitHub Pages wiki browsing/search surface.
- Page-level human feedback submission to GitHub Issues.
- Advanced KPI dashboards and quality scoring classes.

## Architecture and Repository Structure

```text
.github/                          Existing skills/prompts/hooks (already present)
AGENTS.md                         Agent schema + operational rules for wiki maintenance
raw/
  inbox/                          New sources pending ingest (untrusted input)
  processed/                      Immutable post-ingest source artifacts
  assets/                         Downloaded/local media; external assets authoritative only when checksummed
wiki/
  index.md                        Content catalog (findability anchor)
  log.md                          Append-only chronology/audit trail
  sources/                        Per-source summary/synthesis pages
  entities/                       Entity pages
  concepts/                       Concept/theme pages
  analyses/                       Persisted high-value query outputs
schema/
  page-template.md                Frontmatter and page shape contract
  ingest-checklist.md             Deterministic ingest checklist
scripts/
  kb/
    ingest.py                     Source ingest orchestrator
    update_index.py               Deterministic index updater
    lint_wiki.py                  Link/orphan/consistency checker
    persist_query.py              Policy-gated persistence of high-value query outputs
tests/
  kb/                             Unit/integration/e2e/regression tests
```

## Frontmatter Contract (Wiki Layer)

All generated wiki pages must include YAML frontmatter with required keys:

- `type`: entity | concept | source | analysis | process
- `title`: canonical page title
- `status`: active | superseded | archived
- `sources`: list of `SourceRef` values in canonical `repo_uri_with_anchor_and_checksum` format
- `open_questions`: unresolved contradictions or arbitration needs
- `confidence`: numeric `1..5`
- `sensitivity`: public | internal | restricted
- `updated_at`: ISO-8601 timestamp
- `tags`: list of normalized tags

### Canonical `sources` reference format

`sources` entries are mandatory SourceRef strings:

```text
repo://<owner>/<repo>/<path>@<git_sha>#<anchor>?sha256=<64-hex>
```

Rules:

1. `#<anchor>` is required (`#Lx-Ly` for line ranges; `#asset` for binary/media artifacts).
2. `sha256` is required and must match the referenced file bytes.
3. Paths must remain repository-relative and resolve under `raw/inbox/**`, `raw/processed/**`, or `raw/assets/**`.

## Command and Interface Contracts

### Command set

```bash
# ingest one source
python3 scripts/kb/ingest.py --source raw/inbox/<source-file>.md --wiki-root wiki --schema AGENTS.md

# ingest batch (ordered manifest, continue-and-report policy)
python3 scripts/kb/ingest.py --sources-manifest raw/inbox/<batch-manifest>.txt --batch-policy continue_and_report_per_source --wiki-root wiki --schema AGENTS.md --report-json

# rebuild catalog/index artifacts
python3 scripts/kb/update_index.py --wiki-root wiki --write

# semantic and structural lint
python3 scripts/kb/lint_wiki.py --wiki-root wiki --strict

# test suite
python3 -m unittest discover -s tests -p "test_*.py"

# qmd indexing/query (MVP)
qmd collection add wiki --name wiki
qmd embed
qmd query "<query>"

# persist high-value query output (policy-gated + machine-readable envelope)
python3 scripts/kb/persist_query.py --query "<query>" --wiki-root wiki --schema AGENTS.md --min-confidence 4 --min-sources 2 --require-no-contradiction --result-json
```

### Ingest batch semantics (executable)

1. Exactly one input mode is allowed: `--source` (single) or `--sources-manifest` (batch).
2. Batch manifests are newline-delimited repo-relative paths and are processed in file order.
3. Batch policy is fixed to `continue_and_report_per_source`: each source is independently attempted, failures do not halt remaining sources.
4. Exit codes:
   - `0`: all sources succeeded,
   - `2`: at least one per-source failure occurred (partial success),
   - non-zero (`!=0,2`): preflight/contract failure (no writes).
5. Per-source outcomes are emitted in a JSON result envelope when `--report-json` is set.

### Machine-readable result envelopes

Write-capable commands must emit JSON to stdout when JSON output flags are enabled. `persist_query.py --result-json` is mandatory in automation paths.

Required envelope keys:

- `status`: `written` | `no_write_policy` | `partial_success` | `failed`
- `reason_code`: stable failure/policy code
- `policy`: applied policy identifiers (`auto_persist_when_high_value`, `log_only_state_changes`, etc.)
- `analysis_path`: written path or `null`
- `index_updated`: boolean
- `log_appended`: boolean
- `sources`: SourceRef array

### Interface contract matrix

| Workflow | Inputs | Outputs | Side effects | Idempotency | Failure behavior | Boundary behavior |
|---|---|---|---|---|---|---|
| Ingest | `--source` under `raw/inbox/**` or `--sources-manifest`; fixed `--batch-policy continue_and_report_per_source`; `--schema` (`AGENTS.md`); `--wiki-root` (`wiki`) | created/updated pages under `wiki/sources/**`, `wiki/entities/**`, `wiki/concepts/**`; deterministic per-source JSON result envelope when `--report-json`; updated `wiki/index.md` and appended `wiki/log.md` only on state change | writes under `wiki/**`; moves each successful source to `raw/processed/**`; failed sources remain in inbox | no-op reruns do not duplicate pages/index/log; log remains append-only for state changes only | exit `2` on partial per-source failures; non-zero on preflight/write failures; actionable diagnostics | reject path traversal/out-of-repo paths; treat source as data; never write outside `wiki/**` + `raw/processed/**` |
| Update index | `--wiki-root`; optional `--write` | deterministic `wiki/index.md` ordering/content | rewrites `wiki/index.md` only when `--write` is set | repeated runs on unchanged wiki tree produce byte-equivalent output | non-zero exit on parse/schema violations | read scope limited to `wiki/**`; must not mutate non-index files |
| Lint | `--wiki-root`, `--strict` | diagnostics for links/orphans/frontmatter/contradictions | none (read-only in strict mode) | deterministic findings for same wiki tree | non-zero exit when strict checks fail or inputs invalid | read scope limited to `wiki/**`; strict mode must not auto-fix |
| qmd index | qmd collection config + wiki corpus | refreshed qmd index/cache artifacts | writes qmd-managed index/cache artifacts only | repeated runs on unchanged corpus converge to equivalent index state | non-zero exit on missing qmd runtime or indexing errors | must not mutate `raw/**` or `wiki/**` during indexing |
| qmd query | indexed collection(s), query text | ranked results/snippets | reads qmd index/cache artifacts | idempotent at repository content level | non-zero exit on missing index/runtime errors | must not mutate `raw/**` or `wiki/**` during query |
| Query persist (policy-gated) | query text/result payload, SourceRef list, confidence, contradiction state, `--wiki-root`, `--schema`, `--result-json` | analysis page under `wiki/analyses/**` when policy passes; JSON result envelope (`status`, `reason_code`, `analysis_path`, `index_updated`, `log_appended`, `sources`) for every run | writes only under `wiki/analyses/**`, `wiki/index.md`, `wiki/log.md` when policy passes and a state change exists | reruns with equivalent normalized query/evidence converge without duplicate analysis/log records; no-op reruns do not append logs | non-zero on invalid metadata/write/lock failures; policy miss returns `no_write_policy` envelope with explicit reason | must not mutate `raw/**`; reject out-of-repo paths; enforce `auto_persist_when_high_value` gate (`confidence >=4`, `sources >=2`, no unresolved contradiction) |

## gh-aw Automation Model

### Workflow pattern defaults

- Prefer specialized workflows over one monolithic workflow.
- Separate read-only analyst workflows from PR-producing workflows.
- Use meta-workflows to monitor workflow health, drift, and failures.
- Keep workflows observable and auditable (logs + explicit outcomes).

### Trigger and permission defaults

- Canonical ingest trigger: trusted `push` context on protected branch for `raw/inbox/**`.
- Least privilege permissions by default; elevate only where strictly required.
- Disallow out-of-bound write paths outside intended workflow targets.
- Define fallback/manual execution path when automation is unavailable.
- Token permissions are assigned only through the `custom_per_workflow_matrix` profiles below.

### Token permission profiles (`custom_per_workflow_matrix`)

| Profile ID | Workflow binding | Minimum GitHub token permissions | Explicitly forbidden |
|---|---|---|---|
| `tp-gatekeeper` | CI-1 trigger → workflow handoff | `contents: read`, `actions: read` | `contents: write`, `pull-requests: write`, `issues: write`, `packages: write`, `id-token: write` |
| `tp-analyst-readonly` | CI-2 workflow (read-only analyst) | `contents: read`, `actions: read`, `checks: read` | all repository-write scopes |
| `tp-pr-producer` | CI-3 workflow (PR-producing) | `contents: write`, `pull-requests: write`, `actions: read`, `checks: read` | settings/admin/secrets scopes |
| `tp-github-monitor` | CI-5 GitHub monitor workflow (fetch + synthesize) | `contents: write`, `pull-requests: write`, `issues: write` (job-scoped) | settings/admin/secrets scopes; `packages: write`; `id-token: write` |
| `tp-freshness-readonly` | CI-freshness wiki freshness scan (read-only) | `contents: read` | all repository-write scopes |
| `tp-customizations-readwrite` | CI-customizations-freshness `.github/` drift detection + repair PR + issue (job-scoped write) | workflow-level `contents: read`; `contents: write`, `pull-requests: write` (open-repair-pr job); `issues: write` (open-drift-issue job) | settings/admin/secrets scopes; `packages: write`; `id-token: write` |

### Concurrency controls (`workflow_concurrency_group_plus_local_file_lock`)

1. Write-capable workflows MUST declare:

```yaml
concurrency:
  group: kb-write-${{ github.repository }}-${{ github.ref }}
  cancel-in-progress: false
```

2. `scripts/kb/ingest.py`, `scripts/kb/update_index.py --write`, and `scripts/kb/persist_query.py` must acquire an exclusive lock at `wiki/.kb_write.lock` before any write.
3. Lock contention must fail closed with non-zero exit and `reason_code=lock_unavailable` in JSON result envelopes.

### Runtime prerequisite checks (gh-aw)

Write-capable gh-aw automation proceeds only when a preflight check marks every prerequisite as `PASS` (referenced by CI-1..CI-3).

| Prerequisite | PASS condition | FAIL outcome |
|---|---|---|
| gh-aw readiness/integration | required workflow exists and is enabled; run context resolves repository + commit SHA; required runtime/tooling is available for invoked steps (`python3`, repo scripts, and `qmd` when query/index steps run) | exit non-zero before ingest/write steps; emit `prereq_missing:ghaw_readiness`; no repository writes |
| Trusted trigger model | event is trusted `push` on protected branch and changed paths satisfy `raw/inbox/**` policy | fail closed; skip write-capable handoff; log policy rejection reason |
| Permissions scope | effective token matches workflow-bound profile (`tp-gatekeeper`, `tp-analyst-readonly`, or `tp-pr-producer`) and write allowlist (`wiki/**`, `wiki/index.md`, `wiki/log.md`, `raw/processed/**`) | fail closed on permission mismatch or out-of-allowlist write target; no repository writes |
| Concurrency guard | workflow concurrency group is set for write paths and local lock acquisition succeeds before writes | fail closed with `reason_code=lock_unavailable` or `prereq_missing:concurrency_guard`; no partial writes |
| Fallback/manual execution path | maintainer can run local ingest/index/lint sequence and submit PR through normal required checks | mark automation path `action_required` with manual instructions; no partial automation write |

Missing-prerequisite policy:

1. Any single `FAIL` blocks all write-capable side effects.
2. Workflow returns non-zero with explicit, actionable failure reason.
3. Operator fallback path when automation is unavailable:

```bash
python3 scripts/kb/ingest.py --source raw/inbox/<source-file>.md --wiki-root wiki --schema AGENTS.md
python3 scripts/kb/update_index.py --wiki-root wiki --write
python3 scripts/kb/lint_wiki.py --wiki-root wiki --strict
```

### gh-aw handoff interface contract

Handoff rows reference canonical CI IDs from the matrix in the next section.

| Handoff | Inputs | Outputs | Side effects | Idempotency | Failure behavior | Boundary behavior |
|---|---|---|---|---|---|---|
| Trigger → workflow | trusted `push` context on protected branch, commit SHA, filtered changed paths, workflow identity | workflow run context with auditable logs/status | enqueues workflow run only | re-running same SHA/workflow evaluates identical path filters and policy checks | fail closed per CI-1 (non-zero) on trust/path/permission mismatch | write-capable ingest handoff accepts only `raw/inbox/**`; untrusted events cannot reach write path |
| Workflow (read-only analyst) → outputs | validated run context, `tp-analyst-readonly` token, repo snapshot | diagnostics/artifacts/comments | no repository writes | reruns on same SHA produce equivalent diagnostics (except timestamps) | non-zero per CI-2 on analysis failure; no silent success | token scope remains read-only; write scopes forbidden |
| Workflow (PR-producing) → repo | validated run context, allowlisted write targets, `tp-pr-producer` token, lock acquisition | PR/commit with generated updates and explicit check status | may write only `wiki/**`, `wiki/index.md`, `wiki/log.md`, `raw/processed/**`; opens/updates PR | reruns on unchanged SHA converge to no-op or equivalent diff | policy/check failure aborts per CI-3 before merge/write completion with explicit logs | out-of-allowlist path writes are blocked; required checks and approvals gate merge |

### CI quality gate requirements

This is the canonical governance matrix for CI. Other sections must reference these CI IDs (`CI-1..CI-3`) instead of redefining gate logic.

| CI ID | Automation path | Event/path filter | Workflow role | Token profile | Concurrency guard | Required checks (all must pass) | Fail behavior |
|---|---|---|---|---|---|---|---|
| CI-1 | Trigger → workflow handoff (write-capable path) | trusted `push` on protected branch; changed paths limited to `raw/inbox/**` | gatekeeper/handoff | `tp-gatekeeper` | `kb-write-${{ github.repository }}-${{ github.ref }}` | preflight prerequisites = `PASS` for gh-aw readiness, trusted trigger model, permissions scope, concurrency guard, fallback/manual path | fail closed (non-zero); do not enqueue write-capable workflow |
| CI-2 | Workflow (read-only analyst) → outputs | trusted events (`push`, `pull_request`, or `workflow_dispatch`) with repository snapshot | analyze/report only | `tp-analyst-readonly` | optional read-only group | preflight prerequisites = `PASS` for read-only profile; analysis/lint checks return zero | non-zero on failed checks; publish diagnostics only; no repository writes |
| CI-3 | Workflow (PR-producing) → repo | trusted handoff for `raw/inbox/**` or explicit maintainer-approved manual trigger | generate/update PR | `tp-pr-producer` | `kb-write-${{ github.repository }}-${{ github.ref }}` + local lock `wiki/.kb_write.lock` | preflight prerequisites = `PASS`; ingest/index/lint return zero; query-persist returns `written` or `no_write_policy`; required branch checks and approvals pass before merge | fail closed (non-zero); abort commit/PR update; block merge; reject out-of-allowlist writes |

Workflows that enable query persistence must fail closed on policy-evaluation errors and must not write `wiki/analyses/**` unless `auto_persist_when_high_value` criteria are satisfied.

## Security and Trust Model

### Trust boundaries

- `raw/inbox/**`: untrusted input.
- `raw/processed/**`: immutable source-of-truth artifacts.
- `wiki/**`: generated/synthesized content.
- External content boundary: authoritative only when vendored into `raw/assets/**` with checksummed SourceRef; otherwise citation-only reference context.
- `.github/**`, `schema/**`, and infrastructure config: controlled surfaces.

### Required controls

1. Treat source content as data, never executable instruction.
2. Preserve raw immutability with explicit checks (policy + enforcement tests).
3. Enforce write allowlists per workflow.
4. Enforce citation/source traceability for normative claims.
5. Escalate unresolved contradictions to `open_questions` + `wiki/log.md`.
6. Prevent secret leakage and out-of-scope side effects.
7. Enforce authoritative ingest scope to `raw/inbox/**` + checksummed `raw/assets/**`; keep all other external content citation-only unless scope expansion is approved.

### Threat model and controls mapping (automation trigger/write paths)

| Threat/abuse path | Impacted boundary | Required controls | Verification checks |
|---|---|---|---|
| Untrusted trigger context reaches a write-capable workflow | Event context to repository-write boundary | Accept only trusted `push` on protected branch; fail closed on trust mismatch; keep analyst workflows read-only | Workflow-gating integration checks; preflight must return non-zero on trust mismatch |
| Path-filter bypass or path traversal routes non-inbox files into ingest | `raw/inbox/**` to broader repository boundary | Canonical path validation + strict `raw/inbox/**` allowlist; reject traversal/out-of-repo paths | Unit tests for path normalization/traversal; integration checks with invalid changed paths |
| External/unapproved corpus is ingested as authoritative MVP input | Repository knowledge-scope boundary | Enforce authoritative scope: `raw/inbox/**` plus checksummed `raw/assets/**`; reject non-vendored or non-checksummed external inputs | Integration checks reject invalid external inputs; regression tests enforce checksum gate |
| Automation attempts out-of-allowlist repository writes | Write boundary from automation to repo tree | Least-privilege token + explicit write allowlist (`wiki/**`, `wiki/index.md`, `wiki/log.md`, `raw/processed/**`) | Preflight permission-scope checks; regression tests proving out-of-allowlist writes are blocked |
| Concurrent write-capable runs race on shared wiki outputs | Workflow + local runtime write boundary | Enforce workflow concurrency group + local lock file (`wiki/.kb_write.lock`) | Integration checks simulate concurrent runs and assert lock-fail closed behavior |
| Prompt-injected source content attempts policy or command override | `raw/inbox/**` untrusted content to ingest runtime | Treat source as data only; never execute source-provided instructions; deterministic schema-driven ingest | Malicious-source fixtures proving no command execution and no policy override side effects |
| Processed source overwrite/tampering after ingest | `raw/processed/**` immutability boundary | Immutable processed artifacts + append-only audit entries for state changes only (`log_only_state_changes`) | Unit/integration checks reject overwrite; regression tests assert immutability enforcement |
| Unsourced or contradictory synthesis silently replaces established content | `wiki/**` knowledge-integrity boundary | Citation traceability, confidence rubric, contradiction escalation to `open_questions` + `wiki/log.md` | Strict lint checks for missing sources/contradictions; regression checks for conflict escalation |

## Editorial and Knowledge Integrity Policies

1. Neutral, attributed synthesis (no undisclosed opinion as fact).
2. Verifiability-first: claims must map to listed sources.
3. No original research: do not assert unsupported novel conclusions.
4. Contradiction policy:
   - do not silently overwrite high-confidence claims,
   - log conflict and route for human arbitration.
5. Findability/discoverability:
   - index-first navigation is mandatory,
   - lateral links should be maintained to reduce orphan pages.

## Testing Strategy and Verification Matrix

- **Framework:** Python `unittest` (stdlib-first).
- **Target locations:** `tests/kb/`.
- **Coverage target:** ≥90% line coverage over `scripts/kb`.
- **Regression rule:** every production bug gets a reproducing test first.

### Verification matrix

| Policy/constraint (trace) | Unit | Integration | E2E | Regression |
|---|---|---|---|---|
| Frontmatter schema + required `sensitivity` metadata (Assumptions #7; Frontmatter Contract) | required | required | optional | required for schema/metadata drift |
| Canonical SourceRef format `repo_uri_with_anchor_and_checksum` (Assumptions #9; Terminology; Frontmatter Contract) | required | required | optional | required |
| `auto_persist_when_high_value` gate + query-persist no-write behavior below threshold + JSON envelopes (Assumptions #5; Interface Contract: Query persist; Ambiguity Checklist #4) | required | required | optional | required |
| Batch ingest policy `continue_and_report_per_source` + partial-success exit semantics (Assumptions #6; Ingest batch semantics) | required | required | optional | required |
| Ingest side effects (pages + index + log + move) with `log_only_state_changes` (Interface Contract: Ingest; Assumptions #10) | required | required | required | required |
| Trusted-trigger ingest gate (protected-branch `push` + `raw/inbox/**`) (Trigger defaults; Ambiguity Checklist #2) | required | required | required | required |
| Workflow split: read-only analyst vs PR-producing + approval gates (Workflow defaults; Ambiguity Checklist #3) | optional | required | required | required |
| Token profiles (`custom_per_workflow_matrix`) + write allowlist + raw immutability (Assumptions #12; Runtime prerequisite checks; Security/Boundaries) | required | required | required | required |
| Canonical CI quality gates (`CI-1..CI-3`) (CI quality gate requirements) | optional | required | required | required |
| Concurrency controls (`workflow_concurrency_group_plus_local_file_lock`) (Assumptions #13; Concurrency controls) | required | required | required | required |
| Authoritative boundary (`raw/inbox/**` + checksummed `raw/assets/**`) + external citation-only guard (Assumptions #11; Scope; Security model; Ambiguity Checklist #5) | required | required | required | required |
| qmd index/query behavior + runtime prerequisite failures (Assumptions #4; qmd contract; Ambiguity Checklist #1) | required | required | required | required for query/index failures |
| Mermaid support preservation (MVP scope constraint) | required | required | required | required |
| Lint strict failures (links/orphans/unsourced/contradictions) (Lint contract; Editorial policies) | required | required | optional | required |
| Contradiction escalation to `open_questions` + `wiki/log.md` (Editorial policy #4; Security control #5) | required | required | optional | required |
| Normative precedence + tie-break escalation (Normative Precedence section) | required | required | optional | required |
| Phase 2 deferral guard (Ambiguity Checklist #7; Scope) | optional | required | required | required |

## Code Style and Implementation Constraints

- Python `snake_case`; types/dataclasses in `PascalCase`.
- Prefer small, pure helpers; isolate filesystem side effects.
- UTF-8 explicit file IO.
- No broad `try/except` and no silent fallback success paths.
- Keep behavior deterministic and auditable.

## Boundaries

### Always

- Keep `raw/processed/**` immutable after ingest.
- Update `wiki/index.md` + append `wiki/log.md` only when a state change occurs on ingest or policy-approved query-persist operations.
- Keep strict lint (`--strict`) read-only; diagnostics must not mutate repository content.
- Acquire `wiki/.kb_write.lock` before write-capable local commands.
- Preserve source citations for wiki claims.
- Follow skill workflow expectations in `.github/copilot-instructions.md`.

### Ask first

- Expanding scope beyond this spec (for example Phase 2 delivery in MVP).
- Changing schema/frontmatter in backward-incompatible ways.
- Modifying hook behavior or automation trust model assumptions.
- Deleting or archiving high-traffic wiki content.

### Never

- Commit secrets/credentials.
- Mutate processed raw sources.
- Bypass lint/verification gates.
- Add vague or non-actionable process requirements.

## Decision Log (Spec-Level)

| Decision | Status | Rationale |
|---|---|---|
| Persistent wiki architecture (not query-time-only RAG) | accepted | Enables cumulative, auditable knowledge artifacts in-repo. |
| qmd in MVP | accepted | Required for MVP local search/query capability. |
| confidence rubric = numeric `1..5` | accepted | Supports deterministic thresholds and policy checks. |
| query persistence default = `auto_persist_when_high_value` | accepted | Preserves high-value outputs while limiting noise. |
| batch ingest policy = `continue_and_report_per_source` | accepted | Keeps throughput while preserving per-source diagnostics and deterministic partial-success handling. |
| `sources` reference format = `repo_uri_with_anchor_and_checksum` | accepted | Makes provenance parsing and checksum enforcement deterministic. |
| append-log policy = `log_only_state_changes` | accepted | Resolves idempotency vs append-only tension by logging only persisted state changes. |
| external assets policy = `external_assets_allowed_as_authoritative_if_checksumed` | accepted | Allows authoritative external assets only after local vendoring and checksum verification. |
| token permission profile policy = `custom_per_workflow_matrix` | accepted | Enforces concrete least-privilege scopes per workflow role. |
| concurrency control = `workflow_concurrency_group_plus_local_file_lock` | accepted | Prevents race conditions between concurrent write-capable runs. |
| schema contract file = `AGENTS.md` | accepted | Establishes one repo-level agent behavior contract. |
| source `sensitivity` frontmatter metadata required | accepted | Enforces explicit handling of sensitive content classes. |
| normative precedence order + explicit tie-break escalation rule | accepted | Prevents silent conflict resolution during spec refinement. |
| source traceability required for major normative additions | accepted | Keeps policy additions auditable to approved inputs. |
| strict lint mode remains read-only | accepted | Prevents hidden mutations in validation paths and keeps lint behavior deterministic. |
| canonical write-capable ingest trigger = trusted protected-branch `push` for `raw/inbox/**` | accepted | Constrains automation entry points and reduces trigger abuse risk. |
| split workflows into read-only analyst vs PR-producing paths | accepted | Enforces least privilege and clearer approval boundaries. |
| monolithic all-in-one automation workflow | rejected | Conflicts with specialization, observability, and permission isolation. |
| untrusted events reaching write-capable automation paths | rejected | Violates trust-boundary policy; fail-closed behavior is required. |
| repository-local authoritative scope for MVP (`raw/inbox/**` + checksummed `raw/assets/**`) | accepted | Keeps ingestion bounded to local audited artifacts while allowing checksum-verified external assets. |
| query-persist threshold-edge human override workflow | deferred (post-MVP) | MVP keeps deterministic no-write behavior below threshold/with contradictions; any override workflow requires explicit later policy approval. |
| GitHub Pages browse/search surface | deferred (Phase 2) | Explicitly out of MVP scope to avoid scope creep. |
| page-level feedback routing to GitHub Issues | deferred (Phase 2) | Depends on Phase 2 public wiki surface. |
| advanced KPI dashboards and quality scoring classes | deferred (Phase 2) | Post-MVP analytics capability, not bootstrap-critical. |

## Source Traceability for Normative Additions

| Major normative addition | SPEC anchor(s) | Source class | Source trace |
|---|---|---|---|
| Assumption defaults (`qmd` MVP, `auto_persist_when_high_value`, confidence rubric, sensitivity metadata, `continue_and_report_per_source`, canonical SourceRef, `log_only_state_changes`, checksummed external assets, custom token profiles, concurrency controls, `AGENTS.md`) and MVP/Phase 2 boundary lock | Assumptions and Defaults; Scope; Terminology | User decision | Finalized assumption decisions in planning artifacts. |
| Persistent wiki architecture, immutable processed sources, frontmatter contract, and index/log-first behavior | Objective; Architecture and Repository Structure; Frontmatter Contract; Boundaries | Research source | `LLMwiki-best practices-research.md`. |
| gh-aw workflow specialization, analyst vs PR-producing split, and trusted-trigger/least-privilege/write-allowlist guardrails | gh-aw Automation Model; CI quality gate requirements | Research source | Pelis Agent Factory guidance. |
| Threat model and controls mapping, trust-boundary hardening, and contradiction escalation requirements | Security and Trust Model | Custom-agent findings | `@security-auditor` findings. |
| Verification matrix depth, regression-first rule, and policy-to-test mapping | Testing Strategy and Verification Matrix | Custom-agent findings + skill coverage outcomes | `@test-engineer` findings + test-driven/planning skill outcomes. |
| Interface contracts, CI gate matrix, normative precedence/tie-break policy, and decision-log governance | Normative Precedence; Command and Interface Contracts; CI quality gate requirements; Decision Log | Skill coverage outcomes + custom-agent findings | Skill-coverage review outcomes + `@code-reviewer` findings. |

## Research Concept-to-SPEC Mapping (MVP vs Phase 2)

| Research source | Accepted concept | SPEC section(s) | Scope |
|---|---|---|---|
| LLMwiki best-practices research | Persistent wiki model with immutable raw layer and maintained wiki artifacts | Objective; Scope (MVP); Architecture and Repository Structure; Security and Trust Model; Boundaries | MVP |
| LLMwiki best-practices research | `AGENTS.md` as primary contract and strict write boundaries | Assumptions and Defaults; Architecture and Repository Structure; Security and Trust Model; Boundaries | MVP |
| LLMwiki best-practices research | Required structured frontmatter (`sources`, `confidence`, `open_questions`, `sensitivity`, status fields) | Frontmatter Contract (Wiki Layer) | MVP |
| LLMwiki best-practices research | Index-first discoverability, lateral links, and append-only log/audit behavior | Architecture and Repository Structure; Interface contract matrix (Ingest); Editorial and Knowledge Integrity Policies | MVP |
| LLMwiki best-practices research | Verifiability + no-original-research + contradiction escalation to human arbitration | Security and Trust Model; Editorial and Knowledge Integrity Policies; Interface contract matrix (Ingest/Lint) | MVP |
| LLMwiki best-practices research | Semantic linting and deterministic verification coverage expectations | Command and Interface Contracts; Testing Strategy and Verification Matrix | MVP |
| LLMwiki best-practices research | Quality scoring and KPI-style measurement classes | Scope (Phase 2) | Phase 2 |
| Pelis Agent Factory guidance | Specialized workflows over monolithic automation | gh-aw Automation Model → Workflow pattern defaults | MVP |
| Pelis Agent Factory guidance | Split read-only analyst workflows from PR-producing workflows | gh-aw Automation Model → Workflow pattern defaults; gh-aw handoff interface contract | MVP |
| Pelis Agent Factory guidance | Guardrails: trusted triggers, least privilege, and write allowlists | gh-aw Automation Model → Trigger and permission defaults; Runtime prerequisite checks; Security and Trust Model | MVP |
| Pelis Agent Factory guidance | Meta-workflow observability, health monitoring, and explicit failure reporting | gh-aw Automation Model → Workflow pattern defaults; CI quality gate requirements | MVP |
| Pelis Agent Factory guidance | Advanced metrics/analytics depth beyond baseline operational automation | Scope (Phase 2) | Phase 2 |

## Success Criteria

1. `SPEC.md` reflects finalized assumptions, contracts, and policy controls, including SourceRef format, batch ingest semantics, append-log policy, external-asset boundary, token profiles, and concurrency controls.
2. Interface contracts exist for ingest/index/lint/qmd (index + query + policy-gated query persistence) and gh-aw automation boundaries.
3. Security/trust model maps each trigger/write/external-boundary/concurrency path to explicit controls.
4. One canonical CI governance matrix (`CI-1..CI-3`) is declared and referenced by adjacent sections.
5. Verification matrix covers each major policy/feature with at least one test type.
6. Decision log captures non-trivial policy choices and rationale.
7. Implementation-ready milestone gates (`M0..M4`) are explicit and testable.
8. Remaining ambiguities are either resolved in-spec or explicitly deferred.

### Implementation-ready milestone gates

| Gate | PASS criteria | Evidence anchor |
|---|---|---|
| M0: terminology/assumptions freeze | Canonical terminology and all approved assumption decisions are present and internally consistent. | Assumptions and Defaults; Terminology (Canonical) |
| M1: interface executability | Command set + interface matrix specify deterministic inputs, outputs, policies, and failure semantics for single/batch ingest and query persistence. | Command set; Ingest batch semantics; Machine-readable result envelopes; Interface contract matrix |
| M2: security/automation enforcement | CI matrix, token profiles, write allowlists, and concurrency controls are concrete and role-bound. | Token permission profiles; Concurrency controls; Runtime prerequisite checks; CI quality gate requirements; Security and Trust Model |
| M3: verification readiness | Verification matrix traces every major policy to test coverage depth. | Testing Strategy and Verification Matrix |
| M4: pre-implementation go/no-go | Ambiguity checklist has no unresolved item beyond explicit deferrals. | Final Pre-Implementation Ambiguity Review Checklist |

## Final Pre-Implementation Ambiguity Review Checklist

Before implementation planning starts, explicitly review:

1. qmd MVP dependency/runtime profile remains acceptable for bootstrap scope.
2. No deviation from canonical trusted trigger event and custom token profile matrix (`tp-gatekeeper`, `tp-analyst-readonly`, `tp-pr-producer`) for commit-triggered ingest.
3. Read-only vs PR-producing gh-aw workflow split and approval gates remain enforced.
4. `auto_persist_when_high_value` edge handling remains deterministic (`confidence >=4`, `sources >=2`, no unresolved contradiction), with machine-readable `written`/`no_write_policy` outputs, and any override path is explicit.
5. Authoritative ingest boundary remains enforced as `raw/inbox/**` + checksummed `raw/assets/**`; non-vendored/non-checksummed external material remains citation-only.
6. Concurrency controls remain enforced via workflow concurrency group plus local `wiki/.kb_write.lock`.
7. Phase 2 deferrals (GitHub Pages + feedback loop) remain out of MVP.

### Checklist status (final pre-implementation review)

| Agenda item | Status | SPEC evidence |
|---|---|---|
| 1) qmd in MVP scope | resolved-in-spec | Assumptions #4; Scope (MVP includes qmd-backed local search/query); Command set + interface matrix qmd rows; Verification matrix qmd row; Decision Log `qmd in MVP = accepted`. |
| 2) Commit-triggered ingest trust + token model | resolved-in-spec | Scope (commit-triggered ingest), gh-aw Trigger and permission defaults, Token permission profiles, Runtime prerequisite checks, canonical CI matrix (`CI-1..CI-3`), Security threat-controls mapping. |
| 3) gh-aw workflow behavior split | resolved-in-spec | gh-aw Workflow pattern defaults + handoff interface contract enforce read-only analyst vs PR-producing split and approval/check gates; Verification matrix workflow-split row; Decision Log split-workflow entry. |
| 4) `auto_persist_when_high_value` execution details + override handling | deferred-with-explicit-status | Deterministic gate + JSON envelope statuses are resolved in Assumptions #5 + Query persist contract; threshold-edge human override workflow remains explicitly deferred post-MVP in Decision Log. |
| 5) Authoritative external-content boundary | resolved-in-spec | Scope and Security/Trust Model enforce authoritative `raw/inbox/**` + checksummed `raw/assets/**`; non-vendored/non-checksummed external inputs remain citation-only; threat-controls mapping includes rejection checks. |
| 6) Concurrency enforcement model | resolved-in-spec | Assumptions #13; Concurrency controls section; Runtime prerequisite checks (`Concurrency guard`); CI-3 requirements; Query persist and ingest failure behavior include lock-fail closed path. |
| 7) Phase 2 boundary lock (Pages + feedback) | deferred-with-explicit-status | Scope marks GitHub Pages and feedback-to-issues as Phase 2 only; Decision Log records both as deferred (Phase 2). |
