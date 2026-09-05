# Design Proposal: Infigraph for Knowledgebase Agent Guidance, Pre-commit, and CI

**Status:** Proposed

## Summary

Evaluate Infigraph as a tool that helps agents understand the `knowledgebase`
repository. The tool can help agents find symbols, relationships,
architecture, and change impact. It does not replace source inspection,
existing deterministic validators, or human review.

## Terms and abbreviations

- **MCT:** Medicare Coverage Tools.
- **CLI:** command-line interface.
- **MCP:** Model Context Protocol, an interface that allows an agent to call a
  tool server.
- **CI:** continuous integration.
- **PR:** pull request.
- **ADR:** architecture decision record.
- **API:** application programming interface.
- **Worktree:** a Git checkout that has its own files and branch state.
- **Graph:** the indexed Infigraph representation of source files and their
  relationships.
- **Graph identity and age:** the indexed commit must equal the commit being
  analyzed. Age is a separate retention/refresh constraint: the implementation
  must define the maximum acceptable age for an otherwise commit-matching
  index.
- **Blast radius:** the set of symbols or files that a change can affect.

The proposal combines three concerns within `knowledgebase`:

1. **Agent guidance:** tell agents when and how to use Infigraph.
2. **Developer workflow:** provide optional local checks. A commit must not
  depend on a graph service.
3. **CI analysis:** use graph-backed review and impact analysis as advisory PR
  evidence first. Add blocking gates only after the team measures accuracy.

## Problem

The `knowledgebase` repository contains executable Python and TypeScript
surfaces alongside documentation and governance. Agents must often rediscover
relationships by reading local instructions, searching text, reading many
files, and inferring dependency paths.

This process creates these costs:

- call and dependency relationships are expensive to reconstruct;
- repository-wide impact is difficult to assess consistently;
- affected-test discovery is easy to miss;
- every worktree may represent a different branch state; and
- putting detailed discovery procedure in always-on instructions would add
  instruction growth and duplicated guidance.

Infigraph provides a CLI for the initial integration. MCP may be evaluated in
a later phase, but is not part of the initial rollout or its acceptance
criteria.
Source files, tests, security tools, and repository governance remain the final
authority.

## Goals

- Make graph-assisted discovery available through the Infigraph CLI when the
  CLI is installed and the graph both matches the analyzed commit and meets the
  separate age limit.
- Keep the initial integration limited to `knowledgebase`; defer MCP and
  cross-repository analysis to later phases.
- Preserve fallback to `rg`, `grep`, `find`, source reads, and existing
  repository tools.
- Support branch-accurate analysis in local worktrees.
- Support comparison between a branch graph and a separately identified pull
  request base graph.
- Provide a repeatable pull-request review workflow.
- Keep local pre-commit checks within the repository's agreed latency limit.
- Do not require a remote service for local development.
- Avoid duplicating a large Infigraph procedure across future repositories.
- Report graph freshness, unsupported capabilities, and fallback use in agent
  output and CI artifacts.

## Non-goals

- Replacing Gitleaks, dependency auditing, Terraform validation, language
  linters, unit/integration tests, or branch protection checks.
- Treating an empty graph result as proof that a symbol or reference does not
  exist.
- Running a full multi-repository index on every commit.
- Sharing one mutable local graph between independent worktrees.
- Automatically blocking merges on uncalibrated complexity, dead-code, or
  impact findings.
- Assuming that Infigraph supports remote storage, webhook synchronization,
  authentication, or machine-readable output until the team verifies the
  feature against the approved Infigraph version and authoritative
  documentation.
- Requiring MCP servers in organizations or environments that prohibit them.
- Performing cross-repository orchestration or analysis during the initial
  rollout.

## Proposed instruction architecture

### Durable policy

If the team adopts this proposal, record the decision in a `knowledgebase`
ADR. Keep the enforceable rule short in the repository's instruction
templates. The policy must state:

- use the approved Infigraph CLI first for structural discovery when it is
  available and the graph meets the freshness limit;
- use source files and deterministic tools to verify findings that affect a
  decision;
- use repository search when the graph is absent, stale, incomplete, or not
  suitable for an exact text check; and
- never expose secrets or write graph state into the repository.

Put this policy in the `knowledgebase` governance layer, not in one agent
persona. Keep paths, index commands, exclusions, and runtime details in local
knowledgebase instructions.

### Skill-only initial guidance

Start with the reusable skill only. Do not add an always-on routing rule to
`.github/copilot-instructions.md` or `AGENTS.md` during the pilot. This keeps
the procedure at Locality 2, avoids unnecessary always-on token cost and
ADR-028 Locality-4 exceptions, and lets the pilot measure use before any
global instruction becomes permanent.

### Reusable skill

Create a knowledgebase skill at
`.github/skills/infigraph-code-intelligence/SKILL.md` for tasks involving:

- architecture discovery;
- debugging unfamiliar code;
- refactoring;
- API, route, or MCP tool changes;
- executable script and infrastructure impact analysis when applicable;
- test planning; and
- pull-request review.

The initial skill procedure must be CLI-only:

1. Check whether the approved Infigraph CLI is available and whether its
  verified command profile supports the requested task.
2. Record the current repository, branch, commit, and worktree.
3. Check the graph scope, require its indexed commit to equal the current
  commit, and evaluate the graph's age against the separate retention/refresh
  limit.
4. Use the CLI to find symbols, references, callers, callees, dependencies,
  or impact when the capability is supported.
5. Read the exact implementation and the tests for the changed code.
6. Report fallback use, stale data, unsupported capabilities, and the
  knowledgebase-only scope.
7. Run deterministic validation before making a recommendation.

The initial CLI-only skill is stateless. It records only the commit-bound CI
receipt; defer `save_session` and `get_latest_session` session continuity until
the pilot demonstrates value and a separate decision resolves retention,
storage, and access boundaries.

Wire the skill through the repository's normal skill discovery, lifecycle,
intent, and `CONTEXT.md` conventions. Specialized personas must reference the
skill rather than reproduce its procedure. Do not add an always-on routing rule
during the pilot.

### Specialized agents

Keep persona changes thin:

- `@code-reviewer`: use graph-backed review and impact evidence, then verify
  findings in source and tests.
- `@solutions-architect`: inspect architecture, file dependencies, and API
  surfaces within `knowledgebase`.
- `@test-engineer`: identify affected tests and coverage gaps.
- `@security-auditor`: combine graph evidence with established security
  validators; do not treat graph findings as a replacement for them.
- `@documentation-engineer`: use symbol and dependency context to identify
  documentation affected by implementation changes.

### Deferred MCP parity

MCP is outside the initial rollout. Do not require an MCP server, MCP adapter,
or CLI/MCP parity test for the pilot. If agent-facing MCP adoption is proposed
later, define the supported task categories and normalized parity tests in a
separate decision.

## Local worktree model

Scope local graph state to the indexed checkout:

```text
worktree-main/.infigraph/
worktree-agent-1/.infigraph/
worktree-agent-2/.infigraph/
```

Do not point multiple independently changing worktrees at one mutable local
`.infigraph/` directory. This can mix branch states, sessions, and caches.

Recommended behavior:

- keep `.infigraph/` ignored and uncommitted;
- create or refresh it on demand for each worktree;
- index incrementally after checkout when the indexer supports it;
- remove it when the worktree is removed; and
- retain it for long-lived worktrees when the storage cost is acceptable.

For branch-versus-base analysis, compare the current worktree `HEAD` graph
with a graph for the pull request base SHA supplied by the hosting platform.
The analyzed worktree `HEAD` SHA must equal the branch graph's indexed commit,
and the authoritative base SHA must equal the baseline graph's indexed commit.
The age of either graph is evaluated separately against the retention/refresh
limit. The baseline may be materialized from another checkout, but its commit
must be recorded and verified separately from the branch graph. Never use an
arbitrary local `main` checkout as a substitute for the authoritative PR base.

The PR head must incorporate current `main` before the complete receipt is
produced. CI-7 then rebuilds and binds the receipt to the updated head SHA.
Cross-repository graphs and central graph storage are deferred until a later
phase and must not affect the initial pilot.

## Pre-commit workflow

Pre-commit must remain fast with the Infigraph CLI. The wrapper may:

- detect whether source files covered by the check changed;
- report that the local graph is unavailable or stale;
- run one narrowly scoped security or structural check; and
- skip graph work for documentation-only or unrelated changes.

The hook must not perform a cross-repository index. It must not block a
commit only because an Infigraph interface is unavailable. The team must
document and measure any other blocking behavior before adoption.

For the knowledgebase, the hook must be added to `.pre-commit-config.yaml`
under the existing `repos: - repo: local` block. It must coexist with the
existing hooks governed by ADR-016 (locality-ratchet, frontmatter-validation,
detect-secrets, and others). The hook script must follow the `scripts/hooks/`
pattern and be registered in the pre-commit framework rather than running as
a parallel hook system.

## CI workflow

### Pull requests

Start with a non-blocking Infigraph analysis job for `knowledgebase`. Use the
standalone CLI. After the team verifies the installed Infigraph release, the
job can report:

- semantic or structural diff information;
- affected symbols and tests;
- caller/callee and dependency impact;
- API or route surface changes;
- security or taint findings;
- complexity changes; and
- dead-code or unused-reference findings.

The job must publish raw logs as separate CI artifacts. The wrapper must
normalize supported CLI results into the receipt schema and define exit
statuses.

For comparative CI analysis, materialize the PR commit and the recorded base
SHA in separate temporary directories. Give each checkout its own `.infigraph/`
state, never share mutable graph storage between them, and remove both
checkouts and graph directories when the job ends. The comparative receipt
must include the authoritative base SHA, the PR head SHA, the separately
indexed base commit, and the separately indexed head commit. It is valid only
when the indexed base commit equals the authoritative base SHA and the indexed
head commit equals the PR head SHA; graph age remains a separate
retention/refresh constraint.

Initial policy:

- publish review comments and artifacts as advisory results;
- fail the CI-7 job when required Infigraph analysis cannot be executed or
  cannot produce a valid receipt; and
- hand the result to the existing
  `cross-functional-review-evidence/<head-sha>.json` receipt as an optional
  `infigraph` section. CI-7 is not a second merge gate and remains
  non-blocking during the pilot. A failed CI-7 job must still preserve the
  conventional source-and-test review path.

When CI-7 reports a stale or unavailable graph, fail the CI-7 job, record that
state and the failure reason in the `infigraph` section of the existing
cross-functional review evidence receipt, and require conventional source and
test review. The merge gate must validate that the evidence receipt is bound to
the current PR head SHA and that its `infigraph` section, when required for the
change, is also commit-bound: its analyzed head SHA and indexed head commit
must equal that PR head SHA. Only then may the handoff be treated as complete;
the section's advisory findings do not need to be clean. Do not block the
merge for CI-7 during the pilot. Re-evaluate this policy only after the pilot has
measured availability, freshness, false positives, missed impacts, and
reviewer usefulness against a ratified promotion threshold.

For a qualifying code change, the existing cross-functional review merge-gate
validation must require proof that `infigraph-code-intelligence` ran and must
validate the commit-bound `infigraph` section before treating the evidence as
complete. In the pilot, qualifying changes are
limited to `scripts/**/*.py`, `.github/skills/**/logic/**/*.py`, and
`scripts/fleet/**/*.ts`. Workflow YAML and Markdown changes are excluded.
Documentation-only, test-only, generated, lockfile, and CI-only changes are
also initially exempt. The receipt proves that the skill ran; it does not
require findings to be clean.
If the baseline comparison fails, fail the CI-7 job and publish an incomplete
receipt with the failure reason. Preserve the conventional source-and-test
review path; do not block the pilot merge for graph infrastructure
availability.

An analysis that completes successfully may report advisory findings without
failing CI-7. Installation failure, unsupported required capabilities, stale
or missing graph state, timeout, command failure, malformed output, and any
other condition that prevents a valid analysis are CI-7 failures. The receipt
must distinguish `analysis_complete` from `analysis_unavailable` or
`analysis_failed`.
Do not create a second merge gate. CI-7 contributes a commit-bound optional
`infigraph` section to the existing
`cross-functional-review-evidence/<head-sha>.json` receipt, and the existing
cross-functional review gate remains the sole merge-time authority. Its
validation must reject an absent, stale, or SHA-mismatched section for a
qualifying change, while CI-7 itself remains non-blocking in the pilot. Run CI-7
on every qualifying pull-request update; only the receipt bound to the current
head SHA is valid at merge time. Its optional `infigraph` section contains only
the PR number, authoritative base SHA, PR head SHA, separately indexed base and
head commits, Infigraph version and CLI command profile, qualifying changed-file
list or hash, graph state, analysis timestamp and duration, summarized impacts,
fallback used, and explicit advisory status. The indexed base commit must equal
the authoritative base SHA, and the indexed head commit must equal the PR head
SHA. Do not place raw source, full graph exports, or verbose logs in the
receipt; publish those as CI artifacts when needed.

The `knowledgebase` pilot does not introduce GitHub merge queue. Before the
valid receipt is produced, the qualifying PR head must incorporate current
`main`; CI-7 then rebuilds the graph and binds its receipt to that updated head
SHA. Reconsider merge queue during the promotion review if concurrent merges
make exact merge-result validation necessary. If adopted later, CI-7 must also
run on `merge_group` and bind its evidence to the generated merge-group SHA.

After the team measures the results, consider required checks for security or
contract findings that meet the agreed precision threshold.

### Deferred post-merge and scheduled indexing

Do not build a continuously refreshed main-branch graph during the initial
pilot. After the pilot, a nightly or post-merge workflow may:

- index `knowledgebase`;
- consider cross-repository groups or contracts only after a separate rollout
  decision;
- record graph freshness and indexing failures; and
- publish an artifact or dashboard for agent and reviewer use.

Webhook-triggered reindexing, remote storage, namespacing, retention, and
concurrency require an explicit implementation design after the corresponding
Infigraph features are verified. Existing MCT webhook patterns may inform that
design but are not evidence that Infigraph can consume them directly.

## Initial rollout

1. Resolve the current approved Infigraph release during setup rather than
  assuming a historical version. Record the installed version, installation
  source, and checksum when available. Verify its CLI commands, index
  lifecycle, freshness metadata, output formats, licensing, and security model.
  Unsupported commands, flags, output formats, and exit-code assumptions are
  not used. Configure context compression level (`summary` or `aggressive`)
  in `.infigraph/config.toml` only if supported by the verified release. Defer
  MCP tool verification and CLI/MCP parity.
2. Add and wire the reusable CLI-only
  `.github/skills/infigraph-code-intelligence/SKILL.md` through the
  repository's normal skill discovery, lifecycle, intent, and `CONTEXT.md`
  conventions. Complete this wiring before the pilot begins; the skill must
  not depend on MCP.
3. Pilot advisory PR analysis in `knowledgebase` only, including branch-versus-
  PR-base comparison. Use qualifying changes to `scripts/**/*.py`,
  `.github/skills/**/logic/**/*.py`, and `scripts/fleet/**/*.ts` as the pilot
  sample. Exclude workflow YAML and Markdown during this phase; do not begin
  cross-repository rollout.
4. Measure runtime, stale-index rate, false-positive rate, missed-impact rate,
  and developer usefulness across at least 10 PRs.
5. Defer nightly or post-merge main-branch indexing until the pilot validates
  value and graph-state retention requirements.
6. Add thin repository-specific instruction sections, without adding an
  always-on routing rule during the pilot.
7. Add an optional lightweight local warning hook.
8. Promote only checks that meet the agreed precision threshold to required CI
  status.

The team must make an explicit post-pilot decision on whether Infigraph remains
advisory or becomes required. That decision must be based on the recorded pilot
measures and a ratified promotion threshold; it must not be inferred from a
single successful run or the absence of findings. Promote the receipt
requirement only after at least 10 qualifying pilot PRs show all of the
following: a commit-bound receipt is produced for at least 95% of qualifying
PRs, median runtime stays within the agreed budget, reviewers identify material
impact or validation value, and stale or unavailable graph state always
preserves the conventional source-and-test review path. Individual Infigraph
findings remain advisory until separately calibrated.

The target operating model is:

> lightweight local warnings → comprehensive PR review → authoritative
> nightly/main-branch graph

The initial 10-PR pilot uses the CLI only and is limited to `knowledgebase`.
MCP is not a prerequisite for the pilot or for evaluating whether the evidence
receipt should become required. Before any agent-facing MCP adoption or
cross-repository rollout, the team must separately verify the interface,
organizational approval, and any required normalized parity.

## Post-initial feature roadmap

After the 10-PR pilot validates the initial integration, consider these
Infigraph features in subsequent phases:

### Phase 2: Cross-repository analysis

- Multi-repo groups (`group_create`, `group_add`, `group_index`) for
  cross-service Cypher queries.
- SCIP integration for compiler-grade type enrichment in TypeScript, Python,
  and Go repositories.
- Cross-service HTTP dependency detection (`group_deps`).

### Phase 3: Developer experience

- Web UI at `localhost:9749` for graph exploration and debugging.
- Sequence diagram generation (Mermaid) from call graphs.
- Design pattern detection (Singleton, Factory, Observer, Strategy).
- Export formats (Neo4j Cypher, GraphML, JSON) for external tooling.

### Phase 4: Test engineering

- Test context generator for pytest, Jest, and Go testing frameworks.
- Per-file coverage analysis (`get_test_coverage`).

### Phase 5: CI quality gates

- CI check configuration via `check.toml` (security, complexity, dead-code
  thresholds).
- LLM-augmented review (requires external LLM API; separate security review
  needed).

Each phase requires validation against the same precision threshold used for
the initial adoption. Features that require external APIs or team-wide servers
require separate security review before deployment.

## Open questions and validation requirements

- What exact Infigraph CLI commands, flags, exit codes, and output formats are
  available in the current approved release?
- How does the tool represent index freshness? What is the maximum allowed age?
- Does indexing support the Python and TypeScript surfaces included in the
  `knowledgebase` pilot?
- Where does the tool store graph data, embeddings, sessions, and caches? Can
  the operator configure these locations?
- Is `.infigraph/` automatically created, safely concurrent, portable, and
  suitable for per-worktree use?
- What machine-readable output and exit statuses are stable for CI?
- Does Infigraph provide an official GitHub Action, Jenkins integration, or
  reusable CLI wrapper?
- How does the tool handle secrets, source retention, and access control?
- Can branch and pull-request graphs be isolated from the selected PR-base
  graph?
- What is the supported webhook or event-driven reindex model, if any?
- Which findings are deterministic? Which findings are advisory or model-based?

Until these questions are answered from authoritative documentation and a
working pilot, Infigraph guidance must remain opt-in and fallback-friendly.

## Prototype-derived scope recommendations

Five throwaway state-model prototypes explored the proposed integration
boundaries. They model policy choices; they do not verify Infigraph's actual
CLI, MCP, or index behavior. Their conclusions should narrow the initial
pilot until implementation evidence supersedes them:

- **CI-7:** Start advisory. Return exit `0` when analysis completes, including
  neutral and warning findings. Return nonzero when required analysis cannot
  run or cannot produce a valid receipt. Keep the job non-blocking during the
  pilot, and treat graph infrastructure unavailability as a distinct reported
  failure state, not a finding. For qualifying code changes, contribute the
  result to the existing commit-bound cross-functional-review evidence
  receipt; do not introduce a separate receipt gate.
- **Pre-commit:** Use a fast docs-only skip path and targeted checks with a
  warm graph. When the graph is stale or unavailable, use conservative
  changed-file checks rather than blocking or indexing the repository.
- **Worktrees:** Keep graph state and refresh locks per worktree. A fresh
  graph skips refresh; an expired lock can be recovered by the next requester.
- **Locality 4:** A routing-rule edit is allowed only with paired equivalent
  deletion or a cited `Locality-4-Justification:` trailer. Non-Locality-4
  edits are outside this guard.
- **Skill routing:** Wiki retrieval/topology work and code-symbol analysis are
  separate routes. A request connecting wiki content to code uses both;
  contradictory cross-domain wording requires human clarification.

## Conflict and tension matrix

The initial `knowledgebase` review found no broad prohibition against Infigraph.
Cross-repository conflicts and governance tensions are outside the initial
rollout and must be revisited only if later adoption is proposed.

### Deferred compatibility review

| Repository | Source | Issue |
|---|---|---|
| `mct-ai-eoc` | [`docs/adr/0002-module-import-dag.md`](https://github.com/adhocteam/mct-ai-eoc/blob/381ccfa98f28dc7a069e354c8942030a0a966100/docs/adr/0002-module-import-dag.md) | Deferred. If `mct-ai-eoc` is considered for adoption later, confirm that graph-first discovery does not conflict with its convention-based import policy. |

### Deferred governance considerations

| Area | Source | Issue |
|---|---|---|
| CLI runtime truth | [`medicare-pp-cli/SKILL.md`](https://github.com/adhocteam/medicare-pp-cli/blob/3604dbf9088a4a8424f6e7f6006ed50924810deb/SKILL.md), [`internal/cli/agent_context.go`](https://github.com/adhocteam/medicare-pp-cli/blob/3604dbf9088a4a8424f6e7f6006ed50924810deb/internal/cli/agent_context.go) | This repository teaches agents to treat `agent-context`, `which`, and CLI runtime discovery as authoritative. Infigraph must run beside this model, not supersede it. |
| Instruction locality | `knowledgebase` ADR-028 | Every addition to always-on instruction files must follow the Locality-4 process: paired deletion or a locality justification trailer. |
| Skill placement | [`oc-mct-api`](https://github.com/CMSgov/oc-mct-api/tree/f77cef5a96fa7a24784c11c0b31cf07bdff1d49f), [`oc-mct-frontend`](https://github.com/CMSgov/oc-mct-frontend/tree/15a859f6c373a8485d8baec014c1e7a3e1db14e2), [`activate-copilot`](https://github.com/adhocteam/activate-copilot/tree/f8cacf1b20689c984e535bc02e6a3f9a6bc9a5c3), [`mct-junebug`](https://github.com/adhocteam/mct-junebug/tree/81c8cbbfddcfc466b7d5a3a9d1cff5e04a102692) | These repositories use different AI-guidance models: agents, skills, templates, or no AI layer. The Infigraph skill must follow each repository's established tier structure. |
| CI ownership | `knowledgebase` ADR-004, ADR-015, ADR-016 | No current ADR defines an Infigraph CI lane, artifact schema, or exit statuses. |
| Graph state | `knowledgebase` ADR-005, ADR-031 | Freshness, worktree isolation, storage, and lock behavior are not ratified. |
| Security | `knowledgebase` ADR-012, ADR-021, ADR-036 | No ADR defines Infigraph authentication, storage locations, retention, or cross-repository boundaries. |
| Cross-repository rollout | `knowledgebase` `AGENTS.md`, [`activate-copilot` ADR-001](https://github.com/adhocteam/activate-copilot/blob/f8cacf1b20689c984e535bc02e6a3f9a6bc9a5c3/docs/dev/adrs/ADR-001-agent-instructions-skills-files.md), [`activate-copilot` ADR-004](https://github.com/adhocteam/activate-copilot/blob/f8cacf1b20689c984e535bc02e6a3f9a6bc9a5c3/docs/dev/adrs/ADR-004-activate-sharing-structure.md) | No shared policy establishes whether guidance is copied per repository, distributed through templates, or maintained centrally. |

### Repositories without AI-guidance layers

The initial rollout does not require any other repository to add an
AI-guidance surface. Repository-specific instruction placement and exceptions
are deferred until a future cross-repository rollout is separately approved.

## Adoption decision gates

This proposal remains **Proposed**. No repository should add graph-first
guidance until these gates pass:

1. The `knowledgebase` ADR or governance document resolves CLI placement and
  pilot behavior.
2. The knowledgebase ADR sequence below is ratified.
3. The `knowledgebase` pilot completes at least 10 PRs with measured results.
4. The team separately approves any future repository adoption.

For [`mct-ai-eoc`'s import DAG policy](https://github.com/adhocteam/mct-ai-eoc/blob/381ccfa98f28dc7a069e354c8942030a0a966100/docs/adr/0002-module-import-dag.md),
the team should confirm that graph-first discovery does not conflict with the
convention-based import policy.

For [`medicare-pp-cli`'s runtime discovery model](https://github.com/adhocteam/medicare-pp-cli/blob/3604dbf9088a4a8424f6e7f6006ed50924810deb/internal/cli/agent_context.go),
the team must define whether Infigraph runs before, after, or beside the
existing CLI runtime discovery model.

## Required ADR sequence

Ratify these ADRs in the knowledgebase before normative adoption:

1. **ADR: Infigraph CLI integration policy.** Define the supported analysis
  tasks, verified command profile, and fallback rules for the pilot.
2. **ADR: Infigraph graph state, freshness, worktree isolation, locks, and
   security.** Define storage locations, freshness limits, lock paths, stale
   recovery, and source retention.
3. **ADR: Infigraph CI lane (CI-7) definition.** Amend ADR-004 to add CI-7
   (`tp-infigraph-analyst`) as a read-only advisory lane. Define artifact
   schema, exit statuses, and blocking rules.
4. **ADR: Infigraph pre-commit integration.** Add the Infigraph hook to the
   existing `.pre-commit-config.yaml` under the `repos: - repo: local` block.
   Define file filters, time budget, and skip conditions.
5. **ADR: Infigraph cross-repository rollout and template distribution.**
   Define whether guidance is copied, distributed through templates, or
   maintained centrally.
6. **Compatibility statement for the pinned `mct-ai-eoc` import-DAG reference**
  is deferred with all other cross-repository adoption work.

## Repository adoption paths

### Knowledgebase governance

- Ratify the ADR sequence above.
- Add the reusable skill at `.github/skills/infigraph-code-intelligence/SKILL.md`.
- Add a write-surface matrix row in `AGENTS.md` for any `logic/**` scripts in
  the skill directory.
- Add the Infigraph pre-commit hook to `.pre-commit-config.yaml` under the
  existing `repos: - repo: local` block.
- Do not duplicate existing wiki-focused skills (`retrieve-from-index`,
  `check-link-topology`, `search-and-discovery-optimization`). Infigraph
  targets code symbols; these skills target wiki pages. They coexist without
  overlap.

### Future repository adoption

No other repository receives Infigraph CI, hooks, skills, or routing changes in
the initial rollout. A future adoption proposal must define its own scope,
instruction placement, deterministic-check precedence, and cross-repository
boundaries.

## Knowledgebase conflict and augmentation analysis

This section documents how Infigraph features relate to existing knowledgebase
capabilities. It informs the integration design and prevents accidental
replacement or duplication of existing surfaces.

### No conflicts

These Infigraph capabilities have no equivalent in the knowledgebase:

| Infigraph capability | Existing knowledgebase equivalent | Assessment |
|---|---|---|
| Code symbol search | None; existing skills search wiki pages, not code | No conflict |
| Call graph tracing | None; `check-link-topology` traces wiki page links, not code calls | No conflict |
| Code impact analysis | None; no existing code dependency analysis | No conflict |
| Test context generation | None; `test-driven-development` is procedural, not graph-backed | No conflict |

### Governance integration points

These existing governance mechanisms require coordination:

| Mechanism | Constraint | Required action |
|---|---|---|
| ADR-028 locality ladder | Locality 4 additions require paired deletion or `Locality-4-Justification:` trailer | Skill routing rule must comply |
| ADR-004 CI workflow governance | Defines CI-1 through CI-6 | Infigraph advisory lane requires CI-7 definition via ADR amendment |
| ADR-016 pre-commit governance | All hooks use `.pre-commit-config.yaml` framework | Infigraph hook must integrate, not replace |
| AGENTS.md write-surface matrix | Every executable surface requires a matrix row | Skill `logic/**` scripts need entries |

### Augmentation opportunities

These existing skills could use Infigraph data in future phases:

| Existing skill | Potential augmentation |
|---|---|
| `retrieve-from-index` | Route to Infigraph for code symbol lookups when wiki pages reference source files |
| `improve-codebase-architecture` | Use Infigraph design pattern detection and dependency analysis |
| `code-review-and-quality` | Use Infigraph impact analysis to identify affected tests and callers |
| `check-link-topology` | Cross-reference wiki page links with code file existence via Infigraph index |

### Existing skills that must not be replaced

These skills target wiki pages and editorial content. They are not superseded
by Infigraph and must remain unchanged:

- `retrieve-from-index` — wiki retrieval, not code search
- `update-index` — wiki index refresh, not code index
- `search-and-discovery-optimization` — wiki discoverability review
- `suggest-backlinks` — wiki reciprocal link suggestions
- `check-link-topology` — wiki page link graph, not code call graph

### Citation and validator boundary

External repository references in this proposal use GitHub URLs pinned to a full
commit SHA. They are immutable references for this document; they are not
knowledgebase `SourceRef` entries. The current local SourceRef validator
(`scripts/hooks/check_sourceref_format.py`) only scans staged `wiki/**`
Markdown through the pre-commit file filter, checks the shape of `repo://`
tokens, and skips frontmatter and fenced code. It does not validate ordinary
links in `docs/**`, resolve GitHub URLs, verify that a linked commit exists, or
enforce that an external URL is commit-bound. Those stronger guarantees remain
requirements for a future validator or implementation check, not behavior this
proposal claims already exists.

## Related material

- Infigraph repository: <https://github.com/intuit/infigraph>
- Infigraph documentation site: <https://intuit.github.io/infigraph/>
- MCT instruction locality policy: `docs/decisions/ADR-028-instruction-locality-ladder.md`
- MCT pre-commit governance: `docs/decisions/ADR-016-pre-commit-hooks-governance.md`
- MCT control-plane layering: `docs/decisions/ADR-007-control-plane-layering-and-packaging.md`
- MCT write concurrency guards: `docs/decisions/ADR-005-write-concurrency-guards.md`
- MCT split CI workflow governance: `docs/decisions/ADR-004-split-ci-workflow-governance.md`
- MCT extended CI trust model: `docs/decisions/ADR-015-extended-ci-trust-model.md`
- `mct-ai-eoc` import DAG policy: [`docs/adr/0002-module-import-dag.md`](https://github.com/adhocteam/mct-ai-eoc/blob/381ccfa98f28dc7a069e354c8942030a0a966100/docs/adr/0002-module-import-dag.md)
- `medicare-pp-cli` agent context: [`internal/cli/agent_context.go`](https://github.com/adhocteam/medicare-pp-cli/blob/3604dbf9088a4a8424f6e7f6006ed50924810deb/internal/cli/agent_context.go)
- `activate-copilot` instruction placement: [`docs/dev/adrs/ADR-001-agent-instructions-skills-files.md`](https://github.com/adhocteam/activate-copilot/blob/f8cacf1b20689c984e535bc02e6a3f9a6bc9a5c3/docs/dev/adrs/ADR-001-agent-instructions-skills-files.md)