---
name: write-sourceref-citations
description: Writes canonical SourceRef citations from committed repository artifacts. Use when a deterministic helper needs an authoritative provenance string for a raw artifact.
---

# Write SourceRef Citations

## Overview

Use this skill to build canonical `repo://...` SourceRef citations from committed repository artifacts. The helper resolves a real git revision, reads bytes from that revision, computes the checksum, and validates the final citation in authoritative mode.

## When to Use

- When a draft wiki page needs a canonical SourceRef for `raw/processed/**` or `raw/assets/**`
- When reconciling provisional provenance into a commit-bound citation
- When deterministic tooling must emit a validated SourceRef string instead of hand-formatting one

## Contract

- Input: repo-relative raw artifact path, anchor, and git ref
- Path scope is limited to `raw/inbox/**`, `raw/processed/**`, and `raw/assets/**`
- Output: a canonical SourceRef plus resolved commit SHA and checksum
- Validation runs in authoritative mode before success is returned

## Assertions

- Rejects paths outside the raw artifact allowlist
- Fails closed if the git ref does not resolve to a real commit containing the artifact
- Computes checksum from revision bytes, not the working tree
- Uses no shell, no `eval`, and no dynamic dispatch

## Commands

```bash
python3 .github/skills/write-sourceref-citations/logic/write_sourceref_citations.py --path raw/processed/source.md --anchor asset --git-ref HEAD
```

## References

- `AGENTS.md`
- `docs/architecture.md`
- `schema/metadata-schema-contract.md`
- `schema/ingest-checklist.md`
- `scripts/kb/sourceref.py`
