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
import type { JulesClient, SessionResource, Source } from "@google/jules-sdk";
import { runAccountProbe, type AccountProbeEnvelope } from "./jules-account-probe.ts";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeSource(overrides: Partial<Source> = {}): Source {
  return {
    name: "sources/github/myorg/myrepo",
    id: "github/myorg/myrepo",
    type: "githubRepo",
    githubRepo: { owner: "myorg", repo: "myrepo", isPrivate: false },
    ...overrides,
  } as Source;
}

function makeSession(overrides: Partial<SessionResource> = {}): SessionResource {
  const now = new Date();
  return {
    name: "sessions/abc123",
    id: "abc123",
    title: "Test session",
    prompt: "Do something",
    state: "inProgress",
    url: "https://jules.google.com/sessions/abc123",
    createTime: now.toISOString(),
    updateTime: now.toISOString(),
    sourceContext: {
      source: "sources/github/myorg/myrepo",
    },
    ...overrides,
  } as SessionResource;
}

async function* asyncFrom<T>(items: T[]): AsyncIterable<T> {
  for (const item of items) {
    yield item;
  }
}

function makeMockClient(opts: {
  sources?: Source[];
  sessions?: SessionResource[];
}): JulesClient {
  const sources = opts.sources ?? [];
  const sessions = opts.sessions ?? [];
  return {
    sources: Object.assign(
      (_options?: unknown) => asyncFrom(sources),
      { get: async (_filter: { github: string }) => undefined }
    ),
    sessions: (_options?: unknown) => ({
      [Symbol.asyncIterator]: () => asyncFrom(sessions)[Symbol.asyncIterator](),
      then: (onfulfilled: any) => Promise.resolve({ sessions, nextPageToken: undefined }).then(onfulfilled),
      all: async () => sessions,
    } as any),
    session: (_idOrConfig: any) => ({} as any),
    run: async (_config: any) => ({} as any),
    with: (_options: any) => ({} as any),
    connect: (_options: any) => ({} as any),
    select: async (_query: any) => [],
    all: async (_items: any[], _mapper: any) => [],
    storage: {} as any,
    sync: async () => ({} as any),
    getSessionResource: async () => ({} as any),
  } as unknown as JulesClient;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("jules-account-probe", () => {
  test("returns structured envelope with sources and session counts", async () => {
    const twoDaysAgo = new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString();
    const client = makeMockClient({
      sources: [makeSource()],
      sessions: [
        makeSession({ id: "s1", state: "inProgress", createTime: twoDaysAgo }),
        makeSession({ id: "s2", state: "completed" }),
      ],
    });

    const result: AccountProbeEnvelope = await runAccountProbe(client);

    expect(result.probedAt).toBeString();
    expect(result.sources).toHaveLength(1);
    expect(result.sources[0]!.name).toBe("sources/github/myorg/myrepo");
    expect(result.sources[0]!.type).toBe("githubRepo");
    expect(result.sources[0]!.githubRepo?.owner).toBe("myorg");

    expect(result.totals.sessions).toBe(2);
    expect(result.totals.activeSessions).toBe(1);  // only inProgress is active
    expect(result.totals.inProgressSessions).toBe(1);
    expect(result.totals.sources).toBe(1);
  });

  test("sessionsBySource groups sessions correctly", async () => {
    const client = makeMockClient({
      sources: [makeSource()],
      sessions: [
        makeSession({ id: "s1", state: "inProgress", sourceContext: { source: "sources/github/myorg/myrepo" } }),
        makeSession({ id: "s2", state: "inProgress", sourceContext: { source: "sources/github/myorg/myrepo" } }),
        makeSession({ id: "s3", state: "completed", sourceContext: { source: "sources/github/myorg/myrepo" } }),
        makeSession({ id: "s4", state: "queued", sourceContext: { source: "sources/github/other/repo" } }),
      ],
    });

    const result = await runAccountProbe(client);

    const myrepoSummary = result.sessionsBySource.find(
      (s) => s.sourceName === "sources/github/myorg/myrepo"
    );
    expect(myrepoSummary).toBeDefined();
    expect(myrepoSummary!.activeSessionCount).toBe(2);
    expect(myrepoSummary!.inProgressSessionCount).toBe(2);
    expect(myrepoSummary!.inProgressAges).toHaveLength(2);

    const otherSummary = result.sessionsBySource.find(
      (s) => s.sourceName === "sources/github/other/repo"
    );
    expect(otherSummary).toBeDefined();
    expect(otherSummary!.activeSessionCount).toBe(1);  // queued counts as active
    expect(otherSummary!.inProgressSessionCount).toBe(0);
  });

  test("inProgressAges contains session ID and human age string", async () => {
    const threeDaysAgo = new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString();
    const client = makeMockClient({
      sources: [],
      sessions: [
        makeSession({ id: "my-session-id", state: "inProgress", createTime: threeDaysAgo }),
      ],
    });

    const result = await runAccountProbe(client);
    const summary = result.sessionsBySource[0]!;
    expect(summary.inProgressAges).toHaveLength(1);
    expect(summary.inProgressAges[0]!.sessionId).toBe("my-session-id");
    expect(summary.inProgressAges[0]!.ageHuman).toContain("3d");
  });

  test("handles account with no sources gracefully", async () => {
    const client = makeMockClient({ sources: [], sessions: [] });
    const result = await runAccountProbe(client);
    expect(result.sources).toHaveLength(0);
    expect(result.sessionsBySource).toHaveLength(0);
    expect(result.totals.sessions).toBe(0);
    expect(result.totals.activeSessions).toBe(0);
  });

  test("sessions with no sourceContext are grouped under (no source)", async () => {
    const client = makeMockClient({
      sources: [],
      sessions: [
        makeSession({
          id: "s-nosource",
          state: "inProgress",
          sourceContext: { source: "" },
        }),
      ],
    });

    const result = await runAccountProbe(client);
    const noSourceSummary = result.sessionsBySource.find(
      (s) => s.sourceName === "(no source)"
    );
    expect(noSourceSummary).toBeDefined();
    expect(noSourceSummary!.inProgressSessionCount).toBe(1);
  });

  test("all active states are counted", async () => {
    const activeStates = [
      "queued",
      "planning",
      "awaitingPlanApproval",
      "awaitingUserFeedback",
      "inProgress",
      "paused",
    ] as const;

    const sessions = activeStates.map((state, idx) =>
      makeSession({ id: `s${idx}`, state })
    );
    const client = makeMockClient({ sources: [], sessions });

    const result = await runAccountProbe(client);
    expect(result.totals.activeSessions).toBe(activeStates.length);
    expect(result.totals.inProgressSessions).toBe(1);
  });

  test("terminal states (completed, failed) are not counted as active", async () => {
    const client = makeMockClient({
      sources: [],
      sessions: [
        makeSession({ id: "s1", state: "completed" }),
        makeSession({ id: "s2", state: "failed" }),
      ],
    });

    const result = await runAccountProbe(client);
    expect(result.totals.activeSessions).toBe(0);
    expect(result.totals.sessions).toBe(2);
  });
});
