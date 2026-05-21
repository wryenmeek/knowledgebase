import { describe, expect, test } from "bun:test";

interface SpawnResult {
  readonly exitCode: number;
  readonly stdout: string;
  readonly stderr: string;
}

type FleetEnvKey = "JULES_API_KEY" | "GITHUB_TOKEN";

function decodeOutput(bytes: Uint8Array | null | undefined): string {
  return bytes ? new TextDecoder().decode(bytes) : "";
}

function runEnvScript(
  code: string,
  envUpdates: Partial<Record<FleetEnvKey, string | undefined>>
): SpawnResult {
  const mergedEnv = { ...process.env } as Record<string, string>;
  for (const [key, value] of Object.entries(envUpdates)) {
    if (value === undefined) {
      delete mergedEnv[key];
      continue;
    }
    mergedEnv[key] = value;
  }

  const result = Bun.spawnSync({
    cmd: [process.execPath, "--eval", code],
    cwd: import.meta.dir,
    env: mergedEnv,
    stdout: "pipe",
    stderr: "pipe",
  });

  return {
    exitCode: result.exitCode,
    stdout: decodeOutput(result.stdout),
    stderr: decodeOutput(result.stderr),
  };
}

describe("fleet env bootstrap", () => {
  test("fails closed when JULES_API_KEY is required and missing", () => {
    const result = runEnvScript(
      `
        const { assertFleetEnvironment } = await import("./env.ts");
        assertFleetEnvironment({ requireJulesApiKey: true, installConsoleRedaction: false });
      `,
      {
        JULES_API_KEY: undefined,
        GITHUB_TOKEN: "test-gh-token",
      }
    );

    expect(result.exitCode).toBe(1);
    expect(result.stderr).toContain("Missing required environment variable: JULES_API_KEY.");
  });

  test("fails closed when GITHUB_TOKEN is required and missing", () => {
    const result = runEnvScript(
      `
        const { assertFleetEnvironment } = await import("./env.ts");
        assertFleetEnvironment({ requireGitHubToken: true, installConsoleRedaction: false });
      `,
      {
        JULES_API_KEY: "test-jules-key",
        GITHUB_TOKEN: undefined,
      }
    );

    expect(result.exitCode).toBe(1);
    expect(result.stderr).toContain("Missing required environment variable: GITHUB_TOKEN.");
  });

  test("redacts secrets in console output without truncating normal logs", () => {
    const longPayload = "x".repeat(1200);
    const githubToken = "ghp_test_token_secret"; // pragma: allowlist secret
    const julesKey = "jules_test_api_secret"; // pragma: allowlist secret

    const result = runEnvScript(
      `
        const { assertFleetEnvironment } = await import("./env.ts");
        assertFleetEnvironment({ requireJulesApiKey: true, requireGitHubToken: true });
        const payload = "x".repeat(1200);
        console.log("LOG", process.env.GITHUB_TOKEN, payload);
        console.error("ERR", process.env.JULES_API_KEY, payload);
        console.warn("WRN", process.env.GITHUB_TOKEN, payload);
      `,
      {
        JULES_API_KEY: julesKey,
        GITHUB_TOKEN: githubToken,
      }
    );

    const combinedOutput = `${result.stdout}\n${result.stderr}`;
    expect(result.exitCode).toBe(0);
    expect(combinedOutput).toContain("***REDACTED***");
    expect(combinedOutput).not.toContain(githubToken);
    expect(combinedOutput).not.toContain(julesKey);
    expect(combinedOutput).not.toContain("<truncated>");
    expect(combinedOutput).toContain(longPayload);
  });
});
