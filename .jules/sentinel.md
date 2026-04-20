## 2026-05-20 - [Command Injection in Child Process]
**Vulnerability:** The use of `child_process.exec` with string interpolation for system commands (e.g., `git`) enabled shell command injection if untrusted inputs were passed as arguments (e.g., remote names). Additionally, missing `--` parameter separators allowed option injection.
**Learning:** `child_process.exec` passes the entire command string to a shell, making it extremely dangerous with variable input. Even when an argument is quoted or otherwise "sanitized", the shell can still interpret special characters.
**Prevention:** Always use `child_process.execFile` (or its promisified equivalent) which executes the binary directly without spawning a shell, mitigating shell injection entirely. Furthermore, when passing variable arguments to CLIs like `git`, always prepend them with `--` to signal the end of command options, preventing option injection attacks.

## 2026-04-15 - [API Key Exposure]
**Vulnerability:** GITHUB_TOKEN and JULES_API_KEY were partially validated and redacted across different fleet scripts, leading to potential sensitive key exposure in error logs and missing validations where they were needed.
**Learning:** Partial token validation and redaction across a multi-script fleet can lead to sensitive key leakage. Every script must validate all necessary keys on startup and ensure redaction utilities cover all sensitive tokens.
**Prevention:** Centralize token validation and redaction logic. Ensure any string interpolation or logging involving potentially tainted input uses a comprehensive redaction utility for all known sensitive keys in the environment.
