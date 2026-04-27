# ADR-008: Authorize agent write paths for `.github/skills/**` and `docs/**`

## Status
Accepted

## Date
2026-04-19

## Context

Phase 3 of the framework gap closure plan includes two apply-mode scripts:

- `scripts/context/fill_context_pages.py apply` — fills placeholder markers in
  `.github/skills/**` and `docs/**` context pages.
- `scripts/maintenance/generate_docs.py apply` — generates automated documentation
  fragments and writes them to `docs/**`.

Both scripts require write access to paths outside the `wiki/` directory, which
is the primary governed write zone declared in ADR-005 and ADR-007. Without an
explicit authorization record, the repository's deny-by-default write policy would
prohibit these write paths at the AGENTS.md enforcement layer.

The maintainer decision recorded on 2026-04-18 (Cluster A) confirmed:

- Agents may write to `.github/skills/**` and `docs/**` via declared scripts.
- CI-3 stays wiki- and `raw/processed/**`-focused; G1b/G1c are placed in a
  separate `ci-4-framework-writer.yml` workflow scoped to repo documentation and
  Copilot customizations.
- `schema/**` is excluded from the apply write allowlist — schema files are
  authoritative contracts; auto-fill is inappropriate.
- `fill_context_pages.py apply` may still read-scan `schema/**` to detect
  accidental placeholder markers, but writes are restricted to `.github/skills/**`
  and `docs/**` (excluding `docs/staged/**`).

## Decision

Grant the following narrower write authorizations under the deny-by-default policy:

### `fill_context_pages.py apply`

- **Writable paths:** `.github/skills/**/*.md` (placeholder fill only),
  `docs/**/*.md` (context pages only).
- **Explicitly excluded write paths:** `docs/staged/**` (staged manifests are
  inputs, not outputs), `schema/**` (authoritative contracts).
- **Read-only paths (scan only):** `.github/skills/**`, `docs/**`, `schema/**`.
- **Lock requirement:** `wiki/.kb_write.lock` acquired via the shared
  `exclusive_write_lock` utility before every write batch.
- **Approval gate:** `--approval approved` required; absent approval returns
  `approval_required_result` without mutating any files.
- **Hard-fail conditions:** out-of-scope write path, missing or stale lock,
  write-on-failure, staged-fill source outside `docs/staged/**`.

### `generate_docs.py apply`

- **Writable paths:** `docs/**/*.md` (generated documentation fragments only).
- **Read-only paths (inputs):** `.github/skills/**`, `docs/**`, `schema/**`,
  `scripts/**`.
- **Lock requirement:** `wiki/.kb_write.lock` via `exclusive_write_lock`.
- **Approval gate:** `--approval approved` required.
- **Hard-fail conditions:** out-of-scope write path (e.g. anything outside
  `docs/**`), missing lock, write-on-failure.

### CI placement

Both apply modes belong in a new `ci-4-framework-writer.yml` workflow. CI-3
(`ci-3-pr-producer.yml`) remains scoped to `wiki/**` and `raw/processed/**`
only and must not invoke these scripts.

## Alternatives considered

### Allow writes directly in CI-3

- **Rejected:** CI-3 is the wiki governance pipeline; mixing framework-writer
  mutations into it would blur the permission boundary and require CI-3 to hold
  write access to `.github/skills/**`.

### No explicit write authorization (rely on family-level row)

- **Rejected:** The `scripts/context/**` and `scripts/maintenance/**` family rows
  in AGENTS.md are `blocking-only` with no declared direct writable paths. Each
  distinct executable surface requires its own narrower row per matrix rules.

### Allow `schema/**` writes in `fill_context_pages.py apply`

- **Rejected:** Schema files are authoritative contracts. Auto-fill can silently
  corrupt field definitions. Read-scan is sufficient to surface placeholder markers
  as warnings without creating an accidental write path.

## Consequences

- `fill_context_pages.py apply` and `generate_docs.py apply` are now declared
  write surfaces with explicit per-script AGENTS.md rows.
- Both scripts enforce `wiki/.kb_write.lock` before every write — same concurrency
  model as wiki write surfaces.
- `schema/**` remains a read-only surface for automation; changes require explicit
  maintainer authorship.
- Future scripts that need write access to `.github/skills/**` or `docs/**`
  must add their own narrower AGENTS.md row before the write gate is lifted.

## References

- `AGENTS.md` (write-surface matrix rows for `fill_context_pages.py` and
  `generate_docs.py`)
- `ADR-005-write-concurrency-guards.md`
- `ADR-007-control-plane-layering-and-packaging.md`
- `scripts/context/fill_context_pages.py`
- `scripts/maintenance/generate_docs.py`
