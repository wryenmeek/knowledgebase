# ADR-017: Two-category agent persona taxonomy (kb-workflow / dev-support)

## Status
Accepted

## Date
2026-04-27

## Context

The repository grew from a small set of wiki-curation personas to 17 agent
persona files serving two distinct purposes:

1. **Wiki governance personas** — agents that operate within the ingest →
   verification → policy → synthesis → topology → maintenance pipeline.
   These are sequenced, fail-closed, and governed by the write-surface matrix.

2. **Development support personas** — agents that provide code review,
   security auditing, test strategy, documentation engineering, architecture
   review, and framework maintenance. These operate on code, not wiki content.

Without explicit category labels, tooling and documentation treated all 17
personas identically. This created two problems:

- **Routing confusion:** operators invoking agents had no lightweight signal
  to distinguish "this agent affects the knowledge pipeline" from "this agent
  reviews code."
- **Test fragmentation:** framework tests had to hard-code which agents belong
  to which governance tier, without a queryable metadata field to anchor on.

Renaming agents (e.g., prefixing wiki agents with `kb-`) was considered but
rejected: existing agent names are well-established in CI workflows, skill
references, and operator muscle memory; a rename would require a sweep across
all consuming surfaces with no governance benefit beyond what a `category`
field provides.

## Decision

All agent persona files carry a `category` frontmatter field with one of two
values:

- **`kb-workflow`** — the agent operates in the knowledgebase curation
  pipeline (ingest, evidence, policy, synthesis, topology, maintenance,
  quality). These agents are sequenced, write-gated, and governed by
  ADR-005 lock semantics and the write-surface matrix.

- **`dev-support`** — the agent provides development tooling (code review,
  security, testing, documentation, architecture, framework). These agents
  operate on code and framework files, not wiki content. They are not part
  of the wiki governance lane.

Current assignments:

| Category | Personas |
|---|---|
| `kb-workflow` | knowledgebase-orchestrator, source-intake-steward, evidence-verifier, policy-arbiter, synthesis-curator, query-synthesist, topology-librarian, entity-resolution-and-canonicalization, maintenance-auditor, change-patrol, quality-analyst |
| `dev-support` | code-reviewer, security-auditor, test-engineer, documentation-engineer, solutions-architect, framework-engineer |

The `category` field is optional per `check_frontmatter.py` (it does not
block a commit if missing) but is present on all 17 current personas and is
enforced by `tests/kb/test_framework_agents.py`.

## Alternatives Considered

### Agent name prefixes (e.g., `kb-orchestrator`, `dev-code-reviewer`)

- **Pros:** Category is visible in the agent filename itself; no frontmatter
  needed.
- **Cons:** Requires renaming all existing agents; breaks references in CI
  workflows, skill files, `using-agent-skills/SKILL.md`, and operator
  documentation; no governance benefit over a metadata field.
- **Rejected:** Rename cost far outweighs the discoverability benefit.

### Separate agent directories (`.github/agents/kb/` and `.github/agents/dev/`)

- **Pros:** Physical separation; agents are visually grouped.
- **Cons:** Same rename cost; breaks existing path-based references; adds
  directory nesting without runtime benefit.
- **Rejected:** Same as above.

### No formal category distinction

- **Pros:** Simpler schema; no migration needed.
- **Cons:** Tooling cannot filter agents by governance role; test suite must
  hard-code persona lists without a queryable field; routing documentation
  cannot distinguish lane membership from development support.
- **Rejected:** Category is needed for both test assertions and routing clarity.

## Consequences

- `tests/kb/test_framework_agents.py` asserts that all `kb-workflow` personas
  have `category: kb-workflow` and all `dev-support` personas have
  `category: dev-support`. New personas must be assigned a category at
  creation time.
- Routing documentation in `using-agent-skills/SKILL.md` organizes personas
  by category.
- `docs/architecture.md` persona roster table includes a Category column.
- Adding a third category value requires updating: `AGENTS.md` controlled
  vocabulary, `tests/kb/test_framework_agents.py` assertions, and this ADR.
- The `category` field does not affect runtime behavior — it is metadata for
  documentation, testing, and operator routing only.

## References

- `AGENTS.md` § Agent personas — `category` field controlled vocabulary
- `docs/architecture.md` — persona roster table with Category column
- `tests/kb/test_framework_agents.py` — category enforcement tests
- `.github/skills/using-agent-skills/SKILL.md` — category-organized routing table
- `docs/decisions/ADR-007-control-plane-layering-and-packaging.md` — persona role in control-plane model
