import { describe, expect, test } from "bun:test";
import {
  buildDispatchCommentBody,
  countRecentInProgressAttempts,
  markIssueInProgress,
  restoreIssueAfterFailure,
  runWithIssueRecovery,
  selectRecoveryLabelFromEvents,
} from "./fleet-dispatch.ts";

function isoDaysAgo(daysAgo: number): string {
  return new Date(Date.now() - daysAgo * 24 * 60 * 60 * 1000).toISOString();
}

describe("fleet-dispatch label lifecycle", () => {
  test("markIssueInProgress adds in-progress before removing ready-for-agent", async () => {
    const calls: string[] = [];
    const octokit = {
      rest: {
        issues: {
          addLabels: async () => {
            calls.push("add");
          },
          removeLabel: async () => {
            calls.push("remove");
          },
          createComment: async () => {},
          listEvents: async () => ({}),
        },
      },
      paginate: async () => [],
    };

    await markIssueInProgress(octokit as never, "wryenmeek", "knowledgebase", 350);
    expect(calls).toEqual(["add", "remove"]);
  });

  test("dispatch recovery restores labels when the operation fails", async () => {
    const calls: string[] = [];
    const octokit = {
      rest: {
        issues: {
          addLabels: async () => {
            calls.push("add");
          },
          removeLabel: async () => {
            calls.push("remove");
          },
          createComment: async () => {},
          listEvents: async () => ({}),
        },
      },
      paginate: async () => [],
    };

    await expect(
      runWithIssueRecovery(
        octokit as never,
        "wryenmeek",
        "knowledgebase",
        [350],
        async () => {
          await markIssueInProgress(octokit as never, "wryenmeek", "knowledgebase", 350);
          throw new Error("dispatch failed");
        }
      )
    ).rejects.toThrow("dispatch failed");
    expect(calls).toEqual([
      "add",
      "remove",
      "remove",
      "remove",
      "remove",
      "remove",
      "add",
    ]);
  });

  test("dispatch comment embeds exactly task.prompt inside details block", () => {
    const taskPrompt = "Implement exact scoped change.\nDo not edit unrelated files.";
    const body = buildDispatchCommentBody("Task title", "session-123", taskPrompt);
    expect(body).toContain("<details>");
    expect(body).toContain("</details>");
    expect(body).toContain(taskPrompt);
  });

  test("3 recent attempts after latest human ready-for-agent transitions to needs-triage", () => {
    const events = [
      {
        event: "labeled",
        created_at: isoDaysAgo(5),
        label: { name: "ready-for-agent" },
        actor: { login: "human-user", type: "User" },
      },
      {
        event: "labeled",
        created_at: isoDaysAgo(4),
        label: { name: "in-progress" },
        actor: { login: "github-actions[bot]", type: "Bot" },
      },
      {
        event: "labeled",
        created_at: isoDaysAgo(3),
        label: { name: "in-progress" },
        actor: { login: "github-actions[bot]", type: "Bot" },
      },
      {
        event: "labeled",
        created_at: isoDaysAgo(1),
        label: { name: "in-progress" },
        actor: { login: "github-actions[bot]", type: "Bot" },
      },
    ];
    expect(countRecentInProgressAttempts(events)).toBe(3);
    expect(selectRecoveryLabelFromEvents(events)).toBe("needs-triage");
  });

  test("merge reset makes next failure count as 1", () => {
    const events = [
      {
        event: "labeled",
        created_at: isoDaysAgo(20),
        label: { name: "ready-for-agent" },
        actor: { login: "human-user", type: "User" },
      },
      { event: "labeled", created_at: isoDaysAgo(19), label: { name: "in-progress" } },
      { event: "labeled", created_at: isoDaysAgo(18), label: { name: "in-progress" } },
      {
        event: "closed",
        created_at: isoDaysAgo(2),
        commit_id: "abc123",
        verified_merged_pr: true,
      },
      { event: "labeled", created_at: isoDaysAgo(1), label: { name: "in-progress" } },
    ];
    expect(countRecentInProgressAttempts(events)).toBe(1);
  });

  test("operator re-apply of ready-for-agent resets the counter to 0", () => {
    const events = [
      {
        event: "labeled",
        created_at: isoDaysAgo(6),
        label: { name: "ready-for-agent" },
        actor: { login: "human-user", type: "User" },
      },
      { event: "labeled", created_at: isoDaysAgo(5), label: { name: "in-progress" } },
      { event: "labeled", created_at: isoDaysAgo(4), label: { name: "in-progress" } },
      {
        event: "labeled",
        created_at: isoDaysAgo(1),
        label: { name: "ready-for-agent" },
        actor: { login: "human-user", type: "User" },
      },
    ];
    expect(countRecentInProgressAttempts(events)).toBe(0);
  });

  test("attempt counting only includes the last 30 days", () => {
    const events = [
      {
        event: "labeled",
        created_at: isoDaysAgo(40),
        label: { name: "ready-for-agent" },
        actor: { login: "human-user", type: "User" },
      },
      { event: "labeled", created_at: isoDaysAgo(35), label: { name: "in-progress" } },
      { event: "labeled", created_at: isoDaysAgo(2), label: { name: "in-progress" } },
    ];
    expect(countRecentInProgressAttempts(events)).toBe(1);
  });

  test("restoreIssueAfterFailure adds needs-triage on third strike", async () => {
    const labelOps: string[] = [];
    const octokit = {
      rest: {
        issues: {
          addLabels: async (params: { labels: string[] }) => {
            labelOps.push(`add:${params.labels[0]}`);
          },
          removeLabel: async (params: { name: string }) => {
            labelOps.push(`remove:${params.name}`);
          },
          createComment: async () => {},
          listEvents: async () => ({}),
        },
      },
      paginate: async () => [
        {
          event: "labeled",
          created_at: isoDaysAgo(5),
          label: { name: "ready-for-agent" },
          actor: { login: "human-user", type: "User" },
        },
        { event: "labeled", created_at: isoDaysAgo(4), label: { name: "in-progress" } },
        { event: "labeled", created_at: isoDaysAgo(3), label: { name: "in-progress" } },
        { event: "labeled", created_at: isoDaysAgo(2), label: { name: "in-progress" } },
      ],
    };

    const nextLabel = await restoreIssueAfterFailure(
      octokit as never,
      "wryenmeek",
      "knowledgebase",
      350
    );
    expect(nextLabel).toBe("needs-triage");
    expect(labelOps[labelOps.length - 1]).toBe("add:needs-triage");
  });

  test("strikes < 3 selects ready-for-agent and restoreIssueAfterFailure adds it (P1: gap fill)", async () => {
    const labelOps: string[] = [];
    const events = [
      {
        event: "labeled",
        created_at: isoDaysAgo(5),
        label: { name: "ready-for-agent" },
        actor: { login: "human-user", type: "User" },
      },
      { event: "labeled", created_at: isoDaysAgo(3), label: { name: "in-progress" } },
      { event: "labeled", created_at: isoDaysAgo(1), label: { name: "in-progress" } },
    ];
    expect(selectRecoveryLabelFromEvents(events)).toBe("ready-for-agent");

    const octokit = {
      rest: {
        issues: {
          addLabels: async (params: { labels: string[] }) => {
            labelOps.push(`add:${params.labels[0]}`);
          },
          removeLabel: async (params: { name: string }) => {
            labelOps.push(`remove:${params.name}`);
          },
          createComment: async () => {},
          listEvents: async () => ({}),
        },
      },
      paginate: async () => events,
    };

    const next = await restoreIssueAfterFailure(
      octokit as never,
      "wryenmeek",
      "knowledgebase",
      350
    );
    expect(next).toBe("ready-for-agent");
    expect(labelOps[labelOps.length - 1]).toBe("add:ready-for-agent");
  });

  test("bot re-apply of ready-for-agent does NOT reset strikes (P1: isHumanActor guard)", () => {
    // If `isHumanActor` is ever relaxed to allow bot apply, the abort
    // mechanism collapses silently: every recovery cycle would reset the
    // counter and `needs-triage` would become unreachable. Pin the
    // behavior here so a regression fails loud.
    const events = [
      {
        event: "labeled",
        created_at: isoDaysAgo(5),
        label: { name: "ready-for-agent" },
        actor: { login: "github-actions[bot]", type: "Bot" },
      },
      { event: "labeled", created_at: isoDaysAgo(4), label: { name: "in-progress" } },
      { event: "labeled", created_at: isoDaysAgo(3), label: { name: "in-progress" } },
      {
        event: "labeled",
        created_at: isoDaysAgo(2),
        label: { name: "ready-for-agent" },
        actor: { login: "dependabot[bot]", type: "Bot" },
      },
      { event: "labeled", created_at: isoDaysAgo(1), label: { name: "in-progress" } },
    ];
    expect(countRecentInProgressAttempts(events)).toBe(3);
    expect(selectRecoveryLabelFromEvents(events)).toBe("needs-triage");
  });

  test("commit-associated non-merge close does NOT reset strike counter", () => {
    // A commit_id only proves that a commit closed the issue; it does not
    // prove that a pull request was merged.
    // A manual unmerged close (operator clearing stale state) must not
    // erase strike history. Pin this so the guard cannot be removed
    // without a failing test.
    const events = [
      {
        event: "labeled",
        created_at: isoDaysAgo(10),
        label: { name: "ready-for-agent" },
        actor: { login: "human-user", type: "User" },
      },
      { event: "labeled", created_at: isoDaysAgo(9), label: { name: "in-progress" } },
      { event: "labeled", created_at: isoDaysAgo(8), label: { name: "in-progress" } },
      { event: "closed", created_at: isoDaysAgo(5), commit_id: "abc123" },
      { event: "labeled", created_at: isoDaysAgo(1), label: { name: "in-progress" } },
    ];
    expect(countRecentInProgressAttempts(events)).toBe(3);
  });

  test("closed event with incomplete merge metadata does NOT reset strike counter", () => {
    const events = [
      {
        event: "labeled",
        created_at: isoDaysAgo(10),
        label: { name: "ready-for-agent" },
        actor: { login: "human-user", type: "User" },
      },
      { event: "labeled", created_at: isoDaysAgo(9), label: { name: "in-progress" } },
      { event: "labeled", created_at: isoDaysAgo(8), label: { name: "in-progress" } },
      {
        event: "closed",
        created_at: isoDaysAgo(5),
        commit_id: "abc123",
        verified_merged_pr: false,
      },
      { event: "labeled", created_at: isoDaysAgo(1), label: { name: "in-progress" } },
    ];
    expect(countRecentInProgressAttempts(events)).toBe(3);
  });

  test("restoreIssueAfterFailure paginates listEvents with per_page=100 (P2: gap fill)", async () => {
    const paginateArgs: Array<{ fn: unknown; params: Record<string, unknown> }> = [];
    const octokit = {
      rest: {
        issues: {
          addLabels: async () => {},
          removeLabel: async () => {},
          createComment: async () => {},
          listEvents: function listEvents() {},
        },
        repos: {
          listPullRequestsAssociatedWithCommit: async () => ({ data: [] }),
        },
      },
      paginate: async (fn: unknown, params: Record<string, unknown>) => {
        paginateArgs.push({ fn, params });
        return [];
      },
    };
    await restoreIssueAfterFailure(octokit as never, "wryenmeek", "knowledgebase", 350);
    expect(paginateArgs).toHaveLength(1);
    expect(paginateArgs[0]!.fn).toBe(octokit.rest.issues.listEvents);
    expect(paginateArgs[0]!.params).toMatchObject({
      owner: "wryenmeek",
      repo: "knowledgebase",
      issue_number: 350,
      per_page: 100,
    });
  });

  test("restore verifies merge evidence through associated pull requests", async () => {
    const labels: string[] = [];
    const octokit = {
      rest: {
        issues: {
          addLabels: async ({ labels: added }: { labels: string[] }) => {
            labels.push(...added);
          },
          removeLabel: async () => {},
          createComment: async () => {},
          listEvents: function listEvents() {},
        },
        repos: {
          listPullRequestsAssociatedWithCommit: async () => ({
            data: [{ merged_at: isoDaysAgo(2) }],
          }),
        },
      },
      paginate: async () => [
        { event: "labeled", created_at: isoDaysAgo(5), label: { name: "in-progress" } },
        { event: "closed", created_at: isoDaysAgo(2), commit_id: "abc123" },
        { event: "labeled", created_at: isoDaysAgo(1), label: { name: "in-progress" } },
      ],
    };

    await restoreIssueAfterFailure(octokit as never, "wryenmeek", "knowledgebase", 350);
    expect(labels).toEqual(["ready-for-agent"]);
  });

  test("dispatch comment wraps task.prompt in fenced code block so HTML/markdown cannot escape (P3)", () => {
    // Defense against:
    //   1. `</details>` in the prompt closing the collapse wrapper early.
    //   2. `@user` mentions firing notification spam attributed to the bot.
    //   3. Markdown links/images rendering instead of showing source.
    const hostilePrompt =
      "</details>\n\n@everyone please notice me\n[click](http://evil) ![img](http://evil)";
    const body = buildDispatchCommentBody("Task title", "session-x", hostilePrompt);
    // The fence must surround the prompt so the hostile content sits between
    // backticks, not in raw markdown context. The `</details>` outside the
    // fence is the legitimate closing tag of the dispatch wrapper.
    const fenceOpenIdx = body.indexOf("````\n");
    const fenceCloseIdx = body.indexOf("\n````\n\n</details>");
    expect(fenceOpenIdx).toBeGreaterThan(-1);
    expect(fenceCloseIdx).toBeGreaterThan(fenceOpenIdx);
    const fencedSlice = body.slice(fenceOpenIdx, fenceCloseIdx);
    expect(fencedSlice).toContain("</details>");
    expect(fencedSlice).toContain("@everyone");
    expect(fencedSlice).toContain("[click](http://evil)");
    // After the fenced slice, only the wrapper close should remain.
    const afterFence = body.slice(fenceCloseIdx);
    expect(afterFence).toBe("\n````\n\n</details>");
  });
});
