# ADR-016: Use raw git hooks (not the pre-commit framework) for local governance checks

## Status
Accepted

## Date
2026-04-27

## Context

Several governance violations — malformed frontmatter, accidentally staged lock
files, malformed SourceRef citations, missing write-surface matrix rows — were
only caught in CI after a push, creating a slow feedback loop. Catching these
locally before `git push` reduces CI churn and prevents governance violations
from reaching the remote.

Two implementation paths exist:
1. The [`pre-commit` framework](https://pre-commit.com/) — an external Python
   package that installs hooks via a `.pre-commit-config.yaml` manifest.
2. Raw git hooks — a shell script at `.git/hooks/pre-commit` that calls
   repository-local Python scripts directly.

The hooks needed are all implemented as Python scripts in `scripts/hooks/`
and call the same validation logic that runs in CI-2. No new languages or
runtimes are required.

## Decision

Use **raw git hooks** (not the `pre-commit` framework).

A shell script at `scripts/hooks/pre-commit` calls each Python validation
script directly. Developers install it by symlinking or copying it to
`.git/hooks/pre-commit` (documented in README; a setup script automates this).

The following checks run pre-commit:

| Hook script | What it checks | Time |
|---|---|---|
| `check_no_staged_locks.py` | Blocks staged `.lock` files | ~0.1s |
| `check_frontmatter.py` | YAML frontmatter in staged wiki pages, SKILL.md, and agent persona files | ~1.0s |
| `check_sourceref_format.py` | `repo://` citation format in staged wiki pages | ~0.5s |
| `check_hooks_json.py` | JSON syntax, required structure, and shell script path resolution in `.github/hooks/hooks.json` | ~0.3s |
| `check_context_md_format.py` | Frontmatter and required section structure in staged `CONTEXT.md` files | ~0.3s |
| `check_matrix_coverage.py` | Write-surface matrix row exists in `AGENTS.md` for staged new files in `scripts/` and `.github/skills/**/logic/` | ~0.5s |

Total budget: ~2.7s (well under the 5s threshold for developer tolerance).

CI-2 runs the equivalent checks against the full tree regardless of whether
hooks ran locally. Local hooks are a fast-feedback optimization, not a
security boundary.

## Alternatives Considered

### `pre-commit` framework

- **Pros:** Standardized config format; easy to share hooks across projects;
  automatic virtual environment management per hook; community hook registry.
- **Cons:** Requires `pip install pre-commit` and `pre-commit install` as an
  extra setup step; fetches hook definitions from the network on first run;
  adds an external dependency for a repo that otherwise requires only Python
  stdlib; introduces a separate virtual environment per hook.
- **Rejected:** This repository already requires Python 3 with no external
  hook dependencies. The `pre-commit` framework adds complexity without
  benefit for a single-language repo where all hooks are already
  repository-local Python scripts.

### CI-only checks (no local hooks)

- **Pros:** Zero local setup; CI is the single source of truth.
- **Cons:** Round-trip feedback (commit → push → CI → fail → fix → push again)
  costs 2–5 minutes for errors that could be caught in seconds locally.
- **Rejected:** The most common CI failures (malformed frontmatter, staged lock
  files) are fast to check locally; CI-only feedback is unnecessarily slow.

### Mandatory hooks enforced via CI check

- **Pros:** Guarantees hooks ran before a commit reaches CI.
- **Cons:** Requires embedding a hook-ran marker in every commit (e.g., a
  commit trailer), which adds noise and breaks automated commits from CI bots.
- **Rejected:** Local hooks are opt-in by design; CI runs independent checks
  regardless.

## Consequences

- Developers who install the hooks catch the most common governance violations
  locally before pushing.
- Cloud-based agents (Copilot, Jules) that make commits directly bypass local
  hooks; CI-2 remains the authoritative gate.
- Hook updates are distributed by re-running the setup script; no automatic
  notification mechanism exists when hooks change.
- The `scripts/hooks/` directory is in the `AGENTS.md` write-surface matrix
  as `read-only only` — hooks may never write to the repository.
- `git commit --no-verify` bypasses all hooks; this is documented as
  emergency-only, not routine use.

## References

- `scripts/hooks/` — hook implementation scripts
- `.github/workflows/pre-commit.yml` — CI equivalent of local hook checks
- `docs/ideas/pre-commit-guardrails.md` — original design proposal
- `docs/decisions/ADR-005-write-concurrency-guards.md` — lock file semantics (why staged locks must be blocked)
- `AGENTS.md` § Write-surface matrix — `scripts/hooks/**` row
