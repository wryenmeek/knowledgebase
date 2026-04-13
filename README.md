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
| `qmd collection add wiki --name wiki && qmd embed && qmd query "<query>"` | Build/query local semantic index. |
| `python3 scripts/kb/persist_query.py ... --result-json` | Policy-gated persistence of high-value query outputs. |
| `python3 -m unittest discover -s tests -p "test_*.py"` | Run repository test suite. |

## Architecture and decisions

- Canonical specification baseline: [`raw/inbox/SPEC.md`](raw/inbox/SPEC.md)
- Architecture overview: [`docs/architecture.md`](docs/architecture.md)
- Architecture Decision Records (ADRs): [`docs/decisions/README.md`](docs/decisions/README.md)
- MVP operator runbook: [`docs/mvp-runbook.md`](docs/mvp-runbook.md)

## Included packages

- `.github/skills/`, `.github/agents/`, `.github/prompts/`, and `.github/hooks/` — ported from [`addyosmani/agent-skills`](https://github.com/addyosmani/agent-skills)
  - Upstream license: MIT (`.github/third_party/agent-skills-LICENSE`)
