# ADR-022: AFK automation uses deterministic scripts; Copilot CLI reserved for HITL

## Status

Accepted — amended in-place: adds AFK advisory pass tier (see § Amendment)

## Date

2026-05-12

## Context

Research into GitHub agentic workflow tooling identified two candidate executors
for automating wiki maintenance tasks in CI:

1. **Copilot CLI (`copilot -p`)** — synchronous, non-interactive LLM invocation
   that blocks an Actions runner until completion. Requires a fine-grained PAT
   with "Copilot Requests: Read" stored as `COPILOT_GITHUB_TOKEN` (the built-in
   `GITHUB_TOKEN` does not have Copilot API access). Repository hooks, MCP, and
   extensions are disabled by default in `-p` mode.

2. **Deterministic Python scripts** — the existing `scripts/kb/`, `scripts/validation/`,
   and `scripts/maintenance/` surfaces, invocable directly in a workflow step
   using the GH App token pattern (`GH_APP_ID`/`GH_APP_PRIVATE_KEY`).

The ADR-014 AFK allowlist permits only bounded, deterministic writes:
`last_updated`, `quality_assessment.freshness_date`, YAML normalization, index
regeneration, and redirect appends. The `validate_afk_output.py` safety net
checks five invariants before any AFK write proceeds (body unchanged, citations
unchanged, links unchanged, identity unchanged, frontmatter fields bounded).

ADR-014 §4 also lists several **read-only advisory skills** as AFK-allowlisted
(`scan-content-freshness`, `suggest-backlinks`, `cross-reference-symmetry-check`,
and others). These require language-model judgment but produce no governed writes —
their output is structured findings that feed downstream queues or patrol cycles.
These cannot be replaced by deterministic Python scripts.

The question is: which executor runs which class of task?

## Decision

Automation is split into three tiers by what gates the governed write:

**Tier 1 — AFK deterministic write** (Python scripts, no LLM):
- Bounded writes allowlisted by ADR-014: `last_updated`, `quality_assessment.freshness_date`,
  YAML normalization, index regeneration, redirect appends
- Executor: Python scripts invoked directly in workflow steps
- Gate: `validate_afk_output.py` (5-check inline safety net, same runner)
- Token: existing `GH_APP_ID`/`GH_APP_PRIVATE_KEY` app-token
- Output: PR for human merge

**Tier 2 — AFK advisory pass** (`copilot -p` skill invocations, read-only):
- Read-only analysis requiring LM judgment: `suggest-backlinks`,
  `cross-reference-symmetry-check`, `analyze-missed-queries`, `detect-ai-tells`,
  `semantic-wiki-lint`, and equivalent advisory skills
- Executor: `copilot -p` with `COPILOT_GITHUB_TOKEN` fine-grained PAT
- Gate: none — read-only, no governed write occurs in this tier
- Output: structured findings JSON uploaded as artifact; consumed by downstream
  patrol cycles or batched into a human-review issue when actionable
- Human is not notified per-finding; only when downstream aggregation warrants it

**Tier 3 — HITL** (`copilot -p`, human gates the governed write):
- Tasks requiring judgment AND a governed write: content synthesis, test failure
  investigation, governance resolution
- Executor: `copilot -p` with `COPILOT_GITHUB_TOKEN`
- Gate: human approval before any governed write
- Output: PR or issue requiring explicit human merge/close

The executor boundary is therefore: **Python scripts for Tier 1 writes** (LLM
non-determinism is a liability when `validate_afk_output.py` must validate the
diff); **`copilot -p` for Tier 2 and Tier 3** (LM judgment required). The
distinction between Tier 2 and Tier 3 is whether a human gates the governed write.

AFK automation workflows (Tier 1):
- Triggered via `workflow_run` events on upstream analysis workflows
- Invoke `scripts/` surfaces directly as workflow steps
- Run `validate_afk_output.py` inline before any write
- Create PRs for human merge; do not auto-commit to the default branch

AFK advisory workflows (Tier 2):
- Triggered via `workflow_run` or schedule events
- Invoke `copilot -p` with skill-specific prompts
- Upload findings artifact; never write to `wiki/` directly
- Feed `change-patrol` cycle or produce batched issues when threshold exceeded

## Consequences

- LLM non-determinism is kept out of the Tier 1 write path. `validate_afk_output.py`
  validates a script-generated diff, which is simpler and more reliable than
  validating an LLM-generated diff.
- Tier 1 workflows do not require a `COPILOT_GITHUB_TOKEN` secret, limiting
  credential surface to the existing GH App token.
- Tier 2 advisory passes require `COPILOT_GITHUB_TOKEN` but produce no governed
  writes — their blast radius is limited to the findings artifact.
- Any proposal to use `copilot -p` for Tier 1 writes must amend this ADR.
- New Tier 1 scripts must declare a row in the AGENTS.md write-surface matrix
  before any protected write is permitted.
- The `afk-candidate` classification (from `classify_stale.py` or
  `classify_drift.py`) is not operative on its own — `validate_afk_output.py`
  must confirm all 5 checks before any Tier 1 write proceeds. See CONTEXT.md.

## Amendment

**Date:** 2026-05-12 (same day as initial acceptance)

**What changed:** Initial decision framed this as a binary (AFK = scripts, HITL = Copilot CLI). Grilling surfaced that ADR-014 §4 AFK-allowlists several read-only advisory skills (`suggest-backlinks`, `cross-reference-symmetry-check`, etc.) that require LM judgment but produce no writes. These cannot be handled by deterministic scripts and are not HITL (no human gates each finding). Added Tier 2 "AFK advisory pass" to model this class.

**What didn't change:** The Tier 1 rule — Python scripts, not Copilot CLI, for AFK writes — is unchanged. `validate_afk_output.py` remains the gate for any Tier 1 write.

## Related decisions

- [`ADR-030`](ADR-030-cli-write-confirmation.md) — Keeps the deterministic script
  write path's explicit `--apply` confirmation ceremony aligned with the
  AFK/HITL executor boundary this ADR defines.
