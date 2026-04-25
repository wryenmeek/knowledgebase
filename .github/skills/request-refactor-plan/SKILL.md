---
name: request-refactor-plan
description: "Creates a structured refactoring proposal as a GitHub Issue. Use when you identify code that needs refactoring and want to document the proposal with motivation, scope, and acceptance criteria."
---

# Request Refactor Plan

## Overview

Produce a structured refactoring proposal and file it as a GitHub Issue with consistent formatting, risk assessment, and acceptance criteria.

## When to Use

- Code smells or complexity identified during review
- Technical debt that needs a dedicated cleanup effort
- Architecture changes that require planning before execution

Doc-only workflow.

## Procedure

1. **Identify the refactoring target**: specific files, modules, or patterns.
2. **Assess motivation**: why does this need refactoring? What problem does it solve?
3. **Define scope**: which files are affected? What changes are in/out of scope?
4. **Propose approach**: describe the refactoring strategy.
5. **Assess risk**: what could break? What tests cover the affected code?
6. **Write acceptance criteria**: how do you know the refactoring succeeded?
7. **File GitHub Issue** with this template:

```
### Motivation
[Why this refactoring is needed]

### Scope
- Files: [list affected files]
- In scope: [what changes]
- Out of scope: [what doesn't change]

### Proposed Approach
[Description of the refactoring strategy]

### Risk Assessment
[What could break, mitigation plan]

### Acceptance Criteria
- [ ] [Criterion 1]
- [ ] [Criterion 2]
- [ ] All existing tests pass
```

Labels: `refactor`, `enhancement`

## Verification

1. Issue created with all template sections filled.
2. Acceptance criteria are testable and specific.
3. Risk assessment identifies affected test coverage.
