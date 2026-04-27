# Spec: Post-MVP Rollout and Packaging

> **Phase status (2026-04-27):**
> - **Phase 0** ✅ Complete — this spec published; runbook aligned.
> - **Phase 1** ✅ Complete — boundary docs, contract tests, and package-placement rules landed.
> - **Phase 2** ✅ Complete — all script families promoted: `scripts/validation/**`,
>   `scripts/reporting/**`, `scripts/context/**`, `scripts/maintenance/**`,
>   `scripts/ingest/**`, and `scripts/github_monitor/**`.
> - **Phase 3** 🔲 Not started — downstream write-capable workflow slices; requires
>   explicit maintainer approval per §High-risk phase-transition gates.
> - **Phase 4** 🔲 Not started — optional analytics and discovery follow-ons.

## Authority and objective

This document is the **authoritative post-MVP rollout planning spec** for the
wiki-curation framework after the MVP gates documented in `raw/processed/SPEC.md`
and `docs/mvp-runbook.md`. If roadmap prose, backlog notes, or exploratory
appendix text disagree about post-MVP sequencing, scope class, or packaging
placement, this document wins until a newer ADR or approved spec revision
replaces it. Current runtime behavior remains governed by `raw/processed/SPEC.md`,
`docs/mvp-runbook.md`, `docs/architecture.md`, and the accepted ADR set until a
later phase lands and is ratified.

The objective is to expand the framework **without weakening the current
deterministic, fail-closed execution surface**. Post-MVP work must therefore be
sequenced in phases, classified by approval level, and packaged so that
skill-local orchestration stays narrow while reusable or write-capable logic
moves into explicit repository-owned script surfaces.

## Assumptions

1. MVP remains the current source of runtime truth for landed behavior.
2. `scripts/kb/**` remains the only fully authoritative deterministic execution
   surface until a later phase explicitly opens additional repo-level packages.
3. `.github/skills/**` may contain procedural guidance and thin wrappers, but
   wrappers do not become independent policy engines.
4. High-risk expansion means any change that adds write capability, broadens file
   traversal, changes policy gates, introduces new durable outputs, or creates a
   reusable execution surface outside the current MVP boundary.
5. Human approval means explicit maintainer approval captured through normal
   review/merge or an ADR/issue decision before the gated phase transition is
   considered open.

## Commands

```bash
# framework governance baseline
python3 .github/skills/validate-wiki-governance/logic/validate_wiki_governance.py

# focused framework contract checks
python3 -m unittest \
  tests.kb.test_framework_contracts \
  tests.kb.test_framework_skills \
  tests.kb.test_framework_agents \
  tests.kb.test_framework_references \
  tests.kb.test_skill_wrappers

# full repo regression baseline
python3 -m unittest discover -s tests -p "test_*.py"

# deterministic wiki maintenance surfaces that remain authoritative until a
# later phase explicitly widens repo-level packaging
python3 scripts/kb/ingest.py --source raw/inbox/<source-file>.md --wiki-root wiki --schema AGENTS.md --report-json
python3 scripts/kb/update_index.py --wiki-root wiki --write
python3 scripts/kb/lint_wiki.py --wiki-root wiki --strict
python3 scripts/kb/persist_query.py --query "<query>" --result-summary "<summary>" --confidence 4 --source "<SourceRef>" --wiki-root wiki --schema AGENTS.md --result-json
```

## Project structure and package surfaces

| Surface | Posture | What belongs here |
|---|---|---|
| `.github/agents/**` | Contract-only | Persona mission, routing, handoff, fail-closed stop conditions. |
| `.github/skills/<skill>/SKILL.md` | Skill-local procedure | Invocation guidance, gates, references, operator workflow. |
| `.github/skills/<skill>/logic/**` | Skill-local logic | Narrow wrappers or fixed prechecks that are specific to one skill and do not replace repo-level engines. |
| `scripts/kb/**` | Current authoritative repo-level logic | Existing deterministic ingest, index, lint, preflight, and query-persist execution surfaces. |
| `scripts/validation/**` | Approval-gated repo-level logic | Shared validators or evidence/policy checks promoted out of skill-local wrappers. |
| `scripts/reporting/**` | Approval-gated repo-level logic | Deterministic report generation over existing repo artifacts only. |
| `scripts/context/**` | Approval-gated repo-level logic | Shared context assembly or deterministic read models used by multiple skills/personas. |
| `scripts/maintenance/**` | Approval-gated repo-level logic | Reusable maintenance operations that remain bounded by approved write surfaces. |
| `scripts/ingest/**` | Approval-gated repo-level logic | New reusable ingest helpers promoted from wrapper-local orchestration. |
| `tests/kb/**` | Required verification surface | Unit, integration, and regression checks for docs, wrappers, and repo-level scripts. |

## Code style / contract style

Use a **hybrid contract + assertion** style for every post-MVP surface. The
contract names the boundary; assertions make the boundary testable.

```markdown
| Field | Requirement |
|---|---|
| Inputs | Repo-relative only; reject out-of-scope paths |
| Outputs | Deterministic JSON/report artifacts |
| Side effects | Allowlisted write paths only |
| Failure behavior | Non-zero exit and fail closed |

Assertions:
- MUST reject writes outside approved allowlists.
- MUST not bypass evidence or policy gates.
- MUST produce the same result for the same repo state.
```

Naming rules:
- Use imperative, deterministic wording: **must**, **must not**, **only if**.
- Prefer package-surface names over vague role prose.
- Treat phase gates as executable checkpoints, not advisory commentary.

## Testing strategy

- **Doc/contract verification:** keep `docs/mvp-runbook.md`, this spec, and the
  framework docs aligned in the same change set, and use focused framework tests
  to guard the currently audited boundary docs.
- **Wrapper verification:** every skill-local wrapper remains thin, deterministic,
  and covered by targeted tests before it becomes part of a phase gate.
- **Repo-level verification:** any promoted script surface must gain explicit
  tests under `tests/kb/**` before downstream personas rely on it.
- **High-risk transition verification:** no gated phase transition opens until
  validation, write-safety review, and human approval all pass.

## Verification matrix and CI migration rules

This section is the **planning authority** for post-MVP verification expansion.
It does **not** replace today's MVP enforcement in `docs/mvp-runbook.md`; every
phase below assumes the current MVP suites stay green while new surfaces are
introduced, promoted, and eventually consolidated.

### Current MVP suites that stay green in every phase

| MVP suite | Current command or files | Why it stays green |
|---|---|---|
| Focused framework suite | `python3 -m unittest tests.kb.test_framework_contracts tests.kb.test_framework_skills tests.kb.test_framework_agents tests.kb.test_framework_references tests.kb.test_skill_wrappers` | Guards the current wrapper, agent, skill, and boundary-doc contract surface. |
| MVP script surface suites | `tests/kb/test_ingest.py`, `test_update_index.py`, `test_lint_wiki.py`, `test_qmd_preflight.py`, `test_persist_query.py` | Keeps the authoritative `scripts/kb/**` execution surface stable while post-MVP planning evolves. |
| MVP workflow governance suites | `tests/kb/test_ci1_workflow.py`, `test_ci2_workflow.py`, `test_ci3_workflow.py`, `test_ci_permission_asserts.py` | Preserves the landed CI-1/CI-2/CI-3 trust and permission split. |
| MVP verification-matrix suites | `tests/kb/test_unit_verification_matrix.py`, `test_integration_verification_matrix.py`, `test_regression_verification_matrix.py` | Protects the already-ratified unit/integration/regression expectations. |
| Full repo regression baseline | `python3 -m unittest discover -s tests -p "test_*.py"` | Catches cross-surface regressions before any migration phase claims parity. |

### Verification matrix for new post-MVP surfaces

| Surface class | What qualifies | Tests required before the surface is relied on | CI expectation while MVP remains authoritative |
|---|---|---|---|
| Skill-local helpers | New helper logic under `.github/skills/<skill>/logic/**` that supports one skill only | Add targeted unit coverage for deterministic inputs, fail-closed/out-of-scope behavior, and any wrapper-facing helper contract; also keep the focused framework suite green. | Verify through focused framework tests plus targeted helper tests; do not treat helper-only logic as a new CI lane or write surface. |
| Wrapper modes | New wrapper entrypoints or new modes/flags on existing wrappers such as read-only, check-only, or approved write-through modes | Add per-mode tests for argument routing, exit codes, command ordering, no-write envelopes, and allowlist/fail-closed behavior; extend `tests/kb/test_skill_wrappers.py` or a sibling wrapper-focused suite as needed. | Read-only wrapper modes may join CI-2 only after tests land; any write-capable wrapper mode stays behind CI-3 rules and may not bypass repo-level script promotion. |
| Repo-level scripts | New shared surfaces under approved `scripts/**` package families | Add explicit unit, integration, and regression coverage under `tests/kb/**` for CLI contract, JSON/result envelopes, deterministic output, lock behavior, and write-allowlist enforcement. | Read-only scripts migrate into CI-2 after approval and tests; write-capable scripts migrate into CI-3 only after allowlist, lock, and failure-envelope coverage exists. |
| Workflow lanes | New or expanded lane orchestration across CI-1/CI-2/CI-3 or the maintained governance lane order | Add workflow/lane contract tests for trigger scope, permissions, handoff order, called-script expectations, and fail-closed/no-write-on-failure behavior; keep existing CI workflow suites green. | Preserve the CI-1/CI-2/CI-3 split until a later phase is approved; lane-specific checks layer on top of the existing workflow suites rather than replacing them. |

### CI migration rules

| Migration phase | When it applies | Rules |
|---|---|---|
| Pre-script | Before any new repo-level script family becomes authoritative | CI-1/CI-2/CI-3 stay exactly as they are today. New skill-local helpers and wrapper modes must prove themselves with targeted tests plus the current MVP suites above, but they do not yet redefine required CI beyond the existing focused framework and regression baselines. |
| Script-expansion | Once a maintainer has approved a new repo-level script family and its tests | Keep all MVP suites green while the promoted script family gains CI coverage. CI-2 absorbs approved read-only scripts and diagnostics first; CI-3 absorbs approved write-capable scripts only after allowlist, lock, and no-write-on-failure coverage is present. Wrapper and script coverage run together until the promoted script is ratified as the authoritative implementation. |
| Final consolidation | Only after equivalent or stronger script-family coverage is landed and approved as authoritative | Consolidate heavy verification onto the authoritative repo-level script suites, but retain wrapper smoke/contract coverage, the CI-1 trust gate, and the CI-3-only writer boundary. Removing or downgrading an older check requires maintainer approval and proof that the replacement coverage is at least as strong as the MVP suite it supersedes. |

## Boundaries

- **Always do:** fail closed on validation/policy/lock errors; keep writes inside
  approved allowlists; route durable follow-up back through the governance lane;
  promote shared or write-capable logic into repo-level scripts rather than
  hiding it in wrappers.
- **Ask first:** open any new repo-level script family; add write capability to a
  downstream persona; change policy enforcement order; allow new durable outputs,
  redirects, aliases, or analytics pipelines.
- **Never do:** let skill-local logic silently replace `scripts/kb/**`; ship
  wrapper-local write engines with repo-wide effects; bypass evidence,
  policy-arbiter, or maintainer approval gates; introduce telemetry daemons,
  broad crawlers, or external integrations as implicit follow-on work.

## Scope classes

### Required post-MVP work

1. Publish and maintain this authoritative rollout spec.
2. Preserve the landed governance lane order:
   `knowledgebase-orchestrator -> source-intake-steward -> evidence-verifier -> policy-arbiter -> one cleared downstream persona`.
3. Keep current deterministic execution in `scripts/kb/**` authoritative until a
   later phase explicitly promotes additional repo-level packages.
4. Define package placement rules for skill-local vs repo-level logic.
5. Require validation, write-safety review, and human approval before each
   high-risk phase transition.

### Approval-gated work

1. Open any new repo-level package family under `scripts/validation/**`,
   `scripts/reporting/**`, `scripts/context/**`, `scripts/maintenance/**`, or
   `scripts/ingest/**`.
2. Promote wrapper-local checks into reusable validators or shared context
   builders.
3. Add downstream write-capable workflow slices for synthesis, topology, query
   persistence expansion, or alias handling.
4. Expand evidence verification beyond MVP only as an upstream blocking or
   read-only validation surface unless a later approved spec says otherwise.
5. Introduce new durable artifacts, new write targets, or new automation that
   operates across more than one skill/persona boundary.

### Optional later-phase work

1. Recommendation-first analytics and discoverability scoring.
2. Entity-resolution or search/discovery automation beyond read-only assessment.
3. Advanced reporting, dashboards, or GitHub Pages/search enhancements that do
   not weaken governance gates.
4. Other convenience automation that remains explicitly downstream of the
   required and approval-gated rollout phases.

## Packaging rules: skill-local vs repo-level logic

### Skill-local logic stays in `.github/skills/<skill>/logic/**` only when all of the following are true

1. The logic exists to support one skill's invocation contract.
2. The behavior is narrow orchestration, fixed validation, or wrapper composition
   around already-approved repo-level scripts.
3. The logic does not define a new reusable repository API for multiple skills or
   personas.
4. The logic does not add a new write surface, durable artifact family, or broad
   repository crawl.
5. The logic can fail closed without needing shared runtime state beyond the
   current deterministic surfaces.

### Logic must move to repo-level scripts when any of the following are true

1. Multiple skills/personas depend on the same implementation.
2. The behavior is write-capable or produces durable repo artifacts.
3. The behavior needs its own tests, CLI contract, or machine-readable output as
   a reusable surface.
4. The behavior traverses broad repository scope, performs batch processing, or
   becomes part of the authoritative execution path.
5. The behavior encodes policy, validation, or context assembly that should not
   diverge across wrappers.

### Packaging consequences

- Skill-local wrappers may **compose** repo-level logic but must not reimplement
  it.
- Repo-level promotion is itself **approval-gated** and requires tests before the
  new surface is considered authoritative.
- Persona files remain contract surfaces, not implementation homes.

## Rollout sequence

### Phase 0 — Publish the post-MVP spec (**required**)

Deliver this document and align the runbook so maintainers have an authoritative
source for phase order, scope classes, and packaging rules.

**Exit conditions**
- The rollout sequence is explicit.
- Required, approval-gated, and optional work are enumerated.
- High-risk transitions name validation, write-safety, and human-approval gates.

### Phase 1 — Preserve and harden the current boundary (**required**)

Keep MVP behavior authoritative while making the promotion criteria explicit.
This phase is documentation, contract, and test hardening only; it does not open
new write-capable runtime surfaces.

**Includes**
- Boundary docs and tests that keep current execution surfaces aligned.
- Explicit package-placement and gate criteria.
- No replacement of `scripts/kb/**`.

### Phase 2 — Promote shared validation/context/reporting/maintenance/ingest surfaces (**approval-gated**)

Open new repo-level packages only when a wrapper-local behavior has proven to be
shared, reusable, and better owned by the repository than by one skill. This is
the phase that can open `scripts/validation/**`, `scripts/reporting/**`,
`scripts/context/**`, `scripts/maintenance/**`, and `scripts/ingest/**`, but
only for explicitly approved contract surfaces.

**Includes only after approval**
- Shared validators in `scripts/validation/**`.
- Shared deterministic reporting/context helpers in approved package families.
- Reusable maintenance or ingest helpers promoted into approved repo-level
  packages without weakening current allowlists or fail-closed behavior.
- Promotion of wrapper-local logic into tested repo-level entrypoints.

**Does not include yet**
- Downstream write expansion for synthesis/topology automation.
- Optional analytics or telemetry systems.

### Phase 3 — Open controlled downstream write-capable workflow slices (**approval-gated**)

After shared repo-level surfaces exist and remain fail closed, selectively open
new durable-write paths for policy-cleared downstream personas.

**Includes only after approval**
- Write-capable downstream slices for synthesis, query-derived persistence
  expansion, or topology follow-up.
- Explicit allowlists, JSON/result envelopes, and tests for each new surface.
- Writers that stay inside the existing PR-producing/manual-approval model rather
  than inventing a second write path.

**Required invariants**
- Evidence verification remains an upstream blocking gate in the governance lane,
  not a downstream writer.
- No downstream write path opens before governance, evidence, and policy gates
  pass for that lane.
- Any new writer remains inside the existing allowlisted, lock-guarded,
  reviewable write path rather than bypassing CI-3 or the documented manual PR
  flow.

### Phase 4 — Optional optimization and discovery follow-ons (**optional later phase**)

Add recommendation-first analytics, search/discovery optimization, or other
operator conveniences only after the required and approval-gated phases are
stable.

**Includes only if explicitly chosen**
- Read-only or recommendation-first analytics.
- Discovery tuning and entity-resolution follow-up.
- Additional operator-facing reporting surfaces.

## High-risk phase-transition gates

| Transition | Validation gate | Write-safety gate | Human-approval gate |
|---|---|---|---|
| Phase 0 -> Phase 1 | Focused framework docs/tests pass and links remain valid. | No new runtime surface or write target is opened by the spec publication itself. | Maintainer accepts this spec as the rollout source of truth. |
| Phase 1 -> Phase 2 | `validate_wiki_governance.py` plus focused framework tests pass; promoted repo-level logic gains explicit tests under `tests/kb/**`. | Promotion does not widen writes beyond approved allowlists and does not bypass `scripts/kb/**` until the new surface is ratified. | Explicit maintainer approval to open the named package family and its contract. |
| Phase 2 -> Phase 3 | New downstream write-capable slice has deterministic tests, envelope/assertion coverage, and governance-lane verification. | New writes are allowlisted, lock-safe, fail closed, and remain inside the existing PR-producing/manual-reviewable write path; policy/evidence failure blocks all writes. | Explicit maintainer approval for each downstream write lane before activation. |
| Phase 3 -> Phase 4 | Optional subsystem proves recommendation-first value without becoming an unreviewed authority surface. | No telemetry daemon, crawler, external integration, or broad writeback opens unless separately approved and bounded. | Explicit opt-in approval for each optional subsystem; omission is the default. |

## Success criteria

This spec is complete when:

1. A maintainer can execute post-MVP planning from this document without relying
   on appendix prose as the only roadmap source.
2. The required/approval-gated/optional split is explicit enough to stop
   premature scope creep.
3. Package placement decisions can be made deterministically from the rules
   above.
4. Every high-risk phase transition has named validation, write-safety, and
   human-approval gates.
