# Copilot project instructions

This repository uses the Agent Skills framework ported into `.github/skills` and `.github/agents`.

## Build, test, and verify commands

```bash
# Python test suite (covers scripts/kb/, scripts/validation/, scripts/reporting/, etc.)
python3 -m pytest tests/

# Run a single test file
python3 -m pytest tests/kb/test_ingest.py

# TypeScript build verification (scripts/fleet/ only — NOT covered by pytest)
cd scripts/fleet && bun build fleet-plan.ts fleet-dispatch.ts fleet-merge.ts
```

> **Two separate runtimes:** `scripts/fleet/` is a standalone TypeScript/Bun project (`package.json`, `tsconfig.json`). It is independent of the Python test suite. Always run `bun build` after editing TypeScript fleet files — pytest passing does **not** mean TypeScript is clean.

## Planning vs implementation

When asked to **"create a plan"**, output the plan only and wait for explicit approval ("implement", "start", "go ahead") before making any changes. Do not combine plan creation and implementation in a single response.

## Research mode

When a user message begins with `Researching:`, produce analysis and findings only. Do not create files, make commits, or open PRs during the research phase. The prefix is an explicit signal to stay read-only.

## Project structure

- `.github/skills/` → Core skills (`SKILL.md` per skill directory)
- `.github/agents/` → Reusable agent personas
- `.github/hooks/` → Agent lifecycle hooks for VS Code/Copilot
- `.github/prompts/` → Prompt templates (ported from upstream commands)
- `.github/skills/references/` → Canonical shared checklists and reference docs

Skill-level `references/` paths are expected by some skills and may be symlinked to the canonical shared references.

## Skill-first execution rules

- If a task matches a skill, invoke and follow that skill workflow.
- Do not skip required skill phases for non-trivial work.
- Do not “quick-implement” around an applicable skill.
- Prefer explicit lifecycle progression over ad-hoc execution.

## Workflow expectations

- Start with specification and plan for non-trivial changes (`spec-driven-development`, `planning-and-task-breakdown`).
- Implement in small, testable increments (`incremental-implementation`).
- Use tests to drive behavior changes and bug fixes (`test-driven-development`).
- Run quality review before merge (`code-review-and-quality`).

### Lifecycle mapping

- **Orient** → `zoom-out`
- **Explore** → `idea-refine`
- **Stress-test** → `grill-me`
- **Define** → `spec-driven-development`
- **Design** → `api-and-interface-design`
- **Plan** → `planning-and-task-breakdown`
- **Build** → `incremental-implementation`, `test-driven-development`
- **Verify** → `debugging-and-error-recovery`
- **Review** → `code-review-and-quality`
- **Review (quality gate)** → `quality-pass-chain`
- **Document** → `documentation-and-adrs`
- **Edit** → `edit-article`
- **Automate** → `ci-cd-and-automation`
- **Ship** → `shipping-and-launch`
- **Self-audit** → `audit-knowledgebase-workspace`
- **Operate** → `caveman`, `log-intake-rejection`, `reconsider-rejected-source`

### Intent to skill mapping

- Feature / new functionality → `spec-driven-development` → `incremental-implementation` → `test-driven-development`
- Planning / breakdown → `planning-and-task-breakdown`
- Bug / failure / unexpected behavior → `debugging-and-error-recovery`
- Code review → `code-review-and-quality`
- Refactoring / simplification → `code-simplification`
- API / interface design → `api-and-interface-design`
- UI work → `frontend-ui-engineering`
- Quality gate / multi-pass review → `quality-pass-chain`
- Prose restructuring / AI-tell cleanup → `edit-article`
- Source intake rejection → `log-intake-rejection`
- Reconsidering prior rejection → `reconsider-rejected-source`
- Agent-to-agent context compression → `caveman`

## Quality and safety

- Validate input at boundaries and avoid committing secrets (`security-and-hardening`).
- Measure before tuning (`performance-optimization`).
- Keep commits scoped and atomic (`git-workflow-and-versioning`).

## Conventions

- Every skill is in `.github/skills/<name>/SKILL.md`.
- Skill frontmatter should include `name` and `description`.
- Skill descriptions should clearly state what the skill does and “Use when...” triggers.
- Prefer referencing shared docs over duplicating long guidance.

### Jules SDK

`@google/jules-sdk` exports a pre-built singleton — never use a constructor:

```typescript
import { jules } from '@google/jules-sdk';
// jules is ready to use. JULES_API_KEY is read from the environment automatically.
// jules.run()      → AutomatedSession (auto-approve, auto-PR) — use for CI
// jules.session()  → SessionClient (defaults requirePlanApproval:true) — use for human-in-the-loop
// jules.sessions() → async iterator over all sessions
```

Do not use `new Jules()`, `Jules({ apiKey })`, or `jules.createSession()` — none of these exist.

## Codebase-specific patterns

### Path bounds checking

Always use `Path.is_relative_to(wiki_root.resolve())` to verify a resolved path stays inside `wiki_root`. Never use `str(resolved).startswith(str(wiki_root))` — it is not separator-safe and allows sibling directories (e.g. `wiki-extra/`) to pass a `wiki` prefix check. This is the canonical pattern per `docs/architecture.md` Write and safety controls.

### Skill logic imports (ADR-011)

Skill logic files live at `.github/skills/<name>/logic/<file>.py`. To import from `scripts.kb`, use:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))  # repo root
```

`parents[4]` resolves to the repo root. Never inline-reimplement helpers already in `scripts/kb/page_template_utils.py`, `write_utils.py`, `contracts.py`, or `_optional_surface_common.py`.

### Post-implementation quality-pass order

For non-trivial changes, run these skill passes in order — later passes often find issues the earlier ones expose. See `.github/skills/quality-pass-chain/SKILL.md` for the full procedural contract.

**Development quality gate** (4 steps, run in order):

1. `code-review-and-quality` — correctness, security, architecture
2. `code-simplification` — clarity, dead code, loop invariants
3. `test-driven-development` — coverage gaps, edge cases
4. `documentation-and-adrs` — SKILL.md, architecture.md, README.md, docstrings

**Pre-deployment gate** (separate from development quality):

- `shipping-and-launch` — pre-launch checklist, write-surface matrix. Runs before merge to production branch, not during development review.

When a review pass produces test gap findings, address them in the same fix commit — not as a follow-up. Test coverage gaps are first-class review findings, not optional housekeeping.

### Module boundaries within `scripts/` subpackages

In any `scripts/<subpackage>/` directory, never import `_private_prefixed` symbols from a sibling module. If two modules in the same subpackage need to share logic, extract it to a dedicated common module (`_http.py`, `_common.py`, `_shared.py`, etc.) within that subpackage. Importing private internals from a sibling creates hidden coupling and makes the public surface unauditable.

### Constants: import, don't duplicate

Define every module-level constant once and import from the canonical location — even within the same subpackage. Never copy a constant to a sibling file, even with a `# keep in sync with <module>.<CONSTANT>` comment. "Keep in sync" comments are only acceptable when an import would create a genuine circular dependency; in that case, extract to a `_constants.py` module and resolve the cycle.

### CI: `if: always()` on steps downstream of surface scripts

`run_surface_cli`-backed scripts exit `1` on partial success (some entries succeeded, some failed). Any downstream CI step — commit, PR creation, artifact upload — that should run regardless of partial failure **must** have `if: always()`. Without it, successful writes are silently discarded whenever any entry fails.

## Boundaries

- **Always:** follow skill workflow requirements when applicable.
- **Always:** keep changes scoped and verifiable.
- **Never:** add vague, non-actionable skills.
- **Never:** duplicate guidance unnecessarily when references suffice.

## Agent personas

Use personas in `.github/agents` when useful:
- `@code-reviewer`
- `@test-engineer`
- `@security-auditor`

