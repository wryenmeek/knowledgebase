import { describe, expect, test } from "bun:test";
import { getIssuesAsMarkdown } from "./markdown.ts";

type MockIssue = {
  number: number;
  title: string;
  html_url: string;
  user: { login: string };
  author_association: string;
  state: string;
  state_reason: null;
  locked: boolean;
  active_lock_reason: null;
  comments: number;
  created_at: string;
  updated_at: string;
  labels: Array<{ name: string }>;
  assignees: Array<{ login: string }>;
  reactions: null;
};

function makeIssue(number: number, title: string, labels: string[]): MockIssue {
  return {
    number,
    title,
    html_url: `https://example.test/issues/${number}`,
    user: { login: "test-user" },
    author_association: "MEMBER",
    state: "open",
    state_reason: null,
    locked: false,
    active_lock_reason: null,
    comments: 0,
    created_at: "2026-06-22T00:00:00Z",
    updated_at: "2026-06-22T00:00:00Z",
    labels: labels.map((name) => ({ name })),
    assignees: [],
    reactions: null,
  };
}

describe("getIssuesAsMarkdown", () => {
  test("label-scoped planner input includes only ready-for-agent issues", async () => {
    const issues = [
      makeIssue(101, "ready issue", ["ready-for-agent"]),
      makeIssue(102, "in progress issue", ["in-progress"]),
      makeIssue(103, "ready for human issue", ["ready-for-human"]),
    ];
    const seenOptions: Array<{ labels?: string[] }> = [];

    const markdown = await getIssuesAsMarkdown(
      { labels: ["ready-for-agent"] },
      async (options) => {
        seenOptions.push({ labels: options?.labels });
        const selected = options?.labels ?? [];
        return issues.filter((issue) =>
          issue.labels.some((label) => selected.includes(label.name))
        ) as never;
      }
    );

    expect(seenOptions).toEqual([{ labels: ["ready-for-agent"] }]);
    expect(markdown).toContain("## #101: ready issue");
    expect(markdown).not.toContain("## #102: in progress issue");
    expect(markdown).not.toContain("## #103: ready for human issue");
  });
});
