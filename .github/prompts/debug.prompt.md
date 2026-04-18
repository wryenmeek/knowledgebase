---
description: Systematically find the root cause of a failure, then fix it with a regression test
---

Invoke the agent-skills:debugging-and-error-recovery skill alongside agent-skills:test-driven-development.

For any test failure, build break, or unexpected behavior:

1. Reproduce the failure locally with a minimal, deterministic command
2. Read the actual error — don't guess from memory
3. Form a hypothesis about the root cause (not the symptom)
4. Write a failing test that captures the buggy behavior (Prove-It Pattern)
5. Fix the root cause, not just the symptom
6. Confirm the new test passes and existing tests still pass
7. Commit the fix and the regression test together

If you are uncertain about the root cause, stop and gather more evidence instead of guessing.
