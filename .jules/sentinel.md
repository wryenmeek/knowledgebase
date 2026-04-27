## 2026-04-15 - [API Key Exposure]
**Vulnerability:** GITHUB_TOKEN and JULES_API_KEY were partially validated and redacted across different fleet scripts, leading to potential sensitive key exposure in error logs and missing validations where they were needed.
**Learning:** Partial token validation and redaction across a multi-script fleet can lead to sensitive key leakage. Every script must validate all necessary keys on startup and ensure redaction utilities cover all sensitive tokens.
**Prevention:** Centralize token validation and redaction logic. Ensure any string interpolation or logging involving potentially tainted input uses a comprehensive redaction utility for all known sensitive keys in the environment.

## 2026-04-18 - [Command Injection via child_process.exec]
**Vulnerability:** Shell command injection and option injection via user-controllable input (e.g. `remoteName`) in git commands due to the use of `child_process.exec` allowing shell interpolation.
**Learning:** Never use `child_process.exec` for shell commands that interpolate external or variable inputs. Even if the variable seems benign, it can contain malicious payload (e.g., `; echo pwned`) or options (`--help`). Wrapping the implementation in an exported object `gitCommands` was required to test this securely while also supporting mockability in Bun test environments.
**Prevention:** Use `child_process.execFile` (or its promisified version) and separate arguments into an array. Always include the `--` separator before positional variable arguments to prevent them from being parsed as CLI flags.

## 2026-04-20 - [Shell Injection in GitHub Actions Workflows]
**Vulnerability:** Shell injection via direct interpolation of GitHub Actions context variables (e.g., `${{ inputs.base_branch }}`) into shell blocks (`run:` steps) in workflow files like `fleet-dispatch.yml` and `fleet-merge.yml`.
**Learning:** Directly interpolating `${{ ... }}` expressions within a `run:` block is dangerous because the runner simply finds and replaces the string before executing it. If the input contains shell metacharacters like `;`, `&`, or `$()`, an attacker can escape the intended command and execute arbitrary code on the runner.
**Prevention:** Always pass context variables to the `run:` step via the `env:` context. The shell script should reference the environment variables (e.g., `$FLEET_BASE_BRANCH`) instead of using GitHub Actions string interpolation.
