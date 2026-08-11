# Jules Persona PR Learning Loop (`scripts/fleet/pr-learning/`)

Repository-scoped, evidence-bound analyzer for Bolt and Sentinel Jules PR
outcomes. Collects PR history, classifies merge/close outcomes against a
fixed taxonomy, clusters evidence into deduplicated candidates, validates a
bounded memory-entry proposal, and — only after that validation passes —
creates exactly one human-reviewed pull request that appends a single entry
to `.jules/bolt.md` or `.jules/sentinel.md`.

See `schema/jules-pr-learning-contract.md` and
`schema/jules-memory-entry-contract.md` for the authoritative data-shape and
governance contracts, and
`docs/plans/2026-08-10-001-feat-jules-persona-learning-loop-plan.md` for the
full implementation plan (units U1–U7).

This directory never edits `.jules/*.md` directly, executes PR code, or
merges its own proposal. Every module below is pure/read-only except
`propose.ts`, which is the single narrowly-scoped mutation entrypoint.

The collector requires an independently verified Jules session/source link
before a record can support a closed-cause prevention rule. If that verifier
is unavailable, records remain `ambiguous` by design; the loop never falls
back to author, branch, title, or body markers.

## Modules

| Module | Unit | Responsibility |
|---|---|---|
| `types.ts` | U1 | Canonical `OutcomeState`, `ClosureCause`, `EvidenceEnvelope`, `Candidate`, `MemoryEntry`, `ProposalMarker` types and version constants. Authoritative TypeScript implementation of both schema contracts. |
| `fingerprints.ts` | U1 | Text normalization/canonicalization and the versioned `CandidateFingerprint`/`evidence_digest` SHA-256 computations. |
| `collect.ts`, `classify.ts`, `report.ts` | U2 | Read-only GitHub PR collection and outcome classification into a bounded, digest-bound report. |
| `cluster.ts`, `metrics.ts`, `deduplicate.ts` | U3 | Clustering by semantic key, merge-rate/backlog metrics, and deduplication against existing memory/open proposals. |
| `memory-validator.ts` | U4 | Field-level `MemoryEntry` validation: shape, size limits, redaction boundary, stale-target guard, append-only byte-preservation check. |
| `proposal-validator.ts` | U4 | Diff/tree-level validation: exactly one allowlisted file, content-preserving edit only, base-tree stale guard, patch-level redaction scan. |
| `propose.ts` | U5 | **The only mutation entrypoint.** Governed, idempotent branch/commit/PR creation for an already-validated candidate + entry. |

## `propose.ts` (U5): governed proposal creation

`createMemoryProposal(client, input, options)` is a pure orchestrator over
an injected `ProposeGitHubClient`. It requires no credentials to import —
nothing in this module constructs an Octokit instance or reads
`process.env` at module load time. A caller wires a concrete
(Octokit-backed) client only inside a `main()`/CLI entrypoint guarded by
`import.meta.main`, matching every other `scripts/fleet/**` script.

### What it does

Given a validated `Candidate` and `MemoryEntry` (already approved by
`memory-validator.ts` / `proposal-validator.ts`), it:

1. **Looks up before creating.** Skips if an open or closed proposal PR
   already carries a marker for this candidate's fingerprint.
2. **Revalidates the base live.** Re-fetches the base branch head and the
   target file's current blob SHA — a target that changed since
   classification is rejected, never overwritten.
3. **Re-validates the entry** against the live blob SHA and the exact
   byte-for-byte appended content (never trusts a stale approval).
4. **Creates blob → tree → commit** against the freshly revalidated base,
   touching only the single allowlisted `.jules/bolt.md` or
   `.jules/sentinel.md` path.
5. **Looks up a second time** immediately before creating the branch (a
   race guard against a concurrent run for the same fingerprint).
6. **Creates the branch, then the PR**, each wrapped with
   timeout-lookup-recovery: on a retryable-classified failure (per
   `github/mutation-diagnostics.ts`), it re-queries GitHub for the expected
   ref/PR before deciding whether to retry — so a client-observed timeout
   after a server-side success never produces a duplicate mutation.

### What it never does

- Never checks out, clones, or executes any PR code.
- Never calls a merge, auto-merge, issue, label, workflow, or
  session-mutation API. `ProposeGitHubClient` has no such methods — the
  interface itself is the enforcement boundary.
- Never touches any path other than the one recorded in the candidate.
- Never force-pushes or overwrites: if the deterministic branch already
  exists without a matching PR marker, creation fails closed rather than
  guessing.

### Idempotency and concurrency contract (R8, R11)

- **Deterministic branch name:** `jules-memory/<persona>/<fingerprint[:12]>`
  (`computeProposalBranchName`).
- **Marker embedded in the PR body:** a bounded HTML-comment JSON block
  (`renderProposalMarker` / `parseProposalMarker`) carrying `repo`,
  `target_memory_path`, `candidate_fingerprint`, `base_branch`,
  `branch_name`, `producer_workflow`, and `collector_commit` — exactly the
  fields required by `schema/jules-memory-entry-contract.md`'s "Proposal
  marker" section.
- **Non-canceling concurrency group:** `proposalConcurrencyGroupName(fingerprint)`
  and `PROPOSAL_CONCURRENCY_CANCEL_IN_PROGRESS` (`false`) are the constants
  the U6 workflow must wire into `concurrency: { group, cancel-in-progress }`
  for the proposal job, mirroring `jules-archive-stale.yml`'s
  `cancel-in-progress: false` pattern. Distinct fingerprints (which already
  encode persona) always get distinct groups, so unrelated candidates
  proceed independently while concurrent runs for the *same* candidate
  serialize.
- **GitHub-visible state is the real coordination mechanism.** Local
  filesystem locks (ADR-005) do not coordinate separate GitHub Actions
  runners — the marker plus live base-tree revalidation are what make
  concurrent runs converge on at most one proposal PR.

### Testing

`propose.test.ts` exercises every pure helper (branch naming, marker
render/parse, appended-content construction, commit message) plus the full
orchestration flow against `FakeGitHubClient`, an in-memory fake
implementing `ProposeGitHubClient` that records every call. Covered
scenarios include: single-file creation, idempotent re-runs, independent
disjoint-fingerprint runs, branch/PR-creation timeout recovery, stale-target
rejection, missing-target rejection, malformed-fingerprint/commit rejection,
existing/closed/human-edited proposal handling, and a structural assertion
that no call or client method ever references merge/issue/label/session/
checkout/exec behavior.

Run just this suite:

```bash
bun test pr-learning/propose.test.ts
```

Run the whole `pr-learning/` suite:

```bash
bun test pr-learning/
```

## Governance status

As of U7, `.jules/bolt.md` and `.jules/sentinel.md` are a declared and
authorized write surface: `docs/decisions/ADR-037-jules-persona-memory-learning.md`
governs this pipeline, `AGENTS.md`'s write-surface matrix has a
`scripts/fleet/pr-learning/**` row, `.github/CODEOWNERS` and `CONTEXT.md`'s
sensitive-paths glossary list both target files, and
`jules-persona-learning.yml` wires the report/propose workflow described
above. There is deliberately no local file-lock protocol for this surface —
per ADR-037, an ADR-005-style local lock cannot coordinate independent
GitHub Actions runners. Coordination instead relies on the workflow's
non-canceling `concurrency.group`, lookup-before-create against
GitHub-visible proposal markers, and live base-tree/blob-SHA revalidation
immediately before every mutation (all implemented in `propose.ts` and
exercised in `propose.test.ts`).
