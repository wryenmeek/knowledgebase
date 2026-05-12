---
type: concept
title: ".github/ Customizations Governance"
status: active
sources:
  - "repo://local/knowledgebase/raw/processed/github-customizations-governance.md@021d32778765eb6ba54644c53740f2eb2fb70473#asset?sha256=a3b9f5b680f468740adf55bd051285010fe39a0ec2489455ceee0de3453c0290"
open_questions: []
confidence: 5
sensitivity: internal
updated_at: "2026-05-12T06:00:00Z"
tags:
  - github-customizations
  - governance
  - freshness-ci
  - semantic-graph
search:
  boost: 2
---

# .github/ Customizations Governance

## Summary

`.github/` customization governance provides the same automated quality guarantees
for agent personas, prompts, hooks, and `copilot-instructions.md` that wiki pages
and skill logic files already have. Before this system, skill `logic/` files had
four layers of automated governance (pre-commit, pytest, CI, AGENTS.md matrix)
while agent personas and hooks had essentially none.

**Core mechanism: semantic cross-reference graph.** A single graph engine maps
agent personas → skills they claim to use → commands in `copilot-instructions.md`
→ scripts on disk. This graph is built once and wired to two outputs:

1. **Pre-commit + CI gate** (`tests/kb/test_github_customizations.py`) — blocks
   broken references from landing on `main`. Validates:
   - Agent persona files in `.github/agents/` reference skills that exist as
     `.github/skills/<name>/SKILL.md`.
   - All `python3 scripts/...` commands in `copilot-instructions.md` resolve to
     real script files.
   - All skill names in the lifecycle mapping table exist as skill directories.
   - `.github/hooks/hooks.json` is valid JSON with required event keys
     (`SessionStart`, `PreToolUse`, `PostToolUse`, `Stop`) and all referenced
     shell script paths resolve to real files.
   - All `[text](path)` links in `.github/prompts/*.prompt.md` resolve to real
     files.

2. **Scheduled repair workflow** (`github-customizations-freshness.yml`) — detects
   drift that slips through and opens fix PRs or labeled issues. Never
   auto-commits to `main`. Drift is classified as:
   - **Resolvable**: broken reference with a candidate replacement → drafted fix PR.
   - **Ambiguous**: structural break requiring judgment → labeled issue
     `drift:needs-review`.

**Frontmatter guards.** `check_frontmatter.py` was extended to cover
`.github/agents/*.md`, requiring `name` and `description` fields. A new
`check_hooks_json.py` hook validates JSON syntax, structure, and shell script
paths.

**Implementation status.** All three deliverables landed 2026-04-27:
`test_github_customizations.py` running in CI-2; frontmatter + hooks pre-commit
guards active; `github-customizations-freshness.yml` workflow deployed.

## Evidence

- `repo://local/knowledgebase/raw/processed/github-customizations-governance.md@021d32778765eb6ba54644c53740f2eb2fb70473#asset?sha256=a3b9f5b680f468740adf55bd051285010fe39a0ec2489455ceee0de3453c0290`:
  Primary source. Defines the problem, semantic graph approach, three deliverables,
  MVP scope, and explicit "not doing" decisions. All deliverables confirmed
  implemented as of 2026-04-27.

## Open Questions

None — all three deliverables implemented and verified.
