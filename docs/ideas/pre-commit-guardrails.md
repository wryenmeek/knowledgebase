# Design Proposal: Pre-commit Git Guardrails

**Status:** Implemented — 2026-04-27
**Date:** 2025-07-18
**Author:** Design research (Phase 7-B)

> **Implementation note (2026-04-27):** All hook types described in §2 have
> landed in `scripts/hooks/`: `check_no_staged_locks.py` (§2.4),
> `check_frontmatter.py` (§2.1), `check_sourceref_format.py` (§2.3),
> `check_hooks_json.py` (§2.2 extended), `check_context_md_format.py`,
> and `check_matrix_coverage.py` (§2.2 write-surface lint). Raw git hooks
> approach (§5) was adopted. CI runs the same checks (§6). Pre-commit hook
> invokes all scripts in < 3s budget. Open questions from §8: hooks are
> opt-in locally, documented in README; CI runners don't install hooks but
> run equivalent checks; agent cloud commits bypass local hooks by design.

---

## 1. Problem

Several governance checks currently run only in CI or are agent-interpreted at
runtime. This creates a long feedback loop: a contributor commits a wiki page
with malformed frontmatter, pushes, waits for CI, sees the failure, fixes
locally, and pushes again.

Violations that could be caught locally in seconds:

- Missing or malformed frontmatter fields in wiki pages and SKILL.md files
- New `scripts/` or `logic/` files without a write-surface matrix row in AGENTS.md
- Malformed `repo://` SourceRef citations in wiki pages
- Accidentally staged `.lock` files
- Leaked API keys or tokens in staged files

Pre-commit hooks would catch these before `git push`, reducing CI churn and
preventing governance violations from ever reaching the remote.

## 2. Proposed Hooks

### 2.1 Frontmatter Validation (~1s)

**What:** Validate YAML frontmatter in staged `.md` files.
- SKILL.md files: require `name` and `description` fields.
- Wiki pages: require `type`, `title`, `status`; validate `updated_at` format if present.

**Why:** Frontmatter errors are the most common CI failure. Catching them
locally eliminates the most frequent round-trip.

**Implementation:** Python script using `yaml.safe_load()` on the `---` block.
Runs only on staged `*.md` files in `.github/skills/` and `wiki/`.

### 2.2 Write-Surface Matrix Lint (~0.5s)

**What:** When a new file is added under `scripts/` or `.github/skills/**/logic/`,
verify that AGENTS.md contains a write-surface matrix row matching the path.

**Why:** The AGENTS.md write-surface matrix is the security boundary. Undeclared
surfaces must not ship — catching this pre-commit prevents the "forgot to update
the matrix" failure mode.

**Implementation:** Parse AGENTS.md for `| Surface |` table rows, extract path
patterns, check staged new files against them. Only checks *new* files (added),
not modified files.

### 2.3 SourceRef Format Check (~0.5s)

**What:** Validate `repo://` citation format in staged wiki pages.
Pattern: `repo://<owner>/<repo>/<path>@<git_sha>#<anchor>?sha256=<64-hex>`

**Why:** Malformed SourceRefs are hard to spot in review and break provenance
chain verification downstream.

**Implementation:** Regex scan of staged `wiki/**/*.md` files. Report line
numbers of malformed citations.

### 2.4 Lock File Guard (~0.1s)

**What:** Warn and block if any `.lock` file is staged for commit.

**Why:** Lock files (`wiki/.kb_write.lock`, `raw/.github-sources.lock`) are
runtime artifacts that must never be committed. Per AGENTS.md guardrails.

**Implementation:** Check `git diff --cached --name-only` for `*.lock` patterns.
Hard fail — no override except `--no-verify`.

### 2.5 Secrets Detection (~1s)

**What:** Scan staged files for common secret patterns:
- `GITHUB_TOKEN`, `gh_`, `gho_`, `ghp_` prefixed strings
- `API_KEY=`, `SECRET=`, `PASSWORD=` assignments
- Base64-encoded strings >40 chars in non-binary files

**Why:** Defense in depth. Even with `.gitignore`, secrets can leak through
copy-paste into markdown or config files.

**Implementation:** Regex scan with allowlist for known false positives
(e.g., documentation examples with `<placeholder>` markers).

## 3. Performance Budget

Total pre-commit time target: **< 3 seconds** (well under 5s ceiling).

| Hook | Estimated Time | Notes |
|------|---------------|-------|
| Frontmatter validation | ~1.0s | Python startup + YAML parse of staged .md files |
| Write-surface matrix lint | ~0.5s | String matching against AGENTS.md table |
| SourceRef format check | ~0.5s | Regex scan, few wiki files typically staged |
| Lock file guard | ~0.1s | Pure git-diff filename check |
| Secrets detection | ~0.8s | Regex scan of staged file contents |
| **Total** | **~2.9s** | |

Benchmark assumption: typical commit touches 1–5 files. Large commits (20+
files) may exceed budget; hooks should short-circuit if >50 files staged.

## 4. Bypass Mechanism

- `git commit --no-verify` skips all pre-commit hooks.
- Use case: emergency hotfixes, automated commits from CI bots.
- CI runs the same checks regardless — bypass only skips the local gate.
- Repository documentation should note that `--no-verify` is for emergencies
  only, not routine use.

## 5. Framework Choice

**Recommendation: Raw git hooks** (not `pre-commit` framework).

| Factor | `pre-commit` framework | Raw git hooks |
|--------|----------------------|---------------|
| Setup | Requires `pip install pre-commit` + `pre-commit install` | Just `cp hooks/pre-commit .git/hooks/` |
| Dependencies | External Python packages, network fetch on first run | Only Python stdlib (already required by repo) |
| Complexity | Config file + hook definitions + virtual envs | Single shell script calling Python scripts |
| Contributor onboarding | Extra install step | Documented in README, optional setup script |
| Maintenance | Framework updates, version pinning | Direct control, fewer moving parts |

**Rationale:** This repository already requires Python 3 and has no external
pre-commit hook dependencies. A single `scripts/hooks/pre-commit` shell script
that calls the validation Python scripts keeps the dependency surface minimal.
The `pre-commit` framework adds value for multi-language repos with many hooks
but is overhead here.

**Setup:** A `make install-hooks` or `scripts/setup-hooks.sh` target that
symlinks `scripts/hooks/pre-commit` to `.git/hooks/pre-commit`.

## 6. Interaction with CI

Pre-commit hooks **complement** CI — they don't replace it.

| Check | Pre-commit | CI |
|-------|-----------|------|
| Frontmatter validation | ✓ staged files only | ✓ all files |
| Write-surface matrix | ✓ new files only | ✓ full audit |
| SourceRef format | ✓ staged wiki pages | ✓ all wiki pages |
| Lock file guard | ✓ staged files | ✓ full tree |
| Secrets detection | ✓ staged files | ✓ full tree + deeper scan |
| Full test suite | ✗ too slow | ✓ always |
| Governance validators | ✗ subset only | ✓ full suite |

CI remains the authoritative gate. Pre-commit hooks are a fast-feedback
optimization, not a security boundary.

## 7. Implementation Phases

### Phase 1 — Highest value, lowest friction
- Lock file guard (trivial, prevents real mistakes)
- Frontmatter validation (most common CI failure)

### Phase 2 — Medium effort
- Secrets detection (important safety net)
- SourceRef format check (catches subtle errors)

### Phase 3 — Requires more design
- Write-surface matrix lint (needs robust AGENTS.md parsing)

Each phase ships independently. Phase 1 can land in a single PR.

## 8. Open Questions

1. **Mandatory vs opt-in?** Git hooks are local — they can't be enforced.
   Options: (a) recommend in README, (b) add setup script that installs them,
   (c) check in CI whether hooks ran (via commit trailer).

2. **CI environments:** CI runners clone fresh — hooks aren't installed.
   This is fine (CI runs its own checks), but document the distinction.

3. **Hook update distribution:** When hooks change, contributors must
   re-run the setup script. How to notify? Git doesn't auto-update hooks.
   Option: version the hook script, check version at runtime, print a
   "please update hooks" warning if stale.

4. **Windows compatibility:** Current repo tooling assumes Unix. Do hooks
   need to work on Windows (Git Bash)? Or is this a Unix-only project?

5. **Agent commits:** When Copilot or Jules makes commits, do hooks apply?
   They should if running locally, but cloud-based agents bypass local hooks.

## 9. Decision Needed

Whether to adopt pre-commit hooks and which initial set:

- **A) Full adoption:** Implement all 5 hooks in phases.
- **B) Minimal start:** Lock file guard + frontmatter validation only.
- **C) Defer:** Current CI-only checks are sufficient.

## 10. References

- `schema/page-template.md` — frontmatter field requirements
- `AGENTS.md` § Write-surface matrix — surface declaration contract
- `docs/decisions/ADR-005-write-concurrency-guards.md` — lock file semantics
- `scripts/kb/write_utils.py` — lock acquisition implementation
- `schema/metadata-schema-contract.md` — metadata field formats
