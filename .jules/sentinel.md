## 2026-04-15 - [API Key Exposure]
**Vulnerability:** GITHUB_TOKEN and JULES_API_KEY were partially validated and redacted across different fleet scripts, leading to potential sensitive key exposure in error logs and missing validations where they were needed.
**Learning:** Partial token validation and redaction across a multi-script fleet can lead to sensitive key leakage. Every script must validate all necessary keys on startup and ensure redaction utilities cover all sensitive tokens.
**Prevention:** Centralize token validation and redaction logic. Ensure any string interpolation or logging involving potentially tainted input uses a comprehensive redaction utility for all known sensitive keys in the environment.

## 2026-04-18 - [Command Injection via exec]
**Vulnerability:** The git integration utility in `scripts/fleet/github/git.ts` was using `child_process.exec` to run git commands with user/caller-supplied arguments.
**Learning:** Using `exec` invokes a subshell, which is highly vulnerable to command injection if un-sanitized arguments are included. Furthermore, even with an execution wrapper, option injection is possible unless separated correctly.
**Prevention:** Always prefer `child_process.execFile` (or its promisified version) over `child_process.exec` when passing variable arguments. In addition, when using `execFile` with commands like git, always include the `--` separator before variable arguments to prevent option injection attacks.
