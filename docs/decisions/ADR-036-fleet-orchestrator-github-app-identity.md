# ADR-036: Fleet orchestrator GitHub App identity

**Date:** 2026-06-24

## Status

Accepted — amended in-place: extend sensitive-path defense to `.github/actions/**` (see § Amendment); extends ADR-019 and resolves Issue #310

## Context

Fleet phase 2a (`fleet-dispatch.yml`) and downstream phases (2b, 3) need a
write-capable identity that can `gh pr merge --auto` planning PRs and squash-merge
per-task implementation PRs in a way that **does** fire downstream push-triggered
workflows. The default `GITHUB_TOKEN` cannot serve this role because of the Layer 6
suppression trap: GitHub Actions intentionally suppresses workflow runs for events
created by `GITHUB_TOKEN` (except `workflow_dispatch` and `repository_dispatch`).
This is documented behavior, not a bug. Without a non-`GITHUB_TOKEN` identity, the
fleet pipeline cannot run autonomously end-to-end: Phase 2a merges a planning PR,
but Phase 2b's `push` trigger never fires, and the operator must manually
`gh workflow run fleet-dispatch-after-merge.yml --ref main` to proceed.

PR #378 (issue #310 diagnostics, merged 2026-06-23) shipped the code path that
prefers a GitHub App installation token when configured. Initially it suggested
**widening the existing `kb-source-monitor` GitHub App** (App ID 3581628) to fill
this role. That guidance was **architecturally wrong**:

- `kb-source-monitor` exists to ingest external source repositories for the wiki
  pipeline (CI-5). Its scope is intentionally narrow on the **external** source-repo
  installations (`contents: read` only). On the host knowledgebase repo, per
  ADR-012, the App also holds `contents: write` + `pull_requests: write` strictly
  for the CI-5 `fetch-and-update` job (a bounded, schema-validated write surface).
- Widening it further with `issues: write` and the broader auto-merge surface that
  fleet orchestration requires would conflate two unrelated trust domains (source
  ingestion vs. fleet automation) and violate the principle of least privilege.
- The HTTP 422 "permissions requested are not granted to this installation"
  error observed on PR #369 was correct enforcement of that narrow scope, not
  misconfiguration.

Separately, the operator runs Jules-driven fleet orchestration across **four
repositories**: `wryenmeek/knowledgebase`, `wryenmeek/vscode-genai`,
`wryenmeek/hot-springs-island`, and `wryenmeek/Scribe`. All four are single-operator
private repos and all four either ship or are scheduled to ship the same fleet
workflow set (`fleet-plan`, `fleet-dispatch`, `fleet-dispatch-after-merge`,
`fleet-merge`). Provisioning a separate fleet App per repo would multiply
operator setup cost. Practical blast-radius is unchanged under a single-operator
deployment (the operator is the sole writer on all four repos), so a shared App
is acceptable — but note the negative consequence in § Consequences: a shared
App's private key authenticates the App globally, coupling the four repos at the
PEM-exfil layer.

Three patterns were considered for the new fleet identity:

- **A — Widen `kb-source-monitor`**: rejected (above).
- **B — One App per fleet-running repo**: rejected as 4× operator setup with no
  practical blast-radius gain under a single-operator deployment. Would be the
  correct pattern if multiple distinct operators ran fleet on different repos.
- **C — One shared App `fleet-orchestrator` installed selectively on each
  fleet repo**: adopted. Single App, per-repo install controls scope, same
  secrets pattern across repos.

A fourth question — whether to use GitHub OAuth flow instead of a GitHub App —
was considered and rejected: OAuth requires a callback URL hosted by a running
service, cannot work headlessly in CI (no browser to complete the consent
redirect), and loses the bot-identity audit benefit (App actions show as
`fleet-orchestrator[bot]` on PRs and commits; OAuth actions show as the user).

## Decision

Provision a **single shared GitHub App named `fleet-orchestrator`** owned by
the operator account (`wryenmeek`), private visibility, with the following
default installation permissions:

| Permission | Scope | Required for |
|---|---|---|
| `contents` | write | `gh pr merge`, branch updates |
| `pull_requests` | write | `gh pr merge --auto`, PR comments |
| `issues` | write | Per-task tracker comments (resolves issue #311), parent-issue auto-comment automations |
| `metadata` | read | (auto-granted) |

### Permissions explicitly NOT granted (load-bearing exclusions)

These omissions are **intentional safeguards**, not oversights. Tests in
`tests/kb/test_fleet_dispatch_app_token_diagnostics.py` enforce the manifest
shape so a future contributor cannot silently widen the App without amending
this ADR first.

| Permission | Reason for exclusion |
|---|---|
| `workflows` | Blocks the Jules-PR-merged workflow-modification attack class — without `workflows:write` on the App, even a successfully-merged malicious PR cannot mutate `.github/workflows/**`, preserving the audit boundary. |
| `actions` | Blocks cancellation of running CI / arbitrary re-runs (would let a compromised token poison the verification chain). |
| `administration` | Blocks repo settings changes (collaborators, branch protection, environments). |
| `members` | Blocks org-level membership escalation. |

No webhooks (`hook_attributes.active: false`); the App is consumed server-to-server
via `actions/create-github-app-token` only. No OAuth user-to-server scopes.

Token-level least privilege at mint time: each workflow's `create-github-app-token`
step requests only the subset it actually uses via `permission-*` inputs — Phase 2a
mints `contents:write + pull_requests:write` (no `issues`), Phase 3 the same, Phase 2b
adds `issues:write` only because Issue #311's tracker comments require it. The
installation grant is the upper bound; per-mint narrowing is the lower bound.

Repository secret names follow **purpose-prefixed Scheme B**:

- `FLEET_APP_ID` — numeric App ID
- `FLEET_APP_PRIVATE_KEY` — full PEM of the App's private key

These names are deliberately distinct from `GH_APP_ID` / `GH_APP_PRIVATE_KEY`
(reserved for `kb-source-monitor` per its historical convention). Future Apps
follow the same `<PURPOSE>_APP_*` pattern.

The App is installed selectively per fleet repo as that repo is ready:

1. `wryenmeek/knowledgebase` — first install (this ADR ships the workflow changes).
2. `wryenmeek/vscode-genai` — install when its fleet workflows are migrated.
3. `wryenmeek/hot-springs-island` — install when its fleet workflows are migrated.
4. `wryenmeek/Scribe` — install once Scribe ships fleet workflows.

Token cadence: regenerate the installation token **at job start** (one
`actions/create-github-app-token` step per job that needs it) and bind via
**step-scoped `env:`** rather than job-scoped. This keeps the secret available
only to steps that actually need to mutate state, matching the existing
step-scoped secret binding rule in `AGENTS.md`.

Workflow surfaces in scope for this ADR (knowledgebase repo):

Phase 2a queues a planning-PR auto-merge; Phase 2b dispatches one Jules session
per task on the planning-PR merge commit; Phase 3 sequentially squash-merges
the resulting per-task PRs after CI passes (see ADR-019 for the underlying
phase contracts).

- `.github/workflows/fleet-dispatch.yml` — Phase 2a `gh pr merge --auto`
- `.github/workflows/fleet-dispatch-after-merge.yml` — Phase 2b per-task dispatch
  and per-task tracker comments
- `.github/workflows/fleet-merge.yml` — Phase 3 sequential per-task merges

All three switch from `GH_APP_ID` / `GH_APP_PRIVATE_KEY` (or bare `GITHUB_TOKEN`)
to `FLEET_APP_ID` / `FLEET_APP_PRIVATE_KEY` with a `GITHUB_TOKEN` fallback
preserving the existing backout strategy. The warning text emitted on fallback
references `fleet-orchestrator` and `FLEET_APP_*` secret names.

Wiki/framework workflows (CI-3 producer, CI-4 publisher, CI-5 source monitor,
CI-6 drive monitor, github-customizations-freshness) **do not migrate** — they
only open PRs that are HITL-reviewed before merge, so Layer 6 does not apply
to them. They stay on `GITHUB_TOKEN`.

## Consequences

### Positive

- **Layer 6 trap closed for fleet**: Phase 2a auto-merge now fires Phase 2b
  push-triggered workflows without operator intervention. The full
  Phase 1 → 2a → 2b → 3 cycle becomes autonomous.
- **Identity blast radius separated**: source ingestion (`kb-source-monitor`,
  read-only), fleet orchestration (`fleet-orchestrator`, write-capable on
  fleet repos only), wiki/framework writes (`GITHUB_TOKEN`, HITL-reviewed).
  A compromise of any one identity does not escalate to the others.
- **Multi-repo amortization**: one App provisioning cost serves all four fleet
  repos; per-repo install is one-click after the App exists.
- **Unblocks future automations** that require non-`GITHUB_TOKEN` push or
  comment side effects: parent-issue auto-comment on Phase 3 merges, wiki
  freshness triggers chained from fleet merges, commit-scope-check on fleet
  merges, and similar event-driven workflows.
- **Resolves Issue #311** (per-task tracker comments) without granting
  `issues: write` to the bare `GITHUB_TOKEN` (which would widen blast radius
  for every workflow on the repo).

### Negative

- **Operator HITL step required once per repo**: provision App, install,
  store two secrets. Documented via the one-click HTML manifest form in
  `raw/inbox/cloneable-template.md` and the session-local provisioning page
  for the first install.
- **Secret rotation surface widens**: two new secrets per fleet repo. The
  rotation runbook covers this with the same cadence as `GH_APP_PRIVATE_KEY`
  (operator-managed; no automatic rotation today).
- **Multi-repo PEM coupling at the App-credential layer**: although GitHub
  installation tokens are scoped per-installation (✓), the App's *private key*
  authenticates the App globally. A single PEM stored in `wryenmeek/knowledgebase`
  as a repo secret is identical to the secret stored in `vscode-genai`,
  `hot-springs-island`, and `Scribe`. An exfil event in any one repo would let
  an attacker mint installation tokens for all four repos offline
  (`POST /app/installations/{id}/access_tokens`), granting write on all four.
  Mitigation under the current deployment: single-operator trust boundary
  (`wryenmeek` is the sole writer on all installations), so practical blast
  radius ≈ unchanged from operator's PAT being compromised. If the fleet grows
  beyond a single operator, revisit and split into per-operator Apps.
- **Migration touches three workflows in one PR**: `fleet-dispatch.yml`,
  `fleet-dispatch-after-merge.yml`, `fleet-merge.yml`. The size is mitigated
  by keeping the `GITHUB_TOKEN` fallback intact, so any per-workflow regression
  degrades gracefully to current behavior.
- **Warning-emission asymmetry**: only `fleet-dispatch.yml` (Phase 2a) emits a
  three-branch operator warning on App-token-absent / token-creation-failed /
  token-created paths; `fleet-merge.yml` and `fleet-dispatch-after-merge.yml`
  fall back silently when secrets are absent. This is acceptable today because
  only Phase 2a's merge feeds a Layer-6-sensitive push trigger that operators
  actively monitor. If a future automation makes Phase 3's or Phase 2b's push
  trigger likewise observable, replicate the warning template.

### Backout

If the `fleet-orchestrator` App causes an unexpected regression, removing the
two repo secrets is sufficient to disable it — every workflow falls back to
`GITHUB_TOKEN` with an emitted warning annotation. Reverting this ADR's
workflow PR is optional; the fallback is the runtime backout.

## Alternatives considered

- **Widen `kb-source-monitor`** (Option A): rejected as least-privilege
  violation and trust-domain conflation (see Context).
- **One App per fleet repo** (Option B): rejected as 4× operator setup with
  no blast-radius gain (single operator, identical trust boundary).
- **OAuth flow**: rejected — requires a hosted callback service, no headless
  CI compatibility, no bot identity for audit (see Context).
- **Defer fleet App and require manual `gh workflow run` indefinitely**:
  rejected because it blocks every Phase 4+ event-driven automation that
  depends on fleet-merge push triggers.

## Amendment

**Date:** 2026-06-27. **PR:** #397 (Issue #385).

### What changed

`.github/actions/**` is now formally a sensitive path within the same trust
boundary as `.github/workflows/**`. The drift-locked governance surfaces
(`scripts/kb/contracts.py::SENSITIVE_PATHS`, `.github/CODEOWNERS`, and the
`sensitive paths` glossary entry in `CONTEXT.md`) all received the new path
in PR #397.

### Why

PR #397 (Issue #385) extracted the fleet-orchestrator detect+mint logic from
inline blocks in `.github/workflows/fleet-*.yml` into a composite action at
`.github/actions/fleet-orchestrator-token/action.yml`. The composite's detect
step binds `FLEET_APP_PRIVATE_KEY` into bash `env:`, making the new path the
same secret-handling class as the workflows it replaced.

This ADR's original **"Permissions explicitly NOT granted (load-bearing
exclusions)"** subsection (above) names `workflows:write` as the load-bearing
defense against the Jules-PR-merged workflow-modification attack class. That
exclusion is *geographically scoped* to `.github/workflows/**`. The composite
action at `.github/actions/**` was not protected by that exclusion, opening a
concrete attack path: a Jules PR could subtly modify the composite's detect
step to exfiltrate `FLEET_APP_PRIVATE_KEY`; the App's `contents:write` grant
(which it must hold to merge PRs) is sufficient to land such a modification
through Phase 3 auto-merge; an exfiltrated PEM mints installation tokens for
all four fleet repos offline (per `## Negative consequences` above).

Adding `.github/actions/**` to the sensitive-path surfaces does not eliminate
the attack class — only the operator's HITL review of every PR can. But it
**restores the same defense-in-depth that `.github/workflows/**` enjoys**:
CODEOWNERS notification, commit-scope-check gate B (which flags any PR
touching sensitive paths without explicit mention in the PR body), and
optional future enforcement via `require_code_owner_reviews` (currently OFF
per ADR-036's broader trust model).

### What didn't change

- The App's installation grant (still `contents` + `pull_requests` + `issues` + `metadata`).
- The `workflows:write` exclusion is preserved as load-bearing for the
  `.github/workflows/**` defense (this Amendment extends, does not replace).
- The per-mint token-level least privilege contract (each workflow narrows
  via `permission-*` inputs).
- The single-operator deployment model (trust boundary unchanged).
- The fleet-orchestrator App slug, ID, and PEM (no rotation required).

### Forward-looking note

If multi-operator deployment is adopted later (per ADR-035 Tier-3 revisit
2026-07-21, tracked in Issue #353), `require_code_owner_reviews` should be
flipped ON for `.github/workflows/**` and `.github/actions/**` together as
part of that transition (tracked in Issue #364 CODEOWNERS evaluation).

## References

- Issue #310 — Fleet Phase 2a auto-merge GitHub App token (resolves)
- Issue #311 — Fleet dispatch tracker comment permission gap (resolves)
- Issue #385 — Extract fleet-orchestrator App token mint into composite action (Amendment trigger)
- ADR-019 — Fleet Jules orchestration (extended)
- PR #378 — Initial diagnostic shipment (corrected by this ADR)
- PR #397 — Composite action extraction + Amendment governance surface updates
- `.github/copilot-instructions.md` — Layer 6 trap canonical reference
- `raw/inbox/cloneable-template.md` § GitHub App for Fleet Orchestration
- `.github/actions/fleet-orchestrator-token/action.yml` — Composite action introduced by PR #397
