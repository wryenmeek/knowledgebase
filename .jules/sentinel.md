## 2026-04-15 - [API Key Exposure]
**Vulnerability:** GITHUB_TOKEN and JULES_API_KEY were partially validated and redacted across different fleet scripts, leading to potential sensitive key exposure in error logs and missing validations where they were needed.
**Learning:** Partial token validation and redaction across a multi-script fleet can lead to sensitive key leakage. Every script must validate all necessary keys on startup and ensure redaction utilities cover all sensitive tokens.
**Prevention:** Centralize token validation and redaction logic. Ensure any string interpolation or logging involving potentially tainted input uses a comprehensive redaction utility for all known sensitive keys in the environment.
## 2026-04-18 - [Command Injection]
**Vulnerability:** Found `child_process.exec` being used to run git commands with unvalidated input (e.g., `remoteName`) via string concatenation in `scripts/fleet/github/git.ts`. This could allow command injection or option injection.
**Learning:** Using string interpolation with `exec` creates a shell execution context where arbitrary shell metacharacters can be injected by untrusted input.
**Prevention:** Always use `child_process.execFile` (or similar execution without a shell) combined with passing arguments as a discrete array. Furthermore, ensure the `--` separator is included before variable arguments to guard against option injection vulnerabilities.
