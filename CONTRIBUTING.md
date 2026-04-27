# Contributing

Thanks for contributing to the knowledgebase framework.
This guide covers the setup, workflow, and governance rules every contributor needs to follow.

## Setup

### Prerequisites

- Python 3.10+
- [Bun](https://bun.sh) — only needed for `scripts/fleet/` TypeScript orchestration
- `qmd` on your PATH — only needed for full index/query flow (not required for most framework contributions)

### Install dev dependencies and hooks

```bash
pip install -e ".[dev]"
pre-commit install
```

The pre-commit hooks (governed by ADR-016) enforce:
- No staged governance lock files (`.kb_write.lock`, etc.)
- Wiki page and `SKILL.md` frontmatter validation
- `CONTEXT.md` structure (required sections, ≤200 lines)
- SourceRef citation format in markdown files
- Write-surface matrix coverage for any newly added scripts

Run all hooks manually with:

```bash
pre-commit run --all-files
```

## Running tests

```bash
python3 -m pytest tests/ -q
```

Run the targeted framework suite after any `.github/agents/**`, `.github/skills/**`, or `AGENTS.md` write-surface matrix change:

```bash
python3 -m pytest tests/kb/test_framework_contracts.py tests/kb/test_framework_skills.py tests/kb/test_framework_agents.py tests/kb/test_framework_references.py tests/kb/test_framework_write_surface_matrix.py tests/kb/test_skill_wrappers.py -v
```

## Governance rules for contributors

Read these before opening a PR:

- **ADR-007** — Framework control-plane layering: skills wrap scripts, scripts don't grow into agents, agents route through `knowledgebase-orchestrator`. No second runtime.
- **ADR-011** — Before adding a helper function, check `scripts/kb/page_template_utils.py`, `write_utils.py`, `contracts.py`, and `scripts/_optional_surface_common.py`. Import from the canonical module; don't copy.
- **AGENTS.md write-surface matrix** — Every new `scripts/**` package or skill-local `logic/**` directory must have a row in the matrix before it touches any protected path. `test_framework_write_surface_matrix.py` enforces this.
- **ADR-005** — Any wiki write needs `wiki/.kb_write.lock`. Never skip the lock.
- **ADR-006** — Only `raw/inbox/**` and checksummed `raw/assets/**` are valid ingest inputs.

## Adding a skill

1. Create `.github/skills/<name>/SKILL.md` with `name` and `description` frontmatter.
2. If the skill needs executable logic, add it to `.github/skills/<name>/logic/<file>.py`.
3. If the logic writes anything, add a row to the write-surface matrix in `AGENTS.md` and to `tests/kb/test_framework_write_surface_matrix.py`.
4. Reference shared helpers (`scripts/kb/**`) via the import pattern in ADR-011 (`sys.path.insert` to repo root).
5. Run the framework suite.

See `docs/ideas/skill-size-refactoring.md` for skill sizing guidance.

## Adding an agent persona

1. Create `.github/agents/<name>.md` with `category` frontmatter (`kb-workflow` or `dev-support`).
2. `kb-workflow` personas participate in the governed lane; `dev-support` personas are advisory and do not bypass governance.
3. Add a row to the persona roster table in `docs/architecture.md`.
4. Run `tests/kb/test_framework_agents.py` to confirm the persona is correctly classified.

See ADR-017 for the two-category taxonomy rationale.

## Writing an ADR

Use the template in `docs/decisions/README.md`. Store ADRs in `docs/decisions/ADR-NNN-slug.md` with sequential numbering. Update the index table in `docs/decisions/README.md`.

ADRs are required for:
- New `scripts/**` package families
- Changes to CI trust model or permission profiles
- New write surfaces or allowlisted paths
- Agent taxonomy changes
- Any decision that would be expensive to reverse

## Fleet orchestration (`scripts/fleet/`)

The fleet scripts are a standalone TypeScript/Bun project for parallel Jules-based issue dispatch. See `scripts/fleet/README.md` and ADR-019 for usage.

## Architecture and decision records

- Architecture overview: [`docs/architecture.md`](docs/architecture.md)
- Full ADR index: [`docs/decisions/README.md`](docs/decisions/README.md)
- Operator runbook: [`docs/mvp-runbook.md`](docs/mvp-runbook.md)
- Agent and skill governance: [`AGENTS.md`](AGENTS.md)
