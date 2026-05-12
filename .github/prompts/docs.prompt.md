---
description: Record architectural decisions and documentation tied to a change
---

Invoke the agent-skills:documentation-and-adrs skill.

When making an architectural decision, changing a public API, or shipping a feature that future engineers must understand:

1. Identify what context the change creates that is not obvious from the code
2. Decide whether the record belongs as an ADR, a README update, a doc in `docs/`, or inline prose
3. Capture the decision in the decision's own words — problem, forces, options considered, outcome, consequences
4. Cross-reference related decisions and code so the record is discoverable
5. Keep the record concise enough that a reader can load it in under five minutes

Prefer writing the record at the moment the decision is made — not after memory has faded.
