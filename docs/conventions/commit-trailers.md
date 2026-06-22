# Commit Trailers

This document describes the Git-style footer trailers used in this repository
to satisfy the **commit-scope check** gates B and C
(`.github/workflows/commit-scope-check.yml`).

## Format

Trailers follow the [Git trailer convention][git-trailers]: each trailer is a
`Token: Value` line appearing in the **last paragraph** of a commit message or
PR body (separated from the preceding content by a blank line).

```
Short summary line.

Longer description if needed.

Token: value here
Another-Token: value here
```

The trailer block is the last paragraph — content appearing after a blank line
at the end of the text.  A mention of `Reverts:` buried in the middle of a
multi-paragraph PR body does **not** satisfy the gate.

[git-trailers]: https://git-scm.com/docs/git-interpret-trailers

---

## Gate C bypass trailers

**Gate C** fires when `(deletions - insertions) > 50` and no verified bypass
trailer is present.  The two valid bypass mechanisms are:

### `Reverts:` trailer

Signals that the large deletion is an intentional revert of prior work.

**Accepted formats:**

| Format | Example | Validation |
|---|---|---|
| Local issue/PR reference | `Reverts: #42` | Issue or PR `#42` must exist in this repo (`gh issue view 42` or `gh pr view 42`). |
| Cross-repo reference | `Reverts: wryenmeek/knowledgebase#42` | Same validation — the numeric ID must resolve. |
| 40-hex commit SHA | `Reverts: a1b2c3...` (40 chars) | SHA must resolve to a commit reachable from `main` (`git merge-base --is-ancestor`). |

**Placement:** The `Reverts:` trailer must appear in the **last paragraph** of
the PR body OR as a Git footer trailer on the **last commit** of the PR head
ref.  A mention anywhere else in the body does not bypass the gate.

**Examples:**

```
chore: revert migration script

The migration introduced regressions in the staging environment.

Reverts: #87
```

```
fix: undo accidental bulk deletion

Reverts: wryenmeek/knowledgebase#123
```

---

### `Cleanup:` trailer

Signals that the large deletion is a legitimate refactor or dead-code removal
that does not revert specific prior work.  The reason text must be at least
10 characters.

**Format:** `Cleanup: <reason>` where `<reason>` is ≥ 10 characters.

**Placement:** Same rules as `Reverts:` — last paragraph of PR body or last
commit footer.

**Examples:**

```
refactor: prune legacy compatibility shims

Dead-code removal after the v3 API deprecation window closed.

Cleanup: remove deprecated v2 compatibility shims (200 lines)
```

```
chore: archive old strategy documents

The strategies directory was superseded by the wiki synthesis pipeline.

Cleanup: archive obsolete docs/strategies subtree, 1500 lines
```

---

## Gate B acknowledgement

**Gate B** fires when a PR touches a [sensitive path][sensitive-paths] without
naming the surface in the PR title or body first line via a word-boundary token
match.  There is no bypass trailer for gate B — the fix is to update the PR
title or body first line to name the surface.

**Token set (case-insensitive, word-boundary matched):**

| Token | Covers |
|---|---|
| `wiki` | `wiki/` |
| `schema` | `schema/` |
| `adr` or `adrs` | `docs/decisions/` |
| `agents` | `AGENTS.md` |
| `copilot` | `.github/copilot-instructions.md` |
| `contracts` | `scripts/kb/contracts.py` |
| `write_utils` | `scripts/kb/write_utils.py` |
| `spec` | `raw/processed/SPEC.md` |
| `workflows` | `.github/workflows/` |
| `pre-commit` | `.pre-commit-config.yaml` |

**Example:** A PR touching `wiki/` needs the word `wiki` (as a whole word) in
its title or body first line.

- ✅ `wiki: archive obsolete pages` — passes (token `wiki` present)
- ✅ `chore: cleanup` + body first line `Refactors wiki/indexes` — passes
- ❌ `wikipedia integration` — fails (`wikipedia` is not the word `wiki`)
- ❌ `Adopt schema v2` with diff in `wiki/` — fails (`schema` covers `schema/`,
  not `wiki/`)

[sensitive-paths]: ../../CONTEXT.md

---

## Quick reference

| Trailer | Gate | Required when | Placement |
|---|---|---|---|
| `Reverts: #N` | C | Net deletion > 50 lines (revert case) | Last commit footer OR last paragraph of PR body |
| `Reverts: owner/repo#N` | C | Net deletion > 50 lines (revert case) | Last commit footer OR last paragraph of PR body |
| `Reverts: <40-hex SHA>` | C | Net deletion > 50 lines (revert case) | Last commit footer OR last paragraph of PR body |
| `Cleanup: <reason ≥ 10 chars>` | C | Net deletion > 50 lines (refactor case) | Last commit footer OR last paragraph of PR body |
