---
scope: module
last_updated: 2026-04-29
---

# CONTEXT — scripts/github_monitor/

Vocabulary for the GitHub source-monitoring pipeline. `AGENTS.md` takes precedence on any conflict.

## Terms

| Term | Definition |
|------|------------|
| DriftedEntry | A registry entry whose `last_fetched_commit_sha` differs from `last_applied_commit_sha`, indicating the upstream source has changed and a wiki sync is pending. |
| RegistryEntry | A single entry in a `*.source-registry.json` file describing a monitored GitHub source path, its current fetch/apply state, and its target wiki page. |
| drift report | The JSON artifact produced by `check_drift.py` listing all DriftedEntries detected in the current run. Format governed by `schema/drift-report-contract.md`. |
| AFK lane | Entries classified as AFK by `classify_drift.py` (small, non-binary diff below `--afk-max-lines` threshold). These proceed directly to `synthesize_diff.py`. Default threshold is 0 (deny-by-default). |
| HITL lane | Entries classified as HITL by `classify_drift.py`. These generate GitHub Issues for human review instead of running `synthesize_diff.py`. Default for all entries until AFK is enabled. |
| check_drift → classify_drift → synthesize_diff pipeline | The three-step processing pipeline: detect drift → classify AFK/HITL → synthesize wiki update or create Issue. Each step is an independent script with its own SurfaceResult contract. |
| `last_applied_*` fields | Fields in a RegistryEntry (`last_applied_commit_sha`, `last_applied_at`) recording the state of the last successful wiki write. Must NOT advance speculatively — only after confirmed wiki write. |
| `last_fetched_*` fields | Fields in a RegistryEntry recording what was fetched from GitHub. Set by `fetch_content.py` after downloading and SHA-256-verifying new content. |
| raw/assets boundary | Assets downloaded by `fetch_content.py` are stored at `raw/assets/{owner}/{repo}/{commit_sha}/{path}` and never overwritten (path includes commit SHA, so write-once is guaranteed). |
| create_issues | `scripts/github_monitor/create_issues.py` — creates or updates GitHub Issues for HITL-classified drift entries. Dedupe key: registry path + source entry key. |
| classify_drift | `scripts/github_monitor/classify_drift.py` — reads a drift report and emits `afk-entries.json` + `hitl-entries.json`. AFK threshold defaults to 0 (deny-by-default). |
| `_sanitize_gh_md()` | Helper in `create_issues.py` that escapes GitHub Markdown special characters in issue bodies. Do not inline this in CI workflows. |

## Invariants

| Invariant | Description |
|-----------|-------------|
| Lock ordering per ADR-012 | When acquiring both wiki and github-sources locks: always acquire `wiki/.kb_write.lock` first, then `raw/.github-sources.lock`. Reverse order causes deadlock. |
| Write-once assets | Assets in `raw/assets/` are written exactly once via `exclusive_create_write_once()`. The commit SHA in the path prevents inter-run races. Never overwrite an existing asset. |
| `last_applied_*` only advances after confirmed wiki write | `synthesize_diff.py` must not update `last_applied_*` in the registry unless the wiki page write has been confirmed. If the wiki write fails, the registry update must be rolled back or skipped. |
| AFK deny-by-default | `classify_drift.py` defaults `--afk-max-lines 0`, routing all entries to HITL. AFK routing is only enabled when the operator explicitly passes a positive threshold after governance amendment (ADR-014). |

## File Roles

| File | Role |
|------|------|
| `check_drift.py` | Reads source registries, calls GitHub API, produces drift report JSON. Read-only. |
| `classify_drift.py` | Reads drift report, classifies entries as AFK or HITL. Read-only (outputs are transient CI artifacts). |
| `fetch_content.py` | Downloads drifted content to `raw/assets/`, updates `last_fetched_*` in registry under `raw/.github-sources.lock`. |
| `synthesize_diff.py` | Diffs old and new assets, updates wiki page, advances `last_applied_*` under both locks (wiki first). |
| `create_issues.py` | Creates or updates GitHub Issues for HITL-classified entries. |
| `_types.py` | Typed dicts for registry entries, drift report structure, and API response shapes. |
| `_validators.py` | Path traversal and registry structure validators. |
| `_http.py` | GitHub API client helpers: authenticated requests, retry logic, contents and commits endpoints. |
| `_registry.py` | Registry read/update helpers: load, validate, update `last_fetched_*` and `last_applied_*` fields under lock. |
