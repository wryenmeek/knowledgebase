# Rejected Source Registry

This directory stores rejection records for source material that was evaluated
for knowledgebase intake and found unsuitable.

See:
- `docs/decisions/ADR-013-rejected-source-registry.md` — architectural decision
- `schema/rejection-registry-contract.md` — schema contract

## File naming convention

```
<slugified-source-name>--<sha256-prefix-8>.rejection.md
```

## Identity key

Rejection records are identified by the SHA-256 checksum of the original source
bytes (`sha256` frontmatter field), not by filename or path.

## Lifecycle

- **Write-once:** Records are immutable after creation (except `reconsidered_date`)
- **Allowed writer:** Only the `log-intake-rejection` skill surface
- **Lock:** `raw/.rejection-registry.lock`
- **Deletion:** Requires explicit Human Steward sign-off

## Monitoring

There is no automatic cleanup or expiration. The Human Steward should review
this directory when the file count exceeds 50 records and assess whether an
archive or cleanup policy is needed. Retention policy is deferred to a follow-on
ADR if growth warrants it.
