# ADR-024: Synthesis Curator Stage Design — LLM Entity/Concept Extraction in CI-3

## Status
Accepted — amended in-place: single-lock synthesis implemented (#115, 2026-05-19)

## Date
2026-05-15

## Context

After the ingest pipeline (CI-3) writes a source page to `wiki/sources/`, the wiki has no
entity or concept pages — just raw source summaries. Issue #5 ("why doesn't the wiki have
entity pages?") confirmed that no automated synthesis trigger existed: entities and concepts
remained invisible to wiki readers and to the `suggest-backlinks` and `query-synthesist`
skills that depend on them.

The repository already had:

- Three synthesis skill definitions (`extract-entities-and-claims`, `synthesize-entity-page`,
  `synthesize-concept-page`) documented in `.github/skills/` as doc-only placeholders.
- A `models: read` permission scope available in the GitHub Actions token model.
- A self-contained ingest PR flow in CI-3 where human review already happens before merge.

Several design questions had to be resolved before implementation.

## Decision

Implement a synthesis stage directly inside CI-3 (`ci-3-pr-producer.yml`) that runs
immediately after ingest and before `update_index`, using skill-local logic scripts under
`.github/skills/*/logic/`.

The stage calls the GitHub Models API (model: `gpt-4o-mini`) with a self-correcting
three-attempt retry loop, then writes entity and concept draft pages to `wiki/entities/**`
and `wiki/concepts/**` while holding `wiki/.kb_write.lock`. All synthesis steps soft-fail:
they exit 0 and emit `::warning` on any LLM error, so the ingest PR always proceeds.

## Alternatives Considered

### A — Separate CI job or pipeline (rejected)

A dedicated CI job (e.g., triggered by `pull_request`) could call the Models API
independently. Rejected because:
- It would require a second PR workflow with its own trust model and concurrency group.
- Human review already happens on the ingest PR in CI-3; a separate pipeline would either
  require a second review round or write pages without review visibility.
- CI-4 (`framework-writer`) exists for staged agent content but is `workflow_dispatch`-only
  and not suited for automatic post-ingest triggers.

### B — HITL-only synthesis (doc-only skills, operator invokes manually) (rejected)

Keep the skills as doc-only and require an operator to invoke them manually after each
ingest. Rejected because:
- Every ingest would require a manual follow-up step with no enforcement mechanism.
- The whole motivation for CI-3 automation is to eliminate manual steps on the happy path.
- HITL review still occurs — via PR review — even with automated synthesis.

### C — Write draft pages with `status: draft`, gate publication separately (rejected)

Write pages as `status: draft` and require a separate approval step to flip them to
`status: active`. Rejected because:
- No second write-path gate exists today; adding one would require a new CI lane.
- The ingest PR already serves as the HITL gate — the maintainer reviews all staged changes,
  including new entity/concept pages, before merging.
- `status: draft` would exclude pages from `suggest-backlinks` and index queries until
  manually promoted, defeating the purpose of automated synthesis.

### D — Separate token profile with tighter `models: read` scope (deferred)

Create a new CI job with only `models: read` (no `contents: write` or `pull-requests: write`)
to isolate the LLM call from the write-capable step. Deferred, not rejected:
- Reduces blast radius if the LLM endpoint is compromised.
- Adds workflow complexity (new job, artifact handoff, cross-job token passing).
- Current mitigation: `--endpoint` is validated against an allowlist
  (`models.inference.ai.azure.com` only); token is env-var only (never in CLI args to
  prevent `/proc/<pid>/cmdline` exposure).

## Key Design Decisions

### Soft-fail semantics

Synthesis failures never block the ingest PR. Rationale: LLM availability is not a
correctness prerequisite for source ingestion. An Models API outage must not halt all source
intake. The synthesized pages are best-effort additions; their absence does not corrupt the
wiki — it merely leaves entity/concept namespaces empty until the next successful run.

### Token passed as environment variable only

`SYNTHESIS_GITHUB_TOKEN` is mapped from `${{ github.token }}` in the workflow `env:` block
and read by `extract_entities.py` via `os.environ`. It is never passed as a CLI argument.
Rationale: on Linux runners, process arguments are readable from `/proc/<pid>/cmdline` by
any process in the same UID group. Env-var injection is masked in GHA logs and is not
exposed via procfs.

### Endpoint allowlist (`_ALLOWED_ENDPOINT_HOSTS`)

`extract_entities.py` validates `--endpoint` against a frozenset containing only
`models.inference.ai.azure.com` before making any HTTP request. Rationale: prevents
token exfiltration if a caller supplies an attacker-controlled endpoint.

### Three-attempt self-correcting retry loop

The LLM call retries up to three times. On attempts 2 and 3, any schema validation errors
from the prior attempt are injected back into the prompt so the model can self-correct.
Rationale: `gpt-4o-mini` occasionally produces structurally valid JSON that fails the
extraction bundle schema (missing required keys, wrong list types). Re-injecting the
schema errors as feedback produces a corrected response on the next attempt without
requiring a hard failure. Three attempts balances correction opportunity against API cost.

### Lock acquisition: single critical section (implemented)

CI-3 invokes `synthesize_combined.py`, which acquires `wiki/.kb_write.lock` once,
then runs entity and concept draft writes inside the same critical section.
The standalone scripts (`synthesize_entity_page.py` and
`synthesize_concept_page.py`) remain available for manual/operator invocation,
but CI-3 no longer uses two independent lock acquisitions.

### Synthesis runs before `update_index`

The synthesis stage is positioned in CI-3 between the ingest loop and `update_index --write`
so that entity and concept draft pages are included in the index on the same CI run that
creates them. If synthesis ran after `update_index`, the new pages would be absent from the
index until the next CI-3 invocation.

## Consequences

- CI-3's `tp-pr-producer` token profile now includes `models: read`. Any security review
  of `tp-pr-producer` must account for this scope.
- Ingest PRs now include entity and concept draft pages as additional staged changes,
  visible in the PR diff for HITL review before merge.
- LLM extraction quality depends on `gpt-4o-mini` and the quality of the source page body
  (currently capped at 3,500 characters; entities mentioned only in later sections may be
  omitted — see GitHub issue #112).
- Single-lock synthesis in `synthesize_combined.py` removes the prior inter-lock
  window between entity and concept writes (implemented in issue #115).
- Synthesis soft-fail semantics mean entity/concept coverage can silently degrade during
  Models API outages. Operators should monitor `::warning` annotations in CI-3 runs.

## Amendment

**Date:** 2026-05-19

**What changed:** Issue [#115](https://github.com/wryenmeek/knowledgebase/issues/115)
implemented `synthesize_combined.py` as the CI-3 synthesis entry point. Entity
and concept writes now run under one `wiki/.kb_write.lock` acquisition,
replacing the prior two-lock design described in the ADR's original lock
section.

**What didn't change:** Soft-fail behavior, endpoint allowlist enforcement,
three-attempt extraction retry semantics, and synthesis placement before
`update_index` remain unchanged.

## References

- [ADR-004](ADR-004-split-ci-workflow-governance.md) — CI-1/CI-2/CI-3 split
- [ADR-005](ADR-005-write-concurrency-guards.md) — `wiki/.kb_write.lock` semantics
- [ADR-014](ADR-014-hitl-afk-work-classification.md) — HITL/AFK classification
- [ADR-015](ADR-015-extended-ci-trust-model.md) — Extended CI trust model
- Issue [#5](https://github.com/wryenmeek/knowledgebase/issues/5) — root cause triage
- Issue [#112](https://github.com/wryenmeek/knowledgebase/issues/112) — body truncation notice
- Issue [#115](https://github.com/wryenmeek/knowledgebase/issues/115) — single-lock implementation
