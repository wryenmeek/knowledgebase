## 2026-04-15 - [API Key Exposure]
**Vulnerability:** GITHUB_TOKEN and JULES_API_KEY were partially validated and redacted across different fleet scripts, leading to potential sensitive key exposure in error logs and missing validations where they were needed.
**Learning:** Partial token validation and redaction across a multi-script fleet can lead to sensitive key leakage. Every script must validate all necessary keys on startup and ensure redaction utilities cover all sensitive tokens.
**Prevention:** Centralize token validation and redaction logic. Ensure any string interpolation or logging involving potentially tainted input uses a comprehensive redaction utility for all known sensitive keys in the environment.
## 2026-04-19 - [Command Injection via child_process.exec]
**Vulnerability:** `child_process.exec` was used in `scripts/fleet/github/git.ts` with variable arguments, which can lead to command injection if the input is untrusted.
**Learning:** Avoid using `exec` for variable arguments. Instead, prefer `execFile` or `spawn` with an array of arguments, and use `--` to separate options from positional arguments when executing CLI tools like `git`.
**Prevention:** Use `child_process.execFile` over `child_process.exec` when executing shell commands with variable arguments to prevent command injection vulnerabilities, and use `--` before variable arguments to prevent option injection attacks.
