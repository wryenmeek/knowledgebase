#!/usr/bin/env python3
"""Aggregate per-(agent, model) Copilot CLI + Chat cost from local telemetry.

Read-only analyzer for host-local telemetry. Sources:

* CLI per-agent telemetry: ``~/.copilot/session-state/*/events.jsonl``
  (``subagent.completed`` events carry ``agentName``, ``model``,
  ``totalTokens``, ``durationMs``; ``session.shutdown`` carries
  ``totalNanoAiu`` for ground-truth main-agent cost).
* VS Code Copilot Chat OTEL: ``~/.copilot/traces/vscode-otel-*.jsonl``
  (``gen_ai.client.inference.operation.details`` events carry per-call
  ``gen_ai.request.model``, ``gen_ai.usage.input_tokens``,
  ``gen_ai.usage.output_tokens``).

The tool prints three tables to stdout:

1. Baseline: per-(agent, model) invocations + token volume + estimated cost.
2. Savings projection: for each (agent, model) the cheapest viable
   replacement and projected savings.
3. Experimentation priority: agents ranked by absolute cost (largest first)
   with suggested A/B target model.

This surface is read-only. It never writes to the repository. See ``AGENTS.md``
write-surface matrix entry for ``scripts/analysis/**``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.analysis.pricing import (  # noqa: E402
    LIGHTWEIGHT_CANDIDATES,
    POWERFUL_CANDIDATES,
    PRICING,
    PRICING_RETRIEVED,
    MAX_PRICING_STALE_DAYS,
    VERSATILE_CANDIDATES,
    blended_rate,
    estimate_cost_usd,
)

DEFAULT_COPILOT_HOME = Path.home() / ".copilot"
SESSION_STATE_GLOB = "session-state/*/events.jsonl"
OTEL_GLOB = "traces/vscode-otel-*.jsonl"

# Agent → workload class (used to pick candidate replacements).
# Mapped from ~/.copilot/pkg/.../definitions/*.agent.yaml plus inline
# defaults in app.js. Confidence: HIGH (sourced from bundled YAML/binary).
AGENT_CLASS: dict[str, str] = {
    "task": "lightweight",
    "explore": "lightweight",
    "rem-agent": "lightweight",
    "rubber-duck": "versatile",
    "research": "versatile",
    "general-purpose": "versatile",
    "code-review": "powerful",
    "security-review": "powerful",
    # repo-local custom-persona names (workspace agents)
    "code-reviewer": "powerful",
    "test-engineer": "versatile",
    "security-auditor": "powerful",
    "documentation-engineer": "versatile",
    "framework-engineer": "versatile",
    "solutions-architect": "powerful",
    "quality-analyst": "versatile",
    "synthesis-curator": "versatile",
    "knowledgebase-orchestrator": "versatile",
    "policy-arbiter": "versatile",
    "source-intake-steward": "versatile",
    "topology-librarian": "versatile",
    "maintenance-auditor": "versatile",
    "query-synthesist": "versatile",
    "evidence-verifier": "versatile",
    "entity-resolution-and-canonicalization": "versatile",
    "change-patrol": "versatile",
}


@dataclass
class AgentInvocation:
    agent: str
    model: str
    total_tokens: int
    duration_ms: int
    success: bool  # True if totalToolCalls > 0 OR (totalTokens > 0 AND duration > 5s)
    session_id: str
    timestamp: str


@dataclass
class AgentBucket:
    agent: str
    model: str
    invocations: int = 0
    total_tokens: int = 0
    total_duration_ms: int = 0
    failures: int = 0
    sessions: set[str] = field(default_factory=set)

    @property
    def est_cost_usd(self) -> float:
        return estimate_cost_usd(self.model, self.total_tokens)

    @property
    def failure_rate(self) -> float:
        return self.failures / self.invocations if self.invocations else 0.0


@dataclass
class ChatBucket:
    """VS Code Copilot Chat per-model aggregate (exact input/output split)."""

    model: str
    inferences: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def est_cost_usd(self) -> float:
        price = PRICING.get(self.model)
        if price is None:
            return 0.0
        return (
            self.input_tokens * price.input_per_m
            + self.output_tokens * price.output_per_m
        ) / 1_000_000.0


def _epoch_cutoff(days: int) -> float:
    return time.time() - days * 86400.0


def _iter_session_events(
    home: Path, cutoff_epoch: float
) -> Iterator[tuple[str, dict]]:
    """Yield (session_id, event_dict) pairs for sessions modified after cutoff.

    Streams line-by-line; never loads a full file into memory. Skips sessions
    whose ``events.jsonl`` mtime predates ``cutoff_epoch``.
    """
    for path in (home).glob(SESSION_STATE_GLOB):
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if mtime < cutoff_epoch:
            continue
        session_id = path.parent.name
        try:
            with path.open() as f:
                for line in f:
                    try:
                        yield session_id, json.loads(line)
                    except json.JSONDecodeError:
                        continue
        except OSError:
            continue


def _iter_otel_inferences(
    home: Path, cutoff_epoch: float
) -> Iterator[dict]:
    """Yield gen_ai inference operation events from OTEL traces."""
    for path in (home).glob(OTEL_GLOB):
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if mtime < cutoff_epoch:
            continue
        try:
            with path.open() as f:
                for line in f:
                    try:
                        e = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    attrs = e.get("attributes")
                    if not isinstance(attrs, dict):
                        continue
                    if (
                        attrs.get("event.name")
                        == "gen_ai.client.inference.operation.details"
                    ):
                        yield attrs
        except OSError:
            continue


def collect_cli(
    home: Path, days: int
) -> tuple[dict[tuple[str, str], AgentBucket], int, float]:
    """Aggregate per-(agent, model) cost across last ``days`` of CLI sessions.

    Returns ``(buckets, session_count, total_nano_aiu_actual)``. The
    ``totalNanoAiu`` ground truth is summed across observed
    ``session.shutdown`` events; it represents the *actual* billed cost and
    is reported alongside the token-derived estimate.
    """
    cutoff = _epoch_cutoff(days)
    buckets: dict[tuple[str, str], AgentBucket] = {}
    sessions_seen: set[str] = set()
    actual_nano_aiu = 0.0
    for session_id, event in _iter_session_events(home, cutoff):
        et = event.get("type")
        if et == "subagent.completed":
            data = event.get("data", {})
            agent = data.get("agentName") or "?"
            model = data.get("model") or "?"
            tokens = int(data.get("totalTokens") or 0)
            dur = int(data.get("durationMs") or 0)
            tool_calls = int(data.get("totalToolCalls") or 0)
            key = (agent, model)
            bucket = buckets.setdefault(key, AgentBucket(agent=agent, model=model))
            bucket.invocations += 1
            bucket.total_tokens += tokens
            bucket.total_duration_ms += dur
            bucket.sessions.add(session_id)
            sessions_seen.add(session_id)
            # Failure heuristic: 0 tokens AND 0 tool calls AND <5s duration =
            # likely upstream model error (quota, timeout, 5xx).
            if tokens == 0 and tool_calls == 0 and dur < 5000:
                bucket.failures += 1
        elif et == "session.shutdown":
            data = event.get("data", {})
            nano = data.get("totalNanoAiu")
            if isinstance(nano, (int, float)):
                actual_nano_aiu += float(nano)
            sessions_seen.add(session_id)
    return buckets, len(sessions_seen), actual_nano_aiu


def collect_chat(
    home: Path, days: int
) -> dict[str, ChatBucket]:
    """Aggregate per-model VS Code Copilot Chat inferences from OTEL."""
    cutoff = _epoch_cutoff(days)
    buckets: dict[str, ChatBucket] = {}
    for attrs in _iter_otel_inferences(home, cutoff):
        model = attrs.get("gen_ai.request.model") or "?"
        if model == "?":
            continue
        bucket = buckets.setdefault(model, ChatBucket(model=model))
        bucket.inferences += 1
        bucket.input_tokens += int(attrs.get("gen_ai.usage.input_tokens") or 0)
        bucket.output_tokens += int(attrs.get("gen_ai.usage.output_tokens") or 0)
    return buckets


def _cheapest_candidate(
    workload_class: str, current_model: str
) -> str | None:
    """Return cheapest known-priced candidate model for ``workload_class``.

    Skips the current model. Returns ``None`` if no priced candidate is
    cheaper than the current model on blended-rate basis.
    """
    pool = {
        "lightweight": LIGHTWEIGHT_CANDIDATES,
        "versatile": VERSATILE_CANDIDATES,
        "powerful": POWERFUL_CANDIDATES,
    }.get(workload_class, VERSATILE_CANDIDATES)
    current_rate = blended_rate(current_model)
    best: tuple[str, float] | None = None
    for cand in pool:
        if cand == current_model:
            continue
        if cand not in PRICING:
            continue
        rate = blended_rate(cand)
        if current_rate and rate < current_rate:
            if best is None or rate < best[1]:
                best = (cand, rate)
    return best[0] if best else None


def render_baseline_table(
    buckets: dict[tuple[str, str], AgentBucket],
) -> str:
    rows = sorted(
        buckets.values(), key=lambda b: b.est_cost_usd, reverse=True
    )
    out = [
        f"{'agent':<32} {'model':<22} {'inv':>5} {'tok(M)':>8} "
        f"{'est_$':>8} {'avg_dur':>8} {'fail%':>6}"
    ]
    out.append("-" * 92)
    for r in rows:
        out.append(
            f"{r.agent:<32} {r.model:<22} {r.invocations:>5} "
            f"{r.total_tokens/1e6:>8.2f} "
            f"${r.est_cost_usd:>7.2f} "
            f"{(r.total_duration_ms/r.invocations/1000) if r.invocations else 0:>7.1f}s "
            f"{r.failure_rate*100:>5.1f}%"
        )
    return "\n".join(out)


def render_savings_table(
    buckets: dict[tuple[str, str], AgentBucket],
) -> str:
    rows = []
    for b in buckets.values():
        klass = AGENT_CLASS.get(b.agent, "versatile")
        alt = _cheapest_candidate(klass, b.model)
        if alt is None:
            continue
        alt_cost = estimate_cost_usd(alt, b.total_tokens)
        savings = b.est_cost_usd - alt_cost
        if savings <= 0:
            continue
        reduction = savings / b.est_cost_usd * 100 if b.est_cost_usd else 0
        rows.append(
            {
                "agent": b.agent,
                "current_model": b.model,
                "current_cost": b.est_cost_usd,
                "alt_model": alt,
                "alt_cost": alt_cost,
                "savings": savings,
                "reduction": reduction,
            }
        )
    rows.sort(key=lambda r: r["savings"], reverse=True)
    out = [
        f"{'agent':<32} {'current':<22} {'cur_$':>8} {'alt':<22} "
        f"{'alt_$':>8} {'save_$':>8} {'redux':>6}"
    ]
    out.append("-" * 110)
    for r in rows:
        out.append(
            f"{r['agent']:<32} {r['current_model']:<22} "
            f"${r['current_cost']:>7.2f} {r['alt_model']:<22} "
            f"${r['alt_cost']:>7.2f} ${r['savings']:>7.2f} "
            f"{r['reduction']:>5.1f}%"
        )
    total_savings = sum(r["savings"] for r in rows)
    out.append("-" * 110)
    out.append(
        f"{'TOTAL projected savings':<32} "
        f"{'':<22} {'':>8} {'':<22} {'':>8} ${total_savings:>7.2f}"
    )
    return "\n".join(out)


def render_chat_table(buckets: dict[str, ChatBucket]) -> str:
    rows = sorted(buckets.values(), key=lambda b: b.est_cost_usd, reverse=True)
    out = [
        f"{'model':<32} {'inf':>6} {'in(M)':>8} {'out(M)':>8} {'est_$':>8}"
    ]
    out.append("-" * 68)
    for r in rows:
        out.append(
            f"{r.model:<32} {r.inferences:>6} "
            f"{r.input_tokens/1e6:>8.2f} "
            f"{r.output_tokens/1e6:>8.2f} "
            f"${r.est_cost_usd:>7.2f}"
        )
    total = sum(r.est_cost_usd for r in rows)
    out.append("-" * 68)
    out.append(f"{'TOTAL':<32} {'':>6} {'':>8} {'':>8} ${total:>7.2f}")
    return "\n".join(out)


def render_priority_list(
    buckets: dict[tuple[str, str], AgentBucket],
    top_n: int,
) -> str:
    """Rank agents by absolute current cost; recommend A/B target."""
    by_agent: dict[str, float] = defaultdict(float)
    by_agent_invocations: dict[str, int] = defaultdict(int)
    by_agent_models: dict[str, set[str]] = defaultdict(set)
    for b in buckets.values():
        by_agent[b.agent] += b.est_cost_usd
        by_agent_invocations[b.agent] += b.invocations
        by_agent_models[b.agent].add(b.model)
    ranked = sorted(by_agent.items(), key=lambda kv: kv[1], reverse=True)[
        :top_n
    ]
    out = [
        f"{'rank':>4} {'agent':<32} {'invocations':>11} "
        f"{'cost_$':>8} {'current_models'}"
    ]
    out.append("-" * 85)
    for i, (agent, cost) in enumerate(ranked, 1):
        models = ",".join(sorted(by_agent_models[agent]))[:25]
        out.append(
            f"{i:>4} {agent:<32} {by_agent_invocations[agent]:>11} "
            f"${cost:>7.2f} {models}"
        )
    return "\n".join(out)


def _pricing_freshness_warning() -> str | None:
    age = (datetime.now(timezone.utc).date() - PRICING_RETRIEVED).days
    if age > MAX_PRICING_STALE_DAYS:
        return (
            f"WARNING: pricing table last refreshed {PRICING_RETRIEVED} "
            f"({age} days ago, max={MAX_PRICING_STALE_DAYS}). "
            "Re-verify docs.github.com/en/copilot/reference/copilot-billing/"
            "models-and-pricing and refresh scripts/analysis/pricing.py."
        )
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="copilot-agent-cost-baseline",
        description=__doc__.split("\n", 1)[0],
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Look back N days (default: 30). Sessions older than the "
        "cutoff are skipped via mtime check.",
    )
    parser.add_argument(
        "--home",
        type=Path,
        default=DEFAULT_COPILOT_HOME,
        help="Copilot data dir (default: ~/.copilot).",
    )
    parser.add_argument(
        "--skip-chat",
        action="store_true",
        help="Skip VS Code Copilot Chat OTEL analysis (CLI-only mode).",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Top-N rows in priority list (default: 10).",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format (default: text).",
    )
    args = parser.parse_args(argv)

    warning = _pricing_freshness_warning()

    print(
        f"# Copilot agent cost baseline (last {args.days}d, "
        f"home={args.home})"
    )
    if warning:
        print(f"\n{warning}")
    print()

    print("## CLI sub-agent baseline (sourced from session events.jsonl)")
    print()
    cli_buckets, session_count, actual_nano_aiu = collect_cli(
        args.home, args.days
    )
    actual_aiu = actual_nano_aiu / 1e9
    actual_usd = actual_aiu * 0.01
    print(
        f"Sessions analyzed: {session_count} | "
        f"Actual billed (from session.shutdown.totalNanoAiu): "
        f"{actual_aiu:.1f} AI credits ≈ ${actual_usd:.2f}"
    )
    print()
    if cli_buckets:
        print(render_baseline_table(cli_buckets))
    else:
        print("(no sub-agent invocations recorded in window)")
    print()

    print("## Savings projection (per-agent cheapest viable replacement)")
    print()
    if cli_buckets:
        print(render_savings_table(cli_buckets))
    else:
        print("(skipped — no baseline data)")
    print()

    print(f"## Experimentation priority (top {args.top} by absolute cost)")
    print()
    if cli_buckets:
        print(render_priority_list(cli_buckets, args.top))
    else:
        print("(skipped — no baseline data)")
    print()

    if not args.skip_chat:
        print(
            "## VS Code Copilot Chat per-model usage "
            "(from gen_ai OTEL traces)"
        )
        print()
        chat_buckets = collect_chat(args.home, args.days)
        if chat_buckets:
            print(render_chat_table(chat_buckets))
        else:
            print("(no chat inference events recorded in window)")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
