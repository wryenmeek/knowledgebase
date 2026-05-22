# ADR-012: GitHub source monitoring pipeline

## Status
Accepted — amended in-place: secret names corrected (see § Amendment)

## Date
2026-04-21

## Context

The knowledgebase needs a way to monitor specific files in external GitHub repositories
and incorporate their changes as versioned source material in the wiki, without abandoning
the provenance controls established by ADR-006.

ADR-006 already allows external assets as authoritative sources when "vendored and
checksummed under `raw/assets/**`". However, no tooling existed to automate the
fetch-and-vendor cycle, and no CI workflow existed to detect when upstream files changed.

ADR-007 lists approved post-MVP package surfaces but does not include a `scripts/github_monitor/**`
family for external-source monitoring automation.

The knowledgebase's SourceRef format (`repo://owner/repo/path@sha#anchor?sha256=hex`)
already encodes the path to a vendored local asset — no format change is needed for the
feature to work correctly.

`PolicyId.EXTERNAL_ASSETS_ALLOWED_AS_AUTHORITATIVE_IF_CHECKSUMED` is already declared in
`scripts/kb/contracts.py` but has had no runtime consumer. This ADR activates that policy.

## Decision

Implement a GitHub source monitoring pipeline as a new parallel automation lane that does
not replace or modify the existing `raw/inbox/` → `raw/processed/` ingest pipeline.

### Authoritative source boundary extension (extends ADR-006)

`raw/assets/{external-owner}/{external-repo}/{commit-sha}/{path}` paths are authoritative
source inputs when:

1. The content was fetched via the GitHub API using a GitHub App installation token.
2. The sha256 of the fetched bytes was verified immediately after fetch and before any
   write to `raw/assets/**`.
3. The `commit-sha` path component matches the GitHub commit SHA at fetch time.
4. The file is tracked in a registry entry at
   `raw/github-sources/{owner}-{repo}.source-registry.json` with a matching
   `sha256_at_last_applied` field.

The content is immutable post-write: the path encodes the commit SHA, so any change to
the upstream file produces a new path rather than mutating the existing asset.

SourceRefs for vendored GitHub assets follow the existing format using local
knowledgebase commit SHAs:
```
repo://wryenmeek/knowledgebase/raw/assets/{owner}/{repo}/{commit-sha}/{path}@{kb-commit-sha}#anchor?sha256={64-hex}
```
The external origin is preserved in the path structure; no SourceRef format change is
required.

### Registry governance (new mutable artifact type)

`raw/github-sources/{owner}-{repo}.source-registry.json` is a new mutable artifact with:

- **Write strategy:** atomic replace under `raw/.github-sources.lock`
- **Lock:** `raw/.github-sources.lock` (separate from `wiki/.kb_write.lock` to avoid
  contention with wiki writes; when both locks are needed, always acquire
  `wiki/.kb_write.lock` first)
- **Schema owner:** `schema/github-source-registry-contract.md`
- **Three-stage state per entry:**
  - `last_applied_*` — advanced only after wiki page is successfully updated
  - `last_fetched_*` — advanced after successful asset fetch; if synthesis fails,
    the next run can still diff `last_applied_blob_sha` → `last_fetched_blob_sha`
  - Drift detection compares HEAD blob SHA against `last_applied_blob_sha` (content
    identity, not commit identity) to avoid false-positive drift on commit-metadata-only
    changes

### New package surface (extends ADR-007)

`scripts/github_monitor/**` is approved as a new post-MVP package surface for:
- Drift detection, asset fetching, diff-aware wiki synthesis, and CI orchestration
  helpers for the GitHub source monitoring pipeline.

Invariants that still apply:
- CI-1 and CI-2 stay read-only; CI-3 is unchanged; CI-5 is a new additive workflow.
- All write-capable surfaces in `scripts/github_monitor/**` must be declared in the
  `AGENTS.md` write-surface matrix before they can write to any path.
- ADR-005 concurrency model applies: `wiki/.kb_write.lock` for all wiki writes.
- Paths outside `raw/assets/**`, `raw/github-sources/**`, and bounded `wiki/**` remain
  deny-by-default.

### Authentication model

The pipeline uses a **GitHub App** (not a PAT) for authentication:

- External repo access: `contents: read` only — no write permissions on external repos.
- Knowledgebase repo access (CI-5 write job): `contents: write` + `pull-requests: write`.
- App installation ID stored in the source registry per repo: `github_app_installation_id`.
- Secrets required: `GH_APP_ID`, `GH_APP_PRIVATE_KEY` (stored as repo secrets,
  never committed).
- Installation tokens expire after 1 hour; token generation must occur immediately before
  the step that uses it. The token is passed via environment variable only — never as a
  CLI argument.

### CI-5 workflow structure

A scheduled workflow (daily at 06:30 UTC via cron `30 6 * * *`, plus
`repository_dispatch` and `workflow_dispatch`):

1. **`check-drift` job** (`contents: read`): reads registry files, calls GitHub contents
   API, emits JSON drift report. Exits nonzero if any API call fails.
2. **`fetch-and-update` job** (`contents: write`, `pull-requests: write`, protected
   environment): runs only when drift is detected; fetches assets, updates registry.
3. **`classify-drift` job** (`contents: read`): classifies fetched drift entries as AFK or
   HITL per ADR-014 allowlist thresholds.
4. **`synthesize` job** (same permissions, protected environment): applies diff-aware wiki
   updates, opens a PR.

Both write jobs use `concurrency.group: kb-write-${{ github.repository }}` (no `${{ github.ref }}` suffix). This differs from CI-3's branch-scoped group (`kb-write-${{ github.repository }}-${{ github.ref }}`); CI-5 runs on a schedule rather than per-branch, so ref-scoping is not applicable.

### Webhook relay contract (alignment-lock addendum)

The repository adds a deployable GitHub webhook relay wrapper
(`scripts/github_monitor/relay_http.py`) over the relay core
(`scripts/github_monitor/_relay.py`) for low-latency CI-5 triggering.
The relay is additive to the cron schedule (cron remains the safety-net).

`repository_dispatch` contract for `event_type: upstream-source-updated` is frozen to:

- `source_kind` (`"github"`)
- `registry_path`
- `upstream_repo`
- `upstream_ref`
- `upstream_after_sha`
- `delivery_id`
- `observed_at` (ISO-8601)
- `changed_paths`

Security and fail-closed guarantees:

- Validate `X-Hub-Signature-256` before payload processing.
- Enforce source allowlist by dispatching only when upstream `owner/repo`
  matches allowlisted registry files and changed paths intersect monitored entries.
- Suppress replayed deliveries using `delivery_id` with TTL replay cache.
- Keep least-privilege dispatch credentials (GitHub App token or narrowly scoped
  token capable only of calling repository dispatch).

CI-5 consumer behavior is fixed:

- Valid, allowlisted `registry_path` hint => targeted check-drift mode.
- Missing/invalid `registry_path` hint => explicit diagnostic + safe full-scan fallback
  (no hard-fail solely for missing/invalid hint).

## Alternatives considered

### Webhook-based real-time monitoring (amended)

- **Pros:** near-real-time latency for CI-5 drift detection after upstream pushes.
- **Cons:** requires a maintained webhook receiver runtime and relay hardening.
- **Original disposition (2026-04-21):** rejected in favor of cron-only scheduling.
- **Amended disposition (2026-05-22):** accepted as an additive trigger with frozen
  payload contract, strict signature/replay/allowlist controls, and cron retained as
  safety-net fallback.

### Use a PAT instead of a GitHub App

- **Pros:** simpler setup.
- **Cons:** PATs do not auto-rotate; require human to manage expiry; tied to a specific
  user account.
- **Rejected:** GitHub Apps auto-rotate tokens and support fine-grained installation
  permissions; better for long-term maintenance.

### Keep the existing inbox pipeline and manually copy fetched files to raw/inbox/

- **Pros:** no new code; reuses existing ingest logic.
- **Cons:** loses the source-SHA provenance link; breaks diff-aware synthesis; requires
  manual operator intervention on every upstream change.
- **Rejected:** the automated vendor-into-raw/assets approach preserves full provenance
  without operator intervention.

### Store only the diff (not the full file) in raw/assets/

- **Pros:** smaller storage footprint.
- **Cons:** diffs are not self-contained; original file must be retained to reconstruct
  full content; breaks SourceRef semantics which require a complete file.
- **Rejected:** full immutable copies in `raw/assets/` are required for authoritative
  SourceRef provenance.

## Consequences

- `raw/github-sources/` becomes a new mutable zone alongside `wiki/**` and
  `raw/processed/**`.
- `raw/assets/**` gains a new external-vendor sub-path convention
  (`{external-owner}/{external-repo}/{commit-sha}/{path}`).
- `scripts/github_monitor/**` is an approved package location; write-capable scripts must
  still declare their surfaces in `AGENTS.md` before writing.
- `schema/github-source-registry-contract.md` is added as the registry schema owner.
- Two new lock paths: `raw/.github-sources.lock` (registry writes) uses the same
  `fcntl`-based advisory lock pattern as `wiki/.kb_write.lock`.
- The `docs/architecture.md` automation model table gains a CI-5 row.
- `PolicyId.EXTERNAL_ASSETS_ALLOWED_AS_AUTHORITATIVE_IF_CHECKSUMED` in `contracts.py` is
  now exercised by this pipeline.

## Amendment

**Date:** 2026-05-03

**What changed:** Secret names updated from `GITHUB_APP_ID`/`GITHUB_APP_PRIVATE_KEY` to
`GH_APP_ID`/`GH_APP_PRIVATE_KEY`. GitHub rejects custom secrets with the `GITHUB_` prefix
(HTTP 422), so the CI-5 workflow was fixed in commit `db324c4` and this ADR is updated
to match.

**What didn't change:** Authentication model (GitHub App, not PAT), installation token
expiry handling, and the principle that secrets are passed via environment variables only.

---

**Date:** 2026-05-22

**What changed:** Added alignment-locked webhook relay contract for
`upstream-source-updated` (`source_kind`, `registry_path`, `upstream_repo`,
`upstream_ref`, `upstream_after_sha`, `delivery_id`, `observed_at`,
`changed_paths`), added deployable relay wrapper surface
(`scripts/github_monitor/relay_http.py`), and updated CI-5 consumer behavior to
use targeted mode only for valid allowlisted `registry_path` hints with explicit
full-scan fallback diagnostics for missing/invalid hints.

**What didn't change:** Cron-triggered CI-5 remains active as safety-net, GitHub App
authentication model remains preferred, and registry/wiki write-lock ordering
requirements remain unchanged.

## References

- `ADR-004-split-ci-workflow-governance.md`
- `ADR-005-write-concurrency-guards.md`
- `ADR-006-authoritative-source-boundary.md`
- `ADR-007-control-plane-layering-and-packaging.md`
- `raw/processed/SPEC.md`
- `schema/github-source-registry-contract.md`
- `scripts/kb/contracts.py` (`PolicyId.EXTERNAL_ASSETS_ALLOWED_AS_AUTHORITATIVE_IF_CHECKSUMED`)
- `AGENTS.md` (write-surface matrix)
