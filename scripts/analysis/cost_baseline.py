#!/usr/bin/env python3
"""Aggregate per-(agent, model) Copilot CLI + Chat cost from local telemetry.

Read-only analyzer for host-local Copilot telemetry. Sources:

* CLI per-agent telemetry: ``~/.copilot/session-state/*/events.jsonl``
  (``subagent.completed`` events carry ``agentName``, ``model``,
  ``totalTokens``, ``durationMs``; ``session.shutdown`` carries
  ``totalNanoAiu`` for ground-truth main-agent cost).
* VS Code Copilot Chat OTEL: ``~/.copilot/traces/vscode-otel-*.jsonl``
  (``gen_ai.client.inference.operation.details`` events carry per-call
  ``gen_ai.request.model``, ``gen_ai.usage.input_tokens``,
  ``gen_ai.usage.output_tokens``).

The tool emits a :class:`CostBaselineReport` to stdout — either rendered as
human-readable tables (``--format text``, default) or as a deterministic JSON
document (``--format json``) suitable for committing alongside a narrative
research report under ``docs/research/<slug>-<YYYY-MM-DD>.json``.

This surface is read-only. It never writes to the repository. See ``AGENTS.md``
write-surface matrix entry for ``scripts/analysis/**``.

The surface uses a custom :class:`CostBaselineReport` schema (not the generic
``_optional_surface_common.SurfaceResult``) because the analyzer's output is
richer than the generic envelope — per-(agent, model) buckets, per-model
chat aggregates, savings projections, and a priority list cannot be cleanly
expressed as ``SurfaceResult.items``. The standard ``STATUS_PASS`` /
``STATUS_FAIL`` constants, reason-code conventions, and ``JsonArgumentParser``
helper ARE reused from ``_optional_surface_common`` to keep the contract
aligned with sibling analyzers in ``scripts/validation/`` and
``scripts/reporting/``. (Same pattern as
``scripts/validation/check_doc_freshness.py::FreshnessReport``.)

**Known limitations** (also see ``pricing.py``):

* ``--days N`` window is enforced at **file mtime granularity only**.
  Events have a per-event ``timestamp`` field but the tool only filters by
  ``events.jsonl`` mtime. A long-running session whose events file was
  appended to recently contributes ALL of its events to the window. For
  precise per-event windowing, see issue tracker.
* Pricing table covers Default tier only; long-context-tier invocations are
  under-estimated. See ``pricing.py`` module docstring.
* Failure heuristic (``totalTokens=0`` AND ``totalToolCalls=0`` AND
  ``durationMs<5000ms``) may false-positive on legitimate fast no-op
  dispatches. Aggregated 100% failure-rate rows on a single model across
  many agents are reliable (the quota-exhaustion pattern); single-bucket
  small-N rates need manual triage.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterator, Sequence, TextIO

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.analysis.pricing import (  # noqa: E402
    LIGHTWEIGHT_CANDIDATES,
    MAX_PRICING_STALE_DAYS,
    POWERFUL_CANDIDATES,
    PRICING,
    PRICING_RETRIEVED,
    VERSATILE_CANDIDATES,
    blended_rate,
    estimate_cost_usd,
)
from scripts._optional_surface_common import (  # noqa: E402
    JsonArgumentParser,
    REASON_CODE_INVALID_INPUT,
    REASON_CODE_OK,
    STATUS_FAIL,
    STATUS_PASS,
)

REASON_CODE_MISSING_COPILOT_HOME = "missing_copilot_home"

DEFAULT_COPILOT_HOME = Path.home() / ".copilot"
SESSION_STATE_GLOB = "session-state/*/events.jsonl"
OTEL_GLOB = "traces/vscode-otel-*.jsonl"
OTEL_INFERENCE_EVENT_NAME = "gen_ai.client.inference.operation.details"

# Agent → workload class (used to pick candidate replacements). Sourced from
# bundled CLI agent YAMLs (~/.copilot/pkg/.../definitions/*.agent.yaml) plus
# inline defaults in app.js. Workspace custom personas mapped by inspection
# of .github/agents/**. Unknown agents fall back to "versatile" via
# _cheapest_candidate (logged to stderr at the end of each run for visibility).
AGENT_CLASS: dict[str, str] = {
    "task": "lightweight",
    "explore": "lightweight",
    "rem-agent": "lightweight",
    "rubber-duck": "versatile",
    "research": "versatile",
    "general-purpose": "versatile",
    "code-review": "powerful",
    "security-review": "powerful",
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


@dataclass(frozen=True, slots=True)
class AgentBucket:
    agent: str
    model: str
    invocations: int
    total_tokens: int
    total_duration_ms: int
    failures: int
    sessions_count: int

    @property
    def est_cost_usd(self) -> float:
        return estimate_cost_usd(self.model, self.total_tokens)

    @property
    def failure_rate(self) -> float:
        return self.failures / self.invocations if self.invocations else 0.0

    @property
    def avg_duration_seconds(self) -> float:
        if not self.invocations:
            return 0.0
        return self.total_duration_ms / self.invocations / 1000.0

    def to_dict(self) -> dict[str, object]:
        return {
            "agent": self.agent,
            "model": self.model,
            "invocations": self.invocations,
            "total_tokens": self.total_tokens,
            "total_duration_ms": self.total_duration_ms,
            "failures": self.failures,
            "sessions_count": self.sessions_count,
            "est_cost_usd": round(self.est_cost_usd, 4),
            "failure_rate": round(self.failure_rate, 6),
            "avg_duration_seconds": round(self.avg_duration_seconds, 2),
        }


@dataclass(frozen=True, slots=True)
class ChatBucket:
    """Per-model VS Code Copilot Chat aggregate.

    OTEL split between fresh-input and cached-input tokens is not available
    in the ``gen_ai.usage.*`` attributes today — only one ``input_tokens``
    field is published. ``est_cost_usd`` therefore charges 100% of input
    tokens at the fresh-input rate, which **structurally over-estimates** the
    cost for Anthropic models (whose cached-input rate is 10x cheaper) and
    OpenAI models with prompt caching. The CLI side uses a blended rate
    (70% cached); the Chat side cannot distinguish here. Treat Chat dollar
    estimates as an upper bound. See report Caveats section.
    """

    model: str
    inferences: int
    input_tokens: int
    output_tokens: int

    @property
    def est_cost_usd(self) -> float:
        price = PRICING.get(self.model)
        if price is None:
            return 0.0
        return (
            self.input_tokens * price.input_per_m
            + self.output_tokens * price.output_per_m
        ) / 1_000_000.0

    def to_dict(self) -> dict[str, object]:
        return {
            "model": self.model,
            "inferences": self.inferences,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "est_cost_usd": round(self.est_cost_usd, 4),
        }


@dataclass(frozen=True, slots=True)
class SavingsRow:
    agent: str
    current_model: str
    current_cost_usd: float
    alt_model: str
    alt_cost_usd: float
    savings_usd: float
    reduction_pct: float

    def to_dict(self) -> dict[str, object]:
        return {
            "agent": self.agent,
            "current_model": self.current_model,
            "current_cost_usd": round(self.current_cost_usd, 4),
            "alt_model": self.alt_model,
            "alt_cost_usd": round(self.alt_cost_usd, 4),
            "savings_usd": round(self.savings_usd, 4),
            "reduction_pct": round(self.reduction_pct, 2),
        }


@dataclass(frozen=True, slots=True)
class PriorityRow:
    rank: int
    agent: str
    invocations: int
    cost_usd: float
    current_models: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "rank": self.rank,
            "agent": self.agent,
            "invocations": self.invocations,
            "cost_usd": round(self.cost_usd, 4),
            "current_models": list(self.current_models),
        }


@dataclass(frozen=True, slots=True)
class CostBaselineReport:
    status: str
    reason_code: str
    message: str
    data_window_days: int
    pricing_table_retrieved: str
    pricing_stale: bool
    sessions_analyzed: int
    actual_billed_ai_credits: float
    actual_billed_usd: float
    cli_buckets: tuple[AgentBucket, ...]
    chat_buckets: tuple[ChatBucket, ...]
    savings: tuple[SavingsRow, ...]
    priority: tuple[PriorityRow, ...]
    skipped_files: int
    skipped_lines: int
    unknown_agents: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "reason_code": self.reason_code,
            "message": self.message,
            "data_window_days": self.data_window_days,
            "pricing_table_retrieved": self.pricing_table_retrieved,
            "pricing_stale": self.pricing_stale,
            "sessions_analyzed": self.sessions_analyzed,
            "actual_billed_ai_credits": round(self.actual_billed_ai_credits, 2),
            "actual_billed_usd": round(self.actual_billed_usd, 2),
            "cli_buckets": [b.to_dict() for b in self.cli_buckets],
            "chat_buckets": [b.to_dict() for b in self.chat_buckets],
            "savings": [s.to_dict() for s in self.savings],
            "priority": [p.to_dict() for p in self.priority],
            "skipped_files": self.skipped_files,
            "skipped_lines": self.skipped_lines,
            "unknown_agents": list(self.unknown_agents),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, indent=2)


def _epoch_cutoff(days: int) -> float:
    return time.time() - days * 86400.0


def _coerce_int(value: object) -> int:
    """Coerce telemetry numeric to int; return 0 for None / non-numeric / bool.

    Telemetry schemas drift; a field documented as int can occasionally arrive
    as a string, list, or null. Returning 0 keeps the aggregator running
    instead of aborting on a single malformed value.
    """
    if value is None or isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        try:
            return int(value)
        except (ValueError, OverflowError):
            return 0
    return 0


def _iter_session_events(
    home: Path, cutoff_epoch: float, skipped: dict[str, int]
) -> Iterator[tuple[str, dict]]:
    """Stream (session_id, event_dict) pairs across last-N-day session files.

    Increments ``skipped["files"]`` for any file that raises ``OSError`` at
    open time and ``skipped["lines"]`` for any line that fails JSON parse
    OR triggers ``UnicodeDecodeError`` (the latter is caught by
    ``errors="replace"`` on open(), which replaces the offending bytes
    rather than aborting the iteration). Sessions whose ``events.jsonl``
    mtime predates ``cutoff_epoch`` are skipped silently.
    """
    for path in home.glob(SESSION_STATE_GLOB):
        try:
            mtime = path.stat().st_mtime
        except OSError:
            skipped["files"] += 1
            continue
        if mtime < cutoff_epoch:
            continue
        session_id = path.parent.name
        try:
            with path.open(encoding="utf-8", errors="replace") as f:
                for line in f:
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        skipped["lines"] += 1
                        continue
                    if not isinstance(event, dict):
                        skipped["lines"] += 1
                        continue
                    yield session_id, event
        except OSError:
            skipped["files"] += 1


def _iter_otel_inferences(
    home: Path, cutoff_epoch: float, skipped: dict[str, int]
) -> Iterator[dict]:
    """Yield gen_ai inference operation events from OTEL traces.

    Filters to events where ``attributes.event.name`` is exactly
    ``gen_ai.client.inference.operation.details``. Non-inference events
    (auth, hooks, sessions) are skipped without contributing to the
    ``skipped_*`` counters because they are expected, not malformed.
    """
    for path in home.glob(OTEL_GLOB):
        try:
            mtime = path.stat().st_mtime
        except OSError:
            skipped["files"] += 1
            continue
        if mtime < cutoff_epoch:
            continue
        try:
            with path.open(encoding="utf-8", errors="replace") as f:
                for line in f:
                    try:
                        e = json.loads(line)
                    except json.JSONDecodeError:
                        skipped["lines"] += 1
                        continue
                    if not isinstance(e, dict):
                        skipped["lines"] += 1
                        continue
                    attrs = e.get("attributes")
                    if not isinstance(attrs, dict):
                        continue
                    if attrs.get("event.name") == OTEL_INFERENCE_EVENT_NAME:
                        yield attrs
        except OSError:
            skipped["files"] += 1


def collect_cli(
    home: Path, days: int
) -> tuple[
    tuple[AgentBucket, ...], int, float, dict[str, int], tuple[str, ...]
]:
    """Aggregate per-(agent, model) cost from CLI session events.

    Returns:
        cli_buckets, session_count, actual_nano_aiu, skipped_counts,
        unknown_agents (agent names not in :data:`AGENT_CLASS`).
    """
    cutoff = _epoch_cutoff(days)
    raw_buckets: dict[
        tuple[str, str], dict[str, int | set[str]]
    ] = defaultdict(lambda: {
        "invocations": 0,
        "total_tokens": 0,
        "total_duration_ms": 0,
        "failures": 0,
        "sessions": set(),
    })
    sessions_seen: set[str] = set()
    unknown_agents: set[str] = set()
    actual_nano_aiu = 0.0
    skipped = {"files": 0, "lines": 0}
    for session_id, event in _iter_session_events(home, cutoff, skipped):
        et = event.get("type")
        if et == "subagent.completed":
            data = event.get("data")
            if not isinstance(data, dict):
                continue
            agent = data.get("agentName") or "?"
            model = data.get("model") or "?"
            tokens = _coerce_int(data.get("totalTokens"))
            dur = _coerce_int(data.get("durationMs"))
            tool_calls = _coerce_int(data.get("totalToolCalls"))
            key = (agent, model)
            bucket = raw_buckets[key]
            bucket["invocations"] += 1
            bucket["total_tokens"] += tokens
            bucket["total_duration_ms"] += dur
            bucket["sessions"].add(session_id)
            sessions_seen.add(session_id)
            if agent not in AGENT_CLASS and agent != "?":
                unknown_agents.add(agent)
            if tokens == 0 and tool_calls == 0 and dur < 5000:
                bucket["failures"] += 1
        elif et == "session.shutdown":
            data = event.get("data")
            if not isinstance(data, dict):
                continue
            nano = data.get("totalNanoAiu")
            if isinstance(nano, (int, float)) and not isinstance(nano, bool):
                actual_nano_aiu += float(nano)
            sessions_seen.add(session_id)
    cli_buckets = tuple(
        AgentBucket(
            agent=k[0],
            model=k[1],
            invocations=v["invocations"],
            total_tokens=v["total_tokens"],
            total_duration_ms=v["total_duration_ms"],
            failures=v["failures"],
            sessions_count=len(v["sessions"]),
        )
        for k, v in raw_buckets.items()
    )
    return (
        cli_buckets,
        len(sessions_seen),
        actual_nano_aiu,
        skipped,
        tuple(sorted(unknown_agents)),
    )


def collect_chat(
    home: Path, days: int
) -> tuple[tuple[ChatBucket, ...], dict[str, int]]:
    """Aggregate per-model VS Code Copilot Chat inferences from OTEL traces."""
    cutoff = _epoch_cutoff(days)
    raw: dict[str, dict[str, int]] = defaultdict(
        lambda: {"inferences": 0, "input_tokens": 0, "output_tokens": 0}
    )
    skipped = {"files": 0, "lines": 0}
    for attrs in _iter_otel_inferences(home, cutoff, skipped):
        model = attrs.get("gen_ai.request.model") or "?"
        if model == "?":
            continue
        bucket = raw[model]
        bucket["inferences"] += 1
        bucket["input_tokens"] += _coerce_int(attrs.get("gen_ai.usage.input_tokens"))
        bucket["output_tokens"] += _coerce_int(attrs.get("gen_ai.usage.output_tokens"))
    chat_buckets = tuple(
        ChatBucket(
            model=model,
            inferences=v["inferences"],
            input_tokens=v["input_tokens"],
            output_tokens=v["output_tokens"],
        )
        for model, v in raw.items()
    )
    return chat_buckets, skipped


def _cheapest_candidate(
    workload_class: str, current_model: str
) -> str | None:
    """Return cheapest known-priced candidate model for ``workload_class``.

    Skips the current model. Returns ``None`` if no priced candidate is
    cheaper than the current model on blended-rate basis. Returns ``None``
    when ``current_model`` is not in :data:`PRICING` (defensive: refuses
    to recommend swaps based on $0 baseline cost).
    """
    pool = {
        "lightweight": LIGHTWEIGHT_CANDIDATES,
        "versatile": VERSATILE_CANDIDATES,
        "powerful": POWERFUL_CANDIDATES,
    }.get(workload_class, VERSATILE_CANDIDATES)
    current_rate = blended_rate(current_model)
    if not current_rate:
        return None
    best: tuple[str, float] | None = None
    for cand in pool:
        if cand == current_model or cand not in PRICING:
            continue
        rate = blended_rate(cand)
        if rate < current_rate:
            if best is None or rate < best[1]:
                best = (cand, rate)
    return best[0] if best else None


def _build_savings(
    cli_buckets: Sequence[AgentBucket],
) -> tuple[SavingsRow, ...]:
    rows: list[SavingsRow] = []
    for b in cli_buckets:
        klass = AGENT_CLASS.get(b.agent, "versatile")
        alt = _cheapest_candidate(klass, b.model)
        if alt is None:
            continue
        alt_cost = estimate_cost_usd(alt, b.total_tokens)
        savings = b.est_cost_usd - alt_cost
        if savings <= 0:
            continue
        reduction = savings / b.est_cost_usd * 100.0 if b.est_cost_usd else 0.0
        rows.append(
            SavingsRow(
                agent=b.agent,
                current_model=b.model,
                current_cost_usd=b.est_cost_usd,
                alt_model=alt,
                alt_cost_usd=alt_cost,
                savings_usd=savings,
                reduction_pct=reduction,
            )
        )
    rows.sort(key=lambda r: r.savings_usd, reverse=True)
    return tuple(rows)


def _build_priority(
    cli_buckets: Sequence[AgentBucket], top_n: int
) -> tuple[PriorityRow, ...]:
    by_cost: dict[str, float] = defaultdict(float)
    by_inv: dict[str, int] = defaultdict(int)
    by_models: dict[str, set[str]] = defaultdict(set)
    for b in cli_buckets:
        by_cost[b.agent] += b.est_cost_usd
        by_inv[b.agent] += b.invocations
        by_models[b.agent].add(b.model)
    ranked = sorted(by_cost.items(), key=lambda kv: kv[1], reverse=True)[
        :top_n
    ]
    return tuple(
        PriorityRow(
            rank=i,
            agent=agent,
            invocations=by_inv[agent],
            cost_usd=cost,
            current_models=tuple(sorted(by_models[agent])),
        )
        for i, (agent, cost) in enumerate(ranked, 1)
    )


def _pricing_freshness_stale() -> bool:
    age = (datetime.now(timezone.utc).date() - PRICING_RETRIEVED).days
    return age > MAX_PRICING_STALE_DAYS


def build_report(
    *,
    home: Path,
    days: int,
    top_n: int = 10,
    include_chat: bool = True,
) -> CostBaselineReport:
    """Build a :class:`CostBaselineReport` for the configured window.

    Fails closed (``STATUS_FAIL``) if ``home`` is not a directory or if
    ``days`` is not a positive integer.
    """
    if isinstance(days, bool) or not isinstance(days, int) or days < 1:
        return _empty_report(
            status=STATUS_FAIL,
            reason_code=REASON_CODE_INVALID_INPUT,
            message=f"--days must be a positive integer (got: {days!r})",
            days=days if isinstance(days, int) and not isinstance(days, bool) else 0,
        )
    if not home.is_dir():
        return _empty_report(
            status=STATUS_FAIL,
            reason_code=REASON_CODE_MISSING_COPILOT_HOME,
            message=(
                f"Copilot home directory does not exist or is not a "
                f"directory: {home}"
            ),
            days=days,
        )

    cli_buckets, sessions_analyzed, actual_nano_aiu, cli_skipped, unknown = (
        collect_cli(home, days)
    )
    if include_chat:
        chat_buckets, chat_skipped = collect_chat(home, days)
    else:
        chat_buckets = ()
        chat_skipped = {"files": 0, "lines": 0}

    cli_buckets_sorted = tuple(
        sorted(cli_buckets, key=lambda b: b.est_cost_usd, reverse=True)
    )
    chat_buckets_sorted = tuple(
        sorted(chat_buckets, key=lambda b: b.est_cost_usd, reverse=True)
    )
    savings = _build_savings(cli_buckets_sorted)
    priority = _build_priority(cli_buckets_sorted, top_n)

    actual_ai_credits = actual_nano_aiu / 1e9
    actual_usd = actual_ai_credits * 0.01

    return CostBaselineReport(
        status=STATUS_PASS,
        reason_code=REASON_CODE_OK,
        message=(
            f"analysis complete: {sessions_analyzed} sessions across last "
            f"{days}d"
        ),
        data_window_days=days,
        pricing_table_retrieved=PRICING_RETRIEVED.isoformat(),
        pricing_stale=_pricing_freshness_stale(),
        sessions_analyzed=sessions_analyzed,
        actual_billed_ai_credits=actual_ai_credits,
        actual_billed_usd=actual_usd,
        cli_buckets=cli_buckets_sorted,
        chat_buckets=chat_buckets_sorted,
        savings=savings,
        priority=priority,
        skipped_files=cli_skipped["files"] + chat_skipped["files"],
        skipped_lines=cli_skipped["lines"] + chat_skipped["lines"],
        unknown_agents=unknown,
    )


def _empty_report(
    *, status: str, reason_code: str, message: str, days: int
) -> CostBaselineReport:
    return CostBaselineReport(
        status=status,
        reason_code=reason_code,
        message=message,
        data_window_days=days,
        pricing_table_retrieved=PRICING_RETRIEVED.isoformat(),
        pricing_stale=_pricing_freshness_stale(),
        sessions_analyzed=0,
        actual_billed_ai_credits=0.0,
        actual_billed_usd=0.0,
        cli_buckets=(),
        chat_buckets=(),
        savings=(),
        priority=(),
        skipped_files=0,
        skipped_lines=0,
        unknown_agents=(),
    )


def _render_baseline_table(buckets: Sequence[AgentBucket]) -> str:
    out = [
        f"{'agent':<32} {'model':<22} {'inv':>5} {'tok(M)':>8} "
        f"{'est_$':>8} {'avg_dur':>8} {'fail%':>6}"
    ]
    out.append("-" * 95)
    for r in buckets:
        out.append(
            f"{r.agent:<32} {r.model:<22} {r.invocations:>5} "
            f"{r.total_tokens / 1e6:>8.2f} "
            f"${r.est_cost_usd:>7.2f} "
            f"{r.avg_duration_seconds:>7.1f}s "
            f"{r.failure_rate * 100:>5.1f}%"
        )
    return "\n".join(out)


def _render_savings_table(rows: Sequence[SavingsRow]) -> str:
    out = [
        f"{'agent':<32} {'current':<22} {'cur_$':>8} {'alt':<22} "
        f"{'alt_$':>8} {'save_$':>8} {'redux':>6}"
    ]
    out.append("-" * 110)
    for r in rows:
        out.append(
            f"{r.agent:<32} {r.current_model:<22} "
            f"${r.current_cost_usd:>7.2f} {r.alt_model:<22} "
            f"${r.alt_cost_usd:>7.2f} ${r.savings_usd:>7.2f} "
            f"{r.reduction_pct:>5.1f}%"
        )
    total_savings = sum(r.savings_usd for r in rows)
    out.append("-" * 110)
    out.append(
        f"{'TOTAL projected savings':<32} {'':<22} {'':>8} {'':<22} "
        f"{'':>8} ${total_savings:>7.2f}"
    )
    return "\n".join(out)


def _render_chat_table(buckets: Sequence[ChatBucket]) -> str:
    out = [
        f"{'model':<32} {'inf':>6} {'in(M)':>8} {'out(M)':>8} {'est_$':>8}"
    ]
    out.append("-" * 68)
    for r in buckets:
        out.append(
            f"{r.model:<32} {r.inferences:>6} "
            f"{r.input_tokens / 1e6:>8.2f} "
            f"{r.output_tokens / 1e6:>8.2f} "
            f"${r.est_cost_usd:>7.2f}"
        )
    total = sum(r.est_cost_usd for r in buckets)
    out.append("-" * 68)
    out.append(f"{'TOTAL':<32} {'':>6} {'':>8} {'':>8} ${total:>7.2f}")
    return "\n".join(out)


def _render_priority_list(rows: Sequence[PriorityRow]) -> str:
    out = [
        f"{'rank':>4} {'agent':<32} {'invocations':>11} "
        f"{'cost_$':>8} {'current_models'}"
    ]
    out.append("-" * 85)
    for r in rows:
        models_str = ",".join(r.current_models)[:25]
        out.append(
            f"{r.rank:>4} {r.agent:<32} {r.invocations:>11} "
            f"${r.cost_usd:>7.2f} {models_str}"
        )
    return "\n".join(out)


def render_text(report: CostBaselineReport, *, days: int, home: Path) -> str:
    """Render a :class:`CostBaselineReport` as human-readable tables."""
    lines: list[str] = []
    lines.append(
        f"# Copilot agent cost baseline (last {days}d, home={home})"
    )
    if report.pricing_stale:
        age = (datetime.now(timezone.utc).date() - PRICING_RETRIEVED).days
        lines.append("")
        lines.append(
            f"WARNING: pricing table last refreshed "
            f"{PRICING_RETRIEVED} ({age} days ago, max="
            f"{MAX_PRICING_STALE_DAYS}). Re-verify "
            "docs.github.com/en/copilot/reference/copilot-billing/"
            "models-and-pricing and refresh scripts/analysis/pricing.py."
        )
    lines.append("")
    if report.status != STATUS_PASS:
        lines.append(f"ERROR ({report.reason_code}): {report.message}")
        return "\n".join(lines)

    lines.append("## CLI sub-agent baseline (sourced from session events.jsonl)")
    lines.append("")
    lines.append(
        f"Sessions analyzed: {report.sessions_analyzed} | "
        f"Actual billed (from session.shutdown.totalNanoAiu): "
        f"{report.actual_billed_ai_credits:.1f} AI credits ≈ "
        f"${report.actual_billed_usd:.2f}"
    )
    lines.append("")
    if report.cli_buckets:
        lines.append(_render_baseline_table(report.cli_buckets))
    else:
        lines.append("(no sub-agent invocations recorded in window)")
    lines.append("")

    lines.append(
        "## Savings projection (per-agent cheapest viable replacement)"
    )
    lines.append("")
    if report.savings:
        lines.append(_render_savings_table(report.savings))
    else:
        lines.append("(no savings opportunities — all agents already on "
                     "cheapest viable model)")
    lines.append("")

    lines.append(
        f"## Experimentation priority (top {len(report.priority)} by "
        "absolute cost)"
    )
    lines.append("")
    if report.priority:
        lines.append(_render_priority_list(report.priority))
    else:
        lines.append("(no data)")
    lines.append("")

    if report.chat_buckets:
        lines.append(
            "## VS Code Copilot Chat per-model usage "
            "(from gen_ai OTEL traces)"
        )
        lines.append("")
        lines.append(_render_chat_table(report.chat_buckets))
        lines.append("")
        lines.append(
            "  NOTE: Chat cost estimates apply the fresh-input rate to all "
            "input tokens. Cached-input savings (typically 10x on Anthropic, "
            "5-10x on OpenAI with prompt caching) are NOT subtracted. Treat "
            "Chat dollar estimates as an upper bound."
        )
        lines.append("")

    # Observability footer
    footer_parts = []
    if report.skipped_files or report.skipped_lines:
        footer_parts.append(
            f"skipped: {report.skipped_files} unreadable files, "
            f"{report.skipped_lines} malformed lines"
        )
    if report.unknown_agents:
        footer_parts.append(
            f"unmapped agents (defaulted to 'versatile' class): "
            f"{', '.join(report.unknown_agents)}"
        )
    if footer_parts:
        lines.append("# " + " | ".join(footer_parts))

    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(
        prog="copilot-agent-cost-baseline",
        description=(__doc__ or "").split("\n", 1)[0],
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help=(
            "Look back N days (default: 30). Sessions whose events.jsonl "
            "mtime predates the cutoff are skipped. NOTE: per-event "
            "timestamp filtering is not applied — long-running sessions "
            "contribute their full event history if their file was "
            "appended to within the window."
        ),
    )
    parser.add_argument(
        "--home",
        type=Path,
        default=DEFAULT_COPILOT_HOME,
        help=(
            "Copilot data directory (default: ~/.copilot). Only files "
            "matching the fixed sub-paths 'session-state/*/events.jsonl' "
            "and 'traces/vscode-otel-*.jsonl' under this directory are "
            "read; the flag cannot be coerced to read files outside that "
            "pattern."
        ),
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
        help=(
            "Output format. 'text' prints human-readable tables. 'json' "
            "emits a deterministic CostBaselineReport document suitable "
            "for committing alongside a narrative research report (see "
            "docs/research/copilot-agent-cost-baseline-*.md)."
        ),
    )
    return parser


def run_cli(
    argv: Sequence[str] | None = None,
    *,
    output_stream: TextIO = sys.stdout,
) -> int:
    """Parse argv, build a report, and emit it to ``output_stream``.

    Returns 0 on ``STATUS_PASS``, 1 on ``STATUS_FAIL``.
    """
    try:
        args = _build_parser().parse_args(
            list(argv) if argv is not None else None
        )
    except ValueError as exc:
        report = _empty_report(
            status=STATUS_FAIL,
            reason_code=REASON_CODE_INVALID_INPUT,
            message=str(exc),
            days=0,
        )
        output_stream.write(report.to_json())
        output_stream.write("\n")
        return 1

    report = build_report(
        home=args.home,
        days=args.days,
        top_n=args.top,
        include_chat=not args.skip_chat,
    )

    if args.format == "json":
        output_stream.write(report.to_json())
        output_stream.write("\n")
    else:
        output_stream.write(render_text(report, days=args.days, home=args.home))
        output_stream.write("\n")
    return 0 if report.status == STATUS_PASS else 1


def main(argv: Sequence[str] | None = None) -> int:
    return run_cli(argv=argv)


if __name__ == "__main__":
    raise SystemExit(main())
