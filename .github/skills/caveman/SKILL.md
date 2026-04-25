---
name: caveman
description: "Compresses agent-to-agent output by dropping filler, articles, and pleasantries while keeping full technical accuracy. Use when writing internal agent communications, rubber-duck reports, or sub-agent prompts. NOT for human-facing output."
---

# Caveman

## Overview

Strip filler, articles, pleasantries. Keep full technical accuracy. Target ~75% token reduction.

## When to Use

- Writing sub-agent prompts or persona handoff messages
- Producing rubber-duck reports for internal pipeline consumption
- Any agent-to-agent communication where token reduction matters

## Scope restriction

Doc-only workflow. Agent-to-agent communication ONLY — sub-agent prompts, rubber-duck reports, persona handoffs, internal pipeline messages.

## Why not human-facing?

- **`enforce-npov`** — due weight requires full attribution register with proper natural language; telegraphic style drops necessary hedging.
- **`detect-ai-tells`** — uniform telegraphic cadence is a known AI-generation artifact; triggers false positives.

## Rules

1. Drop articles (a/an/the).
2. Drop filler phrases ("it should be noted", "in order to", "it is important").
3. Drop pleasantries ("please", "thank you", "I'd be happy to").
4. **Keep** all technical terms exactly.
5. **Keep** all proper nouns, identifiers, paths, and numbers.
6. **Keep** all SourceRef citations verbatim.
7. Preserve meaning exactly — compression must not alter semantics.

## Verification

Compare original output vs compressed output:
1. Count tokens (approximate: split on whitespace). Target: compressed ≤ 25% of original token count.
2. Verify all technical terms, proper nouns, paths, numbers, and SourceRef citations are present in the compressed output.
3. If token reduction is < 50%, re-apply rules — the output likely retains too much filler.

> Adapted from mattpocock/skills `caveman`. KB variant restricts to agent-to-agent per NPOV/AI-tells policy.
