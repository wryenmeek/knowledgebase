import { describe, expect, test } from "bun:test";
import {
  buildDispatchCommentBody,
  countRecentInProgressAttempts,
  markIssueInProgress,
  restoreIssueAfterFailure,
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
      { event: "closed", created_at: isoDaysAgo(2), commit_id: "abc123" },
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
});
