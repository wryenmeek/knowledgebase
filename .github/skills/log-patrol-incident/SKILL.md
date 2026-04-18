---
name: log-patrol-incident
description: Packages change-patrol incidents into append-only, governance-safe escalation records without creating a direct remediation path. Use when diff review finds destructive, uncited, or policy-sensitive edits that need visible governed follow-up.
---

# Log Patrol Incident

## Overview

Use this skill when `change-patrol` finds a destructive or policy-sensitive edit pattern that must remain visible as a governed incident. It prepares an append-only incident record proposal and escalation bundle without reverting content, rewriting history, or opening a second logging runtime. This is a doc-only workflow.

## Classification

- **Mode:** Doc-only workflow
- **MVP status:** Active
- **Execution boundary:** Incident packaging and governed escalation only. Durable writes remain gated on existing append-only and governance-safe surfaces.

## When to Use

- Diff review finds citation removal, provenance loss, governed metadata deletion, or destructive content changes
- `change-patrol` needs to raise an incident for Human Steward or governance review
- A risky edit must remain visible instead of being silently reverted
- A maintainer needs a stable escalation artifact tied to changed paths and evidence

## Contract

- Input: incident-triggering diff summary, affected paths, and blocking rationale
- Output: an incident record proposal plus the required governance or Human Steward escalation target
- Persistence rule: incident history uses existing governed append-only artifacts such as `wiki/log.md`; this skill itself does not write them
- Handoff rule: destructive or ambiguous incidents return to `knowledgebase-orchestrator` before any content-changing action is considered

## Assertions

- Incident logging preserves why the change is risky and what follow-up lane owns it
- No direct revert, remediation, or destructive history edit is authorized from this skill
- Append-only discipline is preserved when an incident later reaches an approved logging surface
- The skill does not create a second incident ledger, daemon, or background runtime
- Missing evidence or ambiguous ownership remains escalated

## Procedure

### Step 1: Capture the incident trigger

Record the changed paths, the risky diff pattern, and why the edit requires governed review.

### Step 2: Draft the escalation record

Prepare the smallest useful incident summary that names the risk, affected scope, and the next reviewing lane.

### Step 3: Route the incident

Send the proposal back through `knowledgebase-orchestrator`, or escalate to Human Steward review when the risk exceeds deterministic routing authority.

### Step 4: Keep remediation closed

If the request asks for immediate revert or cleanup, stop and keep the response at incident packaging plus escalation only.

## Commands

```bash
python3 -m unittest tests.kb.test_change_patrol_runtime
python3 .github/skills/validate-wiki-governance/logic/validate_wiki_governance.py --mode signal --validator topology-hygiene --path wiki/index.md
```

## Boundaries

- Do not rewrite `wiki/log.md` or any other history in place
- Do not treat incident logging as permission to auto-remediate content
- Do not create a second patrol-incident ledger in MVP
- Do not reopen downstream wiki-writing lanes before governance resolves the incident

## Verification

- [ ] Incident records remain append-only and governance-safe in design
- [ ] Destructive or uncited edits are escalated instead of auto-fixed
- [ ] No direct revert or remediation path is introduced
- [ ] Commands and references resolve inside the repository

## References

- [`AGENTS.md`](../../../AGENTS.md)
- [`docs/architecture.md`](../../../docs/architecture.md)
- [`docs/ideas/wiki-curation-agent-framework.md`](../../../docs/ideas/wiki-curation-agent-framework.md)
- [`raw/processed/SPEC.md`](../../../raw/processed/SPEC.md)
- [`wiki/log.md`](../../../wiki/log.md)
- [`.github/agents/change-patrol.md`](../../agents/change-patrol.md)
- [`.github/skills/log-policy-conflict/SKILL.md`](../log-policy-conflict/SKILL.md)
