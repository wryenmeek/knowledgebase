## 2026-04-15 - [API Key Exposure]
**Vulnerability:** GITHUB_TOKEN and JULES_API_KEY were partially validated and redacted across different fleet scripts, leading to potential sensitive key exposure in error logs and missing validations where they were needed.
**Learning:** Partial token validation and redaction across a multi-script fleet can lead to sensitive key leakage. Every script must validate all necessary keys on startup and ensure redaction utilities cover all sensitive tokens.
**Prevention:** Centralize token validation and redaction logic. Ensure any string interpolation or logging involving potentially tainted input uses a comprehensive redaction utility for all known sensitive keys in the environment.

## 2026-04-16 - [Command Injection via exec]
**Vulnerability:** Shell and option injection vulnerability in `scripts/fleet/github/git.ts` due to dynamic arguments being interpolated directly into `child_process.exec()` strings (e.g., `git remote get-url ${remoteName}`).
**Learning:** Using `exec()` with variable arguments exposes CLI utilities to both shell syntax injection (e.g., `; echo pwned`) and option injection (e.g., `--help` or other flags that alter command behavior). This was particularly risky here because fleet operates on potentially untrusted repositories.
**Prevention:** Always use `child_process.execFile()` instead of `exec()` when invoking shell commands with variable arguments. Additionally, ensure the `--` separator is passed before the variable argument list to prevent option injection attacks. Wrap standard node module exports in an object (e.g., `export const gitCommands = { ... }`) to permit unit test mocking under Bun's module resolution.
