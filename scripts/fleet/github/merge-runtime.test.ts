import { describe, expect, test } from "bun:test";
import {
  decideUpdateBranchAction,
  findRedispatchPullRequest,
  requireRedispatchAuthorLogin,
  resolveUpdateBranchFailure,
  updateSessionMapping,
} from "./merge-runtime.ts";
import { PreflightFailureError } from "./mutation-diagnostics.ts";

describe("merge runtime decisions", () => {
  test("decideUpdateBranchAction classifies update outcomes deterministically", () => {
    expect(
      decideUpdateBranchAction({
        updateOk: true,
        updateStatus: 200,
        retryCount: 0,
        maxRetries: 2,
      })
    ).toBe("ok");
    expect(
      decideUpdateBranchAction({
        updateOk: false,
        updateStatus: 422,
        retryCount: 0,
        maxRetries: 2,
      })
    ).toBe("redispatch");
    expect(
      decideUpdateBranchAction({
        updateOk: false,
        updateStatus: 422,
        retryCount: 2,
        maxRetries: 2,
      })
    ).toBe("abort");
    expect(
      decideUpdateBranchAction({
        updateOk: false,
        updateStatus: 500,
        retryCount: 0,
        maxRetries: 2,
      })
    ).toBe("error");
  });
});

describe("merge redispatch state", () => {
  test("updateSessionMapping updates matching task session id", () => {
    const sessions = [
      { taskId: "task-a", sessionId: "old-a" },
      { taskId: "task-b", sessionId: "old-b" },
    ];
    expect(updateSessionMapping(sessions, "task-b", "new-b")).toBe(true);
    expect(sessions).toEqual([
      { taskId: "task-a", sessionId: "old-a" },
      { taskId: "task-b", sessionId: "new-b" },
    ]);
  });

  test("updateSessionMapping returns false when no task match exists", () => {
    const sessions = [{ taskId: "task-a", sessionId: "old-a" }];
    expect(updateSessionMapping(sessions, "task-missing", "new-id")).toBe(false);
    expect(sessions[0]?.sessionId).toBe("old-a");
  });

  test("requireRedispatchAuthorLogin fails closed on missing author login", () => {
    expect(() =>
      requireRedispatchAuthorLogin(
        {
          number: 12,
          user: { login: null },
        },
        "task-12"
      )
    ).toThrow(PreflightFailureError);
  });

  test("findRedispatchPullRequest ignores body-only session references", () => {
    const now = Date.now();
    const pulls = [
      {
        number: 20,
        head: { ref: "jules/no-token", repo: { full_name: "owner/repo" } },
        body: "redispatch for session new-session-id",
        user: { login: "jules[bot]" },
        created_at: new Date(now + 500).toISOString(),
      },
      {
        number: 21,
        head: { ref: "jules/new-session-id", repo: { full_name: "owner/repo" } },
        body: "redispatch task",
        user: { login: "jules[bot]" },
        created_at: new Date(now + 1_000).toISOString(),
      },
    ];

    const match = findRedispatchPullRequest(pulls, "new-session-id", {
      expectedRepoFullName: "owner/repo",
      expectedAuthorLogin: "jules[bot]",
      notBeforeEpochMs: now,
    });

    expect(match?.number).toBe(21);
  });

  test("resolveUpdateBranchFailure re-dispatches and persists updated session mapping", async () => {
    const sessions = [{ taskId: "task-a", sessionId: "old-session" }];
    let persisted: Array<{ taskId: string; sessionId: string }> | null = null;

    const result = await resolveUpdateBranchFailure({
      updateStatus: 422,
      retryCount: 0,
      maxRetries: 2,
      taskId: "task-a",
      sessions,
      redispatch: async () => ({
        nextPr: {
          number: 99,
          head: { ref: "jules/new-session", repo: { full_name: "owner/repo" } },
          body: null,
        },
        nextSessionId: "new-session",
      }),
      persistSessions: async (updated) => {
        persisted = updated.map((entry) => ({ ...entry }));
      },
    });

    expect(result.action).toBe("redispatch");
    if (result.action === "redispatch") {
      expect(result.nextPr.number).toBe(99);
      expect(result.nextRetryCount).toBe(1);
    }
    expect(sessions[0]?.sessionId).toBe("new-session");
    expect(persisted?.[0]?.sessionId).toBe("new-session");
  });

  test("resolveUpdateBranchFailure aborts when retry ceiling is reached", async () => {
    const result = await resolveUpdateBranchFailure({
      updateStatus: 422,
      retryCount: 2,
      maxRetries: 2,
      taskId: "task-a",
      sessions: [{ taskId: "task-a", sessionId: "old-session" }],
      redispatch: async () => {
        throw new Error("redispatch should not be called");
      },
      persistSessions: async () => {
        throw new Error("persist should not be called");
      },
    });

    expect(result).toEqual({ action: "abort" });
  });

  test("resolveUpdateBranchFailure returns error for non-conflict failures", async () => {
    const result = await resolveUpdateBranchFailure({
      updateStatus: 500,
      retryCount: 0,
      maxRetries: 2,
      taskId: "task-a",
      sessions: [{ taskId: "task-a", sessionId: "old-session" }],
      redispatch: async () => {
        throw new Error("redispatch should not be called");
      },
      persistSessions: async () => {
        throw new Error("persist should not be called");
      },
    });

    expect(result).toEqual({ action: "error" });
  });
});
