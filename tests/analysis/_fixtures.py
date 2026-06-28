"""Shared synthetic-fixture builders for the cost_baseline test suite.

These helpers are not pytest fixtures (no ``@pytest.fixture`` decorator);
they are plain functions imported directly by test modules.

**Exported surface** (cross-file helpers only):

* ``_write_session`` — write a synthetic CLI ``events.jsonl`` session file.
* ``_subagent_completed`` — build a ``subagent.completed`` event dict.
* ``_session_shutdown`` — build a ``session.shutdown`` event dict.
* ``_write_otel_session`` — write a synthetic OTEL traces file.
* ``_otel_inference_event`` — build a ``gen_ai.client.inference...`` OTEL event.

Helpers that are *not* here by design
--------------------------------------
``_session_start``, ``_task_tool_start``, and ``_subagent_with_id`` remain
local to ``test_cost_baseline.py``.  Those helpers produce CLI session-event
shapes that are only needed for the effort-capture / bucket-attribution tests
in that file and are not shared with ``test_cost_baseline_chat.py`` (which
tests OTEL-based chat aggregation) or ``test_pricing.py``.  Moving them here
would add cross-file coupling without any duplication benefit.
"""

from __future__ import annotations

import json
from pathlib import Path


def _write_session(home: Path, session_id: str, events: list[dict]) -> Path:
    sess_dir = home / "session-state" / session_id
    sess_dir.mkdir(parents=True, exist_ok=True)
    p = sess_dir / "events.jsonl"
    p.write_text(
        "\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8"
    )
    return p


def _subagent_completed(
    agent: str = "general-purpose",
    model: str = "gpt-5.5",
    tokens: int = 1_000_000,
    tool_calls: int = 5,
    duration_ms: int = 60_000,
) -> dict:
    return {
        "type": "subagent.completed",
        "data": {
            "agentName": agent,
            "model": model,
            "totalTokens": tokens,
            "totalToolCalls": tool_calls,
            "durationMs": duration_ms,
        },
    }


def _session_shutdown(nano_aiu: int) -> dict:
    return {
        "type": "session.shutdown",
        "data": {"totalNanoAiu": nano_aiu},
    }


def _write_otel_session(
    home: Path, filename: str, events: list[dict]
) -> Path:
    """Write a synthetic OTEL traces file under ``home/traces/``."""
    traces_dir = home / "traces"
    traces_dir.mkdir(parents=True, exist_ok=True)
    p = traces_dir / filename
    p.write_text(
        "\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8"
    )
    return p


def _otel_inference_event(
    model: str = "gpt-5.4",
    input_tokens: int = 1000,
    output_tokens: int = 100,
    *,
    cached_input_tokens: int = 0,
    timestamp: str | None = None,
) -> dict:
    """Build a synthetic OTEL gen_ai inference event (top-level envelope)."""
    attrs: dict[str, object] = {
        "event.name": "gen_ai.client.inference.operation.details",
        "gen_ai.request.model": model,
        "gen_ai.usage.input_tokens": input_tokens,
        "gen_ai.usage.output_tokens": output_tokens,
    }
    if cached_input_tokens:
        attrs["gen_ai.usage.cache_read_input_tokens"] = cached_input_tokens
    event: dict[str, object] = {"attributes": attrs}
    if timestamp is not None:
        event["timestamp"] = timestamp
    return event
