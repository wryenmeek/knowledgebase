---
description: Set up or modify CI/CD pipelines, quality gates, and deployment automation
---

Invoke the agent-skills:ci-cd-and-automation skill.

When building or changing a CI workflow, deployment pipeline, or automated quality gate:

1. Identify the quality signals the pipeline must enforce (tests, lint, type-check, security scan, build)
2. Choose the minimum set of jobs that give fast, trustworthy feedback
3. Run the full suite on main/PR; run focused subsets on push where possible
4. Fail closed on quality-gate errors — never downgrade a real failure to a warning
5. Pin action versions and avoid untrusted third-party actions without review
6. Document non-obvious pipeline behavior in the workflow file or a nearby doc

Prefer editing an existing workflow over adding a new one unless the responsibilities are genuinely distinct.
