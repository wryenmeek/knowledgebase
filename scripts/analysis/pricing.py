"""Official GitHub Copilot per-million-token pricing and effort-output multipliers for AI Credits.

Source: docs.github.com/en/copilot/reference/copilot-billing/models-and-pricing
(retrieved 2026-06-27). Prices are USD per 1,000,000 tokens. 1 AI Credit = $0.01.

Anthropic models include a separate ``cache_write`` price; non-Anthropic models
omit it. ``input`` is uncached/fresh input. ``cached`` is the per-token cost
when input is served from the model provider's cache.

The pricing table is the single source of truth for cost estimation in
``scripts/analysis``. If the docs page is updated, update this table in the
same commit; ``MAX_PRICING_STALE_DAYS`` triggers a warning when the file is
older than the threshold.

**Long-context tier (optional, opt-in per call).** Three models publish a
separate Long-context tier triggered when input tokens exceed a threshold:

  - ``gpt-5.4`` (> 272K input): $5.00 / $22.50 per 1M in/out
  - ``gpt-5.5`` (> 272K input): $10.00 / $45.00 per 1M in/out
  - ``gemini-3.1-pro`` (> 200K input): $4.00 / $18.00 per 1M in/out

These rates are stored in :class:`ModelPrice` via the optional
``long_context_input_per_m``, ``long_context_output_per_m``, and
``input_threshold_tokens`` fields. :func:`estimate_cost_usd` selects the
long-context tier when the caller passes ``input_tokens_for_threshold`` and
that value exceeds the model's threshold. When the parameter is omitted (the
default), Default-tier rates are used — fully backward-compatible.

**Known limitation:** CLI-side sub-agent telemetry (``subagent.completed``)
exposes only aggregate ``totalTokens`` with no input/output split. The
``input_tokens_for_threshold`` parameter cannot be populated from CLI events,
so CLI-side estimates remain bias-down for any invocation that crossed the
long-context threshold. Chat-side OTEL events expose per-call
``gen_ai.usage.input_tokens``, making the parameter applicable there.

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

    All base fields are USD per 1,000,000 tokens. ``cache_write_per_m`` is
    ``None`` for providers that do not bill cache writes separately (currently
    OpenAI, Google, Microsoft).

    The three ``long_context_*`` fields are populated only for models that
    publish a separate Long-context tier. When ``input_threshold_tokens`` is
    set, callers may pass ``input_tokens_for_threshold`` to
    :func:`estimate_cost_usd` to select the appropriate tier automatically.
    ``cached_per_m`` is unchanged between tiers (not separately published for
    the long-context tier).
    """

    input_per_m: float
    cached_per_m: float
    output_per_m: float
    cache_write_per_m: float | None = None
    long_context_input_per_m: float | None = None
    long_context_output_per_m: float | None = None
    input_threshold_tokens: int | None = None


# Keys are the canonical model id used by Copilot CLI / Chat OTEL. See the
# ``Supported AI models`` page for canonical naming.
PRICING: dict[str, ModelPrice] = {
    # OpenAI
    "gpt-5-mini": ModelPrice(0.25, 0.025, 2.00),
    "gpt-5.3-codex": ModelPrice(1.75, 0.175, 14.00),
    "gpt-5.4": ModelPrice(
        2.50, 0.25, 15.00,
        long_context_input_per_m=5.00,
        long_context_output_per_m=22.50,
        input_threshold_tokens=272_000,
    ),
    "gpt-5.4-mini": ModelPrice(0.75, 0.075, 4.50),
    "gpt-5.4-nano": ModelPrice(0.20, 0.02, 1.25),
    "gpt-5.5": ModelPrice(
        5.00, 0.50, 30.00,
        long_context_input_per_m=10.00,
        long_context_output_per_m=45.00,
        input_threshold_tokens=272_000,
    ),
    # Anthropic (cache_write applies)
    "claude-haiku-4.5": ModelPrice(1.00, 0.10, 5.00, cache_write_per_m=1.25),
    "claude-sonnet-4": ModelPrice(3.00, 0.30, 15.00, cache_write_per_m=3.75),
    "claude-sonnet-4.5": ModelPrice(3.00, 0.30, 15.00, cache_write_per_m=3.75),
    "claude-sonnet-4.6": ModelPrice(3.00, 0.30, 15.00, cache_write_per_m=3.75),
    "claude-opus-4.5": ModelPrice(5.00, 0.50, 25.00, cache_write_per_m=6.25),
    "claude-opus-4.6": ModelPrice(5.00, 0.50, 25.00, cache_write_per_m=6.25),
    "claude-opus-4.7": ModelPrice(5.00, 0.50, 25.00, cache_write_per_m=6.25),
    "claude-opus-4.8": ModelPrice(5.00, 0.50, 25.00, cache_write_per_m=6.25),
    "claude-fable-5": ModelPrice(10.00, 1.00, 50.00, cache_write_per_m=12.50),
    # Google
    "gemini-2.5-pro": ModelPrice(1.25, 0.125, 10.00),
    "gemini-3-flash": ModelPrice(0.50, 0.05, 3.00),
    "gemini-3.1-pro": ModelPrice(
        2.00, 0.20, 12.00,
        long_context_input_per_m=4.00,
        long_context_output_per_m=18.00,
        input_threshold_tokens=200_000,
    ),
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
    *,
    effort: str = "default",
) -> float:
    """Return blended USD-per-1M-token rate for ``model``.

    The default shares (20% fresh input, 70% cached input, 10% output) reflect
    typical Copilot agentic workloads where most context is reused turn-to-turn
    after the first few inferences. Override the shares to model a different
    workload profile.

    ``effort`` (``default``/``low``/``medium``/``high``/``xhigh``/``max``)
    scales the output-token component to approximate the cost impact of
    extended reasoning tokens. Multipliers are industry-observed and rounded:

    ====== ======== =====================================================
    Effort Mult.    Notes
    ====== ======== =====================================================
    low    0.7×     reduced reasoning tokens
    default/medium  1.0× baseline
    high   2.5×     2-3× output tokens typical
    xhigh  5.0×     4-6× output tokens typical
    max    7.0×     opus-4.7 only; longest reasoning budget
    ====== ======== =====================================================

    Models that do not support effort (``claude-haiku-4.5``,
    ``claude-sonnet-4.x``, ``gemini-*``, etc.) ignore the parameter — their
    output rate is unaffected because the provider does not expose a
    reasoning-budget knob.

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
    output_mult = _effort_output_multiplier(model, effort)
    return (
        input_share * fresh_input_rate
        + cache_share * price.cached_per_m
        + output_share * price.output_per_m * output_mult
    )


# Effort cost-multipliers applied to the output-token share. Reasoning
# tokens are billed as output by the major providers (OpenAI, Anthropic,
# Google), so extended reasoning at higher effort levels directly inflates
# the output-token line. Multipliers are industry-observed and rounded;
# actual per-task variance is wide (e.g., simple lookups stay near 1×
# even at effort=high). Treat as a planning-grade estimate.
_EFFORT_OUTPUT_MULTIPLIER: dict[str, float] = {
    "low": 0.7,
    "default": 1.0,
    "medium": 1.0,
    "high": 2.5,
    "xhigh": 5.0,
    "max": 7.0,
}

# Models that support an effort knob. Models NOT in this set ignore
# ``effort=`` because the provider does not expose a reasoning budget.
# Source: task tool model registry (system prompt; verified 2026-06-27).
EFFORT_CAPABLE_MODELS: frozenset[str] = frozenset({
    "claude-opus-4.6",
    "claude-opus-4.7",
    "gpt-5-mini",
    "gpt-5.3-codex",
    "gpt-5.4",
    "gpt-5.4-mini",
    "gpt-5.5",
})


def _effort_output_multiplier(model: str, effort: str) -> float:
    """Return the output-token multiplier for ``model`` at ``effort``.

    Per-effort multipliers (applied to the output share only):

    * ``low``: 0.7× (reduced reasoning tokens)
    * ``default`` / ``medium``: 1.0× (baseline)
    * ``high``: 2.5×
    * ``xhigh``: 5.0×
    * ``max``: 7.0× (opus-4.7 only)

    Returns 1.0 for models that don't support effort (any model not in
    :data:`EFFORT_CAPABLE_MODELS`), for non-string or unhashable effort
    values, for unknown effort strings, or for ``effort="default"`` /
    ``"medium"``.
    """
    if model not in EFFORT_CAPABLE_MODELS:
        return 1.0
    if not isinstance(effort, str):
        return 1.0
    return _EFFORT_OUTPUT_MULTIPLIER.get(effort, 1.0)


def estimate_cost_usd(
    model: str,
    total_tokens: int,
    *,
    effort: str = "default",
    input_tokens_for_threshold: int | None = None,
    **shares: float,
) -> float:
    """Estimate USD cost for ``total_tokens`` rendered by ``model``.

    Uses :func:`blended_rate` to compute a per-1M-token blended rate and
    multiplies by ``total_tokens / 1_000_000``. Returns ``0.0`` if the model is
    not in :data:`PRICING`. See :func:`blended_rate` for the ``effort``
    parameter and its multiplier table.

    **Long-context tier selection** (opt-in):

    Pass ``input_tokens_for_threshold`` when the per-call input-token count is
    known. If the value exceeds the model's ``input_threshold_tokens`` and the
    model declares long-context rates, the long-context input and output rates
    are substituted for the Default-tier rates. ``cached_per_m`` is unchanged.
    When ``input_tokens_for_threshold`` is ``None`` (the default), Default-tier
    rates are always used — fully backward-compatible with existing callers.

    Note: CLI-side sub-agent telemetry exposes only aggregate ``totalTokens``
    with no input/output split, so ``input_tokens_for_threshold`` cannot be
    populated there. CLI-side cost estimates therefore remain bias-down for
    invocations that crossed the long-context threshold. Chat-side OTEL events
    expose per-call ``gen_ai.usage.input_tokens``, making this parameter
    applicable on that path.
    """
    price = PRICING.get(model)
    if price is None:
        return 0.0

    use_long_context = (
        input_tokens_for_threshold is not None
        and price.input_threshold_tokens is not None
        and input_tokens_for_threshold > price.input_threshold_tokens
        and price.long_context_input_per_m is not None
        and price.long_context_output_per_m is not None
    )

    if use_long_context:
        # Compute blended rate using long-context input/output rates.
        # Resolve shares with the same defaults as blended_rate (20/70/10).
        input_share = shares.get("input_share", 0.20)
        cache_share = shares.get("cache_share", 0.70)
        output_share = shares.get("output_share", 0.10)
        output_mult = _effort_output_multiplier(model, effort)
        lc_rate = (
            input_share * price.long_context_input_per_m
            + cache_share * price.cached_per_m
            + output_share * price.long_context_output_per_m * output_mult
        )
        return lc_rate * total_tokens / 1_000_000.0

    rate = blended_rate(model, effort=effort, **shares)
    return rate * total_tokens / 1_000_000.0
