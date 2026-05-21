import { describe, expect, test } from "bun:test";
import { evaluateCheckRuns } from "./ci-checks.ts";

describe("evaluateCheckRuns", () => {
  test("fails closed when no checks are present by default", () => {
    expect(evaluateCheckRuns([])).toBe("fail");
  });

  test("allows no-checks only when explicitly configured", () => {
    expect(evaluateCheckRuns([], { allowNoChecks: true })).toBe("pass");
  });

  test("returns pending when checks are still running", () => {
    expect(
      evaluateCheckRuns([
        { status: "in_progress", conclusion: null },
        { status: "completed", conclusion: "success" },
      ])
    ).toBe("pending");
  });

  test("returns pass when all completed checks are success/skipped", () => {
    expect(
      evaluateCheckRuns([
        { status: "completed", conclusion: "success" },
        { status: "completed", conclusion: "skipped" },
      ])
    ).toBe("pass");
  });

  test("returns fail when any completed check fails", () => {
    expect(
      evaluateCheckRuns([
        { status: "completed", conclusion: "success" },
        { status: "completed", conclusion: "failure" },
      ])
    ).toBe("fail");
  });
});
