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
## 2026-06-27 - [Fix Bandit Alert for MD5 Usage in tests]
**Vulnerability:** Use of weak MD5 hash without `usedforsecurity=False` in `tests/drive_monitor/test_fetch_content.py` and `tests/kb/test_audit_workspace_friction_queries.py`.
**Learning:** `hashlib.md5()` triggers `bandit` scanners and FIPS enforcement unless explicitly marked as non-security related, even in test files.
**Prevention:** Always pass `usedforsecurity=False` when using MD5 for checksums, mock fingerprints, or versioning to suppress false positives and ensure compatibility in strict environments.
