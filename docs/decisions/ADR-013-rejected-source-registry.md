# ADR-013: Rejected-source registry

## Status
Accepted

## Date
2026-04-25

## Context

The knowledgebase ingest pipeline (`raw/inbox/` → `raw/processed/`) currently has no
memory of rejected sources. When a source fails intake validation — provenance missing,
format unsupported, quality insufficient, etc. — no record is persisted. The rejection
signal is ephemeral: it exists only in the agent conversation or CI log that produced it.

This means the same source can be re-submitted and re-evaluated repeatedly with no
organizational memory. Operators cannot tell whether a source was already evaluated and
rejected, why it was rejected, or who reviewed it.

ADR-006 defines the authoritative source boundary but says nothing about rejected
material. The boundary governs what enters `raw/processed/`; material that fails to cross
that boundary simply disappears.

`source-intake-steward` (`.github/agents/source-intake-steward.md`) guards the trust
boundary but currently produces only ephemeral rejection signals — no durable artifact is
written when a source is turned away.

`validate-inbox-source` (`.github/skills/validate-inbox-source/SKILL.md`) performs intake
validation but has no prerequisite check against prior rejections. A source that was
rejected last week can arrive in `raw/inbox/` again and consume the full validation
pipeline without anyone realizing it was already evaluated.

## Alternatives Considered

### Append rejection events to `wiki/log.md`

Use the existing append-only log to record rejections as log entries rather than
standalone files. Rejected because log entries are not individually addressable by
sha256 — deduplication would require scanning the entire log on every intake, and the
log's append-only contract is designed for state-change records, not queryable metadata.

### Path-based identity (filename as key)

Identify rejections by the original `raw/inbox/` filename instead of sha256. Rejected
because a renamed file with identical content would bypass the duplicate check. sha256
is content-addressed and rename-proof.

### Structured database (SQLite or JSON index)

Store rejections in a structured store rather than individual markdown files. Rejected
because the repository's existing artifact model uses governed markdown files with
frontmatter (consistent with `raw/processed/`, `wiki/`). A database would introduce a
new storage paradigm and require separate backup/audit tooling.

## Decision

Introduce a governed, write-once rejection registry so the knowledgebase retains durable
memory of every source that was evaluated and found unsuitable.

### 1. New governed zone: `raw/rejected/`

Create `raw/rejected/` as a governed write-once zone for source rejection records.
Rejection records are metadata-only markdown files; source bytes are not copied into this
directory.

### 2. Canonical identity key

The canonical identity key for a rejected source is the `sha256` checksum of the rejected
source's bytes — not the file path. This prevents bypass via rename: a source with the
same content but a different filename is recognized as a duplicate rejection.

Dedupe is by sha256 only.

### 3. Filename scheme

Rejection records follow the naming convention:

```
<slugified-source-name>--<sha256-prefix-8>.rejection.md
```

For example: `cms-manual-chapter-4--a1b2c3d4.rejection.md`.

The 8-character sha256 prefix provides human-readable uniqueness in directory listings
while the full sha256 in frontmatter is the authoritative identity.

### 4. Allowed writers

Only the `log-intake-rejection` skill surface (a new skill with a `logic/` directory and
a corresponding write-surface matrix entry in `AGENTS.md`) may write to `raw/rejected/`.
No other surface, script, or agent is permitted to create or modify rejection records.

### 5. Lock

`raw/.rejection-registry.lock` — a separate lock from `wiki/.kb_write.lock` because
rejection writes do not touch wiki paths.

No ordering relationship with `wiki/.kb_write.lock` is required. Unlike ADR-012, which
needs ordered dual-lock acquisition for CI-5, the rejection registry operates on a fully
independent path family. The lock uses the same `fcntl`-based advisory lock pattern as
`wiki/.kb_write.lock`.

### 6. Rejection record format

Frontmatter:

```yaml
---
slug: <slugified-source-name>
sha256: <64-hex-chars>
rejected_date: <ISO-8601>
source_path: raw/inbox/<original-filename>
rejection_reason: <brief human-readable description>
rejection_category: provenance_missing | format_unsupported | duplicate | out_of_scope | quality_insufficient
reviewed_by: <operator-or-agent-identifier>
reconsidered_date: null
---
```

Body sections:

```markdown
## What was attempted

<description of the source and what ingest step was attempted>

## What was missing

<specific deficiency that caused rejection>

## Notes

<optional additional context, links, or operator commentary>
```

### 7. Un-reject (reconsideration) workflow

An operator invokes the `reconsider-rejected-source` skill, which:

1. Appends `reconsidered_date: <ISO-8601>` to the existing rejection record's frontmatter
   (replacing the `null` value).
2. Moves the source back to `raw/inbox/` for full re-evaluation through the standard
   intake pipeline.

The original rejection record is **never deleted** — it is immutable except for the
`reconsidered_date` field. This preserves the full audit trail: the record shows when the
source was originally rejected, why, and when it was reconsidered.

If the source fails intake validation again after reconsideration, the outcome depends on
whether the source bytes have changed:

- **Same bytes (same sha256):** The existing rejection record still matches by sha256.
  The writer fails closed — no second record is created. The `reconsidered_date` on the
  original record serves as the audit trail that reconsideration was attempted and the
  source was found unsuitable again.
- **Different bytes (different sha256):** A new rejection record is created with the new
  sha256. The original record remains unchanged.

### 8. Lifecycle

Rejection records are immutable after creation (except for the `reconsidered_date` field
added during reconsideration). There is no automatic cleanup or expiration. Archive or
deletion of rejection records requires explicit Human Steward sign-off.

### 9. Ingest checklist integration

`schema/ingest-checklist.md` must add a rejection registry check as a prerequisite step:

1. Compute sha256 of the candidate source's bytes.
2. Check `raw/rejected/` for any file whose frontmatter `sha256` field matches.
3. If a matching rejection record exists and `reconsidered_date` is `null`, halt intake
   and surface the prior rejection reason to the operator.
4. If a matching rejection record exists and `reconsidered_date` is non-null, the source
   was previously reconsidered. It may have been re-rejected after reconsideration.
   Surface both dates and require explicit operator justification with significant new
   evidence before proceeding.
5. If no matching rejection record exists, proceed with intake normally.

### 10. Contracts integration

`scripts/kb/contracts.py` `WRITE_ALLOWLIST_PATHS` must include `raw/rejected/` so that
the `log-intake-rejection` surface can write rejection records without triggering
boundary violations.

### 11. Repository boundary recognition

`enforce-repository-boundaries` (`.github/skills/enforce-repository-boundaries/`) must
recognize `raw/rejected/` as an allowlisted write zone, gated to the
`log-intake-rejection` surface only.

## Consequences

### Positive

- Persistent organizational memory of rejected sources prevents re-evaluation churn.
- Operators can see why a source was rejected, when, and by whom.
- The reconsideration workflow preserves a full audit trail — no rejection history is lost.
- sha256-based identity prevents bypass via rename or path manipulation.
- Separate lock avoids contention with wiki writes.

### Negative

- Storage grows monotonically: rejection records are never automatically cleaned up.
  For the expected volume of rejected sources this is acceptable, but long-term growth
  should be monitored.
- Operators must learn the reconsideration workflow for legitimate re-submissions rather
  than simply re-dropping a file into `raw/inbox/`.

### Neutral

- Rejection records are metadata-only — source bytes stay in (or are removed from)
  `raw/inbox/` independently. The registry does not change how source bytes are stored.
- The happy-path ingest flow (`raw/inbox/` → `raw/processed/`) is unchanged. The only
  addition is a sha256 prerequisite check at the start of intake.
- Two new skill surfaces (`log-intake-rejection`, `reconsider-rejected-source`) must be
  declared in the `AGENTS.md` write-surface matrix before they can write.

## References

- `ADR-006-authoritative-source-boundary.md`
- `schema/ingest-checklist.md`
- `AGENTS.md` (write-surface matrix)
- `scripts/kb/contracts.py` (`WRITE_ALLOWLIST_PATHS`)
- `.github/agents/source-intake-steward.md`
- `.github/skills/validate-inbox-source/SKILL.md`
- `.github/skills/enforce-repository-boundaries/SKILL.md`
