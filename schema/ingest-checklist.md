# Ingest Checklist

Deterministic preflight checklist for ingest operations.

- [ ] Input path is under `raw/inbox/` and inside repository boundaries.
- [ ] Source checksum (`sha256`) is computed and recorded.
- [ ] Canonical SourceRef can be formed with required anchor and checksum.
- [ ] Artifact destination under `raw/processed/` is immutable and collision-safe.
- [ ] Locking requirements are satisfied before any write-capable action.
- [ ] `wiki/log.md` update is gated by `log_only_state_changes`.
- [ ] `wiki/index.md` remains deterministic after updates.
