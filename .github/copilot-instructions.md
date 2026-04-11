# Copilot project instructions

This repository uses the Agent Skills framework ported into `.github/skills` and `.github/agents`.

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

- **Define** → `spec-driven-development`
- **Plan** → `planning-and-task-breakdown`
- **Build** → `incremental-implementation`, `test-driven-development`
- **Verify** → `debugging-and-error-recovery`
- **Review** → `code-review-and-quality`
- **Ship** → `shipping-and-launch`

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
