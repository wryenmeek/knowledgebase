# ADR-037: Jules persona memory learning loop governance

**Date:** 2026-08-10

## Status

Accepted — extends ADR-005, ADR-019, ADR-022, ADR-028

## Context

`.jules/bolt.md` and `.jules/sentinel.md` are passive Markdown journals that
record technical lessons for the Bolt and Sentinel Jules personas. They have
no automated write path today: any change is a manual, unreviewed edit.
`docs/plans/2026-08-10-001-feat-jules-persona-learning-loop-plan.md` (units
U1–U6) built a repository-scoped analyzer under `scripts/fleet/pr-learning/`
that collects Bolt/Sentinel Jules PR outcomes, classifies them against a
fixed taxonomy, clusters evidence into deduplicated candidates, validates a
bounded memory-entry proposal, and can open exactly one human-reviewed pull
request appending a single entry to one of the two memory files.

That code (`collect.ts`, `classify.ts`, `report.ts`, `cluster.ts`,
`metrics.ts`, `deduplicate.ts`, `memory-validator.ts`,
`proposal-validator.ts`, `propose.ts`, and the `jules-persona-learning.yml`
workflow) is implemented and tested, but per
`schema/jules-memory-entry-contract.md` and
`scripts/fleet/pr-learning/README.md`'s "Governance status" section, `.jules/
bolt.md` and `.jules/sentinel.md` remain deny-by-default until a governance
lane exists: an ADR, a CODEOWNERS row, a sensitive-path glossary entry, and
an `AGENTS.md` write-surface matrix row. This ADR is that lane (U7 of the
plan).

A key architectural fact drives this ADR's shape: **ADR-005's dual-layer
concurrency model (workflow `concurrency.group` + local `wiki/.kb_write.lock`
file) does not apply here.** The local-lock half of that model coordinates
concurrent processes on the *same* runner/filesystem; it cannot coordinate
two independent GitHub Actions runners that never share a filesystem. The
proposal mutation path (`propose.ts`) never runs as two processes on one
machine sharing a lock file — it runs as independent Actions jobs, each of
which only ever sees its own ephemeral runner. Claiming an
ADR-005-style local lock "coordinates" `.jules/*.md` writes would therefore
be false: it would look like a governance control while providing none.
Real-world coordination instead comes from three GitHub-visible mechanisms
that `propose.ts` and `jules-persona-learning.yml` already implement:

1. **Non-canceling workflow `concurrency.group`** keyed by
   `persona-mechanism-normalized_rule`, so concurrent runs for the *same*
   candidate serialize at the Actions-scheduler level (`cancel-in-progress:
   false`, matching `jules-archive-stale.yml`'s existing pattern) while
   disjoint candidates proceed independently.
2. **Lookup-before-create against GitHub-visible state**: `propose.ts` scans
   open and closed PRs for an existing `jules-memory-proposal` marker with
   the same candidate fingerprint before creating a branch or PR, and
   repeats that lookup a second time immediately before branch creation (a
   race guard against a run that started concurrently).
3. **Live base-tree and blob-SHA revalidation**: immediately before creating
   the blob → tree → commit, `propose.ts` re-fetches the base branch head
   and the target file's current blob SHA. A target that changed since
   classification (by a human edit, a merged prior proposal, or a
   concurrent run that already landed) is rejected outright — never
   overwritten and never silently merged.

## Decision

### Writable surface (R10)

Exactly two ordinary regular files may ever be modified by this pipeline,
and never any other path in the same proposal: `.jules/bolt.md` and
`.jules/sentinel.md`. Additions, deletions, renames, copies, mode changes,
symlinks, submodules, path traversal, and any other path are rejected by
`proposal-validator.ts` before a commit is ever created. Existing bytes in
either file are always preserved; a proposal only appends one bounded
Markdown block after the file's final byte.

### Two-job trust boundary (R11)

`jules-persona-learning.yml` splits into:

- **`collect`** — always runs, `contents: read` only, no other permission
  scope. Produces a versioned, digest-bound report artifact
  (`jules-persona-learning-report-<run_id>`) and never mutates repository
  state.
- **`propose`** — runs only for `mode: propose`, `contents: write` +
  `pull-requests: write` at job scope (no `issues`, `workflows`,
  `actions`, or session-mutation scope of any kind). Consumes only the
  same-run `collect` artifact after verifying it is bound to this run
  (producer workflow, collector commit, collector run id, base SHA,
  expiry, digest) — see `propose-cli.ts`.

No credential in this workflow can merge, close, label, or redispatch a PR,
or check out and execute PR code. `GH_TOKEN` is bound at step scope, never
job or workflow scope, matching the existing step-scoped secret rule in
`AGENTS.md`.

### No local lock; GitHub-visible coordination only (R8, R11, R13)

`.jules/bolt.md` and `.jules/sentinel.md` are **not** added to
`scripts/kb/write_utils.py`'s lock protocol and do not get a
`raw/.*.lock`-style sibling lock file. ADR-005's local-file-lock layer is
for same-filesystem write races (e.g., two script invocations against
`wiki/index.md` on one runner); it provides no protection across
independent Actions runners and must not be documented as if it did.
Coordination for this surface is the three GitHub-visible mechanisms in
Context above: non-canceling `concurrency.group`, lookup-before-create
against PR markers, and live base-tree/blob-SHA revalidation immediately
before every mutation. All three are enforced in code
(`scripts/fleet/pr-learning/propose.ts`,
`.github/workflows/jules-persona-learning.yml`) and exercised in
`propose.test.ts` and `tests/kb/test_jules_persona_learning_workflow.py`.

### Human-only merge, no fleet auto-processing (R12)

Proposal branches use the `jules-memory/<persona>/<fingerprint[:12]>` prefix
and an immutable HTML-comment PR-body marker
(`jules-memory-proposal: {...}`). `.github/workflows/fleet-merge.yml` and
`.github/workflows/fleet-dispatch.yml` explicitly exclude this branch
prefix so existing fleet automation can never auto-merge or redispatch a
learning proposal. `jules-persona-learning.yml` never calls `gh pr merge`,
`gh pr close`, or any Jules redispatch API against its own PR. Every
learning proposal requires normal trusted CI plus a human review/merge —
branch protection on `main` is the only merge gate.

### Governance additions landed by this ADR

- `.jules/bolt.md` and `.jules/sentinel.md` are added to the `sensitive
  paths` glossary entry in `CONTEXT.md` ## Terms and to
  `.github/CODEOWNERS` (advisory notification only — `require_code_owner_
  reviews` stays OFF, consistent with every other CODEOWNERS row) and to
  `scripts/kb/contracts.py::SENSITIVE_PATHS` (source of truth for
  `check_commit_scope.py`'s gate B).
- `AGENTS.md`'s write-surface matrix gains a row for
  `scripts/fleet/pr-learning/**` declaring: mixed runtime mode
  (collection/classification/clustering/validation modules are read-only
  only; `propose.ts` is blocking-only with external GitHub API side
  effects and no local repository writes), the exact two-file writable
  allowlist, no lock requirement (with the rationale above), and the
  hard-fail conditions already enforced in code.
- `docs/mvp-runbook.md`'s existing `jules-persona-learning.yml` row is
  corrected to reference this ADR instead of a placeholder.
- `schema/jules-pr-learning-contract.md` and
  `schema/jules-memory-entry-contract.md` reference this ADR and document
  the current U1–U6 implementation status. The workflow remains manual and
  report-first; proposal writes are authorized only through the governed
  workflow and human review path described here.
- `tests/kb/test_framework_write_surface_matrix.py` gains an expected-row
  entry for `scripts/fleet/pr-learning/**` so a future contributor cannot
  silently narrow or widen the declared surface without the test failing.
- `docs/decisions/README.md` gains this ADR's index row.

## Alternatives considered

### Add a local `raw/.jules-memory.lock` sibling lock

- **Pros:** superficially consistent with the existing sibling-lock family
  (`wiki/.kb_write.lock`, `raw/.rejection-registry.lock`, etc.).
- **Cons:** cannot coordinate independent GitHub Actions runners, which
  never share a filesystem or lock file. Adding it would create a false
  sense of protection and an unused governance artifact that drifts from
  the code it claims to govern.
- **Rejected:** the real coordination contract is GitHub-visible state
  (concurrency group + PR marker lookup + live base-tree revalidation),
  which is already implemented; a local lock would add no protection.

### Grant `propose.ts` merge or auto-merge capability

- **Pros:** would close the loop fully autonomously.
- **Cons:** directly violates R12 and the plan's explicit non-goal;
  removes the human review step that R9/R10 depend on for catching
  unsupported claims, scope creep, or subtly wrong rules before they enter
  persistent Jules memory.
- **Rejected:** human review of every memory change is a hard requirement,
  not a temporary MVP limitation.

### Fold `.jules/*.md` into the existing `wiki/.kb_write.lock` protocol

- **Pros:** reuses an existing, well-tested lock helper.
- **Cons:** `.jules/*.md` are not wiki artifacts and are never touched by
  any `wiki/**` writer; folding them in would conflate two unrelated
  trust domains (wiki curation vs. Jules persona memory) and would still
  provide no cross-runner protection.
- **Rejected:** the two-file allowlist and GitHub API mutation path are
  fully separate from the wiki write surface.

## Consequences

### Positive

- `.jules/bolt.md` and `.jules/sentinel.md` become an auditable, reviewed
  write surface instead of an ungoverned manual-edit target, with a clear
  paper trail (ADR, CODEOWNERS, matrix row, contract) tying the runtime
  behavior to governance.
- The false-lock trap (documenting a local lock that doesn't actually
  coordinate anything) is avoided by naming the real mechanism explicitly.
- Contract tests (`test_framework_write_surface_matrix.py`,
  `test_codeowners_completeness.py`, `test_commit_scope_check_paths.py`,
  `test_doc_cascade_completeness.py`) now fail if this surface's
  documentation drifts from its declared scope.

### Negative

- No automated write path exists yet against a live repository until an
  operator runs `jules-persona-learning.yml` with `mode: propose` for the
  first time; this ADR only authorizes the surface, it does not schedule
  or trigger anything.
- Advisory CODEOWNERS notification on `.jules/*.md` adds two more rows to
  review during any future CODEOWNERS audit; the marginal cost is small
  (2 of what is now 13 total sensitive-path rows).
- Because there is no lock, a bug that broke the live base-tree
  revalidation could in principle race two runs into a stale write; this
  is mitigated by requiring both the marker lookup and the blob-SHA
  recheck to run immediately before every mutation (already implemented
  and covered by `propose.test.ts`), not by adding a lock that would not
  actually help.

### Backout

Revert the workflow's `mode: propose` path (leave `mode: report` only),
remove the CODEOWNERS/`SENSITIVE_PATHS`/`AGENTS.md` matrix rows, and mark
this ADR's status as amended to reflect the rollback, restoring `.jules/
*.md` to fully manual, ungoverned edits.

## References

- `docs/plans/2026-08-10-001-feat-jules-persona-learning-loop-plan.md`
- `schema/jules-pr-learning-contract.md`
- `schema/jules-memory-entry-contract.md`
- `scripts/fleet/pr-learning/README.md`
- `docs/decisions/ADR-005-write-concurrency-guards.md`
- `docs/decisions/ADR-019-fleet-jules-orchestration.md`
- `docs/decisions/ADR-022-afk-uses-scripts-hitl-uses-copilot-cli.md`
- `docs/decisions/ADR-028-instruction-locality-ladder.md`
