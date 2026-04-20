# knowledgebase

Self-contained, self-organizing knowledgebase with deterministic ingest, indexing,
linting, query, and policy-gated persistence workflows.

## Quick start

```bash
# 1) ingest one source from inbox
python3 scripts/kb/ingest.py --source raw/inbox/<source-file>.md --wiki-root wiki --schema AGENTS.md

# 2) rebuild index
python3 scripts/kb/update_index.py --wiki-root wiki --write

# 3) run strict lint
python3 scripts/kb/lint_wiki.py --wiki-root wiki --strict

# 4) run tests
python3 -m unittest discover -s tests -p "test_*.py"
```

For full operational flow (including qmd and query-persist behavior), see
[`docs/mvp-runbook.md`](docs/mvp-runbook.md).

## Commands

| Command | Description |
|---|---|
| `python3 scripts/kb/ingest.py --source ...` | Ingest one inbox source into wiki artifacts. |
| `python3 scripts/kb/ingest.py --sources-manifest ... --batch-policy continue_and_report_per_source --report-json` | Batch ingest with deterministic partial-success semantics. |
| `python3 scripts/kb/update_index.py --wiki-root wiki --write` | Rebuild deterministic `wiki/index.md`. |
| `python3 scripts/kb/lint_wiki.py --wiki-root wiki --strict` | Run read-only strict wiki validation. |
| `python3 .github/skills/validate-wiki-governance/logic/validate_wiki_governance.py` | Run the fixed framework governance gate over qmd preflight, index, and authoritative commit-bound SourceRef linting (add `--validator freshness-threshold` to opt in to page-age checking). |
| `python3 .github/skills/suggest-backlinks/logic/suggest_backlinks.py <page> [--wiki-root wiki]` | Suggest backlink opportunities for a wiki page; returns JSON `BacklinkProposal` list; read-only. |
| `python3 .github/skills/sync-knowledgebase-state/logic/sync_knowledgebase_state.py --check-only` | Run read-only framework state-sync prechecks, including authoritative commit-bound SourceRef linting. |
| `python3 .github/skills/sync-knowledgebase-state/logic/sync_knowledgebase_state.py --write-index` | Refresh `wiki/index.md` through the allowlisted framework wrapper after authoritative commit-bound SourceRef prechecks pass. |
| `python3 -m unittest tests.kb.test_framework_contracts tests.kb.test_framework_skills tests.kb.test_framework_agents tests.kb.test_framework_references tests.kb.test_skill_wrappers` | Run the targeted framework contracts/skills/agents/reference plus wrapper test suite. |
| `qmd collection add wiki --name wiki && qmd embed && qmd query "<query>"` | Build/query local semantic index. |
| `python3 scripts/kb/persist_query.py ... --result-json` | Policy-gated persistence of high-value query outputs. |
| `python3 -m unittest discover -s tests -p "test_*.py"` | Run repository test suite. |

## Framework operator notes

- **Lane order:** `knowledgebase-orchestrator` → `source-intake-steward` →
  `evidence-verifier` → `policy-arbiter` → one cleared downstream persona
  (`synthesis-curator`, `query-synthesist`, or `topology-librarian`).
- **Governance boundary:** no downstream wiki/content/topology work starts before
  the ingest-safe lane clears; `maintenance-auditor`, `change-patrol`, and
  `quality-analyst` route follow-up back through the governed lane instead of
  opening a second runtime.
- **Skill layer:** `.github/skills/**` now holds both doc-only framework skills
  (taxonomy, ontology, metadata) and thin wrappers over the deterministic
  `scripts/kb/**` entrypoints. ADR-007 keeps `scripts/kb/**` and `tests/kb/**`
  authoritative.
- **Full persona roster and validation matrix:** see
  [`docs/architecture.md`](docs/architecture.md) and
  [`docs/mvp-runbook.md`](docs/mvp-runbook.md).
- **Advisory freshness sweep:** `wiki-freshness.yml` runs weekly (Monday 03:30
  UTC) and on `workflow_dispatch`; advisory by default, upgradeable to blocking
  mode via the `enforcement_mode` input.

## Architecture and decisions

- Canonical specification baseline: [`raw/processed/SPEC.md`](raw/processed/SPEC.md)
- Architecture overview: [`docs/architecture.md`](docs/architecture.md)
- Framework MVP boundary: [`docs/architecture.md#wiki-curation-framework-mvp-boundary`](docs/architecture.md#wiki-curation-framework-mvp-boundary)
  and [`ADR-007`](docs/decisions/ADR-007-control-plane-layering-and-packaging.md)
- Architecture Decision Records (ADRs): [`docs/decisions/README.md`](docs/decisions/README.md)
- MVP operator runbook: [`docs/mvp-runbook.md`](docs/mvp-runbook.md)

## Included packages

- `.github/skills/`, `.github/agents/`, `.github/prompts/`, and `.github/hooks/` — ported from [`addyosmani/agent-skills`](https://github.com/addyosmani/agent-skills)
  - Upstream license: MIT (`.github/third_party/agent-skills-LICENSE`)
- Wiki-curation framework MVP work should add scaffolding and thin wrappers
  around `scripts/kb/**`; those Python entrypoints remain the deterministic
  execution layer for this repository.
