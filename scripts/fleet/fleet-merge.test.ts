import { afterEach, describe, expect, test } from "bun:test";
import {
  clearIssueProgressLabelsAfterMerge,
  restoreIssueForRedispatch,
} from "./fleet-merge.ts";

const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
});

describe("fleet-merge issue label lifecycle", () => {
  test("successful merge clears in-progress and awaiting-feedback labels", async () => {
    const calls: string[] = [];
    globalThis.fetch = (async (input: RequestInfo | URL) => {
      calls.push(String(input));
      return new Response("", { status: 200 });
    }) as typeof fetch;

    await clearIssueProgressLabelsAfterMerge(
      "https://api.github.test/repos/wryenmeek/knowledgebase",
      { Authorization: "******" },
      350
    );

    expect(calls).toEqual([
      "https://api.github.test/repos/wryenmeek/knowledgebase/issues/350/labels/in-progress",
      "https://api.github.test/repos/wryenmeek/knowledgebase/issues/350/labels/awaiting-feedback",
    ]);
  });

  test("merge-conflict redispatch only removes progress labels and restores ready-for-agent", async () => {
    const calls: string[] = [];
    globalThis.fetch = (async (input: RequestInfo | URL) => {
      calls.push(String(input));
      return new Response("", { status: 200 });
    }) as typeof fetch;

    await restoreIssueForRedispatch(
      "https://api.github.test/repos/wryenmeek/knowledgebase",
      { Authorization: "******" },
      350
    );

    expect(calls).toEqual([
      "https://api.github.test/repos/wryenmeek/knowledgebase/issues/350/labels/in-progress",
      "https://api.github.test/repos/wryenmeek/knowledgebase/issues/350/labels/awaiting-feedback",
      "https://api.github.test/repos/wryenmeek/knowledgebase/issues/350/labels",
    ]);
  });

  test("clearing progress labels removes awaiting-feedback", async () => {
    const calls: string[] = [];
    globalThis.fetch = (async (input: RequestInfo | URL) => {
      calls.push(String(input));
      return new Response("", { status: 200 });
    }) as typeof fetch;

    await clearIssueProgressLabelsAfterMerge(
      "https://api.github.test/repos/wryenmeek/knowledgebase",
      { Authorization: "******" },
      351
    );

    expect(calls).toContain(
      "https://api.github.test/repos/wryenmeek/knowledgebase/issues/351/labels/awaiting-feedback"
    );
  });
});
