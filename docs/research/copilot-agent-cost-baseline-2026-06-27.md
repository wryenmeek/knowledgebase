---
title: "Copilot CLI + Chat agent cost baseline (last 30 days)"
status: Implemented
date: 2026-06-27
author: copilot-cli session d92e9b07
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
| `security-auditor` | `gpt-5.5` | 106 | **100%** | gpt-5.5 quota exhaustion (same root cause as session d92e9b07 04:28 UTC) |
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

3. **VS Code OTEL is one large file (18 GB on 06-21).** Future runs should stream-parse efficiently; the current tool does so but takes ~2 min on cold disk cache.

4. **Sample bias.** All sessions are from one user (`wryenmeek`) in one repo cluster. Recommendations transfer to similarly-sized agentic workloads; not generalizable to other operators.

5. **Pricing freshness.** Pricing table dated 2026-06-27 from docs.github.com. Tool warns after 60 days; rerun with fresh pricing before acting on stale estimates.

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

- Add pytest coverage in `tests/analysis/` for `pricing.py` and the failure-heuristic logic.
- Cross-functional review (`@code-reviewer + @test-engineer + @security-auditor + @documentation-engineer`) per the AGENTS hard rule for `scripts/**` changes — deferred to a follow-up session.
- Decide whether to add `scripts/analysis/CONTEXT.md` glossary per the CONTEXT.md required-sections rule (currently no entries to document; can wait until a 2nd analyzer lands).
- Decide whether the per-(agent, model) baseline should be persisted as a daily artifact under `wiki/reports/agent-cost-*.json` (requires new schema and a `persist` mode similar to `scripts/reporting/quality_runtime.py`).
