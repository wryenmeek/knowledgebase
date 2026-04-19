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

| Artifact family | Path pattern | Schema owner | Mutability | Lock requirement |
|---|---|---|---|---|
| Report artifacts | `wiki/reports/<type>-<YYYY-MM-DD>[‑n].json` | `schema/report-artifact-contract.md` | Write-once per run; no mutation of existing files | ADR-005 + `wiki/.kb_write.lock` before every write |

Path rules for `wiki/reports/**`:
1. Only approval-gated scripts with an explicit narrower AGENTS.md row may
   write here.
2. Each write produces a new timestamped file; existing files are never
   overwritten.
3. No topical wiki page may be placed under `wiki/reports/`.

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
