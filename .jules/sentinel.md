## 2026-04-15 - [API Key Exposure]
**Vulnerability:** GITHUB_TOKEN and JULES_API_KEY were partially validated and redacted across different fleet scripts, leading to potential sensitive key exposure in error logs and missing validations where they were needed.
**Learning:** Partial token validation and redaction across a multi-script fleet can lead to sensitive key leakage. Every script must validate all necessary keys on startup and ensure redaction utilities cover all sensitive tokens.
**Prevention:** Centralize token validation and redaction logic. Ensure any string interpolation or logging involving potentially tainted input uses a comprehensive redaction utility for all known sensitive keys in the environment.

## 2026-04-18 - [Command Injection via child_process.exec]
**Vulnerability:** Shell command injection and option injection via user-controllable input (e.g. `remoteName`) in git commands due to the use of `child_process.exec` allowing shell interpolation.
**Learning:** Never use `child_process.exec` for shell commands that interpolate external or variable inputs. Even if the variable seems benign, it can contain malicious payload (e.g., `; echo pwned`) or options (`--help`). Wrapping the implementation in an exported object `gitCommands` was required to test this securely while also supporting mockability in Bun test environments.
**Prevention:** Use `child_process.execFile` (or its promisified version) and separate arguments into an array. Always include the `--` separator before positional variable arguments to prevent them from being parsed as CLI flags.
## 2026-05-10 - [Shell Injection in GitHub Actions via add-mask]
**Vulnerability:** Shell command injection via string interpolation in GitHub Actions `run:` steps, specifically when masking secrets (`echo "::add-mask::${{ steps.app-token.outputs.token }}"`).
**Learning:** String interpolation (`${{ ... }}`) in a `run:` block is evaluated by the GitHub Actions runner before the shell script is generated, allowing malicious strings to break out of the shell quotes or syntax.
**Prevention:** Never interpolate `github.*`, `inputs.*`, or `steps.*` variables directly into `run:` blocks. Pass them to the shell using the step's `env:` block instead (e.g. `env: TOKEN: ${{ steps.token.outputs.token }}` and `run: echo "::add-mask::${TOKEN}"`).

## 2026-05-13 - [Hardcoded Token Logic]
**Vulnerability:** GITHUB_TOKEN and JULES_API_KEY tokens were hardcoded as raw validation checks and inline `process.env` lookups across `fleet-dispatch.ts`, `fleet-merge.ts`, and `fleet-plan.ts`.
**Learning:** Checking or importing tokens ad hoc leads to duplicate or missed token checks. Centralizing these environment variables ensures token visibility and validation on startup across multiple files, while also supporting `console.log` redacting of these tokens everywhere.
**Prevention:** Always export a single object/file handling tokens and sensitive environmental variables (e.g., `env.ts`) to avoid duplicated code, missing error checks, and incomplete log scrubbing.
## 2026-06-21 - Fix Bandit Alert for MD5 Usage
**Vulnerability:** Use of weak MD5 hash without `usedforsecurity=False`.
**Learning:** `hashlib.md5()` triggers `bandit` scanners and FIPS enforcement unless explicitly marked as non-security related.
**Prevention:** Always pass `usedforsecurity=False` when using MD5 for checksums or versioning to suppress false positives and ensure compatibility in strict environments.
## 2026-06-26 - [Log Injection and Expression Injection]
**Vulnerability:** Token exposure via stderr logs and expression injection (`${{ ... }}`) via GitHub-flavoured markdown rendering.
**Learning:** API error messages can contain sensitive credentials (e.g., `ghp_`, `github_pat_`, base64 strings) which can be exposed if stderr is not properly redacted. GitHub markdown might trigger side effects if `${{ ... }}` expressions are not neutralized.
**Prevention:** Centralize and ensure consistent markdown sanitization and error log redaction across all scripts interfacing with external platforms (like GitHub and Google Drive).
## 2024-07-03 - Fix gh CLI Credential Leakage in check_issue_closure_evidence.py
**Vulnerability:** The `scripts/validation/check_issue_closure_evidence.py` script dumped raw `completed.stderr` output directly into `RuntimeError` messages when `gh` CLI commands failed, risking exposure of GitHub tokens (e.g. `ghp_`) in GitHub Actions logs.
**Learning:** External command wrappers like `subprocess.run` do not automatically redact secrets. Passing unredacted output into exceptions bubbles the raw text into user-visible logs, violating credential safety.
**Prevention:** Always wrap external subprocess stderr output with `scripts._redaction.redact_stderr` before formatting it into exceptions or log statements.

## 2024-08-09 - Unintended Network Exposure in Webhook Receivers
**Vulnerability:** WSGI entrypoints defaulted to binding to 0.0.0.0, exposing them to all network interfaces.
**Learning:** Defaulting to 0.0.0.0 without environment configuration exposes the service unnecessarily. Passing HOST="" from environment variables can also mistakenly bind to empty strings if not trimmed and checked.
**Prevention:** Use an environment variable with a safe local fallback, explicitly handling trimmed non-empty strings (`os.environ.get('HOST', '').strip() or '127.0.0.1'`).

## 2026-08-15 - Do not "optimize" fleet-orchestrator-token/action.yml description fields
**Vulnerability:** None — this is a false-positive pattern, not a real vulnerability.
**Learning:** `.github/actions/fleet-orchestrator-token/action.yml` uses `${{ secrets.X }}` and `${{ steps.<id>.outputs.token }}` literals inside YAML `description:` strings purely as documentation examples for callers. Description fields are not an expression-evaluation context, so this is inert text, not an "expression injection" risk. It is also not linted by CI. This file has been repeatedly "fixed" and reverted by unrelated dispatches mistaking it for a real finding (see issue #563).
**Prevention:** Do not flag or edit description-field `${{ }}` text in this file as a security finding. If a task's scope doesn't explicitly include `.github/actions/fleet-orchestrator-token/action.yml` in its `file_ownership`, do not touch it.

## 2026-08-16 - [Fix Bandit Alert for urllib.request.urlopen Usage]
**Vulnerability:** Use of `urllib.request.urlopen` without explicitly restricting the allowed schemes can trigger Bandit B310 alerts and allow unexpected local file access (e.g., `file://`).
**Learning:** `urllib.request.urlopen` by default accepts various schemes. If user-controlled input manages to reach it, this can read arbitrary files. Explicit scheme validation is required.
**Prevention:** Always validate URL schemes (e.g., check that they start with `http://` or `https://`) before calling `urllib.request.urlopen` and use `# nosec B310` to suppress false positives after validation is added.

## 2026-08-20 - [Fix Subprocess Stderr Token Leakage]
**Vulnerability:** Maintenance scripts (`audit_pr_body_vs_diff.py` and `sweep_stale_bot_branches.py`) did not wrap `stderr` generated by `subprocess.run` (e.g. from `gh` or `git` tools) with `redact_stderr` before logging or passing them into exceptions.
**Learning:** `git` and `gh` failures can print diagnostic logs containing auth tokens when failing. If these unredacted logs are bubbled up to `sys.stderr` or exceptions, the GitHub token leaks into CI logs.
**Prevention:** In the `wryenmeek/knowledgebase` repository, to prevent credential leakage (such as GitHub tokens), always wrap `stderr` generated by external CLI tools (e.g., `subprocess.run` executions for `gh` or `git`) with `scripts._redaction.redact_stderr` before logging, printing, or raising exceptions. Ensure the `sys.path` allows module importing for direct script invocation.

## 2024-10-27 - [Fix Subprocess Stderr Token Leakage]
**Vulnerability:** Subprocess `gh` commands within `scripts/validation/check_commit_scope.py` printed their raw `stderr` (e.g., `result.stderr.strip()`) when they failed, which could leak sensitive GitHub tokens (e.g., `ghp_`, `github_pat_`, etc.) if one were part of the diagnostic error messages.
**Learning:** `subprocess.run` executions do not automatically scrub standard error strings of credentials. Relying on raw stderr from CLI tools like `gh` for logs or debug output creates an inadvertent vector for token leakage.
**Prevention:** In the wryenmeek/knowledgebase repository, to prevent credential leakage (such as GitHub tokens), always wrap `stderr` generated by external CLI tools (e.g., `subprocess.run` executions for `gh` or `git`) with `scripts._redaction.redact_stderr` before logging, printing, or raising exceptions.
## 2026-05-15 - [Missing Security Headers]
**Vulnerability:** HTTP endpoints didn't emit defensive headers, making the API susceptible to content MIME sniffing.
**Learning:** API webhooks should include security headers regardless of usage context.
**Prevention:** Apply defense-in-depth to enforce headers like X-Content-Type-Options and Content-Security-Policy on responses.
## 2025-02-27 - [Fix Subprocess Stderr Token Leakage]
**Vulnerability:** Subprocess `git` and `gh` commands within `scripts/hooks/check_approval_flag.py`, `scripts/hooks/check_mixed_scope.py`, and `scripts/hooks/check_test_framework.py` printed their raw `stderr` (e.g., `result.stderr`) when they failed, which could leak sensitive GitHub tokens if one were part of the diagnostic error messages.
**Learning:** `subprocess.run` executions do not automatically scrub standard error strings of credentials. Relying on raw stderr from CLI tools like `git` for logs or debug output creates an inadvertent vector for token leakage.
**Prevention:** In the wryenmeek/knowledgebase repository, to prevent credential leakage, always wrap `stderr` generated by external CLI tools (e.g., `subprocess.run` executions) with `scripts._redaction.redact_stderr` before logging, printing, or raising exceptions. Ensure `import sys` and `from pathlib import Path` are included before updating `sys.path`.
