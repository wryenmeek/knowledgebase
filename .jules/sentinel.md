## 2026-04-15 - [API Key Exposure]
**Vulnerability:** GITHUB_TOKEN and JULES_API_KEY were partially validated and redacted across different fleet scripts, leading to potential sensitive key exposure in error logs and missing validations where they were needed.
**Learning:** Partial token validation and redaction across a multi-script fleet can lead to sensitive key leakage. Every script must validate all necessary keys on startup and ensure redaction utilities cover all sensitive tokens.
**Prevention:** Centralize token validation and redaction logic. Ensure any string interpolation or logging involving potentially tainted input uses a comprehensive redaction utility for all known sensitive keys in the environment.

## 2026-04-17 - [Command Injection Risk in Fleet Git Utils]
**Vulnerability:** The `getGitRepoInfo` function in `scripts/fleet/github/git.ts` was passing user-controlled input (`remoteName`) into `child_process.exec` via string interpolation (`git remote get-url ${remoteName}`). This allows command injection if a malicious remote name like `; rm -rf /` is supplied. It also risked option injection if the remote name was like `--help`.
**Learning:** Using `exec` with variable arguments creates shell injection vulnerabilities because the argument is evaluated by the shell.
**Prevention:** Always use `child_process.execFile` (or its promisified version) instead of `exec` when executing shell commands with variable arguments. Additionally, always include the `--` separator before variable arguments to prevent option injection attacks.
