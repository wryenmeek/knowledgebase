# knowledgebase

Self-contained, self-organizing knowledgebase.

## Included packages

- `.github/skills/`, `.github/agents/`, `.github/prompts/`, and `.github/hooks/` — ported from [`addyosmani/agent-skills`](https://github.com/addyosmani/agent-skills)
  - Upstream license: MIT (`.github/third_party/agent-skills-LICENSE`)

## MVP runbook

For end-to-end MVP operations, see [`docs/mvp-runbook.md`](docs/mvp-runbook.md).  
It covers local ingest/index/lint/qmd/persist/test flow, fail-closed exit handling,
CI-1..CI-3 fallback/manual execution, and M0..M4 milestone evidence mapping.  
It also documents CI-1 trusted-trigger prerequisites (protected default branch and
strict `raw/inbox/**` commit scope).
