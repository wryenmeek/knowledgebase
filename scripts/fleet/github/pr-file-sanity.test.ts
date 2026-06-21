import { describe, expect, test } from "bun:test";
import { inspectPullRequestChangedFiles } from "./pr-file-sanity.js";

function response(options: {
  ok: boolean;
  status: number;
  text?: string;
  json?: unknown;
}): Response {
  return {
    ok: options.ok,
    status: options.status,
    text: async () => options.text ?? "",
    json: async () => options.json ?? [],
  } as Response;
}

describe("inspectPullRequestChangedFiles", () => {
  test("passes when GitHub reports at least one changed file", async () => {
    const result = await inspectPullRequestChangedFiles({
      apiBase: "https://api.github.test/repos/owner/repo",
      headers: { Authorization: "Bearer test" },
      prNumber: 123,
      fetchImpl: async () =>
        response({
          ok: true,
          status: 200,
          json: [{ filename: "src/change.ts" }],
        }),
    });

    expect(result.ok).toBe(true);
    expect(result.file_count).toBe(1);
    expect(result.message).toContain("passed");
  });

  test("fails closed when GitHub reports an empty PR file list", async () => {
    const result = await inspectPullRequestChangedFiles({
      apiBase: "https://api.github.test/repos/owner/repo",
      headers: { Authorization: "Bearer test" },
      prNumber: 123,
      fetchImpl: async () =>
        response({
          ok: true,
          status: 200,
          json: [],
        }),
    });

    expect(result.ok).toBe(false);
    expect(result.file_count).toBe(0);
    expect(result.message).toContain("0/0/0 diff detected");
  });

  test("fails closed when GitHub file inspection fails", async () => {
    const result = await inspectPullRequestChangedFiles({
      apiBase: "https://api.github.test/repos/owner/repo",
      headers: { Authorization: "Bearer test" },
      prNumber: 123,
      fetchImpl: async () =>
        response({
          ok: false,
          status: 502,
          text: "upstream unavailable",
        }),
    });

    expect(result.ok).toBe(false);
    expect(result.file_count).toBe(0);
    expect(result.message).toContain("Failed to inspect PR #123 files (502)");
  });

  test("fails closed when GitHub returns a non-array success payload", async () => {
    const result = await inspectPullRequestChangedFiles({
      apiBase: "https://api.github.test/repos/owner/repo",
      headers: { Authorization: "Bearer test" },
      prNumber: 123,
      fetchImpl: async () =>
        response({
          ok: true,
          status: 200,
          json: { message: "not an array" },
        }),
    });

    expect(result.ok).toBe(false);
    expect(result.file_count).toBe(0);
    expect(result.message).toContain("GitHub response was not an array");
  });

  test("fails closed when GitHub returns invalid JSON", async () => {
    const result = await inspectPullRequestChangedFiles({
      apiBase: "https://api.github.test/repos/owner/repo",
      headers: { Authorization: "Bearer test" },
      prNumber: 123,
      fetchImpl: async () =>
        ({
          ok: true,
          status: 200,
          text: async () => "",
          json: async () => {
            throw new Error("invalid json");
          },
        }) as Response,
    });

    expect(result.ok).toBe(false);
    expect(result.file_count).toBe(0);
    expect(result.message).toContain("Failed to parse PR #123 files response");
  });
});
