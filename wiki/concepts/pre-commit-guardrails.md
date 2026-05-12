---
type: concept
title: "Pre-commit Guardrails"
status: active
sources:
  - "repo://local/knowledgebase/raw/processed/pre-commit-guardrails.md@021d32778765eb6ba54644c53740f2eb2fb70473#asset?sha256=6c88f48b5200b971fb99d1ca2a1aeedf87ce47f6c7540cf02fb07d98acc54d66"
open_questions: []
confidence: 5
sensitivity: internal
updated_at: "2026-05-12T06:00:00Z"
tags:
  - pre-commit
  - git-hooks
  - governance
  - adr-016
search:
  boost: 2
---

# Pre-commit Guardrails

## Summary

The pre-commit guardrails system runs governance checks locally before `git push`,
reducing CI round-trips for the most common validation failures. The hooks complement
CI — they do not replace it; CI remains the authoritative gate.

**Hooks implemented** (all in `scripts/hooks/`):

| Hook | Purpose | Time |
|---|---|---|
| `check_no_staged_locks.py` | Block `.lock` files from being committed | ~0.1s |
| `check_frontmatter.py` | Validate YAML frontmatter in staged `.md` files (wiki pages, SKILL.md, agent personas) | ~1.0s |
| `check_sourceref_format.py` | Validate `repo://` citation format in staged wiki pages | ~0.5s |
| `check_hooks_json.py` | Validate `.github/hooks/hooks.json` syntax, structure, and script paths | ~0.2s |
| `check_context_md_format.py` | Validate `CONTEXT.md` files have required sections (`## Terms`, `## Invariants`, `## File Roles`) and ≤200 lines | ~0.3s |
| `check_matrix_coverage.py` | Verify staged new `scripts/` or `logic/` files have a write-surface matrix row in `AGENTS.md` | ~0.5s |

**Framework choice.** The design proposal recommended raw git hooks. The
implementation adopted the `pre-commit` Python framework (ADR-016 amended
in-place to document this choice). The framework adds value through multi-hook
orchestration and skip logic; the recommendation was superseded by the
implementation decision.

**CI parity.** CI-2 runs the same checks via `pre-commit run --all-files` in
addition to the full pytest suite. Local hooks provide fast feedback; CI provides
the authoritative enforcement gate and full-tree coverage.

**Bypass.** `git commit --no-verify` skips all pre-commit hooks. This is
for emergency hotfixes and automated CI commits only; CI runs the same checks
regardless.

**Setup.** `scripts/hooks/setup-hooks.sh` installs hooks locally:
`pip install pre-commit && pre-commit install`.

## Evidence

- `repo://local/knowledgebase/raw/processed/pre-commit-guardrails.md@021d32778765eb6ba54644c53740f2eb2fb70473#asset?sha256=6c88f48b5200b971fb99d1ca2a1aeedf87ce47f6c7540cf02fb07d98acc54d66`:
  Primary source. Defines the problem, hook types, performance budget, bypass
  mechanism, CI interaction, and implementation phases. Implementation note
  documents that the `pre-commit` framework was adopted (overriding the
  proposal's raw-hooks recommendation) and ADR-016 was amended.

## Open Questions

None — all hooks implemented; open questions from the original proposal resolved
at implementation.
