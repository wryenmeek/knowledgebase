import { describe, expect, test } from "bun:test";

const mergeModulePromise = (async () => {
  const originalJulesApiKey = process.env.JULES_API_KEY;
  const originalGitHubToken = process.env.GITHUB_TOKEN;
  process.env.JULES_API_KEY ??= "present";
  process.env.GITHUB_TOKEN ??= "present";
  try {
    return await import("./fleet-merge.ts");
  } finally {
    if (originalJulesApiKey === undefined) {
      delete process.env.JULES_API_KEY;
    } else {
      process.env.JULES_API_KEY = originalJulesApiKey;
    }
    if (originalGitHubToken === undefined) {
      delete process.env.GITHUB_TOKEN;
    } else {
      process.env.GITHUB_TOKEN = originalGitHubToken;
    }
  }
})();

describe("fleet-merge file sanity gate", () => {
  test("fails closed before waiting for CI when changed-file inspection reports zero files", async () => {
    const { runFleetMergePreMergeGate } = await mergeModulePromise;
    let waitForCICalled = false;
    let caught: unknown;

    try {
      await runFleetMergePreMergeGate({
        apiBase: "https://api.github.test/repos/owner/repo",
        headers: { Authorization: "Bearer test" },
        prNumber: 339,
        allowNoChecks: false,
        inspectChangedFiles: async () => ({
          ok: true,
          file_count: 0,
          message: "Fleet pre-merge sanity check passed for PR #339.",
        }),
        waitForCIImpl: async () => {
          waitForCICalled = true;
          return true;
        },
        log: () => {},
      });
    } catch (error) {
      caught = error;
    }

    expect(caught).toBeInstanceOf(Error);
    expect((caught as Error).message).toContain("0 changed files reported before CI");
    expect(waitForCICalled).toBe(false);
  });
});
