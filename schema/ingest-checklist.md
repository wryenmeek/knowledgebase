# Ingest Checklist

Deterministic preflight checklist for ingest operations.

- [ ] Rejection registry check: compute `sha256` of candidate source bytes and
      check `raw/rejected/` for a record with matching checksum. Three-way
      branch per ADR-013 §9:
      - **No match:** proceed to next checklist item.
      - **Match found, `reconsidered_date` is null:** surface the prior rejection
        to the operator. Re-submission requires the `reconsider-rejected-source`
        workflow.
      - **Match found, `reconsidered_date` is set:** source was previously
        reconsidered and rejected again. Surface both dates and require explicit
        operator justification with new evidence to proceed.
- [ ] Input path is under `raw/inbox/` and inside repository boundaries.
- [ ] Source checksum (`sha256`) is computed and recorded.
- [ ] Canonical SourceRef can be formed with required anchor and checksum, and
      authoritative mode rejects placeholder/sentinel git SHAs, rejects
      symlinked/redirected authoritative artifacts, preserves the raw-zone
      boundary after resolution, resolves `git_sha` to a real git revision,
      confirms the cited path exists in that revision, and verifies recomputed
      artifact bytes from that revision.
- [ ] Provisional ingest-time SourceRefs are not treated as authoritative until a
      later commit-bound reconciliation step can replace placeholder git SHAs.
- [ ] Machine-readable ingest outputs carry a structured provisional provenance marker
      (for example `status: provisional` and `authoritative: false`) whenever
      placeholder git SHAs are emitted before commit-bound reconciliation.
- [ ] Artifact destination under `raw/processed/` is immutable and collision-safe.
- [ ] Ingest write/rollback targets fail closed on symlinked paths before any
      page, index, or log mutation.
- [ ] Target page namespace, slug, and any `browse_path` satisfy [`taxonomy-contract.md`](taxonomy-contract.md).
- [ ] Canonical title, aliases, and merge/split decision satisfy [`ontology-entity-contract.md`](ontology-entity-contract.md).
- [ ] Required frontmatter and any optional extension fields satisfy [`metadata-schema-contract.md`](metadata-schema-contract.md).
- [ ] Locking requirements are satisfied before any write-capable action.
- [ ] `wiki/log.md` update is gated by `log_only_state_changes`.
- [ ] `wiki/index.md` remains deterministic after updates.
