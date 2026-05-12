---
name: triage-issue
description: "Classifies, labels, and prioritizes GitHub Issues with a structured workflow. Use when a new issue needs triage or when reviewing the issue backlog."
---

# Triage Issue

## Overview

Apply consistent classification, severity assessment, and labeling to GitHub Issues so they can be prioritized and assigned effectively.

## When to Use

- A new GitHub Issue has been created and needs classification
- Reviewing the issue backlog for prioritization
- An issue lacks labels, severity, or assignee

Doc-only workflow.

## Procedure

1. **Read the issue** — understand the problem statement and context.
2. **Classify type**: `bug`, `feature`, `refactor`, `docs`, `security`, `question`.
3. **Assess severity**:
   - `critical` — data loss, security vulnerability, complete functionality blocked
   - `high` — major feature broken, significant degradation
   - `medium` — partial functionality affected, workaround exists
   - `low` — cosmetic, minor inconvenience, enhancement request
4. **Apply labels**: type label + severity label + area label (if applicable).
5. **Link related issues**: search for duplicates or related work.
6. **Add triage comment** summarizing classification rationale.

## Verification

1. Issue has type label, severity label, and classification rationale in a comment.
2. Duplicate/related issues are linked.
3. Severity assessment matches the impact described in the issue.
