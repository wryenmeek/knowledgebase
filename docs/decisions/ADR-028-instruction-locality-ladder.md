# ADR-028: Instruction locality ladder for the knowledgebase AI ecosystem

**Date:** 2026-06-12

## Status

Accepted (Phase 1.5 compliance-evidence prerequisite explicitly waived — see § Open questions).

## Purpose

Purpose: guide humans and agents to deliver context via the token-cheapest viable tier; ratchet prevention is consequence. The instruction locality ladder is a token-efficiency hierarchy: every placement decision should minimize expected token waste for the rule's actual trigger pattern, approximated as `(trigger frequency × per-fire cost)`.

The ladder does not classify destinations by file type alone. It classifies when an agent pays the prompt cost. Trigger frequency is one input to the efficiency calculation, not the destination axis. Reading the ladder top-to-bottom makes the trade-off explicit: per-turn cost grows from zero to full-body; conditional cost is paid only when triggered.

## Context

The May→June 2026 clean-window evidence showed a locality ratchet in the always-on Copilot instruction surface:

| Window | Skills | `.github/copilot-instructions.md` | `AGENTS.md` | Interpretation |
|---|---:|---:|---:|---|
| 2026-04-15 → 2026-05-15 | 21 → 102 (+385%) | 73 → 473 (+548%) | not segmented | Roughly proportional growth while the customization surface expanded |
| 2026-05-15 → 2026-06-07 | 102 → 102 (0%) | 473 → 674 (+42.5%) | net +3 lines | `copilot-instructions.md` grew while the skill surface stayed flat |

The May→June window is the load-bearing signal: the instruction file added 201 lines with no corresponding customization-surface growth. The observed ratchet channels were:

| Channel | Net contribution | Example commits |
|---|---:|---|
| `/chronicle improve` and chronicle-themed commits | +48 lines (~24%) | `ac2ff13`, `058827d`, `7d3fa14`, `f52f460`, `0508889` |
| Post-feature-work session capture | +145 lines (~72%) | `e2dc59c`, `892a487`, `b179cb6`, `2772e37` |
| Anomalous CLI auto-checkpoint | +73 lines | `c347741` |

The recurring problem is not that instructions exist. The problem is that rules default to Locality 4, where every turn pays the full token cost, even when a lower-locality destination would deliver the same guidance only when it is relevant.

## Decision

Adopt the instruction locality ladder as the normative placement framework for repository instructions, framework guidance, and future `audit-knowledgebase-workspace improve` findings.

### Locality ladder

| Locality | Trigger | Mechanism | Token cost per turn | Conditional cost when triggered |
|---|---|---|---|---|
| **0** | File read | Code comment, `# noqa` rationale, or docstring | **0** | File body only when reading that file |
| **1** | File matches glob | `.github/instructions/<scope>.instructions.md` with required `applyTo:` frontmatter | **~1 metadata row** | File body on agent `view` when path matches; compliance-dependent |
| **2** | User invocation | `.github/skills/<name>/SKILL.md` or a skill-local `references/` checklist | **0** | Full skill body when invoked |
| **3a** | Tool call, active injection | `PreToolUse` hook returns context | **0** | Injected string before matching tool actions |
| **3b** | Tool call, blocking gate | `PreToolUse` hook exits non-zero | **0** | Block plus reason |
| **3c** | After file edit | `PostToolUse` hook filtered on edit tool and path glob | **0** | Injected string after matching edits |
| **3d** | Commit boundary | `.pre-commit-config.yaml` hook | **0** | Block or warn at `git commit` time |
| **3e** | Prompt submission | `UserPromptSubmit` hook | **0** | Injected string when prompt content matches |
| **4** | Always-on | `.github/copilot-instructions.md` and `AGENTS.md` | **Full file body** | Not applicable; cost is always paid |

### Five-step efficiency check for Locality 4 promotion

A candidate remains at Locality 4 only when all lower-locality options are worse for expected token efficiency and compliance needs:

1. **Locality 0:** Can the rule live beside the exact code or document it explains? If yes, choose this deterministic zero-per-turn destination.
2. **Locality 1:** Can a plausible `applyTo:` glob be authored for the affected files? "No glob exists today" is not sufficient; create the scoped instruction lazily when a glob can target the work.
3. **Locality 2:** Is it a discrete user-invoked workflow or checklist? If yes, use a skill or skill-local reference.
4. **Locality 3a–3e:** Can an existing or new hook fire on the relevant tool action, edit path, commit, or prompt phrase?
5. **Locality 4:** Only if the need is unpredictable from lower-level signals and applies to more than half of sessions should always-on full-body cost be accepted.

### Deletion pairing and trailer escape

Every Locality 4 addition to `.github/copilot-instructions.md` or `AGENTS.md` outside exempt regions must include one of:

1. **Paired deletion:** remove a stale or redundant Locality 4 entry of roughly equivalent token weight in the same commit.
2. **Trailer escape:** add a `Locality-4-Justification:` git trailer using `docs/templates/locality-4-justification-trailer.md`.

Trailer usage has a soft budget: at most one trailer per ten commits touching global rules sections in the rolling window. Beyond that budget, the gate should fail until a paired deletion lands. Trailer validation belongs to a `commit-msg` hook because `pre-commit` cannot see the finalized commit message. The paired line-delta check belongs to `pre-commit`. Contributors must install both stages with `pre-commit install --hook-type pre-commit --hook-type commit-msg` once the hooks land.

Deletion candidates come in two classes:

- **Stale:** cites a file, script, symbol, issue state, or ADR relationship that no longer matches the repository.
- **Redundant-up-the-ladder:** duplicates a lower-locality artifact such as a hook, skill, or scoped instruction. Redundancy claims must cite the lower-locality artifact path and snippet.

### CLI `applyTo:` mechanism sidebar

Locality 1 in Copilot CLI 1.0.60 is a metadata-table-only mechanism. The agent must `view` the instruction file on demand before relying on the content.

Verified by reading the bundled CLI source (`~/.copilot/pkg/<platform>/<version>/app.js`, function `BXo` around line 256, and the loader at line 4326):

```javascript
// Splitter (simplified from BXo):
for (let n of t)
  if (n.type === "vscode" && n.applyTo) r.push(n);   // applyTo files → metadata-table bucket
  else e.push({content: n.content, source: o, ...}); // no-applyTo files → always-loaded bucket
```

- Files with `applyTo:` frontmatter are not loaded in full every turn. The CLI injects a metadata row with `applyTo`, source path, and description, plus a prompt instructing the agent to use `view` when relevant.
- Files without `applyTo:` frontmatter are loaded in full every turn. This is a hidden Locality 4 ratchet.
- The CLI source path is version-local and should be rechecked for drift by grepping for the string `Here is a list of instruction files that contain rules for modifying or creating new code`.

### Hidden-ratchet invariant

`.github/instructions/*.instructions.md` files without `applyTo:` are silently loaded every turn through the always-loaded bucket. They therefore behave like Locality 4 even though they appear to live in a scoped-instruction directory.

The invariant for this repository is: every `.github/instructions/*.instructions.md` file must include non-empty `applyTo:` frontmatter. `scripts/hooks/check_instructions_applyto_present.py` enforces this at commit time. Missing or empty `applyTo:` is a hard failure, not a style issue.

### Locality 2 compliance equivalence

Locality 1 and Locality 2 share the same compliance shape:

- Locality 1: the CLI injects metadata; the agent must decide to `view` the instruction file.
- Locality 2: the user or routing rules invoke a skill; the agent must read and follow the skill body.

Therefore, Locality 1 has a real token-cost advantage over Locality 4, but it does not have a determinism advantage over Locality 2. The `audit-knowledgebase-workspace improve` classifier must surface this by emitting `compliance_risk` on every demotion finding. Locality 1, Locality 2, Locality 3e, and the `/chronicle improve` meta-rule mechanism are agent-dependent; Locality 0 and mechanically enforced Locality 3 gates are deterministic.

Phase 1.5 compliance measurements are not recorded in this slice. Until those measurements land, consumers must treat Locality 1 demotions as agent-dependent token-efficiency wins, not as deterministic enforcement.

### Other recognized instruction locations

The ladder governs this repository's own placement decisions. Other agent tools and Copilot surfaces recognize additional locations that are useful context but out of scope for the locality gate:

- `CLAUDE.md`
- `GEMINI.md`
- `$HOME/.copilot/copilot-instructions.md`
- `COPILOT_CUSTOM_INSTRUCTIONS_DIRS`
- Cursor `.cursor/rules/*.mdc`

Cursor `.mdc` files are recognized by the CLI around the `mPs="rules"` constant in `app.js`. With `alwaysApply: true`, they behave like always-loaded instructions; with `alwaysApply: false`, they behave like metadata-scoped instructions.

Reference material for future drift checks:

- GitHub Docs, path-specific instructions format: <https://docs.github.com/copilot/how-tos/configure-custom-instructions/add-repository-instructions>
- Cursor `.mdc` format: <https://docs.cursor.com/context/rules-for-ai>
- CLI `/help` output, mirrored by `fetch_copilot_cli_documentation`, for the list of currently recognized instruction locations.

### Two-file Locality 4 scope and multi-consumer caveat

This repository has two always-on top-level instruction files:

- `.github/copilot-instructions.md`, the Copilot-CLI-specific behavior file.
- `AGENTS.md`, the repository operational rules file and an agent-guideline filename convention consumed by Antigravity IDE, Gemini CLI, and other tools that recognize `AGENTS.md`.

The +3-line clean-window measurement for `AGENTS.md` reflects Copilot-CLI-driven growth only. It does not measure Antigravity IDE, Gemini CLI, or other `AGENTS.md` consumer growth channels. Because those consumers can have their own session-capture and ratchet vectors, `AGENTS.md` is gated at the same blocking urgency as `.github/copilot-instructions.md`.

The `AGENTS.md` write-surface matrix table body is exempt from the ratchet check because it grows proportionally with declared executable surfaces by design. The exemption applies to the matrix body only, not to prose guidance above or below it.

### Customizations lock

Future write-capable `audit-knowledgebase-workspace --apply` work uses `.github/.customizations.lock` as a sibling lock to `wiki/.kb_write.lock` and `raw/.rejection-registry.lock`. It has no ordering relationship with those locks and must never be held simultaneously with either. Runtime acquisition remains deferred to the slice that enables `--apply` writes.

### CONTEXT.md terms

Term placeholders for `instruction ratchet`, `Locality`, `trailer soft budget`, and `customizations lock` are queued for the follow-up context slice. This ADR intentionally does not modify `CONTEXT.md`; that cascade is owned by the later slice that updates context vocabulary after ADR-028 is accepted.

## Consequences

### Positive

- Always-on instruction growth becomes an auditable last resort instead of the default.
- The `audit-knowledgebase-workspace improve` classifier has a normative objective: minimize expected token waste for the actual trigger pattern.
- Reviewers can distinguish token-efficiency demotions from deterministic enforcement because `compliance_risk` is required.
- `AGENTS.md` is protected for non-Copilot consumers even though the current clean-window measurement is Copilot-CLI-only.

### Negative

- Locality 1 introduces a metadata indirection that still depends on agent behavior.
- Contributors must understand a two-stage hook model for paired deletion and trailer validation once Phase 6 lands.
- Some useful global rules may require trailer escapes until lower-locality destinations are implemented.

### Operational

- New `.github/instructions/*.instructions.md` files must include `applyTo:`.
- Locality 4 additions must pair deletion or carry a budgeted `Locality-4-Justification:` trailer.
- `audit-knowledgebase-workspace improve` dry-run reports must include proposed destination, rationale, deletion candidate, citation when claiming redundancy, `compliance_risk`, and expected token-efficiency ranking.

## Alternatives considered

1. **Keep `/chronicle improve` writing directly to `.github/copilot-instructions.md`.** Rejected because it preserves the always-on destination bias and adds locality review only after the ratchet has already occurred.
2. **Gate only `.github/copilot-instructions.md`.** Rejected because `AGENTS.md` is a multi-consumer convention. The observed +3 clean-window only measures Copilot-CLI-driven growth and would leave Antigravity IDE, Gemini CLI, and other consumers outside the gate.
3. **Treat `.github/instructions/` files as deterministic scoped instructions.** Rejected because CLI `applyTo:` currently injects metadata only. Agent compliance is required.
4. **Allow frontmatter-less instruction files as broad scoped guidance.** Rejected because the CLI splitter loads them every turn, creating a hidden Locality 4 ratchet.

## Related decisions

- ADR-005: Write concurrency guards
- ADR-013: Rejected-source registry
- ADR-016: Pre-commit hooks governance
- ADR-018: CONTEXT.md vocabulary pattern
- ADR-022: AFK automation uses deterministic scripts; Copilot CLI reserved for HITL

## Open questions

- Phase 1.5 agent-compliance rate per surface remains pending. When issue #196 lands, fold the measured CLI and VS Code compliance evidence into this ADR and fill the surface compliance table expected by the source plan.
- The trailer soft budget is accepted as 1 per 10 commits for the initial hook design, but the rolling-window definition and threshold may need adjustment after the Phase 6 hooks land and real commit history exposes false-positive or bypass patterns.

## References

- `docs/ideas/audit-workspace-improve-flow.md`
- `.github/skills/audit-knowledgebase-workspace/SKILL.md`
- `.github/skills/audit-knowledgebase-workspace/references/locality-ladder.md`
- `docs/templates/locality-4-justification-trailer.md`
- `scripts/hooks/check_instructions_applyto_present.py`
