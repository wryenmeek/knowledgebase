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

The following phrasings do **not** grant implementation authorization — produce the plan only:
- "create a plan to implement X"
- "create a plan to fix X"
- "create a plan to address X"
- "plan out how to implement X"

Only begin implementing when the user sends a standalone approval message after seeing the plan.

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
- New skill creation → `write-a-skill`
- Refactoring proposal / request → `request-refactor-plan`
- Issue triage / classification → `triage-issue`
- Architecture improvement → `improve-codebase-architecture`

## Quality and safety

- Validate input at boundaries and avoid committing secrets (`security-and-hardening`).
- Measure before tuning (`performance-optimization`).
- Keep commits scoped and atomic (`git-workflow-and-versioning`).

### Unpushed commits at task completion

Before marking any task complete, run `git log origin/HEAD..HEAD --oneline`. If unpushed commits exist, either push them or call them out explicitly in the task summary. Never silently leave work unshipped.

### SQL tracking table currency

SQL tracking tables (`todos`, `review_findings`, etc.) must be updated in the **same step** as the code change that resolves them — not as a separate cleanup pass. A finding that is fixed in code but still shows `open` in SQL is stale and misleading. Update status atomically with the fix.

### Mermaid diagram syntax (GitHub renderer)

When writing Mermaid diagrams in markdown research reports or docs:
- **Avoid** `{{...}}` — GitHub's renderer treats double-braces as template syntax and breaks the diagram
- **Avoid** `**` glob patterns in node labels — interpreted as bold markdown
- **Avoid** bare `%` in labels — treated as comment prefix
- **Avoid** unquoted parentheses inside node text — use `["label (text)"]` quoting
- After writing any Mermaid block, mentally parse each node label for these characters

### Grill-me: verify codebase facts before proposing

When the grill-me skill produces a proposed answer that is a **factual claim about the codebase** (e.g., "this constant probably doesn't exist", "this function signature is X"), verify with grep or view before proposing. Only use memory for design preferences and reasoning — not for claims about what code exists.

### FRAMEWORK_BOUNDARY_DOCS — test-monitored files with required literal strings

These files are checked by `tests/kb/test_framework_contracts.py` (`test_boundary_docs_list_same_execution_surface`) using literal `assertIn` — **shorthand will break the test**:

| File | Required literal strings (must all appear verbatim) |
|---|---|
| `docs/ideas/wiki-curation-agent-framework.md` | `scripts/kb/ingest.py`, `scripts/kb/update_index.py`, `scripts/kb/lint_wiki.py`, `scripts/kb/qmd_preflight.py`, `scripts/kb/persist_query.py` |

**Rule:** Never use `scripts/kb/**` shorthand when editing these files — always spell out every entrypoint name explicitly. When delegating edits to subagents, state the required literal strings in the prompt; subagents that rewrite tables with glob shorthand will silently drop them.

## Conventions

- Every skill is in `.github/skills/<name>/SKILL.md`.
- Skill frontmatter should include `name` and `description`.
- Skill descriptions should clearly state what the skill does and “Use when...” triggers.
- Prefer referencing shared docs over duplicating long guidance.

### `docs/ideas/` status lifecycle

When implementing a feature described in a `docs/ideas/` document, update that document's status field in the same PR. A fully implemented feature with a "Draft" or "Proposed" status is misleading and causes repeated manual audit work.

Status values: `Proposed` → `In Progress` → `Implemented`. For partial completion use `Implemented (Phase N)` (e.g., `Implemented (Phase 1)` when 4 of 22 skills are addressed). `Implemented` is terminal. This repo does not use `Superseded` for ideas documents — see the ADR evolution pattern below for how ADRs evolve.

### `docs/ideas/` archival to intake

Fully implemented and verified `docs/ideas/` documents may be archived to `raw/inbox/` for wiki source intake. This makes the design proposal citable as wiki source evidence through the normal intake pipeline.

**Eligibility:** Only documents with `status: Implemented` and zero outstanding remediation items. Paired documents (e.g., a one-pager and its companion spec) must be archived together.

**Procedure:**
1. Move the document as-is to `raw/inbox/<filename>.md` — no content transformation.
2. Leave a minimal stub at the original `docs/ideas/` path containing: title, status line, and a one-line pointer to the archived location.
3. `Implemented` remains the terminal status — no new status value is needed.
4. Do not create companion `.meta.json` files in `raw/inbox/` — inbox selectors do not currently filter them and they would be ingested as sources. The intake steward classifies the source type during normal intake.

**Stub template:**
```markdown
# <Original Title>

**Status:** Implemented — <summary> (<date>)

> Archived to `raw/inbox/<filename>.md` for wiki source intake.
> Full design proposal and implementation notes are in the archived copy.
```

### ADR evolution pattern

This repo does not use "Superseded" status for ADRs. When an ADR needs updating:
- **Minor correction / implementation diverged:** Change status to `Accepted — amended in-place: <description> (see § Amendment)`. Add an `## Amendment` section before References documenting: date, what changed, why, and what didn't change.
- **Extended by a new ADR:** Change status to `Accepted — extended by ADR-xxx`. The original ADR remains in place; the new ADR documents the extension.

Follow the precedent set by ADR-004 and ADR-015. Never mark an ADR as "Superseded" — there is zero repo precedent for that status.

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

**Hard rule:** Do not commit code or doc fixes while test gaps from the same review remain open. A review that surfaces both a code bug and a missing test must land both fixes in the same commit. Never commit the code fix first and defer the test fix — doing so requires an explicit user prompt to recover and has recurred across multiple sessions.

### Module boundaries within `scripts/` subpackages

In any `scripts/<subpackage>/` directory, never import `_private_prefixed` symbols from a sibling module. If two modules in the same subpackage need to share logic, extract it to a dedicated common module (`_http.py`, `_common.py`, `_shared.py`, etc.) within that subpackage. Importing private internals from a sibling creates hidden coupling and makes the public surface unauditable.

### Constants: import, don't duplicate

Define every module-level constant once and import from the canonical location — even within the same subpackage. Never copy a constant to a sibling file, even with a `# keep in sync with <module>.<CONSTANT>` comment. "Keep in sync" comments are only acceptable when an import would create a genuine circular dependency; in that case, extract to a `_constants.py` module and resolve the cycle.

### Contract test cascades

Adding to certain enums or dicts triggers test failures in contract-alignment tests that assert exhaustive expected tuples. Always update the downstream test when extending these:

| When you add to… | Also update… |
|---|---|
| `TokenProfileId` in `scripts/kb/contracts.py` | Expected tuple in `tests/kb/test_contracts.py::test_spec_aligned_token_profiles_and_paths` |
| `WORKFLOW_POLICY_MATRIX` in `tests/kb/test_ci_permission_asserts.py` | `expected_contracts` dict in the same file |
| `GovernedArtifactContract` entries in `contracts.py` | `test_governed_artifact_contracts_cover_declared_state_targets` expected set |
| Files in a CONTEXT.md domain directory | Bump `last_updated` in the domain's CONTEXT.md |

**CONTEXT.md domain mapping:** `scripts/kb/` → `scripts/kb/CONTEXT.md`, `schema/` → `schema/CONTEXT.md`, `scripts/github_monitor/` → `scripts/github_monitor/CONTEXT.md`, `scripts/drive_monitor/` → `scripts/drive_monitor/CONTEXT.md`, `.github/skills/` or `.github/agents/` or `.github/hooks/` → `.github/skills/CONTEXT.md`, `wiki/` → `wiki/CONTEXT.md`. Enforced by `tests/kb/test_context_md_freshness.py` — fails when ≥10 domain commits land after the `last_updated` date.

### CONTEXT.md required sections

The pre-commit hook (`check_context_md_format.py`) validates these exact section headings: `## Terms`, `## Invariants`, `## File Roles`. These differ from what ADR-018 describes (`## Entities`, `## Patterns`) — **the hook is authoritative**. Max 200 lines. Frontmatter requires `scope` and `last_updated` fields.

### Parallel fleet agent file ownership

When dispatching parallel sub-agents (via `task` tool), explicitly partition file ownership so no two agents commit to the same file. Cross-agent regressions are invisible — each agent sees a peer's breakage as "pre-existing." If two tasks must touch the same file, serialize them or assign one agent as the sole owner of that file.

### Sub-agent SQL limitations

Sub-agents launched via the `task` tool do not share the parent session's SQL database. The parent agent must update SQL tracking tables (e.g., `UPDATE todos SET status = 'done'`) itself after reading each sub-agent's result. Never rely on sub-agents to update SQL status.

### Review sub-agent scope boundary

When dispatching review sub-agents (code-reviewer, security-auditor, test-engineer, etc.), explicitly constrain them to the current repository root in the prompt. Sub-agents must not read or review files from parent or sibling directories, even if referenced in documentation. This prevents confusion when multiple repos share a common parent directory.

### CI: `if: always()` on steps downstream of surface scripts

`run_surface_cli`-backed scripts exit `1` on partial success (some entries succeeded, some failed). Any downstream CI step — commit, PR creation, artifact upload — that should run regardless of partial failure **must** have `if: always()`. Without it, successful writes are silently discarded whenever any entry fails.

## Interactive-only skills (autopilot guard)

The following skills require real-time interactive dialogue with the user. They **must not** run autonomously in autopilot mode:

- `idea-refine`
- `grill-me`

**Rule:** When either skill is invoked and `ask_user` returns "The user is not available to respond," immediately halt all skill processing. Do not produce variations, evaluations, decision logs, or output artifacts. Respond:

> "⚠️ **[skill-name]** is interactive-only and cannot run in autopilot mode. Press **Shift+Tab** to exit autopilot and re-run your request."

This rule takes precedence over any "work autonomously" instruction from the autopilot system.

## Operational patterns

### Verify status claims before acting

When a `docs/ideas/` document, plan, or feature claims a terminal status (`Implemented`, `Done`), verify its key claims against the actual codebase before taking any action that depends on that status (archiving, closing, reporting completion). Documents frequently claim completion while gaps remain — three of five "Implemented" docs in the April 2026 review had unresolved issues. Treat status fields as assertions to be checked, not facts to be trusted.

### Default to parallel subagent dispatch

When asked to review, audit, or investigate broad areas of the codebase, default to dispatching parallel subagents without waiting for the user to say "use subagents." This applies to:
- Multi-file code review and simplification passes
- Documentation accuracy audits
- Cross-functional best-practices validation
- Broad codebase research (e.g., "what's incomplete?")

### Investigate root causes proactively

When reporting on CI/automation health, investigate failure root causes — don't just count failures or report surface-level stats. If a workflow has 19 consecutive failures, read the logs and diagnose the error before reporting. When Jules PRs aren't being created, check the dispatch pipeline, not just the PR list.

### "Fleet deployed" continuation signal

When the user sends "Fleet deployed" (or similar), it means they have pushed commits and are ready for the next planned phase to proceed. Treat it as a continuation signal: check the current plan state, identify the next pending task, and execute it.

### Cross-functional review as default post-implementation step

After non-trivial implementation work, proactively suggest a cross-functional review using parallel custom agent dispatch. The standard pattern:
1. Dispatch `@code-reviewer`, `@test-engineer`, `@security-auditor`, and `@documentation-engineer` in parallel
2. Each agent reviews the recent commits against best practices, ADRs, and repo documentation
3. Consolidate findings and present as a unified report
4. Address findings before considering the work complete

This parallels the quality-pass-chain skill but uses custom agents for richer, domain-specific review.

## Boundaries

- **Always:** follow skill workflow requirements when applicable.
- **Always:** keep changes scoped and verifiable.
- **Never:** add vague, non-actionable skills.
- **Never:** duplicate guidance unnecessarily when references suffice.

## Agent personas

Use personas in `.github/agents` when useful:

**Dev-support** (advisory; do not bypass wiki governance lane):
- `@code-reviewer` — correctness, readability, architecture, security, performance
- `@test-engineer` — test strategy, coverage gaps, edge cases
- `@security-auditor` — vulnerability detection, threat modeling, hardening
- `@documentation-engineer` — ADRs, SKILL.md, architecture docs, README, docstrings
- `@solutions-architect` — structural improvement proposals, refactoring plans
- `@framework-engineer` — new skill authoring, framework integrity, `.github/` surface

## Drive monitor test patterns

`scripts/drive_monitor/` depends on Google API libraries (`google-auth`, `googleapiclient`, `httplib2`) that may not be installed in all environments. Tests use `sys.modules` stub injection instead of real imports:

```python
# Stub Google API deps before importing the module under test
sys.modules.setdefault("googleapiclient", types.ModuleType("googleapiclient"))
sys.modules.setdefault("googleapiclient.discovery", types.ModuleType("googleapiclient.discovery"))
# ... then import the module
from scripts.drive_monitor import _http
```

Other patterns:
- Pipeline functions return `SurfaceResult` — assert on `.ok`, `.errors`, `.warnings` fields
- Registry tests use real JSON files in `tmp_path`, not mocks
- Lock mocks must target the actual import path (e.g., `scripts.drive_monitor._registry.write_utils.exclusive_write_lock`)
- `subprocess.run` is mocked for `gh` CLI calls in `create_issues.py` tests

### Jules SDK and session management

**`.env` loading:** `bun` does not auto-load `.env` files. When running Jules SDK scripts, export the key first:

```bash
export $(grep JULES_API_KEY .env | xargs) && bun run script.ts
```

Before asking the user for `JULES_API_KEY`, check whether `.env` exists at the repo root and contains the key.

**SDK over REST for mutations:** The Jules REST API (`jules.googleapis.com`) works for read-only session listing, but mutation endpoints (`sendMessage`, `approvePlan`, `archive`) have undocumented request schemas that vary across API versions. Always use the `@google/jules-sdk` singleton (`jules.session(ID).send()`, `.approve()`, `.archive()`) for any session mutation.

**Scope operations to the target repo:** `jules.sessions()` returns sessions across ALL repositories (can be 1,000+). Always filter by `sourceContext.source` before operating:

```typescript
for await (const s of jules.sessions()) {
  if (s.sourceContext?.source !== 'sources/github/wryenmeek/knowledgebase') continue;
  // ... process
}
```

**Session deduplication:** Jules frequently re-dispatches the same task, producing duplicate PRs (observed: 10 PRs for frontmatter optimization, 8 for command injection — 30 PRs total, 1 merged). Before dispatching a new Jules task, check for existing open PRs addressing the same issue. When reviewing Jules PRs, always verify the diff matches the title/description claims — hallucinated fixes have been observed (PR title says "fix X" but diff changes unrelated files).

