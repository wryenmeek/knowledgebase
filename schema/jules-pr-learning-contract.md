# Jules PR Learning Contract

**Schema version:** 1
**Taxonomy version:** 1
**Canonicalization version:** 1
**Produced by:** `scripts/fleet/pr-learning/collect.ts`, `scripts/fleet/pr-learning/classify.ts` (U2)
**Consumed by:** `scripts/fleet/pr-learning/cluster.ts`, `scripts/fleet/pr-learning/deduplicate.ts`, `scripts/fleet/pr-learning/memory-validator.ts`, `scripts/fleet/pr-learning/propose.ts` (U3–U5)
**Governed by:** `docs/plans/2026-08-10-001-feat-jules-persona-learning-loop-plan.md` (U1), `docs/decisions/ADR-037-jules-persona-memory-learning.md` (U7)

---

## Purpose

This contract is the single authoritative definition of the outcome state
machine, closure taxonomy, evidence/provenance envelope, canonical
normalization rules, and candidate fingerprint used to turn raw Jules persona
PR history into deduplicated, evidence-bound learning candidates. It exists
so collection, classification, clustering, deduplication, and proposal
validation share one deterministic interpretation instead of re-deriving
their own ad hoc rules. `scripts/fleet/pr-learning/types.ts` is the
TypeScript implementation of the shapes defined here; this document is
authoritative when the two disagree.

This contract does not itself grant any write permission. It defines data
shapes only. Write authority for `.jules/*.md` is governed by
[`jules-memory-entry-contract.md`](jules-memory-entry-contract.md) and, once
landed, the AGENTS.md write-surface matrix row for
`scripts/fleet/pr-learning/propose.ts` (U5/U7).

---

## Outcome state machine

Every collected PR is classified into exactly one `OutcomeState`:

| State | Meaning |
|---|---|
| `merged` | `merged_at` is present and non-null. This is the sole merge authority — a non-null `merge_commit_sha` without `merged_at` is **not** sufficient. |
| `closed_unmerged` | The PR reached a final closed state (`state: "closed"`), `merged_at` is null, and the identity/evidence predicate (below) passed. |
| `open` | The PR is open, draft, has pending checks, or has not reached a stable final state. Never counted in terminal metrics. |
| `ambiguous` | Evidence is incomplete, conflicting, or the identity predicate failed. A quarantine state, never a negative outcome, and never eligible for learning. |

Precedence rules (evaluated in this order):

1. If `merged_at` is present and non-null → `merged`, regardless of any other field.
2. Else if the PR is still open (including draft, pending checks, or reopened
   before it reaches its configured stabilization cutoff) → `open`.
3. Else if the identity/evidence predicate (R1) fails, or event history is
   internally inconsistent (e.g. conflicting base/head SHAs across API
   responses, mismatched repository fields, missing author identity) →
   `ambiguous`.
4. Else → `closed_unmerged`.

Transitions:

```
Open -> Open (draft or checks pending)
Open -> ClosedUnmerged (final close without merge)
Open -> Merged (merged_at becomes present)
ClosedUnmerged -> Open (reopened)
ClosedUnmerged -> Merged (later merge)
Merged -> Merged (a later revert is reported separately, never re-classified)
Open -> Ambiguous (incomplete or conflicting evidence)
ClosedUnmerged -> Ambiguous (identity or event conflict discovered later)
```

A reopened PR is counted in terminal metrics only after its final state
passes the configured stabilization cutoff (a fixed lookback watermark
defined by the collector, not by this contract). Reverts of a merged PR
remain `merged` for the primary metric and must be surfaced as a separate,
explicitly labeled signal — never as a state transition away from `merged`.

---

## Identity / evidence predicate (R1)

A PR is only eligible to leave the `open` state with a non-`ambiguous`
classification when **all** of the following hold:

- `author_id` is present and stable (a `null` or missing author is
  `ambiguous`).
- `session_id` (or equivalent Jules session/source identifier) is present
  and independently verified — matched to a real Jules session record, not
  merely present as a text token in the PR title, branch name, or body.
- `base_repo_full_name` and `head_repo_full_name` are both present and
  **equal** to the configured repository-scope boundary
  (`wryenmeek/knowledgebase` for the MVP). A fork head (`head_repo_full_name`
  differs from `base_repo_full_name`) is `ambiguous`, never accepted.
- `evaluated_head_sha` is present and immutable (the exact SHA that was
  reviewed/checked, not a live/mutable ref).

Copied session-ID-shaped text in a title/body/branch is **not** sufficient
on its own; it must be corroborated by an independently verified session
record before the identity predicate can pass. Missing linkage is always
`ambiguous` — it is never treated as an accepted fallback identity.

---

## Closure taxonomy (R3)

`closed_unmerged` and `ambiguous`-quarantined-after-classification PRs carry
exactly one `ClosureCause` from this fixed, versioned taxonomy
(`taxonomy_version: 1`):

| Value | Meaning |
|---|---|
| `duplicate_or_superseded` | The change duplicates or was superseded by another PR/commit. |
| `scope_creep` | The PR grew beyond its original, reviewable scope. |
| `unsupported_claim` | The PR's stated rationale (performance, correctness, etc.) was not independently verifiable. |
| `test_or_policy_failure` | CI, contract, or governance validation failed and was not remediated before closure. |
| `unsafe_change` | The change was rejected as a safety/security risk. |
| `stale_artifact` | The PR targeted content/config that had since changed underneath it. |
| `conflict_or_rebase` | The PR could not be merged due to conflicts and was abandoned rather than rebased. |
| `unknown` | Evidence exists but does not support any of the above causes with confidence. |

Rules:

- `unknown` and any closure cause backed by insufficient or conflicting
  evidence can **never** satisfy the two-distinct-PR clustering threshold
  (R6/R7). They are reported for backlog visibility only.
- Adding a new taxonomy value requires incrementing `taxonomy_version`.
  Fingerprints computed under different taxonomy versions are never treated
  as equivalent (see Candidate fingerprint, below).
- A `merged` PR never carries a `ClosureCause`; the field is `null` for
  `merged` and `open` records.

---

## Evidence / provenance envelope (R4)

Every collected record (regardless of resulting `OutcomeState`) is an
`EvidenceEnvelope` with the following required fields:

| Field | Type | Required | Description |
|---|---|---|---|
| `repo` | string (`owner/repo`) | ✅ | Repository scope boundary; must equal the configured target repo. |
| `pr_number` | integer | ✅ | Pull request number. |
| `persona` | `"bolt" \| "sentinel"` | ✅ | Which Jules persona produced the PR. |
| `outcome` | `OutcomeState` | ✅ | See state machine above. |
| `closure_cause` | `ClosureCause \| null` | ✅ | Required non-null only when `outcome` is `closed_unmerged`; `null` otherwise. |
| `base_sha` | string (40-char hex) | ✅ | Base branch SHA the PR was opened/rebased against. |
| `evaluated_head_sha` | string (40-char hex) | ✅ | The immutable head SHA that was actually evaluated (checked, reviewed). |
| `merge_sha` | string (40-char hex) \| null | ✅ | Merge commit SHA if merged, else `null`. Never sufficient alone to imply `merged` — see state machine rule 1. |
| `author_id` | string \| null | ✅ | Stable author identity (login or numeric ID); `null` triggers `ambiguous`. |
| `session_id` | string \| null | ✅ | Verified Jules session/source identifier; `null` triggers `ambiguous`. |
| `base_repo_full_name` | string \| null | ✅ | Base repository full name from the PR API response. |
| `head_repo_full_name` | string \| null | ✅ | Head repository full name; must equal `base_repo_full_name` for eligibility. |
| `event_ids` | string[] | ✅ | Identifiers (event/check/review IDs) that support the classification decision. May be empty only when `outcome` is `open`. |
| `collected_at` | string (ISO-8601 UTC) | ✅ | Timestamp the record was collected/observed (this snapshot run). Never used for backlog-aging computations — see `created_at` below. |
| `created_at` | string (ISO-8601 UTC) | ✅ | Timestamp the PR was actually opened, per the PR API's own `created_at`. This is the outcome-relevant instant for "aged open" backlog aging (R6/R7); it is never the same instant as `collected_at`, which only records when this snapshot was taken and would otherwise make an aged-open computation permanently report zero backlog age. |
| `as_of` | string (ISO-8601 UTC) | ✅ | The fixed collector snapshot watermark this record belongs to. |
| `taxonomy_version` | integer | ✅ | Taxonomy version used to assign `closure_cause`. |
| `evidence_digest` | string (sha256 hex, 64 chars) | ✅ | Digest over the canonicalized evidence used for this classification (see Normalization, below). Enables regeneration detection. |
| `reverted` | boolean | ✅ | `true` only when a `merged` PR's merge was later reverted (structured `reverted` label/marker evidence, never inferred from prose). Always `false` for non-`merged` outcomes. Reported as a distinct backlog-visibility signal (`reverted_count`), separate from `aged_open_count` — a reverted merge is not evidence of prevention/hygiene value and must never be silently folded into the merged-outcome success count. |

An envelope missing any required field, or with `closure_cause` set for a
non-`closed_unmerged` outcome (or unset for a `closed_unmerged` outcome), is
malformed and must be rejected — never partially trusted.

---

## Normalization / canonicalization (R7)

Before computing a candidate fingerprint or comparing two candidates for
equivalence, text inputs (mechanism description, affected scope, rule text)
must be canonicalized as follows (`canonicalization_version: 1`):

1. Unicode-normalize to NFC.
2. Trim leading/trailing whitespace.
3. Collapse all interior runs of whitespace (including newlines and tabs) to
   a single ASCII space.
4. Lowercase for comparison purposes only (the original case is preserved in
   any generated memory entry text — normalization applies only to the
   fingerprint/dedup computation, never to published prose).
5. Sort any unordered list-valued component (e.g., `affected_scope` paths)
   lexicographically before joining, so that input order never changes the
   fingerprint.

Two candidates whose only difference is whitespace, key order, or list
order must normalize to an identical string and therefore produce an
identical fingerprint. Any change to the normalization algorithm itself
requires incrementing `canonicalization_version`; fingerprints computed
under different canonicalization versions are never treated as equivalent.

---

## Candidate fingerprint (R7)

A `CandidateFingerprint` is computed from the following ordered,
canonicalized components, joined with the ASCII unit separator `\u001f`
before hashing:

```
persona | mechanism | affected_scope (sorted, joined with ",") | normalized_rule | taxonomy_version | canonicalization_version | target_memory_path
```

The fingerprint is the lowercase hex-encoded SHA-256 digest of that joined
string. Including `evidence_digest` context and `target_memory_path` in the
underlying candidate object (even though not hashed directly into the
semantic key) ensures deduplication can distinguish "same lesson, same
target" from "same lesson, different target file" — the fingerprint itself
is scoped to the semantic cluster key (`persona | mechanism |
affected-scope | normalized-rule`) per R7, while the full `Candidate`
object separately carries `evidence_digest` and `target_memory_path` for
proposal-time validation (U4).

Two candidates are the same cluster if and only if their fingerprints are
byte-identical. Changing `taxonomy_version` or `canonicalization_version`
always yields a distinct fingerprint, even for textually identical input,
so historical clusters are never silently merged across a taxonomy change.

---

## Candidate eligibility (R6)

A `Candidate` becomes eligible for a memory proposal only when:

- **Technical lesson:** at least one independently verified `merged` PR
  supports a scoped, evidence-backed rule, **or**
- **Closed-cause prevention rule:** at least two *distinct* PRs (different
  `pr_number` values) share the same candidate fingerprint with
  `outcome: closed_unmerged` and a non-`unknown` `closure_cause`.

A single `closed_unmerged` PR, or any number of PRs with `closure_cause:
unknown` or `outcome: ambiguous`, never satisfies eligibility.

---

## Collector/proposer session-verification contract (R1, R6, R11, R13)

Every `CollectionReport` (see `scripts/fleet/pr-learning/report.ts`) carries
a top-level `session_verification: "authoritative" | "none"` field,
recording whether the collection run(s) that produced it used a real,
independently verified Jules session/source registry
(`"authoritative"`) or `NullSessionVerifier`/no verifier at all
(`"none"`, the fail-closed default when unspecified).

This field is deliberately excluded from the report's content `digest` —
it describes collection *provenance*, not evidence content — but every
`propose` consumer must check it before doing anything else:

- If `session_verification` is `"none"` (or absent, for an older artifact
  schema), **every** candidate's `session_id` was quarantined `ambiguous`
  by construction (R1), so no envelope can ever satisfy R6 eligibility.
  `propose-cli.ts`'s `validateArtifactBindings` refuses to proceed with an
  explicit "propose mode is unavailable" error at artifact-validation
  time — before re-collection or eligibility re-derivation even run —
  rather than allowing the operator to hit a misleading "does not satisfy
  R6 eligibility" error deep in the propose flow.
- Only `"authoritative"` permits `propose-cli.ts` to continue past
  artifact-binding validation.

As of this MVP, `collect-and-report-cli.ts` always passes
`sessionVerification: "none"` to `buildCollectionReport` (see its module
docstring) — no authoritative Jules session registry is wired up yet
(deferred follow-up work per the loop's plan doc). **`propose` mode is
therefore currently unavailable end-to-end**, by design: this matches the
plan's explicit requirement that "proposal mode must fail closed before
any write" until an authoritative verifier is wired.

---

### Report digest revalidation

Before consuming `report.envelopes` for session verification or eligibility,
every `propose` consumer must recompute the report digest from the report's
`schema_version`, `repo`, `as_of`, and canonicalized envelope set, then compare
it with `report.digest`. A mismatch, or a missing required report field, is a
hard failure; the consumer must not derive session links, eligibility, or
proposal evidence from the artifact.

## TypeScript implementation

The canonical TypeScript types, enums, and pure functions implementing this
contract live in:

- `scripts/fleet/pr-learning/types.ts` — `OutcomeState`, `ClosureCause`,
  `EvidenceEnvelope`, `Candidate`, `MemoryEntry`, `ProposalMarker`, and the
  `TAXONOMY_VERSION` / `CANONICALIZATION_VERSION` / `CONTRACT_SCHEMA_VERSION`
  constants.
- `scripts/fleet/pr-learning/fingerprints.ts` — `normalizeText()`,
  `computeCandidateFingerprint()`, `computeEvidenceDigest()`.

Later units (U2–U5) must import these types rather than redefining
equivalent shapes locally, per the repository's "constants: import, don't
duplicate" convention.

---

## Validation

Any consumer of an `EvidenceEnvelope` or `Candidate` must validate:

- All required fields listed above are present and correctly typed.
- `closure_cause` is set if and only if `outcome === "closed_unmerged"`.
- `merge_sha` presence never overrides state machine rule 1 (`merged_at`
  authority).
- `evidence_digest` and `candidate_fingerprint` are 64-character lowercase
  hex strings.

A malformed envelope or candidate is a hard failure for the consuming stage
— it must not be partially processed or silently coerced into a different
outcome state.

---

## Governance

- This is a **contract-only** document for U1. No collector, classifier, or
  proposal writer is implemented yet (see U2–U6 in the linked plan).
- No `.jules/*.md` write path exists yet; see
  [`jules-memory-entry-contract.md`](jules-memory-entry-contract.md) for the
  memory entry shape that a future U4/U5 writer must produce, and U7 for the
  ADR, CODEOWNERS, and write-surface matrix rows required before any write
  is authorized.
