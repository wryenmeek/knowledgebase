# ADR-020: Criteria for approving post-MVP script package families

## Status
Accepted

## Date
2026-04-27

## Context

ADR-007 established the MVP packaging boundary: authoritative Python execution
lives in `scripts/kb/**`; everything else (agents, skills, skill-local logic)
is scaffolding. ADR-007's historical note (amended 2026-04-16) approved five
post-MVP package families — `scripts/validation/**`, `scripts/reporting/**`,
`scripts/context/**`, `scripts/maintenance/**`, and `scripts/ingest/**` — but
did not state the criteria that justified that approval or that govern future
package family additions.

Without explicit criteria:
- It is unclear when a new collection of scripts warrants its own package
  family vs. an extension to an existing one.
- The write-surface matrix in `AGENTS.md` cannot reliably distinguish a
  well-scoped new package from scope creep.
- Agents and developers lack a deterministic test for whether a proposed new
  package family requires ADR-level approval.

`scripts/github_monitor/**` was added after ADR-007's amendment (via ADR-012)
and represents a sixth package family. Documenting the approval criteria
retroactively captures the judgment that was applied in each case.

## Decision

A new top-level Python script package family (a new directory under `scripts/`)
requires **ADR-level approval** and must satisfy all of the following criteria
before any code is committed:

### Approval criteria

1. **Single coherent domain** — all scripts in the family share a well-defined
   functional scope. The scope must be stated in one sentence. If the scope
   requires "and" to describe, it is probably two families.

2. **Cannot live in `scripts/kb/**`** — the work is not a deterministic
   knowledgebase operation (ingest, index, lint, persist, preflight). If it
   could reasonably be a new module in `scripts/kb/`, it should be.

3. **Write-surface matrix row exists before first commit** — every executable
   surface in the new family must have a row in `AGENTS.md`'s write-surface
   matrix at the time of the PR that introduces the directory. Undeclared
   families are hard-rejected by CI.

4. **Tests exist before reliance** — the family must have at least one test
   file under `tests/kb/**` covering its CLI contract, fail-closed behavior,
   and allowlist enforcement before any downstream persona or skill can invoke
   it as an authoritative surface.

5. **ADR captures rationale** — the ADR must state: what the family does,
   why it cannot live in `scripts/kb/**`, what the write boundaries are,
   and which CI workflow owns it.

### Approved package families (as of 2026-04-27)

| Family | Domain | Authorizing decision |
|---|---|---|
| `scripts/kb/**` | Core knowledgebase operations (ingest, index, lint, persist, preflight) | ADR-007 (MVP boundary) |
| `scripts/validation/**` | Shared validators and evidence/policy checks promoted from skill-local wrappers | ADR-007 historical note |
| `scripts/reporting/**` | Deterministic report generation over existing repo artifacts | ADR-007 historical note |
| `scripts/context/**` | Shared context assembly and deterministic read models used by multiple skills | ADR-007 historical note |
| `scripts/maintenance/**` | Reusable maintenance operations bounded by approved write surfaces | ADR-007 historical note |
| `scripts/ingest/**` | New reusable ingest helpers promoted from wrapper-local orchestration | ADR-007 historical note |
| `scripts/github_monitor/**` | External source drift detection, content fetch, and bounded wiki synthesis | ADR-012 |
| `scripts/fleet/**` | Jules-based parallel issue-to-PR dispatch orchestration (TypeScript/Bun) | ADR-019 |
| `scripts/hooks/**` | Pre-commit governance hook scripts (read-only, no repo writes) | ADR-016 |

### What does NOT require a new package family

- A new script that fits naturally within an existing family's domain.
- A new module (`.py` file) added to `scripts/kb/**` for a new knowledgebase
  operation.
- Skill-local logic files in `.github/skills/<skill>/logic/**` — these are
  governed by ADR-008, not this ADR.

## Alternatives Considered

### Approve new families informally (ADR-007 historical note pattern)

- **Pros:** Low ceremony; fast to ship.
- **Cons:** Criteria are implicit; future contributors cannot determine whether
  their proposed family meets the bar; the write-surface matrix drifts from
  the approved set.
- **Rejected:** The `scripts/github_monitor/**` addition demonstrated the need
  for explicit criteria — it met all five criteria but those criteria were not
  written down at the time.

### Prohibit new package families (everything in `scripts/kb/**`)

- **Pros:** Maximum coherence; single authoritative Python surface.
- **Cons:** `scripts/kb/**` would grow to include orthogonal concerns (GitHub
  monitoring, report generation, maintenance operations) that are poorly served
  by the existing module structure.
- **Rejected:** Separation of concerns outweighs consolidation for domains
  with distinct write surfaces and CI owners.

### Require a full RFC process for each family

- **Pros:** Maximum governance rigor.
- **Cons:** Overhead for a single-maintainer repository where ADRs already
  serve the decision-capture function.
- **Rejected:** ADR-level approval is sufficient given the existing CI and
  write-surface matrix enforcement.

## Consequences

- Any PR that creates a new directory directly under `scripts/` without an
  approved ADR and write-surface matrix row must be rejected.
- The write-surface matrix in `AGENTS.md` is the operational enforcement of
  this ADR — a family that has an ADR but no matrix row is still undeclared.
- Adding a script to an existing approved family does not require a new ADR,
  but does require a matrix row update if the script's write surface is new.
- This ADR does not govern `scripts/fleet/**` at the Python level (fleet is
  TypeScript/Bun); it is listed in the approved families table for
  completeness.

## References

- `docs/decisions/ADR-007-control-plane-layering-and-packaging.md` — MVP boundary and amendment
- `docs/decisions/ADR-012-github-source-monitoring.md` — approval of `scripts/github_monitor/**`
- `docs/decisions/ADR-016-pre-commit-hooks-governance.md` — approval of `scripts/hooks/**`
- `docs/decisions/ADR-019-fleet-jules-orchestration.md` — approval of `scripts/fleet/**`
- `AGENTS.md` § Write-surface matrix — operational enforcement of approved families
- `docs/ideas/spec.md` — post-MVP rollout spec with package placement rules
