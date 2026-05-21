import { describe, expect, test } from "bun:test";
import { waitForCI } from "./merge-ci.ts";

interface MockResponse {
  json: () => Promise<unknown>;
}

function buildFetchSequence(responses: Array<() => MockResponse>) {
  let index = 0;
  return async () => {
    const next = responses[index];
    if (!next) {
      throw new Error(`unexpected fetch call ${index}`);
    }
    index += 1;
    return next();
  };
}

describe("waitForCI", () => {
  test("fails closed when no checks are present and override is disabled", async () => {
    const logs: string[] = [];
    const result = await waitForCI({
      apiBase: "https://api.example.test/repos/owner/repo",
      headers: {},
      prNumber: 42,
      allowNoChecks: false,
      fetchImpl: buildFetchSequence([
        () => ({ json: async () => ({ head: { sha: "abc123" } }) }),
        () => ({ json: async () => ({ check_runs: [] }) }),
      ]),
      log: (message) => logs.push(message),
      sleep: async () => {},
      now: () => Date.now(),
    });

    expect(result).toBe(false);
    expect(logs.join("\n")).toContain("Failing closed");
  });

  test("allows no-checks only with explicit override", async () => {
    const logs: string[] = [];
    const result = await waitForCI({
      apiBase: "https://api.example.test/repos/owner/repo",
      headers: {},
      prNumber: 42,
      allowNoChecks: true,
      fetchImpl: buildFetchSequence([
        () => ({ json: async () => ({ head: { sha: "abc123" } }) }),
        () => ({ json: async () => ({ check_runs: [] }) }),
      ]),
      log: (message) => logs.push(message),
      sleep: async () => {},
      now: () => Date.now(),
    });

    expect(result).toBe(true);
    expect(logs.join("\n")).toContain("Override enabled; proceeding");
  });

  test("polls pending checks until they complete", async () => {
    const logs: string[] = [];
    let nowMs = 0;
    const result = await waitForCI({
      apiBase: "https://api.example.test/repos/owner/repo",
      headers: {},
      prNumber: 77,
      allowNoChecks: false,
      maxWaitMs: 60_000,
      pollIntervalMs: 30_000,
      fetchImpl: buildFetchSequence([
        () => ({ json: async () => ({ head: { sha: "def456" } }) }),
        () =>
          ({
            json: async () => ({
              check_runs: [{ status: "in_progress", conclusion: null }],
            }),
          }) as MockResponse,
        () =>
          ({
            json: async () => ({
              check_runs: [{ status: "completed", conclusion: "success" }],
            }),
          }) as MockResponse,
      ]),
      log: (message) => logs.push(message),
      now: () => nowMs,
      sleep: async (ms) => {
        nowMs += ms;
      },
    });

    expect(result).toBe(true);
    expect(logs.join("\n")).toContain("CI still running");
  });
});

