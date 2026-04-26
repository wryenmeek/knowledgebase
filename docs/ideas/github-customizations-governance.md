# `.github/` Customization Governance Parity

**Status:** Idea — ready for planning  
**Origin:** idea-refine session, 2026-04-25  
**Research basis:** [`session-state/research/how-are-our-github-customization-files-monitored-m.md`](../../.copilot/session-state/0c7cee66-37cd-4dfb-bbfc-d9639001dc7c/research/how-are-our-github-customization-files-monitored-m.md)

---

## Problem Statement

*How might we make silent drift in `.github/` development-workflow files detectable, preventable, and self-correcting — at the same confidence level as wiki governance — without adding ceremony that discourages contributors from maintaining these files?*

The research baseline: skill `logic/` files have 4-layer automated governance (pre-commit + pytest + CI + AGENTS.md matrix). Agent personas, prompts, hooks, and `copilot-instructions.md` have essentially none. The most painful failure mode identified: **agent personas drift from the skills they claim to use** — a semantic consistency problem that current structural checks cannot catch.

---

## Recommended Direction

**One semantic graph engine. Two outputs: gate and heal.**

The core insight: all three value-delivering directions (semantic graph, governance rail extensions, self-healing repair) share the same primitive — a cross-reference graph that maps:

```
agent personas → skills they claim to use
                         ↓
               commands in copilot-instructions
                         ↓
                  scripts on disk
```

Build that graph *once* and wire it to two outputs:

1. **Pre-commit + CI gate** — blocks broken references from landing in main
2. **Scheduled repair workflow** — detects drift that slips through (or arrives via non-commit paths) and opens a fix PR for human review

V3-style governance rails are applied *selectively*, not uniformly:
- `hooks.json` — broken JSON silently disables all lifecycle automation; schema validation is 20 lines and extremely high ROI
- Agent persona frontmatter — extend the existing SKILL.md frontmatter pre-commit hook to cover personas; same pattern, trivial addition

Prompts get link-resolution checking only. `copilot-instructions.md` is treated as a **test contract source** — its skill names and commands are extracted and validated, not wrapped in frontmatter governance.

The self-healing loop is real but bounded: the healer produces PRs for human review and auto-commits nothing. Drift is split into two buckets:
- **(a) Resolvable** — broken reference where a candidate replacement exists (fuzzy skill-name match, script at a new path) → drafted fix in the PR
- **(b) Ambiguous** — structural breaks requiring judgment → labeled issue (`drift:needs-review`) with full context

---

## Key Assumptions to Validate

- [ ] **Skill references in agent personas are extractable** — The `## Required skills / upstream references` section and backtick-formatted skill names cover ~80% of references. *Validate by auditing 5 agent files before building the parser. If prose format is inconsistent, the graph engine needs a multi-strategy extractor.*
- [ ] **`copilot-instructions.md` skill/command references are consistently formatted** — The lifecycle mapping section uses skill names in a structured table; `python3 scripts/` commands are consistently formatted. *Validate with a single grep pass before building the extractor.*
- [ ] **Fleet-dispatch PR pattern is adaptable for framework repairs** — The existing `fleet-dispatch.yml` assumes Jules sessions; a lightweight standalone repair workflow may be simpler. *Check before committing to the fleet pattern.*
- [ ] **Weekly repair cycle is acceptable latency** — If agent-skill drift is blocking agent work (not just aesthetically wrong), a weekly schedule is too slow. *Validate: has broken persona → skill reference ever actively caused an agent to fail? If yes, push-triggered is needed.*

---

## MVP Scope

Three deliverables, in dependency order:

### Deliverable 1 — `test_github_customizations.py`

Single test file added to `tests/kb/`. This is the graph engine expressed as pytest. Covers:

- **Agent personas** (`tests/kb/test_github_customizations.py`): Parse all `.github/agents/*.md`, extract skill names from `## Required skills / upstream references` sections and backtick-formatted references; assert each named skill exists as `.github/skills/<name>/SKILL.md`
- **`copilot-instructions.md`**: Extract all `python3 scripts/...` commands; assert each script file exists. Extract all skill names from the lifecycle mapping table; assert each exists as a skill directory.
- **`.github/hooks/hooks.json`**: Assert valid JSON; assert required keys (`hooks`, known event names: `SessionStart`, `PreToolUse`, `PostToolUse`, `Stop`); assert each referenced shell script path resolves to a real file.
- **`.github/prompts/*.prompt.md`**: Assert all `[text](path)` links resolve to real repo files.

Runs in CI-2 (already runs `pytest tests/`). Zero new infrastructure required.

### Deliverable 2 — Frontmatter + hooks.json pre-commit guards

- **Extend `check_frontmatter.py`**: Cover `.github/agents/*.md` — require `name` and `description` frontmatter fields (same fields as `SKILL.md`, same hook, ~15-line addition). Add `updated_at` as recommended but non-blocking for now.
- **New `check_hooks_json.py`** pre-commit hook: validate JSON syntax + required structure + shell script file existence. Wire in `.pre-commit-config.yaml`.
- Add both to AGENTS.md write-surface matrix as read-only surfaces.
- Add `scripts/hooks/**` test expectations to `test_framework_write_surface_matrix.py`.

### Deliverable 3 — `github-customizations-freshness.yml` scheduled workflow

Weekly GitHub Actions workflow (or push-triggered on `.github/**` changes) that:

- Runs the same graph-building logic as the test file (imported from a shared module)
- Outputs a structured drift report (JSON, not prose)
- For **resolvable drift**: opens a PR with a specific proposed fix and `auto:framework-repair` label
- For **ambiguous drift**: opens a labeled issue (`drift:needs-review`) with full context of what changed and what it references
- Never commits directly to main — all repairs are human-reviewed PRs

---

## Not Doing (and Why)

- **Full AGENTS.md matrix rows for agent/prompt files** — They don't execute code. The matrix is for write surfaces. Adding doc-only rows adds noise without governance value.
- **Governed write path (lock + approval) for agents and prompts** — These are not wiki-style knowledge artifacts with provenance requirements. The ceremony is appropriate for knowledge content; it's overkill for framework documentation.
- **Auto-merge repair PRs** — Self-healing means *detecting and proposing*, not committing autonomously to framework files. Human review at the PR stage is the right boundary.
- **Frontmatter governance for `.github/prompts/`** — Prompts change rarely, are low-risk, and adding frontmatter would disrupt the prompt format Copilot reads. Link-resolution checking is sufficient.
- **`copilot-instructions.md` frontmatter** — Would disrupt the format the Copilot runtime reads. Treat it as a contract source for validation, not a governed artifact with its own metadata lifecycle.
- **Content validation for skill SKILL.md** — Out of scope. The question is whether *references to* skills are consistent; what skills *say* is a separate editorial governance concern.
- **Transitive reference validation** — MVP validates direct references only. (Agent A uses Skill B which references Script C — C is not validated in MVP.)

---

## Open Questions

- What is the right fuzzy-match threshold for "this broken reference is probably this renamed skill"? Levenshtein distance, or check for a skill with a substring match?
- Should `test_github_customizations.py` stand alone or be integrated into `test_framework_skills.py`? (Standing alone keeps concerns separated and is the safer default.)
- Should the repair workflow trigger on push to `.github/**` (fast feedback, more runs) or remain weekly (lower noise, simpler scheduling)?
- Does the graph engine need to handle the 3 agent personas (`security-auditor`, `code-reviewer`, `test-engineer`) currently missing from `test_framework_agents.py::ALL_PERSONAS`? Or is adding them to that test a separate (simpler) fix?
- Should `updated_at` in agent frontmatter be enforced (blocking) or advisory in MVP? Advisory reduces friction during the migration period.
