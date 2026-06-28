---
scope: repo
last_updated: 2026-06-27
---

# CONTEXT

Shared vocabulary for the `wryenmeek/knowledgebase` repository. This file is descriptive — it does **not** override normative rules in `AGENTS.md` or `.github/copilot-instructions.md`. When any term here conflicts with `AGENTS.md`, `AGENTS.md` takes precedence.

## Terms

| Term | Definition |
|------|------------|
| SourceRef | Canonical citation format: `repo://<owner>/<repo>/<path>@<git_sha>#<anchor>?sha256=<64-hex>`. Commit-bound — `git_sha` must resolve to a real git revision containing the cited artifact. |
| governed artifact | A knowledgebase file whose creation, update, and deletion are controlled by the write-surface matrix and require a declared write surface. |
| fail closed | On any error, policy gap, or lock contention: exit non-zero and make no write. Never silently skip validation or proceed with partial state. |
| intake package | The validated bundle of provenance metadata, checksum, and source content produced by `source-intake-steward` before any synthesis can begin. |
| write-surface matrix | The table in `AGENTS.md` declaring every automation surface's runtime mode, writable paths, lock requirements, and hard-fail behavior. Every `scripts/**/*.py` and `.github/skills/**/logic/**/*.py` must have a row. |
| KB_WRITE_LOCK | The file `wiki/.kb_write.lock` — the primary concurrency guard for all wiki writes. Always acquired first when combining with other locks (see ADR-005, ADR-012). |
| AFK | "Away from Keyboard" — a processing mode where automation handles a task end-to-end without human review at each step. Requires an ADR-014 allowlist entry. |
| HITL | "Human in the Loop" — default processing mode requiring human review before any governed write. Default when AFK is not explicitly allowlisted. |
| drift report | The JSON artifact produced by `scripts/github_monitor/check_drift.py` or `scripts/drive_monitor/check_drift.py` describing which monitored sources have changed since their last applied state. |
| knowledgebase-orchestrator | The custom agent persona in `.github/agents/knowledgebase-orchestrator.md` that routes wiki tasks through the correct lane (ingest-safe, AFK, HITL) and enforces gate ordering. |
| rejection registry | The write-once collection of records under `raw/rejected/` documenting why a source was rejected during intake. Governed by `schema/rejection-registry-contract.md` and ADR-013. |
| raw/inbox | The untrusted incoming source boundary. Files here are not yet validated. No automation reads from `raw/inbox` except `source-intake-steward` and `scripts/ingest/**`. Completed `docs/ideas/` design proposals may be archived here for wiki source intake. |
| raw/processed | Immutable post-ingest artifacts. Files written here are write-once — they are never overwritten after the initial ingest commit. |
| wiki | The curated knowledge directory. All wiki writes go through the declared write-surface matrix. `wiki/log.md` is append-only. |
| SurfaceResult | The `dataclass` from `scripts/_optional_surface_common.py` used as the structured exit contract for all `run_surface_cli`-backed surfaces. |
| afk-candidate | Provisional page or source classification emitted by `classify_stale.py` or `classify_drift.py`. Indicates a candidate for AFK-lane processing but is **not operative** — `validate_afk_output.py` must confirm all 5 safety checks pass before any write proceeds. Do not treat `afk-candidate` as a write authorization. |
| AFK automation workflow | A GitHub Actions workflow performing ADR-014 AFK-allowlisted tasks. Two sub-tiers per ADR-022: (1) **AFK deterministic write** — Python scripts for bounded writes, no LLM; (2) **AFK advisory pass** — `copilot -p` skill invocations producing structured findings but no governed writes, feeding downstream patrol cycles or batched issues. Neither sub-tier notifies a human per-finding. |
| AFK advisory pass | A Tier-2 AFK automation workflow invoking a read-only advisory skill via `copilot -p`. Produces structured findings (backlink suggestions, link-symmetry gaps, AI-tell detections, etc.) uploaded as a workflow artifact. Never writes to `wiki/` directly. Human involvement is triggered only by downstream aggregation — patrol cycle or issue threshold. See ADR-022. |
| sensitive paths | The explicit allowlist of paths whose modification triggers heightened review and notification: `wiki/`, `schema/`, `docs/decisions/`, `AGENTS.md`, `.github/copilot-instructions.md`, `scripts/kb/contracts.py`, `scripts/kb/write_utils.py`, `raw/processed/SPEC.md`, `.pre-commit-config.yaml`, `.github/workflows/`, `.github/actions/`. Referenced by `.github/CODEOWNERS` (advisory notification) and the commit-scope check (gate B). Issue #342. Not to be confused with the CI-3 trusted-trigger-model `sensitive_paths` list in `tests/kb/test_ci3_workflow.py`, which gates manual workflow dispatch with a partially overlapping but distinct path set. |
| silent-revert PR | A PR whose title/scope suggests a small or unrelated change but whose diff silently removes substantial content from sensitive paths. The canonical example is Scribe's `bolt: ...` PR (sha `82d56196`) that deleted 2474 lines of docs/strategies under a `bolt` scope label. Defended by Tier 0 layer (see issue wryenmeek/knowledgebase#342). |

## Invariants

| Invariant | Description |
|-----------|-------------|
| Fail closed | Every validation, policy, and lock step must fail closed on error. Partial success is treated as failure on protected/write paths. |
| wiki/log.md append-only | `wiki/log.md` must only receive appended entries. No deletions, no reorders, no edits to existing entries. |
| SourceRef commit-bound | Every SourceRef `git_sha` must resolve to a real commit that contains the cited artifact with matching `sha256`. Placeholder SHAs are provisional only. |
| Lock ordering | When acquiring multiple locks: always acquire `wiki/.kb_write.lock` first, then `raw/.github-sources.lock` or `raw/.drive-sources.lock` (ADR-005, ADR-012, ADR-021). Reverse order causes deadlock. |
| Immutable processed artifacts | Files in `raw/processed/` are write-once. Ingest creates them; no surface may overwrite. |
| RegistryEntry write-once after ingest | Once a registry entry's `last_applied_*` fields are set, they advance only when a confirmed wiki write completes. They must not advance speculatively. |

## File Roles

| Path | Role |
|------|------|
| `raw/inbox/` | Untrusted incoming source material awaiting intake validation. |
| `raw/processed/` | Immutable post-ingest Markdown and `.meta.json` artifact pairs. |
| `raw/assets/` | Binary and media assets tracked by SHA-256 checksum. |
| `raw/github-sources/` | Source registry files for monitored GitHub paths. |
| `raw/drive-sources/` | Source registry files for monitored Google Drive folders. Governed by `schema/drive-source-registry-contract.md`. |
| `raw/rejected/` | Write-once rejection records for sources that failed intake (ADR-013). |
| `raw/wiki-processing/` | Governed checkpoint registry for resumed/revalidated synthesis. Governed by `schema/wiki-processing-checkpoint-registry-contract.md` (ADR-026/ADR-027). |
| `wiki/` | Curated knowledgebase pages, governed artifacts, and audit logs. |
| `schema/` | Authoritative contracts for page templates, taxonomy, metadata, and ingest. Read-only for all automation. |
| `scripts/kb/` | Canonical utility modules: `page_template_utils`, `write_utils`, `contracts`, `sourceref`. All new helpers must extend these before creating new modules (ADR-011). |
| `scripts/hooks/` | Read-only-only pre-commit + PostToolUse hook scripts. No governed repository writes permitted. |
| `scripts/validation/` | Read-only-only validators. |
| `scripts/reporting/` | Read-only by default; `persist` modes declare narrower write-surface rows. |
| `scripts/ingest/` | Ingest surfaces. `apply` mode writes to `raw/processed/**` only. |
| `scripts/github_monitor/` | GitHub drift monitoring. Write modes declared in write-surface matrix. |
| `scripts/drive_monitor/` | Google Drive drift monitoring. Write modes declared in write-surface matrix. |
| `scripts/context/` | Context page management: fill placeholders, publish status, generate docs. |
| `scripts/maintenance/` | Maintenance surfaces: auditing, freshness scanning, follow-up recommendations. |
| `scripts/analysis/` | Read-only host-data analyzers. Process `~/.copilot/**` telemetry into cost/usage reports. No repository writes. |
| `scripts/fleet/` | Fleet orchestration (TypeScript/Bun). Independent of Python test suite. |
| `docs/` | Architecture docs, ADRs, staged content, and design proposals (`docs/ideas/`). |
| `.github/skills/` | Skill definitions (`SKILL.md`) and logic (`logic/`) for agent workflows. |
| `.github/agents/` | Agent persona definitions. |
| `tests/` | Pytest test suite. All new scripts need corresponding test coverage. |
