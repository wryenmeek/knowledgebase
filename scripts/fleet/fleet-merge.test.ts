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

  test("merge-conflict redispatch restores ready-for-agent and removes progress labels", async () => {
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

  test("awaiting-feedback removal applies for all exit states from awaitingUserFeedback", async () => {
    const exitStates = ["inProgress", "completed", "failed"] as const;
    for (const _state of exitStates) {
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

      expect(
        calls.some((url) => url.endsWith("/labels/awaiting-feedback"))
      ).toBeTrue();
    }
  });
});
