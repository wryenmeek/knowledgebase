// Copyright 2026 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import { describe, expect, test } from "bun:test";
import { collectAndClassifyPersona, requireOutputPath } from "./collect-and-report-cli.ts";
import type { CollectorFetchLike, CollectorFetchResponse } from "./collect.ts";

const REPO = "wryenmeek/knowledgebase";
const AS_OF = "2026-08-10T00:00:00.000Z";
const LOOKBACK = "2026-07-01T00:00:00.000Z";
const SHA_A = "a".repeat(40);
const SHA_B = "b".repeat(40);

function jsonResponse(status: number, body: unknown): CollectorFetchResponse {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  };
}

function makeMergedPullDetail(overrides: Record<string, unknown> = {}) {
  return {
    number: 100,
    state: "closed",
    draft: false,
    created_at: "2026-08-01T00:00:00.000Z",
    merged_at: "2026-08-02T00:00:00.000Z",
    merge_commit_sha: SHA_B,
    mergeable_state: "clean",
    base: { sha: SHA_A, repo: { full_name: REPO } },
    head: { sha: SHA_B, repo: { full_name: REPO } },
    user: { login: "google-labs-jules[bot]" },
    labels: [],
    ...overrides,
  };
}

interface FakeRoutes {
  list?: unknown[][];
  detailByNumber?: Record<number, unknown>;
  eventsByNumber?: Record<number, unknown[]>;
  checkRunsByHeadSha?: Record<string, unknown[]>;
}

function makeFetch(routes: FakeRoutes): CollectorFetchLike {
  return (async (url: string) => {
    const pullsListMatch = url.match(/\/pulls\?state=all.*page=(\d+)/);
    if (pullsListMatch) {
      const page = Number(pullsListMatch[1]);
      const pages = routes.list ?? [];
      return jsonResponse(200, pages[page - 1] ?? []);
    }

    const detailMatch = url.match(/\/pulls\/(\d+)$/);
    if (detailMatch) {
      const number = Number(detailMatch[1]);
      return jsonResponse(200, routes.detailByNumber?.[number] ?? makeMergedPullDetail({ number }));
    }

    const eventsMatch = url.match(/\/issues\/(\d+)\/events/);
    if (eventsMatch) {
      const number = Number(eventsMatch[1]);
      return jsonResponse(200, routes.eventsByNumber?.[number] ?? []);
    }

    const checkRunsMatch = url.match(/\/commits\/([0-9a-f]+)\/check-runs/);
    if (checkRunsMatch) {
      const sha = checkRunsMatch[1]!;
      return jsonResponse(200, { check_runs: routes.checkRunsByHeadSha?.[sha] ?? [] });
    }

    throw new Error(`unexpected URL in fake fetch: ${url}`);
  }) as CollectorFetchLike;
}

function baseOptions(overrides: Partial<Parameters<typeof collectAndClassifyPersona>[0]> = {}) {
  return {
    apiBase: "https://api.github.test/repos/owner/repo",
    headers: { Authorization: "***" },
    repoFullName: REPO,
    persona: "bolt" as const,
    authorLogins: ["google-labs-jules[bot]"],
    asOf: AS_OF,
    lookbackWatermark: LOOKBACK,
    ...overrides,
  };
}

describe("collectAndClassifyPersona (TDZ/ordering regression: R1)", () => {
  test("a normally successful collection (result.complete === true) with zero classification errors never throws and folds complete=true", async () => {
    // This is exactly the previously-broken path: a healthy collection
    // run with no classification errors. The buggy version read the
    // block-scoped `classifyErrors` before its declaration and threw a
    // `ReferenceError` on every such run.
    const fetchImpl = makeFetch({
      list: [[makeMergedPullDetail({ number: 100 })], []],
      eventsByNumber: { 100: [{ id: 9001, event: "merged" }] },
      checkRunsByHeadSha: { [SHA_B]: [] },
    });

    let caught: unknown;
    let result: Awaited<ReturnType<typeof collectAndClassifyPersona>> | undefined;
    try {
      result = await collectAndClassifyPersona(baseOptions({ fetchImpl }));
    } catch (error) {
      caught = error;
    }

    expect(caught).toBeUndefined();
    expect(result?.complete).toBe(true);
    expect(result?.errors).toEqual([]);
  });

  test("classification errors (from a malformed record) fold complete=false without ever throwing a ReferenceError", async () => {
    // An unresolvable outcome (open PR reported with a merge_commit_sha
    // set) trips `classifyPullRequests`'s own validation and produces a
    // classification error; `complete` must become false via that error,
    // not via any premature read.
    const fetchImpl = makeFetch({
      list: [
        [
          makeMergedPullDetail({
            number: 101,
            state: "open",
            merged_at: null,
            merge_commit_sha: SHA_B, // contradictory: open PR with a merge commit
          }),
        ],
        [],
      ],
      eventsByNumber: { 101: [] },
      checkRunsByHeadSha: { [SHA_B]: [] },
    });

    let caught: unknown;
    let result: Awaited<ReturnType<typeof collectAndClassifyPersona>> | undefined;
    try {
      result = await collectAndClassifyPersona(baseOptions({ fetchImpl }));
    } catch (error) {
      caught = error;
    }

    expect(caught).toBeUndefined();
    expect(result?.complete).toBe(false);
    expect(result?.errors.some((message) => message.startsWith("bolt: "))).toBe(true);
  });

  test("an incomplete collection result (pagination fail-closed) folds complete=false", async () => {
    const fetchImpl = (async (url: string) => {
      if (/\/pulls\?state=all/.test(url)) {
        // Always return a full page so pagination never terminates
        // naturally, forcing the collector's own fail-closed pagination
        // guard to report `complete: false`.
        return jsonResponse(200, Array.from({ length: 1 }, (_, i) => makeMergedPullDetail({ number: 200 + i })));
      }
      if (/\/pulls\/\d+$/.test(url)) {
        return jsonResponse(200, makeMergedPullDetail({ number: 200 }));
      }
      if (/\/issues\/\d+\/events/.test(url)) {
        return jsonResponse(200, []);
      }
      if (/\/commits\/[0-9a-f]+\/check-runs/.test(url)) {
        return jsonResponse(200, { check_runs: [] });
      }
      throw new Error(`unexpected URL in fake fetch: ${url}`);
    }) as CollectorFetchLike;

    let caught: unknown;
    let result: Awaited<ReturnType<typeof collectAndClassifyPersona>> | undefined;
    try {
      result = await collectAndClassifyPersona(baseOptions({ fetchImpl }));
    } catch (error) {
      caught = error;
    }

    expect(caught).toBeUndefined();
    expect(result?.complete).toBe(false);
  });
});

describe("requireOutputPath (missing explicit report path guard)", () => {
  test("throws when no positional argument is supplied (argv.length === 2)", () => {
    expect(() => requireOutputPath(["bun", "collect-and-report-cli.ts"])).toThrow(
      /explicit out-of-tree report path is required/
    );
  });

  test("throws when the positional argument is an empty string", () => {
    expect(() => requireOutputPath(["bun", "collect-and-report-cli.ts", ""])).toThrow(
      /explicit out-of-tree report path is required/
    );
  });

  test("returns the path when a non-empty positional argument is supplied", () => {
    expect(requireOutputPath(["bun", "collect-and-report-cli.ts", "out/report.json"])).toBe(
      "out/report.json"
    );
  });
});
