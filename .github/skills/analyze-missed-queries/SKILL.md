---
name: analyze-missed-queries
description: Scans wiki pages for coverage gaps — missing citations, low-confidence markers, placeholder text, and empty sources — to identify where synthesis work is needed. Use when quality-analyst needs evidence of knowledge gaps before prioritizing new synthesis work.
---

# Analyze Missed Queries

## Overview

This skill implements wiki coverage gap analysis for the `quality-analyst` persona.
It scans wiki pages for gap markers: placeholder `TODO`/`PLACEHOLDER`/`TBD` text,
low-confidence frontmatter, empty sources lists, and unresolved question markers.
Gap findings route to `prioritize-curation-backlog`. Analysis is read-only.

## Classification

- **Mode:** `scan` — read-only gap analysis from wiki evidence
- **MVP status:** Active
- **Execution boundary:** Read-only. No new wiki pages are created directly.

## When to Use

- A query log or operator feedback indicates that `query-synthesist` regularly
  fails on a topic area
- `quality-analyst` needs evidence of knowledge gaps before recommending new
  synthesis work to `knowledgebase-orchestrator`
- An operator wants to understand which domains have insufficient wiki coverage
- `prioritize-curation-backlog` requires a missed-query analysis to weight new-page
  work against update work

## Contract

- **Input:** wiki page paths (defaults to all `wiki/**/*.md` pages)
- **Output:** per-page gap findings listing gap type and pattern; summary includes
  `scanned_count` and `gap_page_count`
- **Handoff:** coverage gaps route to `prioritize-curation-backlog` and then to
  `knowledgebase-orchestrator` for intake consideration

## Assertions

- No wiki pages are created or modified directly by this skill
- Coverage gaps are evidence only; synthesis requires the full intake-safe lane
- Wiki paths outside `wiki/**` are rejected (path-escape protection)
- Missing query log fails closed with an explicit error rather than a silent empty report
- This skill operates on repo-local wiki evidence only; external query logs are not
  imported without operator consent

## References

- `AGENTS.md`
- `raw/processed/SPEC.md`
- `.github/skills/analyze-missed-queries/logic/analyze_missed_queries.py`
- `.github/agents/quality-analyst.md`
- `.github/agents/query-synthesist.md`
