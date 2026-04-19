---
name: analyze-missed-queries
description: Reviews queries that produced low-quality or no-result answers to identify wiki coverage gaps. Use when quality-analyst needs evidence of what knowledge is absent before prioritizing new synthesis work.
---

# Analyze Missed Queries

## Overview

This skill documents the missed-query analysis step for the `quality-analyst` persona.
A missed query is any query to `query-synthesist` that produced a low-confidence
answer, a partial result, or no matching wiki page. Analyzing these gaps provides
evidence for curation prioritization decisions. Analysis is read-only; gap findings
route to `prioritize-curation-backlog`.

**Doc-only workflow.** No `logic/` dir is introduced.

## Classification

- **Mode:** Doc-only workflow
- **MVP status:** Active
- **Execution boundary:** Read-only gap analysis. No new wiki pages are created
  directly from this skill.

## When to Use

- A query log or operator feedback indicates that `query-synthesist` regularly
  fails on a topic area
- `quality-analyst` needs evidence of knowledge gaps before recommending new
  synthesis work to `knowledgebase-orchestrator`
- An operator wants to understand which domains have insufficient wiki coverage
- `prioritize-curation-backlog` requires a missed-query analysis to weight new-page
  work against update work

## Contract

- Input: a query log or a set of query results marked as low-confidence or no-match
- Output: a structured coverage-gap report listing topic areas, query patterns,
  and evidence of what is missing
- Handoff: coverage gaps route to `prioritize-curation-backlog` and then to
  `knowledgebase-orchestrator` for intake consideration

## Assertions

- No wiki pages are created or modified directly by this skill
- Coverage gaps are evidence only; synthesis requires the full intake-safe lane
- Query results used as input must be repo-local or explicitly consented operator
  records — no external service calls
- Missing query log fails closed with an explicit error rather than a silent empty report

## References

- `AGENTS.md`
- `docs/architecture.md`
- `raw/processed/SPEC.md`
- `.github/agents/quality-analyst.md`
- `.github/agents/query-synthesist.md`
