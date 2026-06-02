# ADR-027: Infrastructure validation trigger model for CI-3

**Status:** Accepted

**Date:** 2026-06-02

## Context

The wiki synthesis pipeline (CI-3) was originally designed to be triggered only by the intake gatekeeper (CI-1) when new sources are available. This assumes a linear governance flow: `intake -> verification -> policy -> synthesis`.

However, infrastructure changes (topology validators, synthesis workflow updates, skill logic changes) need to be validated end-to-end without requiring corresponding intake changes. When PR #165 fixed the topology-hygiene validator by updating `wiki/index.md` and `.github/workflows/ci-3-pr-producer.yml`, there was no automatic way to trigger CI-3 re-validation because those changes touched only control-plane files, not `raw/inbox/**`.

This created a gap: infrastructure fixes were implemented but unvalidated end-to-end.

## Decision

Enable CI-3 to be triggered automatically by direct `push` events to `main` when those pushes modify CI-3 infrastructure files only:

- `.github/workflows/ci-3-pr-producer.yml` (the synthesis workflow itself)
- `.github/skills/validate-wiki-governance/**` (topology and synthesis validators)
- `.github/skills/synthesize-entity-page/**` (entity synthesis implementation)
- `.github/skills/synthesize-concept-page/**` (concept synthesis implementation)

This establishes a second, parallel trigger path (`infrastructure_revalidation`) alongside the primary intake-driven path (`intake_driven`). Both trigger types:

1. Run through the full CI-3 synthesis pipeline
2. Are gated by the same governance checks (preflight prerequisites, permissions, path filtering)
3. Update the checkpoint registry (when implemented) with `trigger: infrastructure_revalidation`
4. Maintain strict path filtering to reject pushes mixing infrastructure files with inbox or other control-plane changes

## Rationale

**Why automatic push trigger?**
- Infrastructure bugs (validator crashes, workflow errors) should be caught immediately at commit time, not deferred to the next inbox ingestion
- Enables fail-closed validation: if the infrastructure change breaks synthesis, the push succeeds but synthesis fails, leaving evidence in CI logs
- Aligns with CI/CD best practices: infrastructure changes self-validate

**Why path-filtered?**
- Prevents accidental triggering on unrelated control-plane changes (e.g., docs-only commits)
- Maintains mixed-scope governance policy: infrastructure validation runs are still pure control-plane, never mixing inbox
- Reduces noisy CI-3 reruns that consume runtime budget

**Why separate from intake-driven runs?**
- Checkpoint registry must track trigger source for recovery semantics (e.g., after `infrastructure_revalidation`, partial failure doesn't block `intake_driven` runs, only infrastructure fixes)
- Allows operator to prioritize: manual rescan can target specific trigger type if needed

## Alternatives considered

1. **Manual workflow_dispatch only** — Infrastructure fixes would require operator intervention to validate. Rejected: adds friction and delays bug discovery.

2. **Always re-trigger on any .github/ change** — Would spam CI-3 with runs unrelated to synthesis (e.g., CI-2 workflow updates, ADR edits). Rejected: wastes budget, adds noise.

3. **Wait for next inbox change** — Defers validation until new source arrives. Rejected: infrastructure bugs would remain undetected for potentially days.

## Consequences

**Positive:**
- Infrastructure fixes now validate end-to-end immediately
- Catches synthesis workflow errors before they impact intake processing
- Supports the checkpoint registry design (docs/ideas/wiki-processing-checkpoint-registry.md) by establishing multiple trigger paths

**Negative:**
- CI-3 runtime budget consumed on every infrastructure change (mitigated by path-filtering to only synthesis-critical files)
- Operators must understand two trigger semantics (intake_driven vs. infrastructure_revalidation) when diagnosing failures

**Operational:**
- CI-3 preflight must validate that only infrastructure files changed (implemented in .github/workflows/ci-3-pr-producer.yml, lines 109–147)
- Checkpoint registry schema includes `trigger` and `triggered_by` fields to distinguish runs
- No checkpoint state is required to enable this trigger; runs proceed regardless of checkpoint completeness

## Related decisions

- ADR-007: Control-plane layering and packaging (infrastructure changes are control-plane only)
- ADR-026: Wiki processing checkpoint registry (checkpoint registry tracks trigger source)

## Migration and rollback

**To enable:** Merge `.github/workflows/ci-3-pr-producer.yml` changes that add push trigger and event handler.

**To disable:** Remove `push:` trigger section from CI-3 workflow YAML; reverts to intake-only + manual dispatch.

**Rollback impact:** None; existing runs are unaffected. New infrastructure changes will no longer auto-validate (must use manual_dispatch).

## Open questions

- Should `infrastructure_revalidation` runs update wiki/ artifacts (entities, concepts) if synthesis succeeds? Currently yes (same as intake_driven). Alternative: skip write to wiki/, only validate topology. **Decision pending operator feedback.**
