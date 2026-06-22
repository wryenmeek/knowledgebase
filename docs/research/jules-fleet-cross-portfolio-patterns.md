---
scope: research
last_updated: 2026-06-21
---

# Jules-based fleet patterns across the operator portfolio

Cross-portfolio research synthesis from 2026-06-21, motivated by issue #82 (Jules dispatch outage 2026-05-26 → 2026-06-19), issue #341 (architectural fallback gap), and issue #342 (silent-revert PR defensive layer).

This document captures evidence-bound findings about how three sibling repositories (`wryenmeek/hot-springs-island`, `wryenmeek/vscode-genai`, `wryenmeek/Scribe`) handle the same class of Jules-fleet operational problems we are solving in `wryenmeek/knowledgebase`. It is the **source of truth** for the design rationale behind the Tier 0/1/2/3 plan distributed across issues #345–#351; the ideas-umbrella `docs/ideas/fleet-defensive-layer-and-label-driven-dispatch.md` references this artifact for evidence.

## Headline finding

**No repository in the operator's portfolio runs a multi-provider implementation-agent abstraction.** `knowledgebase`, `hot-springs-island`, `vscode-genai`, and `Scribe` are all Jules-first for implementation work. Scribe's Gemini workflows are scoped to triage / review / comment-trigger only — not to implementation. This means our Tier 3 question ("should we abstract over multiple implementation providers?") has no prior art to lift from, and the deferral until 2026-07-21 is empirically justified.

## Threat model evidence — Scribe's bot-revert audit (most consequential finding)

Scribe ran a 90-day audit of `Jules-bot`-authored commits and discovered **2 silent-revert PRs in 81 commits (2.5% rate)**:

| Date | PR title | Silently deleted | Surface |
|---|---|---|---|
| 2026-04-16 | `bolt: optimize set conversion` | 2,474 lines | `docs/strategies/` |
| 2026-06-03 | `perf: ...` | 703 lines | `docs/architecture/` |

Both PRs used **benign Conventional Commits prefixes** that masked bulk deletion under titles a routine review would not flag. Both passed Scribe's review processes because nothing in the workflow inspected scope-vs-diff alignment.

Source: `repo://wryenmeek/Scribe/docs/project-history/2026-Q2/bot-revert-audit-jules-2026-06-issue-755.md` (pinned at audit time).

**Applied to our repo:** zero silent-revert PRs observed in our `agents/issue-*` history as of 2026-06-21. But Scribe's 2/81 base rate implies ~25% cumulative probability across the next dozen merged Jules PRs (`1 - (1 - 0.025)^12 ≈ 0.26`). The Tier 0 defensive layer (issues #345 / #346 / #347 / #351) exists to close this window **before** it produces our first incident, not after.

## Pattern catalog

### Pattern 1 — Stale bot-branch sweep (Scribe)

- Source: `repo://wryenmeek/Scribe/.github/workflows/sweep-stale-bot-branches.yml@<pin SHA at port time>`
- Mechanism: nightly cron enumerates refs matching narrow bot-author patterns, filters to >Nd old with no open PR, deletes via `git push --delete origin`.
- Scribe configuration: 7-day stale threshold, real-delete mode.
- Our adoption (issue #346 / #351): **14-day threshold (more conservative)**, dry-run mode for 14 nights, environment-approval gate on flip to real-delete, branch-name argv discipline mandated, post-filter exclude blocklist as defense-in-depth.
- Branch-pattern divergence: Scribe uses `jules/*`; we use `agents/issue-*` for our fleet convention (mixed authorship). The sweeper's allowlist regex excludes `agents/issue-*` deliberately because review can take weeks.

### Pattern 2 — Commit-scope check (Scribe → us with modifications)

- Source: `repo://wryenmeek/Scribe/.github/workflows/commit-scope-check.yml@<pin SHA at port time>`
- Scribe mechanism (Gate A): assert PR title's Conventional Commits scope matches the paths the diff touches.
- Our problem: we don't enforce Conventional Commits, so Gate A is unusable verbatim.
- Our substitution (issue #347): **Gates B + C** (sensitive-paths-vs-title + deletion-ratio with verified `Reverts:` trailer). Gate B uses word-boundary token regex (NOT substring match — `wiki` must not match `wikipedia`). Gate C requires the `Reverts:` trailer to reference an existing issue/PR or a main-ancestor SHA in last-commit footer or last paragraph (NOT anywhere in body — that's trivially forgeable).
- Both gates apply to all PRs, not just bot-authored — the historical attack class includes copy-paste-via-LLM-then-PR human workflows.
- Scribe-attack regression test: a synthetic PR `bolt: optimize set conversion` body `Reverts: #1` deleting 2474 lines of `wiki/` must FAIL Gate C in our implementation.

### Pattern 3 — Un-stick `awaitingUserFeedback` sessions (HSI)

- Source: `repo://wryenmeek/hot-springs-island/scripts/fleet/fleet-submit-prs.ts@<pin SHA at port time>`
- Mechanism: daily script iterates Jules sessions filtered to current-repo source, finds those in `awaitingUserFeedback`, sends a canonical "Please submit your changes as a Pull Request now" prompt.
- **Empirical validation in our repo (2026-06-21):** session `13840077902252741245` was idle 13h in `awaitingUserFeedback`. One `client.send()` with HSI's verbatim prompt transitioned it to `IN_PROGRESS` within minutes. The HSI un-stick prompt works on our Jules deployment.
- Our adoption (issue #348): verbatim port plus `CURRENT_REPO_SOURCE` import (not re-literal), `runMutationWithDiagnostics` wrap (so `quota_saturation` exits 0 not 1), `--dry-run` flag, daily 04:00 UTC schedule, and `awaiting-feedback` label application as the coordinating mechanism with #350's label-driven dispatch.

### Pattern 4 — No notification on quota saturation (HSI ADR-029)

- Source: `repo://wryenmeek/hot-springs-island/docs/decisions/ADR-029-fleet-dispatch-quota-saturation-exit-code.md@<pin SHA at port time>` (Accepted 2026-06-10)
- HSI rationale: notifying operators on transient quota-saturation events "trains operators to ignore the alert channel."
- Our adoption (issue #350 → ADR-034): no comments, no GitHub Issues, no Slack/email on `quota_saturation`. Operational visibility comes from (a) scheduled probe canary (issue #349) emitting `::warning::` and updating a pinned tracking issue ONLY on sustained failures and (b) the per-issue dispatch comment audit trail enriched in #350 Pillar 2.
- Replaces the original "we should add notification" instinct that surfaced in our initial #341 response.

### Pattern 5 — Label-driven dispatch with claim mutex (HSI ADR-030)

- Source: `repo://wryenmeek/hot-springs-island/docs/decisions/ADR-030-fleet-label-driven-dispatch.md@<pin SHA at port time>` (Proposed 2026-06-20 — **one day old when we evaluated it**, no landed implementation)
- HSI's five pillars: planner downgrade (label filter), dispatcher claim semantics (label mutation), `awaiting-feedback` label, failure recovery, archival lifecycle.
- Our adoption (issue #350 → ADR-033): verbatim adoption **with three local additions**:
  1. **3-strikes-then-`needs-triage` abort.** HSI's proposal has no abort condition; ours adds one to prevent infinite dispatch loops on unfixable issues. Reset semantics: counter resets on (a) merged PR linked to issue OR (b) operator-driven `ready-for-agent` re-apply; only counts events from the last 30 days; only counts post-human-actor label-add (filters out workflow-driven additions).
  2. **Workflow `concurrency:` group, not labels, is the mutex.** GitHub label API has no compare-and-swap. The "label as mutex" framing in HSI's proposal is misleading; without a serializing `concurrency: { group: ..., cancel-in-progress: false }` block, two `workflow_dispatch` invocations both succeed at label transitions and spawn two Jules sessions per issue. Our ADR-033 documents this explicitly: labels are derived state and visibility, not a concurrency primitive.
  3. **Label mutation order reversed:** `addLabels(['in-progress'])` BEFORE `removeLabel('ready-for-agent')` (HSI's spec is silent on order). Worst-case intermediate state has BOTH labels (visible, planner-filter naturally excludes), NOT NEITHER (invisible to both planner and failure-recovery paths).

### Pattern 6 — Commit-count check (vscode-genai)

- Source: `repo://wryenmeek/vscode-genai/...@<pin SHA at port time>` — small workflow that checks per-PR commit count, flags >N as suspicious.
- Useful complement to Gate C but **not adopted** in this round — overlaps significantly with Gate C's deletion-ratio gate and we want to validate the FP rate of the deletion gate first before stacking more checks.

### Pattern 7 — `jules-pr-coach` (vscode-genai)

- Source: `repo://wryenmeek/vscode-genai/...@<pin SHA at port time>` — workflow that posts coaching comments on Jules PRs identifying common antipatterns.
- Useful but **not adopted** in this round — deferred until the Tier 0 + Tier 1 layers stabilize and we can measure which antipatterns actually occur in our PR stream.

## Tier rationale (summary)

The findings above route into 4 tiers (issues #345–#351):

- **Tier 0 — Defensive layer** (issues #345 #346 #347 #351): closes the silent-revert vector Scribe documented. Ships before any other change because content destruction is irreversible while operational annoyance is recoverable. Ratified-Q1 success metric: zero content destruction.
- **Tier 1 — Operational resilience** (issues #348 #349): un-sticks `awaitingUserFeedback` sessions (HSI Pattern 3) and adds the scheduled probe canary (Pattern 4 visibility channel) that would have surfaced #82 on day 1 instead of day 24.
- **Tier 2 — Label-driven dispatch** (issue #350): adopts HSI's Pattern 5 verbatim with the three local additions above. New ADR-033 + ADR-034 + ADR-032 body-only cleanup.
- **Tier 3 — Multi-provider abstraction** (deferred 30 days to 2026-07-21): no portfolio prior art exists; revisit after the other tiers stabilize. Codex, Devin, `copilot-swe-agent`, etc. remain candidates but no concrete plan today.

## Cross-portfolio gaps (what no one in the portfolio does)

1. **No multi-provider implementation-agent abstraction.** All four repos are Jules-first for implementation. The hypothesis that "we should fall back to `copilot-swe-agent`" (which ADR-032 currently states aspirationally) is not implemented anywhere in the portfolio. Issue #350 cleans up the misleading ADR-032 text.
2. **No semantic merge-impact analysis.** No repo runs a check that says "this PR claims to add a feature but its diff is 90% removal" — Gate C is a proxy. Long-term, this could become a synthesis-driven check; deferred.
3. **No cross-repo Jules quota dashboard.** All four repos share the operator's single Jules account. A per-repo probe canary (Pattern 4 / our #349) is the per-repo signal; a portfolio-level dashboard does not exist and would require infrastructure outside any single repo. Deferred.

## Source-pin policy

Every cross-repo citation in this document uses `repo://<owner>/<repo>/<path>@<pin SHA>` form per AGENTS.md guardrail #4. SHAs are pinned at port-time, not at research-time, because the cited files (especially HSI ADR-030) are in active development and may change before we land our adoptions.

## Provenance

- Triggering events: issue #82 (Jules outage 2026-05-26 → 2026-06-19, root-caused to bare-body `FAILED_PRECONDITION` quota saturation misclassification, fixed by PR #296 / ADR-032 on 2026-06-19), issue #341 (architectural fallback gap filed 2026-06-21), issue #342 (Tier 0 defensive layer filed 2026-06-21).
- Research conducted via 3 parallel `explore` subagents across HSI, vscode-genai, and Scribe on 2026-06-21.
- Plan ratified in a 12-question `/grill-with-docs` session on 2026-06-21; full decision log distributed across the 7 implementation issue bodies and ADR-033/034 (pending implementation in issue #350).
- Cross-functional review pass on the 7 issue specs surfaced 70 findings; 63 remediated in the same session by rewriting the issue bodies (see comment thread on each issue dated 2026-06-21).
