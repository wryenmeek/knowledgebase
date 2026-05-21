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

describe("fleet plan/dispatch preflight", () => {
  for (const entrypoint of ["fleet-plan.ts", "fleet-dispatch.ts"] as const) {
    test(`${entrypoint} fails closed on invalid base branch`, () => {
      const result = Bun.spawnSync({
        cmd: ["bun", "run", entrypoint],
        cwd: path.join(import.meta.dir),
        env: {
          ...process.env,
          JULES_API_KEY: "test-key", // pragma: allowlist secret
          GITHUB_TOKEN: "test-token", // pragma: allowlist secret
          FLEET_BASE_BRANCH: "bad branch",
        },
        stdout: "pipe",
        stderr: "pipe",
      });

      const stderr = decode(result.stderr);
      expect(result.exitCode).not.toBe(0);
      expect(stderr.toLowerCase()).toContain("preflight failed");
      expect(stderr).toContain("Invalid base branch");
    });

    test(`${entrypoint} fails closed when base branch is not visible`, () => {
      const missingBranch = `zz_missing_branch_${Date.now()}_${entrypoint.replace(".ts", "")}`;
      const result = Bun.spawnSync({
        cmd: ["bun", "run", entrypoint],
        cwd: path.join(import.meta.dir),
        env: {
          ...process.env,
          JULES_API_KEY: "test-key", // pragma: allowlist secret
          GITHUB_TOKEN: "test-token", // pragma: allowlist secret
          FLEET_BASE_BRANCH: missingBranch,
        },
        stdout: "pipe",
        stderr: "pipe",
      });

      const stderr = decode(result.stderr);
      expect(result.exitCode).not.toBe(0);
      expect(stderr.toLowerCase()).toContain("preflight failed");
      expect(stderr).toContain("not visible in local or origin refs");
    });
  }

  test("fleet-dispatch.ts fails closed on invalid FLEET_PENDING_DATE", () => {
    ensureBaseBranchVisible();
    const result = Bun.spawnSync({
      cmd: ["bun", "run", "fleet-dispatch.ts"],
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
    expect(stderr.toLowerCase()).toContain("preflight failed");
    expect(stderr).toContain("Invalid FLEET_PENDING_DATE");
  });
});
