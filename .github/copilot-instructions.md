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

- **Explore** → `idea-refine`
- **Define** → `spec-driven-development`
- **Plan** → `planning-and-task-breakdown`
- **Build** → `incremental-implementation`, `test-driven-development`
- **Verify** → `debugging-and-error-recovery`
- **Review** → `code-review-and-quality`
- **Document** → `documentation-and-adrs`
- **Automate** → `ci-cd-and-automation`
- **Ship** → `shipping-and-launch`
- **Self-audit** → `audit-knowledgebase-workspace`

### Intent to skill mapping

- Feature / new functionality → `spec-driven-development` → `incremental-implementation` → `test-driven-development`
- Planning / breakdown → `planning-and-task-breakdown`
- Bug / failure / unexpected behavior → `debugging-and-error-recovery`
- Code review → `code-review-and-quality`
- Refactoring / simplification → `code-simplification`
- API / interface design → `api-and-interface-design`
- UI work → `frontend-ui-engineering`

## Quality and safety

- Validate input at boundaries and avoid committing secrets (`security-and-hardening`).
- Measure before tuning (`performance-optimization`).
- Keep commits scoped and atomic (`git-workflow-and-versioning`).

## Conventions

- Every skill is in `.github/skills/<name>/SKILL.md`.
- Skill frontmatter should include `name` and `description`.
- Skill descriptions should clearly state what the skill does and “Use when...” triggers.
- Prefer referencing shared docs over duplicating long guidance.

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

## Build, test, and lint commands

```bash
# Run the full Python test suite (~45s, 314 tests)
python3 -m pytest tests/

# Run a single test file
python3 -m pytest tests/kb/test_ingest.py

# Verify TypeScript fleet scripts compile (no pytest coverage for these)
cd scripts/fleet && bun build fleet-plan.ts fleet-dispatch.ts fleet-merge.ts
```

`scripts/fleet/` is a standalone TypeScript/Bun project (its own `package.json`, `bun.lock`, `tsconfig.json`) — completely separate from the Python test suite. **Always run `bun build` after editing any TypeScript in `scripts/fleet/`** — the Python tests will not catch TypeScript syntax errors there.

## Planning vs. implementation

**"Create a plan" means plan only.** When asked to create a plan, output the plan and wait for explicit approval before making any changes. The user says things like "implement", "start", "go ahead", or "get to work" to trigger implementation. Do not combine plan creation and implementation in a single response.

**"Researching:" prefix = no writes.** When a user message begins with `Researching:`, produce analysis and findings only. Do not create files, make commits, or open PRs. The research phase ends when the user gives an explicit action command.

## Jules SDK

The `@google/jules-sdk` package exports a pre-built singleton — not a constructor class:

```typescript
import { jules } from '@google/jules-sdk';
// jules is ready to use immediately; reads JULES_API_KEY from env automatically.
// Never use: new Jules(), Jules({ apiKey }), or jules.createSession()
```

Key method semantics:
- `jules.run(config)` → auto-approves plan, auto-creates PR. **Use for CI.**
- `jules.session(config)` → defaults `requirePlanApproval: true`, pauses for human approval.
- `jules.session(id: string)` → rehydrates an existing session by ID.
- `jules.createSession()` → **does not exist.**
