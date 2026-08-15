# Jules Memory Entry Contract

**Schema version:** 1
**Produced by:** `scripts/fleet/pr-learning/memory-validator.ts`, `scripts/fleet/pr-learning/propose.ts` (U4/U5)
**Consumed by:** `.jules/bolt.md`, `.jules/sentinel.md` (governed target files, authorized by U7)
**Governed by:** `docs/plans/2026-08-10-001-feat-jules-persona-learning-loop-plan.md` (U1), `docs/decisions/ADR-037-jules-persona-memory-learning.md` (U7)

---

## Purpose

This contract defines the bounded, structured shape of a single memory
entry that the learning loop (U3–U5) may propose for append to
`.jules/bolt.md` or `.jules/sentinel.md`, plus the proposal marker used to
make branch/PR creation idempotent (R8, R11). It also defines the size
limits and redaction boundary that keep generated entries free of raw PR
text, secrets, private session content, exploit payloads, or unsupported
quantitative claims (R9).

This contract does not itself grant write permission to `.jules/*.md`.
U7 (`docs/decisions/ADR-037-jules-persona-memory-learning.md`) is what
authorizes those two files as a governed write surface — an `AGENTS.md`
write-surface matrix row, `.github/CODEOWNERS` entries, and a `CONTEXT.md`
sensitive-paths glossary entry now exist for
`scripts/fleet/pr-learning/propose.ts`. There is deliberately no local
file-lock protocol for this surface: per ADR-037, ADR-005-style local locks
cannot coordinate independent GitHub Actions runners, so coordination is
instead a workflow `concurrency.group` plus GitHub-visible proposal-marker
lookup and live base-tree/blob-SHA revalidation immediately before every
mutation.

---

## Writable target allowlist (R10)

Exactly two paths may ever be modified by this pipeline, and never any
other path in the same proposal:

- `.jules/bolt.md`
- `.jules/sentinel.md`

A proposal touching any other path, or touching more than one of the two
files, or performing an add/delete/rename/copy/mode-change/symlink/
submodule operation instead of a content-preserving append, is rejected in
full — the entire proposal fails, not just the offending file.

---

## Memory entry shape

Each proposed entry is a `MemoryEntry` object with the following required
fields:

| Field | Type | Required | Description |
|---|---|---|---|
| `entry_id` | string | ✅ | Stable, unique identifier for this entry (derived from `candidate_fingerprint`, e.g. first 12 hex chars). Used to detect duplicate append attempts. |
| `persona` | `"bolt" \| "sentinel"` | ✅ | Which memory file this entry targets (`bolt` → `.jules/bolt.md`, `sentinel` → `.jules/sentinel.md`). |
| `rule` | string | ✅ | The bounded, actionable lesson or prevention rule. Plain prose; no raw PR diff/body text. |
| `evidence` | string[] | ✅ | 1–3 bounded evidence references (e.g., `"PR #123 (merged)"`, `"PR #456, #789 (closed: test_or_policy_failure)"`). References PR numbers and outcome only — never quotes PR body/comment text verbatim. Proposal tooling derives these references from the independently verified evidence envelopes rather than trusting free-form operator text. |
| `verification` | string | ✅ | How the rule was verified (e.g., "reproducible benchmark", "two independent closures with matching root cause"). |
| `scope` | string | ✅ | The bounded area the rule applies to (e.g., a module path or mechanism name). Must not be the literal string `"*"` or otherwise unbounded. |
| `retraction_condition` | string | ✅ | The condition under which this entry should be revisited or retracted (e.g., "if the referenced function signature changes"). |
| `candidate_fingerprint` | string (64-char hex) | ✅ | The fingerprint from `jules-pr-learning-contract.md` that produced this entry. |
| `memory_blob_sha` | string (40-char hex) | ✅ | The blob SHA of the target `.jules/*.md` file at generation time, used for stale-snapshot detection (see below). |
| `generated_at` | string (ISO-8601 UTC) | ✅ | Timestamp the entry was generated. |

### Size limits

| Field | Limit |
|---|---|
| `rule` | ≤ 500 characters |
| Each `evidence` string | ≤ 200 characters |
| `evidence` array | ≤ 3 items |
| `verification` | ≤ 300 characters |
| `scope` | ≤ 200 characters |
| `retraction_condition` | ≤ 300 characters |
| Rendered Markdown block (all fields combined) | ≤ 2,000 characters |

An entry exceeding any limit is rejected before any write attempt — the
generator must truncate or re-summarize upstream of this contract; the
validator does not silently truncate.

### Redaction boundary

Before an entry may be validated as writable, every string field must be
scanned and rejected (not redacted-and-passed) if it contains:

- Anything matching a secret-shaped pattern: bearer tokens, PEM key
  headers/footers, GitHub tokens (`gh[pousr]_`), AWS-style access keys,
  generic `key=`/`token=`/`password=` assignment patterns, or URLs that
  embed inline basic-auth credentials before the host.
<!-- pragma: allowlist secret -->
- Shell metacharacter sequences that resemble command injection payloads
  (`` `...` ``, `$(...)`, `;rm `, pipe chains to network tools).
- GitHub Actions workflow expression syntax (`${{ ... }}`).
- Raw PR body/comment/review/log text copied verbatim beyond a short
  (≤ 80 character) quoted fragment used only for the `evidence` field.
- Any first-person imperative phrasing that reads as an instruction to an
  agent reading the memory file (defense against prompt injection smuggled
  through PR text into a generated entry) — the `rule` field must describe
  a lesson about code, never issue a directive to "ignore", "bypass",
  "disable", "skip", "override", "circumvent", "suppress", "overrule", or
  "disregard" any governance step (verb + governance-noun co-occurrence,
  e.g. "override the review gate" — see `REDACTION_PATTERNS` in
  `scripts/fleet/pr-learning/types.ts` for the enforced pattern).
- Unsupported quantitative claims: a numeric performance/quality claim
  (e.g., a percentage) is only allowed when `verification` names a
  reproducible measurement; otherwise the number must be omitted.

For example, `"This reduces latency by 50%."` with
`"Reproducible benchmark across three runs."` is allowed, while the same rule
with `"Looks right."` is rejected. Ordinary numeric prose without a
performance or quality claim is not affected.

Any match hard-fails the entire proposal (R13). This is the same
"deny-by-default, fail closed" posture applied elsewhere in the repository
(see `AGENTS.md` guardrails).

---

## Rendered Markdown shape

A validated `MemoryEntry` renders to a single Markdown block appended to
the end of the target file, following the existing heading style already
used in `.jules/bolt.md` and `.jules/sentinel.md`:

```markdown
## <persona-appropriate emoji + short title>

**Learning:** <rule>
**Evidence:** <evidence[0]>[, <evidence[1]>[, <evidence[2]>]]
**Verification:** <verification>
**Scope:** <scope>
**Retraction condition:** <retraction_condition>
<!-- entry_id: <entry_id> | fingerprint: <candidate_fingerprint> -->
```

The trailing HTML comment carries `entry_id` and `candidate_fingerprint` so
a future deduplication pass can detect an existing entry without re-parsing
prose. It must never be rendered as visible Markdown (HTML comments are
already invisible in rendered output) and must never be interpreted as an
instruction by any agent reading the file.

**Append-only / byte-preservation rule:** the writer only ever appends this
block after the existing file's final byte (with exactly one blank line of
separation before the new heading). Every byte of the existing file must be
byte-identical before and after the write. This is the same convention
`wiki/log.md` already uses for append-only governed artifacts (see
`schema/governed-artifact-contract.md`).

---

## Stale-snapshot guard (memory blob SHA)

Every `MemoryEntry` carries `memory_blob_sha`: the Git blob SHA of the
target `.jules/*.md` file at the moment the entry was generated. Before any
proposal mutation:

1. Re-fetch the current blob SHA of the target file at the proposal's
   recorded `base_sha`.
2. If the current blob SHA does not equal `memory_blob_sha`, the target has
   changed since generation. The proposal must be rejected or regenerated
   against the new blob — it must **never** overwrite the newer content or
   attempt automatic conflict resolution.

This mirrors the content-addressed stale-memory protection described in the
plan's Key Technical Decisions.

---

## Proposal marker (R8, R11)

To make branch/PR creation idempotent across concurrent runs, every
proposal carries a `ProposalMarker`:

| Field | Type | Required | Description |
|---|---|---|---|
| `repo` | string (`owner/repo`) | ✅ | Repository the proposal targets. |
| `target_memory_path` | `".jules/bolt.md" \| ".jules/sentinel.md"` | ✅ | The single file this proposal modifies. |
| `candidate_fingerprint` | string (64-char hex) | ✅ | The fingerprint from `jules-pr-learning-contract.md` driving this proposal. |
| `base_branch` | string | ✅ | The branch the proposal PR targets (must be `main` per repository convention). |
| `branch_name` | string | ✅ | Deterministic proposal branch name, derived as `jules-memory/<persona>/<fingerprint[:12]>`. |
| `producer_workflow` | string | ✅ | The workflow file name that produced this proposal (for later verification, U6). |
| `collector_commit` | string (40-char hex) | ✅ | The commit SHA of the collector run that produced the underlying evidence. |

The marker is embedded in the PR body as a bounded, structured block (not
free text) so a lookup-before-create check can find an existing open/closed
proposal for the same `candidate_fingerprint` before creating a new one.
Two concurrent runs for the same fingerprint must converge on at most one
proposal PR — this is a proposal-creation-time (U5) responsibility, but the
marker shape that makes it possible is defined here so later units share
one format.

---

## Validation

A memory entry or proposal marker failing any of the following is a hard
failure; no write is attempted:

- Target path is not exactly one of the two allowlisted files.
- Any size limit is exceeded.
- Any redaction-boundary pattern matches.
- `memory_blob_sha` does not match the live target blob at proposal time.
- `entry_id` or `candidate_fingerprint` is missing or malformed (not 64-char
  hex where hex is required).
- The rendered Markdown block would mutate any byte before the appended
  section.

---

## Governance

- The validator and writer are implemented (`memory-validator.ts`,
  `proposal-validator.ts`, `propose.ts`; U4/U5).
- `.jules/bolt.md` and `.jules/sentinel.md` are now declared as a governed
  write surface in `AGENTS.md` (`scripts/fleet/pr-learning/**` row),
  `.github/CODEOWNERS`, and `CONTEXT.md`'s sensitive-paths glossary, per
  `docs/decisions/ADR-037-jules-persona-memory-learning.md` (U7). There is
  intentionally no local lock protocol for this surface — ADR-005-style
  local file locks cannot coordinate independent GitHub Actions runners;
  coordination is the workflow `concurrency.group` plus GitHub-visible
  proposal-marker lookup and live base-tree/blob-SHA revalidation described
  in ADR-037.
