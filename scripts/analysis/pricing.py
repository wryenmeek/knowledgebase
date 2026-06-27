"""Official GitHub Copilot per-million-token pricing for AI Credits.

Source: docs.github.com/en/copilot/reference/copilot-billing/models-and-pricing
(retrieved 2026-06-27). Prices are USD per 1,000,000 tokens. 1 AI Credit = $0.01.

Anthropic models include a separate ``cache_write`` price; non-Anthropic models
omit it. ``input`` is uncached/fresh input. ``cached`` is the per-token cost
when input is served from the model provider's cache.

The pricing table is the single source of truth for cost estimation in
``scripts/analysis``. If the docs page is updated, update this table in the
same commit; ``MAX_PRICING_STALE_DAYS`` triggers a warning when the file is
older than the threshold.

This module is import-only and contains no I/O. It is safe to import from
read-only analyzer surfaces.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


PRICING_RETRIEVED = date(2026, 6, 27)
MAX_PRICING_STALE_DAYS = 60


@dataclass(frozen=True)
class ModelPrice:
    """Per-1M-token USD pricing for a single Copilot model.

    All four fields are USD per 1,000,000 tokens. ``cache_write`` is ``None``
    for providers that do not bill cache writes separately (currently
    OpenAI, Google, Microsoft).
    """

    input_per_m: float
    cached_per_m: float
    output_per_m: float
    cache_write_per_m: float | None = None


# Keys are the canonical model id used by Copilot CLI / Chat OTEL. See the
# ``Supported AI models`` page for canonical naming.
PRICING: dict[str, ModelPrice] = {
    # OpenAI
    "gpt-5-mini": ModelPrice(0.25, 0.025, 2.00),
    "gpt-5.3-codex": ModelPrice(1.75, 0.175, 14.00),
    "gpt-5.4": ModelPrice(2.50, 0.25, 15.00),
    "gpt-5.4-mini": ModelPrice(0.75, 0.075, 4.50),
    "gpt-5.4-nano": ModelPrice(0.20, 0.02, 1.25),
    "gpt-5.5": ModelPrice(5.00, 0.50, 30.00),
    # Anthropic (cache_write applies)
    "claude-haiku-4.5": ModelPrice(1.00, 0.10, 5.00, cache_write_per_m=1.25),
    "claude-sonnet-4": ModelPrice(3.00, 0.30, 15.00, cache_write_per_m=3.75),
    "claude-sonnet-4.5": ModelPrice(3.00, 0.30, 15.00, cache_write_per_m=3.75),
    "claude-sonnet-4.6": ModelPrice(3.00, 0.30, 15.00, cache_write_per_m=3.75),
    "claude-opus-4.5": ModelPrice(5.00, 0.50, 25.00, cache_write_per_m=6.25),
    "claude-opus-4.6": ModelPrice(5.00, 0.50, 25.00, cache_write_per_m=6.25),
    "claude-opus-4.6-fast": ModelPrice(5.00, 0.50, 25.00, cache_write_per_m=6.25),
    "claude-opus-4.7": ModelPrice(5.00, 0.50, 25.00, cache_write_per_m=6.25),
    "claude-opus-4.8": ModelPrice(5.00, 0.50, 25.00, cache_write_per_m=6.25),
    "claude-fable-5": ModelPrice(10.00, 1.00, 50.00, cache_write_per_m=12.50),
    # Google
    "gemini-2.5-pro": ModelPrice(1.25, 0.125, 10.00),
    "gemini-3-flash": ModelPrice(0.50, 0.05, 3.00),
    "gemini-3.1-pro": ModelPrice(2.00, 0.20, 12.00),
    "gemini-3.5-flash": ModelPrice(1.50, 0.15, 9.00),
    # Microsoft
    "mai-code-1-flash": ModelPrice(0.75, 0.075, 4.50),
    # Fine-tuned (GitHub)
    "raptor-mini": ModelPrice(0.25, 0.025, 2.00),
}

# Workload-class buckets, used by cost_baseline.py to suggest a cheaper
# replacement for each (agent, current_model) pair. Order = preference,
# cheapest first.
LIGHTWEIGHT_CANDIDATES: tuple[str, ...] = (
    "gpt-5.4-nano",
    "gpt-5-mini",
    "raptor-mini",
    "gemini-3-flash",
    "claude-haiku-4.5",
)
VERSATILE_CANDIDATES: tuple[str, ...] = (
    "claude-haiku-4.5",
    "claude-sonnet-4.6",
)
POWERFUL_CANDIDATES: tuple[str, ...] = (
    "claude-sonnet-4.6",
    "claude-opus-4.7",
)


def blended_rate(
    model: str,
    input_share: float = 0.20,
    cache_share: float = 0.70,
    output_share: float = 0.10,
) -> float:
    """Return blended USD-per-1M-token rate for ``model``.

    The default shares (20% fresh input, 70% cached input, 10% output) reflect
    typical Copilot agentic workloads where most context is reused turn-to-turn
    after the first few inferences. Override the shares to model a different
    workload profile.

    ``cache_write`` is treated as ``input`` for blending purposes when the
    model does not bill cache writes separately, otherwise the cache-write
    rate is used for the input share (slightly conservative; biases the
    estimate slightly higher for Anthropic models, which matches the docs
    pricing table's "cache write" line).
    """

    if abs(input_share + cache_share + output_share - 1.0) > 1e-6:
        msg = "input_share + cache_share + output_share must equal 1.0"
        raise ValueError(msg)
    price = PRICING.get(model)
    if price is None:
        return 0.0
    fresh_input_rate = (
        price.cache_write_per_m
        if price.cache_write_per_m is not None
        else price.input_per_m
    )
    return (
        input_share * fresh_input_rate
        + cache_share * price.cached_per_m
        + output_share * price.output_per_m
    )


def estimate_cost_usd(model: str, total_tokens: int, **shares: float) -> float:
    """Estimate USD cost for ``total_tokens`` rendered by ``model``.

    Uses :func:`blended_rate` to compute a per-1M-token blended rate and
    multiplies by ``total_tokens / 1_000_000``. Returns ``0.0`` if the model is
    not in :data:`PRICING`.
    """

    rate = blended_rate(model, **shares)
    return rate * total_tokens / 1_000_000.0
