## 2026-04-15 - [API Key Exposure]
**Vulnerability:** GITHUB_TOKEN and JULES_API_KEY were partially validated and redacted across different fleet scripts, leading to potential sensitive key exposure in error logs and missing validations where they were needed.
**Learning:** Partial token validation and redaction across a multi-script fleet can lead to sensitive key leakage. Every script must validate all necessary keys on startup and ensure redaction utilities cover all sensitive tokens.
**Prevention:** Centralize token validation and redaction logic. Ensure any string interpolation or logging involving potentially tainted input uses a comprehensive redaction utility for all known sensitive keys in the environment.

## 2026-04-18 - [Command Injection via child_process.exec]
**Vulnerability:** Shell command injection and option injection via user-controllable input (e.g. `remoteName`) in git commands due to the use of `child_process.exec` allowing shell interpolation.
**Learning:** Never use `child_process.exec` for shell commands that interpolate external or variable inputs. Even if the variable seems benign, it can contain malicious payload (e.g., `; echo pwned`) or options (`--help`). Wrapping the implementation in an exported object `gitCommands` was required to test this securely while also supporting mockability in Bun test environments.
**Prevention:** Use `child_process.execFile` (or its promisified version) and separate arguments into an array. Always include the `--` separator before positional variable arguments to prevent them from being parsed as CLI flags.

## 2026-05-02 - [Unvalidated Secret Exposure via Console Logs]
**Vulnerability:** A missing centralized validation mechanism allowed scripts (like `fleet-dispatch`, `fleet-merge`, and `fleet-plan`) to execute without fully checking required environment variables (`GITHUB_TOKEN` and `JULES_API_KEY`). Furthermore, ad-hoc string replacement across the scripts left potential holes for logging to print sensitive tokens.
**Learning:** Overriding global logging functions (`console.log`, `console.error`, `console.warn`) using native formatters (like Node's `util.format`) and writing directly to output streams (`process.stdout.write`) provides a robust catch-all mechanism to redact keys globally without mutating actual objects or dropping log structure.
**Prevention:** Always maintain a centralized environment configuration file (like `env.ts`) that asserts the existence of required keys on startup and installs a global interceptor to scrub sensitive environment variables from standard streams before they write to disk or CI logs.
