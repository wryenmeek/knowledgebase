# Cloneable Knowledgebase Template

## Problem Statement

How might we make the knowledgebase framework instantly forkable as a clean slate, with zero
ambiguity about what is template-layer vs. domain content?

## Recommended Direction

Documentation-first, script-next. Ship a `TEMPLATE.md` at the repo root immediately — this
solves 80% of the problem with no code changes. Follow with `scripts/init.py --fresh` to
automate the content wipe. Enable the GitHub Template Repository flag to surface a
"Use this template" button as the canonical entry point.

The core insight is that this repo has two layers that are not yet labeled:

- **Framework layer** (reusable as-is): `scripts/`, `tests/`, `.github/`, `schema/`,
  `docs/decisions/`, `pyproject.toml`
- **Content layer** (instance-specific, must be replaced): `wiki/` pages, `raw/` source
  material, `raw/processed/SPEC.md` domain sections, and domain-specific prose in
  `CONTEXT.md` and `README.md`

`TEMPLATE.md` makes the split legible in 10 minutes. The init script enforces it
automatically. A devcontainer is the right long-term endgame — Codespaces opens, runs the
init script, installs qmd, and you are fully operational — but it depends on the boundary
being proved clean first.

## Key Assumptions to Validate

- [ ] Framework/content boundary is clean enough to automate — write the file manifest and
  check whether any file is ambiguously placed
- [ ] `qmd` is the only non-pip external dependency — test with a fresh clone and
  `pip install -e .`; document any other gaps in `TEMPLATE.md`
- [ ] Tests pass on a repo with `wiki/` and `raw/` wiped — run `pytest` after manually
  clearing content dirs before writing the init script
- [ ] Template users are comfortable running a one-line Python command — if not, the GitHub
  template flag + `TEMPLATE.md` alone may be sufficient

## MVP Scope

1. **GitHub Template Repository flag** — 1-click in repo settings; surfaces the
   "Use this template" button as the canonical onboarding path
2. **`TEMPLATE.md` at repo root** — explains the two-layer split; lists what to delete,
   what to edit (`CONTEXT.md`, `README.md`, `raw/processed/SPEC.md`), what to install,
   and what to run to verify a green test suite
3. **`scripts/init.py --fresh`** — wipes content dirs; creates empty stubs for `wiki/`,
   `raw/inbox/`, `raw/processed/`; installs pip deps; drops a sample inbox document so
   the first `ingest.py` run demonstrates the pipeline; runs `pytest` to confirm a clean
   framework state

## Resolved Decisions

- **`init.py` when qmd is not installed:** skip with a printed warning — pip-installable
  deps are the minimum bar; qmd installation is documented in `TEMPLATE.md`
- **`CONTEXT.md` and `AGENTS.md`:** "edit heavily" — they are structural scaffolding and
  must be kept, but the domain-specific prose must be replaced by the template user
- **Sample inbox document:** yes — a minimal well-formed example source gives the first
  `ingest.py` run something real to process and proves the pipeline end-to-end

## Not Doing (and Why)

- **PyPI extraction** — abstraction overhead; the framework is not stable enough to version
  independently yet
- **`framework` branch** — adds git branching complexity with no payoff over the template
  repository flag
- **Devcontainer now** — right endgame for AFK and Codespaces use; revisit after
  `TEMPLATE.md` ships and the framework/content boundary is proved clean
- **Renaming directories** — breaking change to existing structure; a checklist achieves
  the same clarity without disruption

## Open Questions

- What taxonomy should the sample inbox document use — real Medicare stub or a generic
  "example policy document" to avoid content-layer leakage into the framework?
