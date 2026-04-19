# ADR-010: ADR-006 compliance review for `convert_sources_to_md.py apply`

## Status
Accepted

## Date
2026-04-19

## Context

`scripts/ingest/convert_sources_to_md.py` exposes an `apply` mode that converts
repository-local source files to Markdown and writes the output to
`raw/processed/**`. Before the `write_surface_not_declared_result` gate can be
lifted (G1f), this mode must be verified against ADR-006, which restricts
authoritative ingestion to:

- repository-local sources under `raw/inbox/**`, and
- checksummed external assets vendored under `raw/assets/**`.

This ADR records the outcome of that compliance review and documents the
constraints required for G1f to proceed.

## Review findings

### Input boundary

The script's `ALLOWED_SOURCE_ROOTS` constant currently includes both
`raw/inbox` and `raw/assets`. This is correct for `inspect` and `preview`
modes, which are read-only operations that may enumerate any ADR-006-compliant
source path.

For `apply` mode, however, the effective conversion scope must be restricted
to `raw/inbox/**` only. Assets in `raw/assets/**` are vendored binary artifacts
(checksummed at ingest time) that are not subject to text-conversion workflows.
Allowing `raw/assets/**` as a write-mode source would risk re-processing an
already-immutable artifact.

**Required constraint:** The apply mode must reject any path that does not
resolve under `raw/inbox/**`. Paths in `raw/assets/**` remain valid input for
`inspect` and `preview` only.

### Output boundary

Apply mode must write converted Markdown output exclusively to `raw/processed/**`.
This is an ADR-006-compliant authoritative ingest output path. Files written here
are immutable post-write: subsequent apply runs must not overwrite existing
processed artifacts.

**Required constraint:** If a `raw/processed/<slug>.md` file already exists for
the given input path, the apply run must fail closed with an explicit error rather
than silently overwriting.

### Checksum recording

ADR-006 requires that authoritative inputs have verifiable provenance. For
`raw/inbox/**` sources, provenance is established at ingest time by recording a
SHA-256 checksum. The apply mode must record the checksum of each converted source
file as part of the output metadata.

**Required constraint:** The apply mode must write a companion `raw/processed/<slug>.meta.json`
file alongside each converted Markdown file. This metadata file records:
- `source_path`: repo-relative path of the original `raw/inbox/**` source.
- `source_sha256`: hex-encoded SHA-256 of the source file bytes at conversion time.
- `converted_at`: ISO 8601 UTC timestamp.
- `surface`: the script surface identifier (`scripts/ingest/convert_sources_to_md.py`).

### Fail-closed conditions

The apply mode must fail closed (non-zero exit, `STATUS_FAIL` result) when:

1. Any supplied path does not resolve under `raw/inbox/**`.
2. The target `raw/processed/<slug>.md` or `raw/processed/<slug>.meta.json`
   already exists (immutability enforcement).
3. `wiki/.kb_write.lock` cannot be acquired.
4. Approval is absent (`--approval approved` not provided).
5. Source type is not supported for deterministic conversion (`.html`, `.txt`,
   `.md`; PDF and other formats are not supported without an external converter).

## Decision

`convert_sources_to_md.py apply` is ADR-006-compliant subject to the constraints
enumerated above being implemented in G1f. The `write_surface_not_declared_result`
gate may be lifted once:

1. The apply mode input boundary is restricted to `raw/inbox/**`.
2. The immutability guard (fail on existing output) is implemented.
3. Checksum metadata is written alongside each converted file.
4. An AGENTS.md narrower row for `scripts/ingest/convert_sources_to_md.py` is
   added before the gate is removed.

## Consequences

- G1f implementation is unblocked, subject to the listed constraints.
- `inspect` and `preview` modes retain their current `ALLOWED_SOURCE_ROOTS`
  (including `raw/assets`) — no change needed for read-only modes.
- `raw/processed/**` remains immutable post-write; no script other than the
  ingest surface may overwrite processed artifacts.
- Checksum metadata is co-located with processed artifacts for auditable provenance.

## References

- `ADR-006-authoritative-source-boundary.md`
- `ADR-005-write-concurrency-guards.md`
- `scripts/ingest/convert_sources_to_md.py`
- `AGENTS.md` (narrower row for `scripts/ingest/convert_sources_to_md.py` — to be
  added in G1f)
- `raw/processed/SPEC.md`
