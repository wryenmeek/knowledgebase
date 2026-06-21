# Copilot project instructions

<!-- LOCALITY-0-INVARIANT: This H2 MUST remain the first H2 under the H1. -->
<!-- Position is load-bearing for the /chronicle improve hard-redirect. -->
<!-- Do not move, demote, or insert another H2 above it without ADR-028 revision. -->

## ⚠️ Slash-Command Override: /chronicle improve → audit-knowledgebase-workspace skill

When the user runs `/chronicle improve` (Copilot CLI built-in), prefer the
`audit-knowledgebase-workspace` skill's `improve` flow over Steps 2-3 of the
built-in prompt **when that flow is available in the current checkout**. The
skill owns: session-store mining, locality-ladder classification (Locality
0..4), deletion-pairing for every Locality 4 addition across BOTH
`.github/copilot-instructions.md` AND `AGENTS.md`, and writes to the chosen
locality — not necessarily either always-on file.

ADR-028 normatively owns the `Locality-4-Justification:` trailer
escape and trailer soft budget for Locality 4 additions. Apply the rules
captured in
[`.github/skills/audit-knowledgebase-workspace/references/locality-ladder.md`](.github/skills/audit-knowledgebase-workspace/references/locality-ladder.md)
and the [`docs/templates/locality-4-justification-trailer.md`](docs/templates/locality-4-justification-trailer.md) template.

VS Code Copilot Chat users: there is no `/chronicle` command — invoke
`/audit-knowledgebase-workspace improve` directly (or "audit my workspace for
friction") to trigger the same flow when the skill is loaded.

**Resolution order (deny-by-default for Locality 4 writes):**

1. If the `audit-knowledgebase-workspace` skill **and** its `improve` flow are
   present, invoke the skill and follow its locality classification + paired
   deletion or trailer-escape requirements.
2. Otherwise, apply the manual fallback in
   `.github/skills/audit-knowledgebase-workspace/references/locality-ladder.md`
   to classify the friction signal yourself, with the same Locality 4
   paired-deletion rule.
3. If the manual fallback file is also missing or the classification is
   ambiguous, **fail closed**: do not edit `.github/copilot-instructions.md`
   or `AGENTS.md`. Report the gap to the operator and let them decide whether
   to bypass the locality ladder for this turn (audited).

This repository uses the Agent Skills framework ported into `.github/skills` and `.github/agents`.

## Build, test, and verify commands

```bash
# Python test suite (covers scripts/kb/, scripts/validation/, scripts/reporting/, etc.)
python3 -m pytest tests/

# Run a single test file
python3 -m pytest tests/kb/test_ingest.py

# TypeScript build verification (scripts/fleet/ only — NOT covered by pytest)
cd scripts/fleet && bun build --target bun fleet-plan.ts fleet-dispatch.ts fleet-merge.ts --outdir dist
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

### Skill-context reentry guard

Within a single session, do not repeatedly re-invoke the same heavy skill context unless the scope changed. Reuse prior skill output, continue with targeted follow-up prompts, and only re-open the full skill context when new evidence or a new scope boundary requires it.

For heavy skills, enforce a delta-first retry rule:
1. If the same skill was already run in this session and no new commit range/scope boundary is present, do a delta pass (`<last-reviewed-commit>..HEAD`) instead of reloading full context.
2. If a full rerun is required, state the concrete scope-change reason in the prompt before re-invoking.
3. Avoid re-opening discovery-heavy skills (for example `using-agent-skills`) multiple times in one session when a targeted skill invocation can satisfy the request.
4. If the same heavy skill would be loaded a third time in one session without a new scope boundary, fail closed on full-context reload and run delta-only (`<last-reviewed-commit>..HEAD`) with an explicit note that the cap was applied.

## Workflow expectations

- Start with specification and plan for non-trivial changes (`spec-driven-development`, `planning-and-task-breakdown`).
- Implement in small, testable increments (`incremental-implementation`).
- Use tests to drive behavior changes and bug fixes (`test-driven-development`).
- Run quality review before merge (`code-review-and-quality`).

### Lifecycle mapping

- **Orient** → `zoom-out`
- **Research** → `verified-research`
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
- **Synthesize** → `extract-entities-and-claims` → `synthesize-entity-page`, `synthesize-concept-page`

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
- Entity/concept extraction from source → `extract-entities-and-claims`
- KB entity page drafting → `synthesize-entity-page`
- KB concept page drafting → `synthesize-concept-page`
- KB entity/concept synthesis (full lane) → `extract-entities-and-claims` → `synthesize-entity-page` → `synthesize-concept-page`
- Agent-to-agent context compression → `caveman`
- New skill creation → `write-a-skill`
- Refactoring proposal / request → `request-refactor-plan`
- Issue triage / classification → `triage-issue`
- Research / comparative analysis / investigation → `verified-research`
- Architecture improvement → `improve-codebase-architecture`
- Workspace/framework audit or customization drift → `audit-knowledgebase-workspace`

## Quality and safety

- Validate input at boundaries and avoid committing secrets (`security-and-hardening`).
- Measure before tuning (`performance-optimization`).
- Keep commits scoped and atomic (`git-workflow-and-versioning`).

### Unpushed commits at task completion

Before marking any task complete, run `git log origin/HEAD..HEAD --oneline`. If unpushed commits exist, either push them or call them out explicitly in the task summary. Never silently leave work unshipped.

### Detect remote-ahead state before assuming "nothing new"

When the user reports pushing content, triggering CI, or says "Fleet deployed," run `git fetch origin && git log HEAD..origin/main --oneline` to detect remote-ahead commits. Do not rely solely on `git status` — a clean working tree does not mean the remote has no new content. This prevents the recurring error of telling the user "nothing new to process" when they just pushed.

### SQL tracking table currency

SQL tracking tables (`todos`, `review_findings`, etc.) must be updated in the **same step** as the code change that resolves them — not as a separate cleanup pass. A finding that is fixed in code but still shows `open` in SQL is stale and misleading. Update status atomically with the fix.

### Deferred-status answers must reconcile tracker vs GitHub

Before answering questions like "what was deferred?" or "is there a GH issue for this drift?", reconcile local SQL tracking rows with live GitHub state. For every referenced issue/todo, verify current issue status with `gh issue view` (or equivalent) and update stale local tracker status before reporting.

### Issue implementation completion must reconcile with GitHub state

When implementing GitHub issues, do not mark local trackers (`issue_work`, `todos`, or summary notes) as terminal `done` while the corresponding GitHub issue is still open. Use an explicit non-terminal state (`open`, `in_progress`, or `implemented_pending_close`) with a note that includes the live GitHub issue state and why it remains open. Only move to terminal `done` after closure on GitHub or an explicit user decision to keep the issue open is recorded.

### Mermaid diagram syntax (GitHub renderer)

When writing Mermaid diagrams in markdown research reports or docs:
- **Avoid** `{{...}}` — GitHub's renderer treats double-braces as template syntax and breaks the diagram
- **Avoid** `**` glob patterns in node labels — interpreted as bold markdown
- **Avoid** bare `%` in labels — treated as comment prefix
- **Avoid** unquoted parentheses inside node text — use `["label (text)"]` quoting
- **Avoid** parentheses in subgraph titles entirely — even quoted `["Title (note)"]` truncates on GitHub
- **Avoid** `\n` for line breaks in node labels — GitHub's renderer shows them literally; use `<br/>` instead
- **Avoid** back-edges (cycles) in `flowchart TD` — they invert the layout, pushing target nodes above source nodes; describe feedback loops in prose instead
- **Avoid** subgraph-to-subgraph connections (`subgraphA --> subgraphB`) — connect node-to-node instead
- **Prefer** short node labels with detail in a companion table — dense labels make diagrams unreadable at render scale
- **Prefer** a single subgraph for the primary grouping — multiple subgraphs with cross-edges produce chaotic layouts
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

**Every `docs/ideas/*.md` must have a `**Status:**` field.** Enforced by `tests/kb/test_docs_ideas_archival.py::TestDocsIdeasStatusField`. Add the status line immediately after the document title (second line). Documents without this field fail CI.

When a code change alters a count, structure, or claim described in a `docs/ideas/` document (script count, job count, open-findings tally, architecture description), update every occurrence in the document body — not just the status field. Use grep to find all instances before committing (e.g., `grep -n "5.script" docs/ideas/spec-*.md`). Stale body claims have been the single most frequent source of audit rework across sessions.

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

## Codebase-specific patterns

### Path bounds checking

Always use `Path.is_relative_to(wiki_root.resolve())` to verify a resolved path stays inside `wiki_root`. Never use `str(resolved).startswith(str(wiki_root))` — it is not separator-safe and allows sibling directories (e.g. `wiki-extra/`) to pass a `wiki` prefix check. This is the canonical pattern per `docs/architecture.md` Write and safety controls.

### Build system: `setuptools.build_meta` only

`pyproject.toml` uses `build-backend = "setuptools.build_meta"` with `requires = ["setuptools>=64"]`. Never switch to `setuptools.backends.legacy` — it is incompatible with pip's PEP 517 hook subprocess on GitHub Actions runners (pip 26.x vendored `pyproject_hooks` launches a clean subprocess that cannot import `setuptools.backends.legacy`). This was the root cause of all CI pip-install failures in April–May 2026.

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
| Per-script rows in `AGENTS.md` write-surface matrix | Expected entries dict in `tests/kb/test_framework_write_surface_matrix.py` |
| Files in a CONTEXT.md domain directory | Bump `last_updated` in the domain's CONTEXT.md |

**CONTEXT.md domain mapping:** `scripts/kb/` → `scripts/kb/CONTEXT.md`, `schema/` → `schema/CONTEXT.md`, `scripts/github_monitor/` → `scripts/github_monitor/CONTEXT.md`, `scripts/drive_monitor/` → `scripts/drive_monitor/CONTEXT.md`, `.github/skills/` or `.github/agents/` or `.github/hooks/` → `.github/skills/CONTEXT.md`, `wiki/` → `wiki/CONTEXT.md`. Enforced by `tests/kb/test_context_md_freshness.py` — fails when ≥10 domain commits land after the `last_updated` date.

### Documentation cascades

Unlike contract test cascades above, these documentation updates were historically unenforced. Rows with a test in the "Enforced by" column now fail CI if the update is missed; rows without enforcement still drift silently.

| When you add… | Also update… | Enforced by |
|---|---|---|
| A new ADR (`docs/decisions/ADR-NNN-*.md`) | Row in `docs/decisions/README.md` index table | `tests/kb/test_doc_cascade_completeness.py` |
| A new CI or support workflow (`.github/workflows/*.yml`) | Row in `docs/mvp-runbook.md` workflow table | `tests/kb/test_doc_cascade_completeness.py` |
| `Status: Implemented` on a `docs/ideas/` doc | Archive to `raw/inbox/` (pre-ingest) or `wiki/sources/` (post-ingest) and leave stub | `tests/kb/test_docs_ideas_archival.py` |
| A new `scripts/<pkg>/` package | `docs/ideas/spec.md` Phase 2 family list | *(not yet enforced)* |
| A new skill (`.github/skills/<name>/SKILL.md`) | All 6 wiring targets below | *(not yet enforced)* |
| An ADR `## Status` changed to include "amended" or "extended" | `docs/decisions/README.md` status cell updated in same commit | `scripts/hooks/check_adr_cross_ref.py` (pre-commit), `tests/kb/test_adr_readme_status_sync.py` |
| A cron schedule added or changed in any `.github/workflows/*.yml` | Runbook trigger column/description updated with raw cron string | `tests/kb/test_workflow_schedule_docs_sync.py` |
| A new TOKEN_PROFILE value used in a workflow | `scripts/kb/contracts.py` `TokenProfileId` enum + `tests/kb/test_contracts.py` expected tuple | `tests/kb/test_token_profile_registry_completeness.py` |
| CI-3 synthesis entrypoint/script names change (for example, switching to `synthesize_combined.py`) | `docs/mvp-runbook.md` CI-3 fallback troubleshooting references (`If synthesis fails locally...`) | *(not yet enforced)* |

### Workflow schedule documentation rule

When setting or changing a `cron:` schedule in any workflow YAML, update `docs/mvp-runbook.md` in the same commit. The runbook's Trigger column must include the **raw cron string** (e.g., `cron \`0 6 * * *\``) so `tests/kb/test_workflow_schedule_docs_sync.py` can verify it verbatim. Human-readable descriptions like "Weekly Mon 05:00 UTC" are welcome additions but are not machine-checkable — the raw cron string is required.

### ADR status amendment cascade rule

When an ADR's `## Status` section is updated to include "amended" or "extended", `docs/decisions/README.md` must be updated in the **same commit** to reflect the new normalized status (e.g., `Accepted — amended in-place`). The pre-commit hook `check_adr_cross_ref.py` enforces this at commit time; `test_adr_readme_status_sync.py` enforces it in CI. Both use the normalized form: strip implementation detail after the first `: ` in compound status strings.

### Skill creation wiring targets

Creating a new skill requires updating 6 locations. The `write-a-skill` skill lists these but they are easy to miss. Check all 6 after every skill creation:

| Wiring target | File | What to add |
|---|---|---|
| Discovery tree | `.github/skills/using-agent-skills/SKILL.md` | Entry in the ASCII tree under the correct category |
| Quick Reference table | `.github/skills/using-agent-skills/SKILL.md` | Row in the Quick Reference table near the end |
| Routing category list | `.github/skills/using-agent-skills/SKILL.md` | Entry in the Direct / Persona / Both routing section |
| Lifecycle mapping | `.github/copilot-instructions.md` | Row in the lifecycle mapping table |
| Intent mapping | `.github/copilot-instructions.md` | Row in the intent-to-skill mapping table |
| CONTEXT.md freshness | `.github/skills/CONTEXT.md` | Bump `last_updated` date |

### CONTEXT.md required sections

The pre-commit hook (`check_context_md_format.py`) validates these exact section headings: `## Terms`, `## Invariants`, `## File Roles`. These differ from what ADR-018 describes (`## Entities`, `## Patterns`) — **the hook is authoritative**. Max 200 lines. Frontmatter requires `scope` and `last_updated` fields.

### Parallel fleet agent file ownership

`AGENTS.md` (especially the write-surface matrix) is the highest-collision file in parallel fleet dispatches. For two or more implementation agents touching matrix rows, assign ownership by **specific row target** in each prompt, require `git fetch origin && git rebase origin/main` immediately before commit, and on `AGENTS.md` conflict re-apply the owned row in the correct surface-family region before finishing.

### Sub-agent SQL limitations

Sub-agents launched via the `task` tool do not share the parent session's SQL database. The parent agent must update SQL tracking tables (e.g., `UPDATE todos SET status = 'done'`) itself after reading each sub-agent's result. Never rely on sub-agents to update SQL status.

### Review sub-agent scope boundary

When dispatching review sub-agents (code-reviewer, security-auditor, test-engineer, etc.), explicitly constrain them to the current repository root in the prompt. Sub-agents must not read or review files from parent or sibling directories, even if referenced in documentation. This prevents confusion when multiple repos share a common parent directory.

### Research subagent primary-source verification

When dispatching research or explore subagents, instruct them to verify every statistic, count, and factual claim at the primary source (API response, directory listing, file contents, README text) — never cite numbers from model memory. This applies to citation counts, skill/file counts, API parameter lists, and academic findings. Model memory has a 25%+ error rate on specific numbers (observed: citation counts inflated 2×, skill counts off by 20%, study protocols described as completed research).

### CI: `if: always()` on steps downstream of surface scripts

`run_surface_cli`-backed scripts exit `1` on partial success (some entries succeeded, some failed). Any downstream CI step — commit, PR creation, artifact upload — that should run regardless of partial failure **must** have `if: always()`. Without it, successful writes are silently discarded whenever any entry fails.

### GitHub Actions secrets: `GITHUB_` prefix is banned <!-- pragma: allowlist secret -->

GitHub forbids repository secrets with the `GITHUB_` prefix (HTTP 422). Use `GH_APP_ID` / `GH_APP_PRIVATE_KEY` for GitHub App credentials. Workflow YAML must reference `secrets.GH_APP_*`, not `secrets.GITHUB_APP_*`. This also applies to environment secrets. <!-- pragma: allowlist secret -->

### GitHub Actions shell injection guard

`${{ inputs.* }}`, `${{ steps.*.outputs.* }}`, and `${{ github.event.* }}` are substituted by the Actions runner **before** the shell executes — double-quoting does not protect against injection. Fix: route through an `env:` block and reference the env var in the `run:` block:

```yaml
env:
  VAR: ${{ inputs.untrusted_value }}
run: |
  echo "$VAR"   # safe — runner expansion already finished; shell sees a literal string
```

Never interpolate `${{ expr }}` directly into a `run:` block when the source can be caller-controlled (workflow inputs, PR branch names, event payloads).

### Git flag injection via branch names

`git pull origin "$BRANCH"` with a crafted branch value like `--upload-pack=/tmp/evil` passes git option flags even when the shell variable is double-quoted (quoting blocks shell word-splitting but not git option parsing). Fix: always use `--` to terminate git option parsing before the refspec:

```bash
git pull origin -- "$BRANCH"
```

Apply this pattern to every git command that accepts a branch name sourced from workflow inputs, PR metadata, or external state.

### Step-scoped secret binding for high-value tokens

Secrets like `JULES_API_KEY` that are only needed for one step must be declared at the **step level**, not the job level. Job-level `env:` makes the secret available to all steps in the job (including `actions/checkout`, third-party actions, and error-handler steps) unnecessarily widening the attack surface:

```yaml
# Wrong — job-level secret leaks to all steps
jobs:
  example:
    env:
      JULES_API_KEY: ${{ secrets.JULES_API_KEY }}

# Correct — step-scoped secret
jobs:
  example:
    steps:
      - name: Run Jules SDK
        env:
          JULES_API_KEY: ${{ secrets.JULES_API_KEY }}
        run: bun run scripts/fleet/fleet-merge.ts
```

### `workflow_run` vs `check_suite` for event-driven triggers

Use `workflow_run` (trigger on a named workflow completing) not `check_suite: completed` for event-driven fan-out. `check_suite` fires for **every** CI suite on **every** branch — with 4+ suites per PR, GitHub's concurrency group silently drops the third trigger. `workflow_run` targeting a single named workflow produces exactly one trigger per CI cycle.

### `GITHUB_TOKEN`-authored events do not trigger downstream workflows

GitHub Actions intentionally suppresses workflow runs for events created by the default `GITHUB_TOKEN` — except `workflow_dispatch` and `repository_dispatch`. Applies to `push`, `pull_request`, `check_suite`, `issue_comment`, etc. So a pipeline where workflow A pushes to `main` via `GITHUB_TOKEN` and expects workflow B to fire on the resulting push will **silently no-op**.

**Fixes (in order of preference):** (1) GitHub App installation token via `actions/create-github-app-token` with `GH_APP_ID`/`GH_APP_PRIVATE_KEY` secrets — App-token pushes fire downstream workflows normally; (2) `workflow_dispatch` escape hatch with a fail-closed re-detection path that does not rely on `HEAD~1` diff; (3) `workflow_run` chaining (already preferred over `check_suite`). Canonical incident: Issue #310 (fleet Phase 2a→2b handoff, 2026-06-20).

## Interactive-only skills (autopilot guard)

The following skills require real-time interactive dialogue with the user. They **must not** run autonomously in autopilot mode:

- `idea-refine`
- `grill-me`

**Rule:** When either skill is invoked and `ask_user` returns "The user is not available to respond," immediately halt all skill processing. Do not produce variations, evaluations, decision logs, or output artifacts. Respond:

> "⚠️ **[skill-name]** is interactive-only and cannot run in autopilot mode. Press **Shift+Tab** to exit autopilot and re-run your request."

This rule takes precedence over any "work autonomously" instruction from the autopilot system.

## Operational patterns

### Research report output

When saving research reports (from `/research`, `Researching:` prefix, or any investigative analysis), write them to `docs/research/` in the repository root instead of the session-local folder. Use a slug derived from the research topic as the filename (e.g., `docs/research/elevenlabs-sdk-compatibility.md`). This keeps research artifacts version-controlled, shareable, and discoverable across sessions.

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

### Honor explicit review scope requests

When the user requests review of "all changes", "all N files", or specifies a commit range, review the full scope — do not silently narrow to recent files or a convenient subset. Use `git diff` or `git log` to enumerate the complete changeset, then partition into parallel subagent reviews if the scope exceeds what one pass can cover. If you must limit scope, state the limitation explicitly before starting ("reviewing 40 of 116 files in this pass; will continue in a follow-up"). For full-scope reviews, report a coverage statement up front (`reviewed X/Y files`, commit range) and return the full material finding set in one pass before remediation (do not stop after the first issue).

### "Fleet deployed" continuation signal

When the user sends "Fleet deployed" (or similar), it means they have pushed commits and are ready for the next planned phase to proceed. Treat it as a continuation signal: check tracker + plan state, take the first unfinished actionable item (`todos` non-`done`, then plan/checkpoint), and execute it immediately. Do not restart with a fresh broad audit unless no unfinished tracked items exist.

### Global long-session checkpoint guard

For any session (not only Fleet-deployed flows), when context ages beyond a practical boundary (for example >40 turns or spanning >24 hours), compact the working state before continuing broad work:
1. Create a short checkpoint-style handoff (completed work, open items, next actionable step).
2. Continue from the checkpointed plan/todo instead of re-deriving prior context from scratch.
3. Use this guard before launching broad audits, full-scope reviews, or heavy multi-skill passes.

### Micro-turn batching trigger

If the user sends repeated short acknowledgements/route markers (for example "agreed", "proceed", "fleet deployed", single-letter option replies), avoid one-step-at-a-time churn:
1. Consolidate pending decisions into a numbered decision block.
2. Execute selected items in one batch rather than requiring multiple micro-turn confirmations.
3. Preserve momentum by defaulting to the first unfinished actionable item when user intent is continuation.

### "Pickup where you left off" resume protocol

When the user says "pickup where you left off" (or equivalent typo/variant like "youleft"), immediately resume from durable state instead of re-discovery. Execute this exact sequence:
1. Read the latest checkpoint.
2. Run `git fetch origin` and confirm both local-ahead and remote-ahead state (`git log origin/main..HEAD --oneline` and `git log HEAD..origin/main --oneline`).
3. Identify the first unfinished actionable item from local tracking first (`todos` non-`done`; then `issue_work`/plan/checkpoint).
4. Continue from that item directly (not a fresh broad audit).

### Ready-for-agent issue orchestration protocol

When the user asks to work "open ready-for-agent issues", run this lane by default:
1. Enumerate open `ready-for-agent` GitHub issues and open PRs touching the same scope (dedup before coding).
2. For each issue, run a dedicated `verified-research` pass (one issue per pass) to confirm current codebase state and acceptance gaps.
3. Implement/remediate with subagents, then run the cross-functional review gate (`@code-reviewer`, `@test-engineer`, `@security-auditor`, `@documentation-engineer`).
4. Run `documentation-and-adrs` and `audit-knowledgebase-workspace` before claiming completion.
5. Reconcile local tracker state with live GitHub issue state, then close the issue or record why it remains open.

### Session-close verification bundle

After merging a PR (or when reporting merge readiness/completion), proactively provide one bundled status update that includes: (1) CI/check rollup state, (2) unresolved review-thread/comment count, and (3) issue/deferred-ledger reconciliation state. Do this without waiting for separate follow-up prompts for each status check.

Before the first `task_complete` in any implementation/audit session, provide the same closeout bundle even if no merge occurred, plus:
4. Documentation cascade check result (what needed updates vs what was already current).
5. `.github/` customization cascade check result (what needed updates vs none required).

### Cross-functional review as default post-implementation step

After non-trivial implementation work, **proactively run** a cross-functional review using parallel custom agent dispatch — do not wait for the user to ask. The standard pattern:
1. Dispatch `@code-reviewer`, `@test-engineer`, `@security-auditor`, and `@documentation-engineer` in parallel
2. Each agent reviews the recent commits against best practices, ADRs, and repo documentation
3. Consolidate findings and present as a unified report
4. Address findings before considering the work complete

This parallels the quality-pass-chain skill but uses custom agents for richer, domain-specific review.

**Hard rule: `task_complete` is blocked on implementation tasks** until `@code-reviewer`, `@test-engineer`, `@security-auditor`, and `@documentation-engineer` have all been dispatched and any P0–P2 findings remediated. Do not call `task_complete` for any session that created or modified `scripts/**`, `tests/**`, `.github/skills/**/logic/**`, or `.github/workflows/**` without having run this review first.

### Post-remediation docs/customizations audit pair

For any session that merged one or more PRs, run `documentation-and-adrs` and `audit-knowledgebase-workspace` **before the first `task_complete`** against the full landed range (`<first-merged-PR-base>..HEAD`, where `<first-merged-PR-base>` is the base commit of the first PR merged chronologically in that session on the target branch). File uncovered gaps as `ready-for-agent` follow-up issues and remediate P0–P2 findings in-session.

### Auto-remediate P0–P2 findings after cross-functional review

After completing a cross-functional review, automatically proceed to remediate all P0–P2 findings without waiting for user approval — the review itself is the approval gate. Present the findings report, then immediately start fixing them. Only pause for user input on P3+ (suggestions/style) or findings where the correct fix is genuinely ambiguous.

### Deferred findings issue ledger

When P3+ findings are intentionally deferred, create (or verify) a GitHub issue for each deferred item in the same session, then report a ledger: issue number, deferred item, and owner. If an item is intentionally not filed, state that explicitly with rationale.

### Deferred work issue-tracking applies beyond review findings

The deferred issue ledger rule is not limited to P3+ review findings. Any acknowledged-but-unimplemented item (audit drift, workflow/documentation/customization gap, scoped deferral, or partial implementation) must either be fixed in-session or tracked in a GitHub issue before task completion. Report the same ledger fields: issue number, deferred item, owner.

### Session-close deferred remediation ledger

Before closing any implementation/audit session, build a full deferred ledger (not just P3 review findings):
1. Enumerate acknowledged/deferred items from review outputs, ADR "deferred" sections, and session tracker rows.
2. Reconcile each item against live GitHub issue state (`gh issue view`).
3. If an item has no issue, open one in the same session and include it in the ledger.
4. Report one table: deferred item, issue number, and current issue status.

### `/chronicle improve` deterministic flow

When the user runs `/chronicle improve`, execute this sequence without improvising:
1. Read `.github/copilot-instructions.md`.
2. If `/chronicle improve` already ran in this session and no new evidence boundary exists (no new commit range, no new friction signal, and <10 new turns), run a delta amend pass instead of a fresh full improve pass.
3. Query `session_store` for recent repo-scoped sessions and friction signals using the two-pass strategy (see below).
4. Present 3-5 evidence-backed recommendations.
5. Ask which recommendations to apply.
6. If no selection arrives and execution continues autonomously, apply all proposed recommendations and state that assumption explicitly.
7. Update `.github/copilot-instructions.md` with only the selected recommendations.

### `/chronicle tips` deterministic flow

When the user runs `/chronicle tips`, execute this sequence:
1. Query `session_store` for repo-scoped workflow patterns using the two-pass strategy (see below).
2. Fetch Copilot CLI documentation to anchor feature recommendations.
3. Inspect repo-local custom surface (`.github/skills/**`, `.github/agents/**`) so recommendations reflect available capabilities.
4. Return 3-5 personalized, non-obvious workflow tips grounded in observed data (cite concrete patterns, counts, or session IDs).
5. Prefer capability and prompting improvements that reduce repeated coordination turns and improve first-pass execution quality. When in limited-evidence mode, ground all recommendations in observable patterns from this session only.

### `/chronicle cost-tips` deterministic flow

When the user runs `/chronicle cost-tips`, execute this sequence:
1. Query `session_store` for cost proxies (turn count, message length, checkpoint frequency/timing, repeated prompts, repeated large context payloads, and session duration).
2. Read representative turn history from high-cost sessions to identify root causes (not just aggregates).
3. Fetch Copilot CLI documentation and map findings to concrete controls (`/compact`, `/new`, `/usage`, `/model`, `/delegate`, `/fleet`, `/tasks`, `/after`, `/every`, `/ask`).
4. Return 3-5 evidence-backed cost recommendations with specific workflow changes and quantified savings estimates when possible.
5. If local store lacks token-level telemetry, state that limitation and recommend `/usage` plus cloud session store for exact token accounting. Switch to two-pass strategy: repo-scoped first, broader if 0 rows, limited-evidence if still 0.

**Two-pass session_store query strategy (applies to all /chronicle flows):** (1) Try repo-scoped query first (fast, precise). (2) If 0 rows returned, run broader query (recent history across repos, <7 days). (3) If still 0 rows, switch to "limited-evidence mode" — provide recommendations grounded in observable patterns within current session context only, with explicit telemetry gap acknowledgment at the start. Never fabricate claims about other sessions or repos when telemetry is unavailable.

### Multi-issue commit boundary discipline

In multi-issue orchestration sessions, do not carry a large mixed working tree across issues. After each issue-slice reaches green checks, commit and push that slice before starting the next one. Keep each commit scoped to one issue/remediation bundle (including its required tests/docs).

### GitHub CLI multiline body safety

For `gh issue create/edit` and `gh pr create/edit` with multiline markdown bodies, always use `--body-file` with a single-quoted heredoc. Avoid inline `--body` strings when content contains backticks or shell metacharacters.

### Executable-command doc drift guard

When editing documentation/instruction files that contain executable commands (especially `.github/copilot-instructions.md`, `docs/mvp-runbook.md`, and `docs/architecture.md`), verify each changed command in-session (or the closest repo-safe equivalent) before task closure. If a command cannot be executed in the current environment, open a tracking issue and mark the guidance as unverified in the session summary.

### "What skills should have been used?" is an execution directive

When a user asks **"what skills should have been used to validate these changes?"** (or any close variant), treat this as a directive to execute — not just an informational question. Immediately:
1. Identify the applicable skills for the change types in scope, including `audit-knowledgebase-workspace` when `.github/**` customizations or always-on context changed
2. Invoke `quality-pass-chain` when the change scope is non-trivial or touches code paths
3. Dispatch the corresponding custom agents in parallel (use `@code-reviewer`, `@test-engineer`, `@security-auditor`, `@documentation-engineer` as appropriate)
4. Collect results, present consolidated findings, and remediate P0–P2 findings before any completion signal

Do not answer with a list and stop. The question means "run them now," and `task_complete` is blocked until that execution lane finishes.

### "What documentation/customizations should have been updated?" is an execution directive

When a user asks **"what documentation should have been updated?"**, **"what documents should have been updated?"**, **"what customizations should have been updated?"**, or close variants (including `.github` customization wording), treat it as an execution directive. Immediately:
1. Determine the commit range in scope (`<last-reviewed-commit>..HEAD` when available).
2. Run `documentation-and-adrs` against that scope and produce concrete required doc updates.
3. Run `audit-knowledgebase-workspace` for `.github` customization drift in the same scope.
4. Return one consolidated cascade report (docs + customizations) with fixed vs. deferred items and reasons.

Do not answer these prompts with a speculative list only; execute the audit lane first.

### "What deferred work remains?" is an execution directive

When a user asks about deferred/acknowledged-but-unimplemented work (including typo variants such as `deffered`, `aknowledged`, `remediaiton`), treat it as an execution directive. Immediately:
1. Enumerate deferred items from session trackers/review outputs.
2. Reconcile each item with live GitHub issue state via `gh issue view`.
3. Create missing issues in-session for uncovered deferred items.
4. Return one final ledger table: deferred item, issue number, and live issue status.

Do not stop at narrative summaries for deferred-work prompts; complete reconciliation and issue coverage in the same response cycle.

### Grill-me decision logs are sufficient specs

When grill-me produces a complete decision log with resolved questions, treat that log as a sufficient spec for implementation. Do not require a separate spec-driven-development pass unless the scope is large enough to warrant formal task breakdown (5+ files, new module, or cross-cutting concern).

### Batch all review finding types in one remediation commit

When remediating review findings, batch all finding types (code, test, doc, security) into a single remediation commit rather than addressing them type-by-type in separate passes. A review that surfaces a code bug, a missing test, and a stale doc reference must land all three fixes together — not code first, tests later, docs last.

### Chronicle-improve dedup hygiene

When handling `/chronicle improve`:
1. Add a new instruction only when the pattern appears in at least 2 repository sessions.
2. Search `.github/copilot-instructions.md` first and amend an existing section in place when coverage already exists.
3. If a new rule supersedes an older one, remove or merge the older text in the same edit.
4. Prefer concise deltas over appending near-duplicate policy blocks.
5. Keep each `/chronicle improve` edit small by default (one new subsection or a compact in-place amendment) unless the user explicitly asks for broader restructuring.
6. When this file is the repeatedly touched surface in recent sessions, prioritize consolidation/pruning over adding new standalone sections.

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
