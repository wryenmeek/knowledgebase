# Cloneable Knowledgebase Template

**Status:** Proposed — no implementation started

## Problem Statement

How might we make the knowledgebase framework instantly forkable as a clean slate, with zero
ambiguity about what is template-layer vs. domain content?

## Recommended Direction

Documentation-first, script-next. Ship a `TEMPLATE.md` at the repo root immediately — this
solves 80% of the problem with no code changes. Follow with `scripts/init.py --fresh` to
automate the content wipe. Enable the GitHub Template Repository flag to surface a
"Use this template" button as the canonical entry point.

The core insight is that this repo has two layers that are not yet labeled:

- **Framework layer** (reusable as-is): `scripts/`, `tests/`, `.github/`, `schema/`,
  `docs/decisions/`, `pyproject.toml`
- **Content layer** (instance-specific, must be replaced): `wiki/` pages, `raw/` source
  material, `raw/processed/SPEC.md` domain sections, and domain-specific prose in
  `CONTEXT.md` and `README.md`

`TEMPLATE.md` makes the split legible in 10 minutes. The init script enforces it
automatically. A devcontainer is the right long-term endgame — Codespaces opens, runs the
init script, installs qmd, and you are fully operational — but it depends on the boundary
being proved clean first.

## Key Assumptions to Validate

- [ ] Framework/content boundary is clean enough to automate — write the file manifest and
  check whether any file is ambiguously placed
- [ ] `qmd` is the only non-pip external dependency — test with a fresh clone and
  `pip install -e .`; document any other gaps in `TEMPLATE.md`
- [ ] Tests pass on a repo with `wiki/` and `raw/` wiped — run `pytest` after manually
  clearing content dirs before writing the init script
- [ ] Template users are comfortable running a one-line Python command — if not, the GitHub
  template flag + `TEMPLATE.md` alone may be sufficient

## MVP Scope

1. **GitHub Template Repository flag** — 1-click in repo settings; surfaces the
   "Use this template" button as the canonical onboarding path
2. **`TEMPLATE.md` at repo root** — explains the two-layer split; lists what to delete,
   what to edit (`CONTEXT.md`, `README.md`, `raw/processed/SPEC.md`), what to install,
   and what to run to verify a green test suite
3. **`scripts/init.py --fresh`** — wipes content dirs; creates empty stubs for `wiki/`,
   `raw/inbox/`, `raw/processed/`; installs pip deps; drops a sample inbox document so
   the first `ingest.py` run demonstrates the pipeline; runs `pytest` to confirm a clean
   framework state

## Resolved Decisions

- **`init.py` when qmd is not installed:** skip with a printed warning — pip-installable
  deps are the minimum bar; qmd installation is documented in `TEMPLATE.md`
- **`CONTEXT.md` and `AGENTS.md`:** "edit heavily" — they are structural scaffolding and
  must be kept, but the domain-specific prose must be replaced by the template user
- **Sample inbox document:** yes — a minimal well-formed example source gives the first
  `ingest.py` run something real to process and proves the pipeline end-to-end

## Not Doing (and Why)

- **PyPI extraction** — abstraction overhead; the framework is not stable enough to version
  independently yet
- **`framework` branch** — adds git branching complexity with no payoff over the template
  repository flag
- **Devcontainer now** — right endgame for AFK and Codespaces use; revisit after
  `TEMPLATE.md` ships and the framework/content boundary is proved clean
- **Renaming directories** — breaking change to existing structure; a checklist achieves
  the same clarity without disruption

## CI Service Credentials Setup

The framework's CI-5 and CI-6 workflows require external service credentials. Both can be
configured primarily via CLI tools.

### Google Drive Service Account (CI-6)

CI-6 monitors Google Drive sources for drift. It needs a GCP service account with Drive API
access, stored as the `GDRIVE_SA_KEY` repository secret.

**Prerequisites:** `gcloud` CLI authenticated, a GCP project with billing enabled.

```bash
# 1. Set your GCP project
export GCP_PROJECT="your-project-id"

# 2. Enable Drive API (idempotent)
gcloud services enable drive.googleapis.com --project="$GCP_PROJECT"

# 3. Create service account
gcloud iam service-accounts create kb-drive-monitor \
  --display-name="Knowledgebase Drive Monitor" \
  --description="Service account for CI-6 Google Drive source monitoring" \
  --project="$GCP_PROJECT"

# 4. Create key, set as GitHub secret, delete local copy
SA_EMAIL="kb-drive-monitor@${GCP_PROJECT}.iam.gserviceaccount.com"
TMPKEY=$(mktemp)
gcloud iam service-accounts keys create "$TMPKEY" \
  --iam-account="$SA_EMAIL" --project="$GCP_PROJECT"
gh secret set GDRIVE_SA_KEY < "$TMPKEY"
rm -f "$TMPKEY"
```

After setting the secret, share each monitored Drive folder with the service account email
address (`kb-drive-monitor@<project>.iam.gserviceaccount.com`) as a Viewer.

### GitHub App for Source Monitoring (CI-5)

CI-5 monitors external GitHub repositories for drift. It needs a GitHub App installed on the
repo, stored as `GH_APP_ID` and `GH_APP_PRIVATE_KEY` secrets (GitHub bans the
`GITHUB_` prefix for repository secrets — HTTP 422).

GitHub App creation requires one browser step; the rest is CLI.

**Step 1 — Create the app (browser):**

```bash
# Open the app creation page with a pre-filled manifest form.
# Alternatively, navigate to: https://github.com/settings/apps/new
cat > /tmp/create-gh-app.html <<'HTMLEOF'
<!DOCTYPE html><html><body>
<form id="f" action="https://github.com/settings/apps/new" method="post">
<input type="hidden" name="manifest" value='{
  "name": "YOUR-REPO-source-monitor",
  "url": "https://github.com/OWNER/REPO",
  "hook_attributes": {"active": false},
  "public": false,
  "default_permissions": {"contents": "write", "metadata": "read"},
  "default_events": []
}' />
<button type="submit" style="font-size:18px;padding:10px 20px;">
  Create GitHub App
</button>
</form></body></html>
HTMLEOF
open /tmp/create-gh-app.html   # macOS; use xdg-open on Linux
```

After clicking "Create GitHub App" on GitHub's confirmation page, note the **App ID** shown.

**Step 2 — Generate a private key (browser):**

On the app's settings page (`https://github.com/settings/apps/<app-slug>`), scroll to
"Private keys" and click "Generate a private key." Save the `.pem` file.

**Step 3 — Set secrets and install (CLI):**

```bash
# Set the App ID
echo "YOUR_APP_ID" | gh secret set GH_APP_ID

# Set the private key (pipe the PEM file)
gh secret set GH_APP_PRIVATE_KEY < ~/Downloads/your-app-name.*.private-key.pem

# Install the app on your repo (browser — one click)
open "https://github.com/settings/apps/<app-slug>/installations"
```

Clean up the private key file after setting the secret:
```bash
rm ~/Downloads/your-app-name.*.private-key.pem
rm -f /tmp/create-gh-app.html
```

### Repository Environment

Both CI-5 and CI-6 write jobs require a `protected-pr-write` GitHub environment:

```bash
gh api -X PUT "repos/OWNER/REPO/environments/protected-pr-write"
```

### Branch Protection

CI-1 checks `github.ref_protected` which requires branch protection on `main`:

```bash
gh api -X PUT "repos/OWNER/REPO/branches/main/protection" \
  --input - <<'EOF'
{
  "required_status_checks": {
    "strict": false,
    "contexts": ["CI-2 Analyst Diagnostics / diagnostics"]
  },
  "enforce_admins": false,
  "required_pull_request_reviews": null,
  "restrictions": null
}
EOF
```

## Open Questions

- What taxonomy should the sample inbox document use — real Medicare stub or a generic
  "example policy document" to avoid content-layer leakage into the framework?
