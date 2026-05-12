# Governed Artifact Contract

This document is the authoritative contract for repo-local state artifacts that
are not topical wiki pages. It defines reserved paths, schema ownership,
mutation rules, and write expectations that future state-sync or maintenance
automation must satisfy before writing durable state.

## Scope and authority

- Applies to governed process artifacts under `wiki/`.
- Complements [`taxonomy-contract.md`](taxonomy-contract.md) for process-page
  placement and [`metadata-schema-contract.md`](metadata-schema-contract.md) for
  page/frontmatter semantics where a governed artifact also carries Markdown
  structure.
- Declaring a path here does **not** by itself grant write permission. Writers
  remain deny-by-default until a narrower script/workflow contract explicitly
  names the artifact and preserves existing allowlists and ADR-005 lock rules.

## Reserved governed artifact matrix

| Artifact ID | Path | Schema owner | Purpose | Mutation semantics | Lock requirement | Atomic write expectation |
|---|---|---|---|---|---|---|
| `wiki-index` | `wiki/index.md` | `schema/taxonomy-contract.md` | Deterministic discovery/catalog artifact for the curated wiki tree. | Mutable snapshot; writers replace the whole file from regenerated content. | ADR-005 workflow concurrency plus `wiki/.kb_write.lock` before any write-capable automation mutation. | Stage complete replacement content in-repo and publish via atomic same-directory replace where the platform supports it. |
| `wiki-log` | `wiki/log.md` | `schema/governed-artifact-contract.md` | Append-only audit trail for real state changes. | Append-only; existing entries are never edited or deleted in place. | ADR-005 workflow concurrency plus `wiki/.kb_write.lock`; append occurs only when a state change happened. | Append one normalized entry under the lock; never rewrite prior log history as part of ordinary sync. |
| `wiki-open-questions` | `wiki/open-questions.md` | `schema/governed-artifact-contract.md` | Repository-wide ledger of unresolved contradictions, arbitration needs, and follow-up questions that exceed page-local `open_questions`. | Mutable ledger; writers may add, resolve, reorder, or supersede tracked items deterministically. | ADR-005 workflow concurrency plus `wiki/.kb_write.lock` before any mutation. | Write a complete next-state file and publish via atomic same-directory replace. |
| `wiki-backlog` | `wiki/backlog.md` | `schema/governed-artifact-contract.md` | Governed backlog of approved maintenance or curation follow-up items. | Mutable ledger; status and priority may change as work advances. | ADR-005 workflow concurrency plus `wiki/.kb_write.lock` before any mutation. | Write a complete next-state file and publish via atomic same-directory replace. |
| `wiki-status` | `wiki/status.md` | `schema/governed-artifact-contract.md` | Governed status snapshot summarizing the last successful sync/maintenance state. | Mutable snapshot; each run may replace stale status with the newest approved state. | ADR-005 workflow concurrency plus `wiki/.kb_write.lock` before any mutation. | Write a complete next-state file and publish via atomic same-directory replace. |

## Pattern-based report artifacts

`wiki/reports/` is a governed output directory for approval-gated reporting
surfaces. Unlike the fixed-path artifacts above, report artifacts are
dynamically named per run. Their schema and write semantics are declared in
[`schema/report-artifact-contract.md`](report-artifact-contract.md).

## GitHub source monitoring artifacts

`raw/github-sources/` and `raw/assets/` are governed by the GitHub source
monitoring pipeline introduced in ADR-012. Unlike the `wiki/` artifacts above,
these use dynamic path names and require glob-pattern matching via
`governed_artifact_contract_by_pattern()` in `scripts/kb/contracts.py`.

| Artifact ID | Path pattern | Schema owner | Purpose | Mutation semantics | Lock requirement | Atomic write expectation |
|---|---|---|---|---|---|---|
| `github-source-registry` | `raw/github-sources/*.source-registry.json` | `schema/github-source-registry-contract.md` | Per-repo registry of tracked file paths with three-stage state machine (applied / fetched / checked). | Mutable; writers update entry fields and replace the full file. | `raw/.github-sources.lock` (separate from `wiki/.kb_write.lock`; see lock ordering in ADR-012). | Read full JSON under lock → mutate entry → atomic replace → release lock. |
| `external-asset` | `raw/assets/**` | `docs/decisions/ADR-012-github-source-monitoring.md` | Immutable vendored copy of an external file at a specific commit SHA. Path encodes `{owner}/{repo}/{commit_sha}/{file_path}`. | Write-once (`exclusive_create_write_once()`); idempotent if bytes match; hard fail if bytes differ. | None (path includes commit SHA; no inter-run race possible). | `O_CREAT \| O_EXCL` open; SHA-256 verified before and after write. |

| Artifact family | Path pattern | Schema owner | Mutability | Lock requirement |
|---|---|---|---|---|
| Report artifacts | `wiki/reports/<type>-<YYYY-MM-DD>[‑n].json` | `schema/report-artifact-contract.md` | Write-once per run; no mutation of existing files | ADR-005 + `wiki/.kb_write.lock` before every write |

Path rules for `wiki/reports/**`:
1. Only approval-gated scripts with an explicit narrower AGENTS.md row may
   write here.
2. Each write produces a new timestamped file; existing files are never
   overwritten.
3. No topical wiki page may be placed under `wiki/reports/`.

## Rejection registry artifacts

`raw/rejected/` stores write-once rejection records governed by ADR-013. Unlike
`wiki/` artifacts, these are metadata-only records keyed by sha256 identity.

| Artifact ID | Path pattern | Schema owner | Purpose | Mutation semantics | Lock requirement | Atomic write expectation |
|---|---|---|---|---|---|---|
| `rejection-record` | `raw/rejected/*.rejection.md` | `schema/rejection-registry-contract.md` | Write-once metadata record for rejected intake sources. | Write-once (`exclusive_create_write_once`); immutable post-write except `reconsidered_date` (manual operator update under lock). | `raw/.rejection-registry.lock` (separate from `wiki/.kb_write.lock`; sequential acquisition, never held simultaneously). | `O_CREAT \| O_EXCL`; sha256 dedupe before write. |

## Path ownership rules

1. Reserved governed artifacts live at fixed root-level `wiki/*.md` paths in MVP.
2. Pattern-based report artifacts live under `wiki/reports/` with per-run
   timestamped filenames; see the section above.
3. No other writer may repurpose these paths for topical content.
4. New governed state targets must add a row here before any automation writes
   them; undeclared targets remain deny-by-default even if they live under
   `wiki/**`.

## Mutation and lock rules

1. `wiki/log.md` is the only append-only governed artifact in the current set.
2. `wiki/index.md`, `wiki/open-questions.md`, `wiki/backlog.md`, and
   `wiki/status.md` are mutable snapshot/ledger artifacts and must be rewritten
   as a whole, not patched opportunistically without reconciliation.
3. Every write-capable mutation of a governed artifact must honor ADR-005:
   workflow-level concurrency plus `wiki/.kb_write.lock`.
4. Lock failures fail closed; no governed artifact may partially update outside
   the lock window.

## Extension rule for future artifacts

- Future governed artifacts must declare:
  - fixed repo-relative path,
  - schema owner under `schema/**`,
  - append-only vs mutable semantics,
  - lock requirement,
  - and append vs atomic-replace expectation.
- Until that declaration lands, future state-sync work may read candidate
  artifacts but must not write them.

## Doc-only skills with write-adjacent effects

Some skills define operator-mediated workflows that result in governed
artifact mutation but have no runtime-executable logic (`logic/` directory).
These skills are exempt from the AGENTS.md write-surface matrix because there
is no surface to declare. Governance is enforced by the schema contract's
"Authorized updater" column and by the operator following the skill's
documented procedure under lock.

Example: `reconsider-rejected-source` guides an operator through setting
`reconsidered_date` in a rejection record's frontmatter. The mutation is
governed by `schema/rejection-registry-contract.md` (authorized updater:
"operator via reconsider-rejected-source, manual under lock"), not by a
matrix row. See ADR-013 Consequences for rationale.
