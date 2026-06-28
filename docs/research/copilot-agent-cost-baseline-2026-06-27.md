---
title: "Copilot CLI + Chat agent cost baseline (last 30 days)"
status: Implemented
date: 2026-06-27
author: copilot-cli session &lt;redacted&gt;
tool: scripts/analysis/cost_baseline.py
data_window: 2026-05-28 → 2026-06-27 (30 days)
data_sources:
  - ~/.copilot/session-state/*/events.jsonl (153 CLI sessions, 2.6 GB)
  - ~/.copilot/traces/vscode-otel-*.jsonl (VS Code Copilot Chat OTEL, ~19 GB)
pricing_source: docs.github.com/en/copilot/reference/copilot-billing/models-and-pricing (retrieved 2026-06-27)
---

# Copilot CLI + Chat agent cost baseline (last 30 days)

**Status:** Implemented — analyzer committed at `scripts/analysis/cost_baseline.py`, re-runnable.

## Headline numbers

> **Update (2026-06-27):** the headline figures pre-date the effort dimension; see [Addendum: effort dimension capture](#addendum-2026-06-27-effort-dimension-capture) for the re-bucketed numbers. The "$12,537 / `general-purpose` / `gpt-5.5`" row below collapsed three effort tiers; re-split it estimates ~$34,488 (xhigh $28,238 + default $4,728 + max $1,522). The estimate-to-actual gap widens from 1.2× to ~3.4× in the effort-aware view because the 5× xhigh output multiplier compounds the existing Anthropic-cache over-estimate. The original recommendation (migrate general-purpose off gpt-5.5) still holds.

| Metric | Value | Source |
| --- | --- | --- |
| **Actual billed (CLI sessions, last 30d)** | **$10,262.39** (1,026,238 AI credits) | sum of `session.shutdown.totalNanoAiu` across 153 sessions |
| **VS Code Chat estimated (last 30d)** | $4,482.07 | gen_ai OTEL token totals × per-token price |
| **Top single agent cost (CLI)** | $12,537 estimated, `general-purpose` on `gpt-5.5`, 428 invocations | `subagent.completed` aggregate |
| **Top single optimization** | Migrate `general-purpose` off `gpt-5.5` | see "Recommended swaps" |

> **About the estimate-vs-actual gap:** the per-sub-agent token-derived estimate sums to higher than the session-level `totalNanoAiu` actual. Most likely causes: (a) my blended-rate uses a conservative 20% fresh-input / 70% cached / 10% output mix that may overweight fresh input for some agents, (b) some `totalTokens` values may double-count cached tokens. Treat per-agent dollar figures as **directional upper bounds**; the actual session-level total is authoritative. The ranking and the savings *deltas* are reliable regardless.

## Recommended swaps (sorted by projected monthly savings)

| Rank | Agent | Current model | Invocations | Est. current cost | Conservative target | Aggressive target | Conservative savings | Notes |
| ---: | --- | --- | ---: | ---: | --- | --- | ---: | --- |
| 1 | `general-purpose` | `gpt-5.5` | 428 | $12,537 | `claude-sonnet-4.6` | `claude-haiku-4.5` | **~$6,200/mo (50%)** | Sonnet matches workload class; Haiku is aggressive and may regress on multi-step reasoning. |
| 2 | `tdd` | `claude-opus-4.7` | 28 | $887 | `claude-sonnet-4.6` | `claude-haiku-4.5` | ~$355/mo (40%) | TDD = test writing + iterative refinement; Sonnet should be safe. |
| 3 | `code-reviewer` | `claude-opus-4.7` | 29 | $484 | `claude-sonnet-4.6` | — | ~$194/mo (40%) | Code review = reasoning-heavy; do NOT go below Sonnet. |
| 4 | `documentation-engineer` | `claude-opus-4.7` | 27 | $366 | `claude-sonnet-4.6` | — | ~$146/mo (40%) | Doc writing is well within Sonnet capability. |
| 5 | `code-review` (built-in) | `claude-opus-4.7` | 43 | $284 | `claude-sonnet-4.6` | — | ~$114/mo (40%) | Built-in code-review variant; same logic as #3. |
| 6 | `test-engineer` | `claude-opus-4.7` | 21 | $264 | `claude-sonnet-4.6` | — | ~$106/mo (40%) | Test writing benefits from reasoning; stay at Sonnet. |
| 7 | `qa` | `claude-opus-4.7` | 18 | $246 | `claude-sonnet-4.6` | `claude-haiku-4.5` | ~$98/mo (40%) | QA workload varies; consider per-task model pinning. |
| 8 | `security-auditor` | `claude-opus-4.7` | 20 | $161 | — (keep Opus) | — | $0 | Security review benefits from highest-recall model. |
| 9 | `research` | `claude-sonnet-4.6` | 33 | $137 | `claude-haiku-4.5` | — | ~$45/mo (33%) | Citation-heavy; Haiku may miss multi-source synthesis. Test carefully. |
| 10 | `docs` | `claude-opus-4.7` | 2 | $104 | `claude-sonnet-4.6` | — | ~$42/mo (40%) | Low invocations; low priority. |

**Conservative total (Sonnet-only swaps, keep security/research at current):** approximately **$7,300/mo (~71% of current CLI billed total).**

The aggressive total ($12,553) in the tool output assumes every workload moves to Haiku, which will likely regress quality on the `general-purpose`, `tdd`, and reasoning-heavy personas. Use it as an upper bound only.

## Concerning failure-rate signals (separate from cost)

The analyzer's failure heuristic = `subagent.completed` events with `totalTokens=0` AND `totalToolCalls=0` AND `durationMs<5000ms` (likely upstream model error: quota, timeout, 5xx).

| Agent | Model | Invocations | Failure rate | Likely cause |
| --- | --- | ---: | ---: | --- |
| `security-auditor` | `gpt-5.5` | 106 | **100%** | gpt-5.5 quota exhaustion (same root cause as the diagnostic session previously documented) |
| `code-reviewer` | `gpt-5.5` | 129 | **100%** | same |
| `test-engineer` | `gpt-5.5` | 122 | **100%** | same |
| `documentation-engineer` | `gpt-5.5` | 104 | **100%** | same |
| `code-review` (built-in) | `gpt-5.5` | 101 | **100%** | same |
| `github-customization-steward` | `gpt-5.5` | 76 | **100%** | same |
| `compound-engineering:ce-code-simplicity-reviewer` | `gpt-5.4-mini` | 12 | **100%** | likely flighted-then-quota or model misroute |
| `medicare-domain-advisor` | `claude-opus-4.7` | 8 | 62.5% | NOT a quota pattern; investigate prompt/agent |
| `code-review` | `claude-sonnet-4.6` | 9 | 55.6% | investigate (could be legitimate complex diffs) |
| `general-purpose` | `gpt-5.4-mini` | 18 | 50% | model too small for general-purpose workload |
| `explore` | `gpt-5.4-mini` | 30 | 20% | flighted default; quality questionable |

**Interpretation:** in the last 30 days, **at least 750+ sub-agent dispatches silently failed on `gpt-5.5`** across many custom personas. The cost of these failures isn't tokens — it's wasted operator time waiting for a sub-agent that never started, and rework when the operator falls back to direct implementation.

## VS Code Copilot Chat side (separate dataset)

| Model | Inferences | Input tokens (M) | Output tokens (M) | Est. cost |
| --- | ---: | ---: | ---: | ---: |
| `claude-opus-4.6` | 3,817 | 377 | 1.75 | $1,930 |
| `gpt-5.4` | 7,065 | 719 | 6.91 | $1,902 |
| `gpt-5.4-mini` | 5,509 | 553 | 9.31 | $457 |
| `gpt-5.5` | 106 | 17 | 0.05 | $87 |
| `claude-opus-4.7` | 72 | 9.8 | 0.10 | $52 |
| `claude-sonnet-4.6` | 126 | 11.8 | 0.10 | $37 |
| `claude-haiku-4.5` | 124 | 11.8 | 0.11 | $12 |

Chat usage is much more diverse model-wise. The 7K-inference GPT-5.4 line and 3.8K-inference Claude Opus 4.6 line dominate. **Chat optimization is a separate question** because the user picks model interactively per turn; the route is to change defaults in VS Code's `github.copilot.chat.preferredModels` settings, not the CLI's `subagents.agents.<name>.model` mechanism.

## Experimentation playbook (using OTEL + events.jsonl as quality gates)

### Recommended first experiment: `general-purpose` → `claude-sonnet-4.6`

**Setup:**
```jsonc
// ~/.copilot/settings.json
"subagents": {
  "agents": {
    "general-purpose": { "model": "claude-sonnet-4.6" }
  }
}
```

**Quality gates (compute weekly using `scripts/analysis/cost_baseline.py --days 7`):**

| Metric | Baseline (last 30d) | Pass criterion |
| --- | --- | --- |
| Avg `totalToolCalls` per dispatch | TBD (compute from baseline data) | ≥ baseline − 15% |
| Avg `durationMs` per dispatch | 1573s (gpt-5.5 baseline) | ≤ baseline + 25% |
| Failure rate (zero-token < 5s) | 0.7% (gpt-5.5 baseline) | ≤ 5% |
| `session.error` quota_exceeded events | tracked separately | ≤ baseline |
| Estimated per-invocation cost | $29.30 (gpt-5.5) | $17.50 expected (sonnet-4.6); should drop by 40% |

### Iteration plan after experiment 1

1. **Week 1–2:** general-purpose pinned to sonnet-4.6. Verify quality gates.
2. **Week 3:** if green, pin `tdd` and `documentation-engineer` to sonnet-4.6.
3. **Week 4:** if green, pin `code-reviewer` and `test-engineer` to sonnet-4.6.
4. **Optional later experiment:** try aggressive Haiku swap on `general-purpose` for plain-text tasks only (requires per-task model override pattern, which the current `task` tool supports via the `model:` argument).

### Stop-experiment triggers

- Failure rate doubles vs. baseline
- 3+ operator complaints about quality regression in a week
- `continueOnAutoMode` auto-switching fires more than 2× the baseline rate

## Caveats and known limitations

1. **Blended-rate estimate is an upper bound.** Per-sub-agent `totalTokens` doesn't separate input / cached / output. The default mix (20%/70%/10%) likely overweights fresh input for chat-style workloads. The session-level `totalNanoAiu` actual is authoritative.

2. **Failure heuristic has false positives.** A legitimate <5s no-op dispatch (e.g., a check that finds nothing to do) would be counted as a failure. The aggregated 100% failure rate on `gpt-5.5` across many agents over 750+ invocations is too consistent to be false-positive — it's the quota pattern. Smaller agents need manual triage.

3. **Long-context tier is now modeled in `pricing.py` (both CLI-side and Chat-side biases remain).** `gpt-5.4`, `gpt-5.5`, and `gemini-3.1-pro` publish a separate Long-context tier (2× input / 1.5× output) above 272K input tokens (272K for OpenAI, 200K for Gemini). As of issue #401, `pricing.py` stores these rates and `estimate_cost_usd` selects the correct tier when the caller supplies the per-call input-token count via `input_tokens_for_threshold` — the API is available. Chat-side OTEL events expose per-call `gen_ai.usage.input_tokens`, making the data available to enable the per-call threshold check; however, the wiring through `ChatBucket.est_cost_usd` is not yet implemented and will land in a follow-up issue. CLI-side sub-agent telemetry exposes only aggregate `totalTokens` with no input/output split, so the per-call threshold is not applicable there either. Both CLI-side (aggregate token granularity prevents per-call threshold) and Chat-side (wiring pending) biases remain until the follow-up lands.

4. **VS Code OTEL is one large file (18 GB on 06-21).** Future runs should stream-parse efficiently; the current tool does so but takes ~2 min on cold disk cache.

5. **Chat-side dollar figures now use blended-rate or exact split (updated 2026-06-28).** When OTEL exposes `gen_ai.usage.cache_read_input_tokens` per event, the analyzer uses an exact split: `fresh_input * input_per_m + cached_input * cached_per_m + output * output_per_m` (Option B). When that field is absent, it falls back to `blended_rate()` with the default 20/70/10 mix (Option A), matching the CLI side. The prior 100% fresh-rate overestimate is removed. Use `--chat-cache-share <frac>` to override the assumed cache fraction in the fallback path.

6. **`--days` window is mtime-granular by default; `--strict-window` enables per-event filtering (updated 2026-06-28).** The default mode filters by `events.jsonl` file mtime, so a long-running session appended to recently contributes all events including older ones. Add `--strict-window` to skip individual events whose `timestamp` field predates the cutoff. The header line in the output reports which mode is active.

7. **Sample bias.** All sessions are from one user (`wryenmeek`) in one repo cluster. Recommendations transfer to similarly-sized agentic workloads; not generalizable to other operators.

8. **Pricing freshness.** Pricing table dated 2026-06-27 from docs.github.com. Tool warns after 60 days; rerun with fresh pricing before acting on stale estimates.

## How to re-run

```bash
# Last 30 days (default)
python3 scripts/analysis/cost_baseline.py

# Last 7 days for an experiment-tracking pass
python3 scripts/analysis/cost_baseline.py --days 7

# CLI-only (skip 19 GB OTEL pass)
python3 scripts/analysis/cost_baseline.py --skip-chat
```

Tool source: `scripts/analysis/cost_baseline.py`
Pricing source: `scripts/analysis/pricing.py`

## Open follow-ups

All deferred items have been filed as `ready-for-agent` GitHub issues:

- **[#400](https://github.com/wryenmeek/knowledgebase/issues/400)** — Expand `tests/analysis/` coverage: fail-soft contracts, OTEL parser, renderer smoke (P1/P2/P3 blocks from the test-engineer review)
- **[#401](https://github.com/wryenmeek/knowledgebase/issues/401)** — ~~Add long-context tier pricing to `scripts/analysis/pricing.py`~~ **Implemented** — long-context rates now stored in `ModelPrice`; `estimate_cost_usd` tier-selects when `input_tokens_for_threshold` is supplied.
- **[#402](https://github.com/wryenmeek/knowledgebase/issues/402)** — Apply blended-rate to Chat-side cost math (fix the structural overestimate noted in Caveat §5)
- **[#403](https://github.com/wryenmeek/knowledgebase/issues/403)** — Per-event timestamp filter for `--days` window (close the mtime-granularity gap noted in Caveat §6)

Cross-functional review for the initial commit (`feat(analysis): add Copilot agent cost baseline analyzer`) was completed in-session: `@code-reviewer`, `@test-engineer`, `@security-auditor`, `@documentation-engineer` all dispatched in parallel; P0–P2 findings remediated before merge in the same commit pair (initial + remediation).

---

## Addendum (2026-06-27): effort dimension capture

After the initial report shipped, telemetry inspection (`session.start.reasoningEffort` + `tool.execution_start.arguments.reasoning_effort` for `task` tool calls) revealed that **effort level is the single largest hidden cost driver** that the effort-blind v1 analyzer was collapsing.

### Implementation

`AgentBucket` now keys on `(agent, model, effort)` instead of `(agent, model)`. Effort is resolved per-dispatch via two-pass scan:

1. Per-session: record `session.start.reasoningEffort` as the session default
2. Per-task-dispatch: record any explicit `task` tool `arguments.reasoning_effort` (~2.7% of dispatches)
3. Per-`subagent.completed`: resolve effort = per-call override OR session default OR `"default"`

`pricing.py` adds an output-token multiplier per effort level (low 0.7×, medium 1.0×, high 2.5×, xhigh 5.0×, max 7.0×) applied only to effort-capable models (gpt-5.x + claude-opus-4.6/4.7). Sonnet/Haiku/Gemini ignore the parameter.

### Re-bucketed headline numbers (same 30d window)

| Agent / model / effort | Inv | Est cost (30d) | Notes |
|---|---|---|---|
| `general-purpose / gpt-5.5 / xhigh` | 245 | **$28,238** | Driven by my `effortLevel: max` session default cascading |
| `general-purpose / gpt-5.5 / default` | 162 | $4,728 | Pre-`effortLevel:max` sessions |
| `general-purpose / gpt-5.5 / max` | 21 | $1,522 | Explicit per-dispatch max |
| `tdd / claude-opus-4.7 / xhigh` | 17 | $1,780 | |
| `code-reviewer / claude-opus-4.7 / xhigh` | 29 | $1,631 | |
| `documentation-engineer / claude-opus-4.7 / xhigh` | 24 | $1,253 | |

**Estimate-to-actuals ratio** is now ~3.4× ($34k est vs $10k actual), wider than v1's 1.2×. The aggressive 5× xhigh multiplier compounds the Anthropic-cache over-estimate; treat per-row estimates as planning-grade.

### What this resolves

The v1 report could not explain why `general-purpose/gpt-5.5` cost $12k for "428 invocations at 0.7% fail rate." The answer: ~57% of those invocations ran at xhigh effort, ~38% at default, ~5% at max. The mean cost-per-invocation differs by ~5× across these slices.

### What the user's 14-agent settings.json patch does

Applied 2026-06-27:

- Pins `general-purpose`, `code-reviewer`, `code-review`, `security-auditor`, `security-review`, `rubber-duck` to `claude-sonnet-4.6` (no effort knob; quota-stable)
- Pins `documentation-engineer`, `docs`, `github-customization-steward` to `claude-haiku-4.5` (structured output; no effort knob)
- Pins `tdd` to `gpt-5.3-codex` at `effortLevel: medium` (code-specialized; medium effort sufficient)
- Pins `test-engineer`, `qa`, `research`, `explore` to `gpt-5.4-mini` at `effortLevel: high` (lightweight + high effort to match sonnet-tier reasoning on focused tasks)

Expected effect (re-measure in 7d):

- Eliminates the ~706 silent-failure gpt-5.5 dispatches from the v1 report
- Caps the xhigh-effort spend by routing big-volume agents to non-effort-capable Anthropic models
- Tests whether `gpt-5.4-mini high` and `gpt-5.3-codex medium` produce work quality matching the sonnet/opus baselines

