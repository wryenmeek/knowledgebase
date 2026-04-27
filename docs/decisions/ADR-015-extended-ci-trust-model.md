# ADR-015: Extend CI governance with framework-writer (CI-4) and GitHub-monitor (CI-5) workflows

## Status
Accepted

## Date
2026-04-27

## Context

ADR-004 established a three-workflow CI trust model (CI-1 gatekeeper, CI-2
read-only analyst, CI-3 PR-producing wiki writer). That model covers the
ingest-to-wiki write path but leaves two write-capable operations ungoverned:

1. **Framework-path writes** — agent-generated content in `docs/**` and
   `.github/skills/**`. These paths are not wiki artifacts and should not
   go through CI-3's wiki write allowlists, but they still require
   maintainer-approved automation with least-privilege permissions.

2. **External source drift detection and synthesis** — scheduled monitoring of
   upstream GitHub repositories for content drift, followed by conditional
   synthesis of updates into bounded wiki pages. This requires GitHub App
   authentication for external API calls, scheduled triggers, and a
   conditional write path that ADR-004's three-workflow model does not cover.

Both operations also need their own token permission profiles and concurrency
guards separate from CI-3 to avoid sharing write-capable credentials across
unrelated workflows.

## Decision

Add two new CI workflows extending the ADR-004 trust model:

### CI-4: Framework Writer

- **Trigger:** `workflow_dispatch` only (no event-driven or scheduled triggers).
  An agent stages a manifest; a maintainer manually dispatches the workflow
  with `maintainer_approved: true`.
- **Permission profile:** `tp-framework-writer` — elevated `contents: write`
  and `pull-requests: write` scoped to `docs/**` and `.github/skills/**` only.
- **Write allowlist:** `docs/**` and `.github/skills/**` markdown files;
  `docs/staged/**` is read-only input, never a write target.
- **Operations:** `fill-context` (via `scripts/context/fill_context_pages.py`)
  and `generate-docs` (via `scripts/maintenance/generate_docs.py`).
- **Gate:** Protected-environment review enforces human approval before the
  write job runs. The `maintainer_approved` input is a belt-and-suspenders
  attestation on top of environment protection.
- **Concurrency:** Non-cancellable once write job starts; prevents orphaned
  branches from mid-flight cancellation.

### CI-5: GitHub Source Monitor

- **Trigger:** Daily schedule (`cron: '0 6 * * *'`) and `workflow_dispatch`
  for manual runs against a specific registry file.
- **Permission profile:** `tp-github-monitor` — `contents: write` and
  `pull-requests: write` for the synthesis write job only; drift detection
  and classification jobs run read-only.
- **Architecture:** Three-stage pipeline:
  1. `check-drift` — read-only; queries GitHub API for upstream content changes.
  2. `classify-drift` — read-only; separates AFK-eligible from HITL-required
     entries per ADR-014 classification rules.
  3. `fetch-and-synthesize` — write-capable; runs only when drift detected;
     conditionally dispatches AFK writes or opens issues for HITL review.
- **Write allowlist:** Bounded `wiki/**` pages declared in registry entries
  and `raw/assets/{owner}/{repo}/{commit_sha}/**` asset paths.
- **Lock ordering:** `wiki/.kb_write.lock` acquired before
  `raw/.github-sources.lock` per ADR-005 and ADR-012.

## Alternatives Considered

### Extend CI-3 to cover framework paths

- **Pros:** Single write-capable workflow; fewer files to maintain.
- **Cons:** CI-3's write allowlist is scoped to `wiki/**` and `raw/processed/**`;
  mixing framework-path writes into CI-3 would broaden its blast radius and
  require cross-domain permission escalation.
- **Rejected:** Least-privilege principle requires separate permission contexts
  for wiki writes vs. framework writes.

### Merge CI-5 into CI-3

- **Pros:** Consolidates write operations.
- **Cons:** CI-5 needs external GitHub API authentication (GitHub App token)
  that CI-3 does not; scheduled triggers differ from CI-3's event model;
  the conditional AFK/HITL classification path has no analogue in CI-3.
- **Rejected:** Different trigger model, auth model, and write domain.

### Schedule-driven wiki synthesis without a separate workflow

- **Pros:** Simpler architecture.
- **Cons:** No separation between read-only drift detection and write-capable
  synthesis; no conditional branching between AFK and HITL paths.
- **Rejected:** Lacks the fail-closed gating that ADR-014 requires.

## Consequences

- The CI trust model now has five named workflow roles (CI-1 through CI-5)
  each with a distinct permission profile.
- `ci-4-framework-writer.yml` and `ci-5-github-monitor.yml` must be listed in
  `test_ci_permission_asserts.py` with their declared `CI_ID` and
  `TOKEN_PROFILE` env vars.
- Framework-path writes (CI-4) remain human-approved; wiki writes from drift
  synthesis (CI-5 AFK path) are gated by ADR-014 classification.
- CI-5's AFK path is the only scheduled write automation in the codebase;
  any expansion must go through ADR-014's AFK allowlist governance.

## References

- `docs/decisions/ADR-004-split-ci-workflow-governance.md` — baseline three-workflow model
- `docs/decisions/ADR-005-write-concurrency-guards.md` — lock semantics
- `docs/decisions/ADR-012-github-source-monitoring.md` — CI-5 monitoring pipeline
- `docs/decisions/ADR-014-hitl-afk-work-classification.md` — AFK/HITL gate for CI-5
- `.github/workflows/ci-4-framework-writer.yml`
- `.github/workflows/ci-5-github-monitor.yml`
- `raw/processed/SPEC.md` (Security and Trust Model; Token permission profiles)
