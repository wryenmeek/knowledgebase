import { describe, expect, test } from "bun:test";
import path from "node:path";

function decode(output: Uint8Array): string {
  return new TextDecoder().decode(output);
}

const TEST_BASE_BRANCH = "fleet-preflight-base";

function ensureBaseBranchVisible(): void {
  const result = Bun.spawnSync({
    cmd: ["git", "branch", "--force", TEST_BASE_BRANCH, "HEAD"],
    cwd: path.join(import.meta.dir),
    stdout: "pipe",
    stderr: "pipe",
  });
  if (result.exitCode !== 0) {
    throw new Error(`failed to create test base branch: ${decode(result.stderr)}`);
  }
}

describe("fleet-merge preflight", () => {
  test("fails closed when FLEET_MAX_RETRIES is invalid", () => {
    ensureBaseBranchVisible();
    for (const invalidValue of ["abc", "-1", "11", "1.5"]) {
      const result = Bun.spawnSync({
        cmd: ["bun", "run", "fleet-merge.ts"],
        cwd: path.join(import.meta.dir),
        env: {
          ...process.env,
          JULES_API_KEY: "test-key", // pragma: allowlist secret
          GITHUB_TOKEN: "test-token", // pragma: allowlist secret
          FLEET_BASE_BRANCH: TEST_BASE_BRANCH,
          FLEET_MAX_RETRIES: invalidValue,
        },
        stdout: "pipe",
        stderr: "pipe",
      });

      const stderr = decode(result.stderr);
      expect(result.exitCode).not.toBe(0);
      expect(stderr).toContain("Fleet merge preflight failed");
      expect(stderr).toContain("FLEET_MAX_RETRIES must be an integer between 0 and 10");
    }
  });

  test("fails closed when FLEET_PENDING_DATE is invalid", () => {
    ensureBaseBranchVisible();
    const result = Bun.spawnSync({
      cmd: ["bun", "run", "fleet-merge.ts"],
      cwd: path.join(import.meta.dir),
      env: {
        ...process.env,
        JULES_API_KEY: "test-key", // pragma: allowlist secret
        GITHUB_TOKEN: "test-token", // pragma: allowlist secret
        FLEET_BASE_BRANCH: TEST_BASE_BRANCH,
        FLEET_PENDING_DATE: "../bad-date",
      },
      stdout: "pipe",
      stderr: "pipe",
    });

    const stderr = decode(result.stderr);
    expect(result.exitCode).not.toBe(0);
    expect(stderr).toContain("Fleet merge preflight failed");
    expect(stderr).toContain("Invalid FLEET_PENDING_DATE");
  });
});
