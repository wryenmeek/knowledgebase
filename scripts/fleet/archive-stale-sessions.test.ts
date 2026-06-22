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

import { describe, expect, mock, test } from "bun:test";
import fs from "node:fs";
import path from "node:path";
import type { JulesClient, SessionResource } from "@google/jules-sdk";
import {
  archiveStaleSessions,
  buildSessionIssueIndexFromFleet,
  parseCliArgs,
  CURRENT_REPO_SOURCE,
  type ArchiveCliArgs,
} from "./archive-stale-sessions.ts";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

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

function daysAgo(days: number): string {
  return new Date(Date.now() - days * 24 * 60 * 60 * 1000).toISOString();
}

async function* asyncFrom<T>(items: T[]): AsyncIterable<T> {
  for (const item of items) {
    yield item;
  }
}

function makeMockClient(sessions: SessionResource[], archiveFn?: (id: string) => Promise<void>): JulesClient {
  const archiveMock = archiveFn ?? (async (_id: string) => {});
  return {
    sessions: (_options?: unknown) => ({
      [Symbol.asyncIterator]: () => asyncFrom(sessions)[Symbol.asyncIterator](),
      then: (onfulfilled: any) => Promise.resolve({ sessions, nextPageToken: undefined }).then(onfulfilled),
      all: async () => sessions,
    } as any),
    session: (idOrConfig: any) => ({
      archive: () => archiveMock(typeof idOrConfig === "string" ? idOrConfig : idOrConfig.id),
    } as any),
    sources: Object.assign(
      (_options?: unknown) => asyncFrom([])[Symbol.asyncIterator](),
      { get: async (_filter: { github: string }) => undefined }
    ) as any,
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

const DEFAULT_ARGS: ArchiveCliArgs = {
  state: "inProgress",
  olderThanDays: 7,
  sourceFilter: undefined,
  repoAll: false,
  apply: false,
};

// ---------------------------------------------------------------------------
// parseCliArgs tests
// ---------------------------------------------------------------------------

describe("parseCliArgs", () => {
  test("requires --older-than-days", () => {
    expect(() => parseCliArgs([])).toThrow(
      "--older-than-days is required"
    );
  });

  test("requires positive integer for --older-than-days", () => {
    expect(() => parseCliArgs(["--older-than-days", "0"])).toThrow(
      "--older-than-days must be a positive integer"
    );
    expect(() => parseCliArgs(["--older-than-days", "-5"])).toThrow(
      "--older-than-days must be a positive integer"
    );
    expect(() => parseCliArgs(["--older-than-days", "abc"])).toThrow(
      "--older-than-days must be a positive integer"
    );
  });

  test("defaults to state=inProgress and apply=false", () => {
    const args = parseCliArgs(["--older-than-days", "7"]);
    expect(args.state).toBe("inProgress");
    expect(args.apply).toBe(false);
    expect(args.sourceFilter).toBeUndefined();
    expect(args.olderThanDays).toBe(7);
  });

  test("parses --state override", () => {
    const args = parseCliArgs(["--older-than-days", "3", "--state", "paused"]);
    expect(args.state).toBe("paused");
  });

  test("parses --source-filter", () => {
    const args = parseCliArgs([
      "--older-than-days",
      "3",
      "--source-filter",
      "sources/github/myorg/myrepo",
    ]);
    expect(args.sourceFilter).toBe("sources/github/myorg/myrepo");
  });

  test("trims copy-paste whitespace from --source-filter", () => {
    const args = parseCliArgs([
      "--older-than-days",
      "3",
      "--source-filter",
      "  sources/github/myorg/myrepo\n",
    ]);
    expect(args.sourceFilter).toBe("sources/github/myorg/myrepo");
  });

  test("--apply with whitespace-only --source-filter is denied", () => {
    expect(() =>
      parseCliArgs(["--older-than-days", "7", "--source-filter", "   ", "--apply"])
    ).toThrow("--source-filter requires a non-empty value");
  });

  test("--apply with empty --source-filter is denied", () => {
    expect(() =>
      parseCliArgs(["--older-than-days", "7", "--source-filter", "", "--apply"])
    ).toThrow("--source-filter requires a non-empty value");
  });

  test("parses --apply flag with --repo current", () => {
    const args = parseCliArgs([
      "--older-than-days",
      "3",
      "--repo",
      "current",
      "--apply",
    ]);
    expect(args.apply).toBe(true);
    expect(args.sourceFilter).toBe(CURRENT_REPO_SOURCE);
  });

  test("--apply without source scope fails closed", () => {
    expect(() =>
      parseCliArgs(["--older-than-days", "7", "--apply"])
    ).toThrow("--apply requires an explicit source scope");
  });

  test("--apply with --repo current succeeds and resolves to this repo", () => {
    const args = parseCliArgs([
      "--older-than-days",
      "7",
      "--repo",
      "current",
      "--apply",
    ]);
    expect(args.apply).toBe(true);
    expect(args.sourceFilter).toBe(CURRENT_REPO_SOURCE);
    expect(args.repoAll).toBe(false);
  });

  test("--apply with --repo all succeeds and sets repoAll=true", () => {
    const args = parseCliArgs([
      "--older-than-days",
      "7",
      "--repo",
      "all",
      "--apply",
    ]);
    expect(args.apply).toBe(true);
    expect(args.sourceFilter).toBeUndefined();
    expect(args.repoAll).toBe(true);
  });

  test("--repo with invalid value throws", () => {
    expect(() =>
      parseCliArgs(["--older-than-days", "7", "--repo", "unknown"])
    ).toThrow('--repo must be "current" or "all"');
  });

  test("dry-run without source scope is allowed", () => {
    const args = parseCliArgs(["--older-than-days", "7"]);
    expect(args.apply).toBe(false);
    expect(args.sourceFilter).toBeUndefined();
    expect(args.repoAll).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// archiveStaleSessions tests
// ---------------------------------------------------------------------------

describe("archiveStaleSessions", () => {
  test("dry-run is the default — no archive calls", async () => {
    const archiveMock = mock(async (_id: string) => {});
    const sessions = [
      makeSession({ id: "old1", state: "inProgress", createTime: daysAgo(10) }),
    ];
    const client = makeMockClient(sessions, archiveMock);

    const result = await archiveStaleSessions(client, DEFAULT_ARGS);

    expect(result.dryRun).toBe(true);
    expect(result.archived).toHaveLength(0);
    expect(result.candidates).toHaveLength(1);
    expect(archiveMock).not.toHaveBeenCalled();
  });

  test("--apply triggers real archive calls", async () => {
    const archiveMock = mock(async (_id: string) => {});
    const sessions = [
      makeSession({ id: "old1", state: "inProgress", createTime: daysAgo(10) }),
      makeSession({ id: "old2", state: "inProgress", createTime: daysAgo(15) }),
    ];
    const client = makeMockClient(sessions, archiveMock);

    const args: ArchiveCliArgs = {
      ...DEFAULT_ARGS,
      sourceFilter: "sources/github/myorg/myrepo",
      apply: true,
    };
    const result = await archiveStaleSessions(client, args);

    expect(result.dryRun).toBe(false);
    expect(result.archived).toHaveLength(2);
    expect(result.archivedCount).toBe(2);
    expect(archiveMock).toHaveBeenCalledTimes(2);
  });

  test("age filter excludes sessions younger than olderThanDays", async () => {
    const archiveMock = mock(async (_id: string) => {});
    const sessions = [
      makeSession({ id: "old", state: "inProgress", createTime: daysAgo(10) }),
      makeSession({ id: "new", state: "inProgress", createTime: daysAgo(2) }),
    ];
    const client = makeMockClient(sessions, archiveMock);

    const result = await archiveStaleSessions(client, { ...DEFAULT_ARGS, apply: false });

    expect(result.candidates).toHaveLength(1);
    expect(result.candidates[0]!.sessionId).toBe("old");
  });

  test("state filter excludes sessions with other states", async () => {
    const sessions = [
      makeSession({ id: "in-progress", state: "inProgress", createTime: daysAgo(10) }),
      makeSession({ id: "completed", state: "completed", createTime: daysAgo(10) }),
      makeSession({ id: "paused", state: "paused", createTime: daysAgo(10) }),
    ];
    const client = makeMockClient(sessions);

    const result = await archiveStaleSessions(client, DEFAULT_ARGS);

    expect(result.candidates).toHaveLength(1);
    expect(result.candidates[0]!.sessionId).toBe("in-progress");
  });

  test("source-filter scopes to specific source", async () => {
    const sessions = [
      makeSession({
        id: "target",
        state: "inProgress",
        createTime: daysAgo(10),
        sourceContext: { source: "sources/github/myorg/myrepo" },
      }),
      makeSession({
        id: "other",
        state: "inProgress",
        createTime: daysAgo(10),
        sourceContext: { source: "sources/github/otherorg/other" },
      }),
    ];
    const client = makeMockClient(sessions);

    const args: ArchiveCliArgs = {
      ...DEFAULT_ARGS,
      sourceFilter: "sources/github/myorg/myrepo",
    };
    const result = await archiveStaleSessions(client, args);

    expect(result.candidates).toHaveLength(1);
    expect(result.candidates[0]!.sessionId).toBe("target");
    expect(result.filters.sourceFilter).toBe("sources/github/myorg/myrepo");
  });

  test("errors during archive are captured per-session, not fatal", async () => {
    const archiveMock = mock(async (id: string) => {
      if (id === "error-session") {
        throw new Error("archive failed: quota exceeded");
      }
    });
    const sessions = [
      makeSession({ id: "ok-session", state: "inProgress", createTime: daysAgo(10), sourceContext: { source: "sources/github/myorg/myrepo" } }),
      makeSession({ id: "error-session", state: "inProgress", createTime: daysAgo(10), sourceContext: { source: "sources/github/myorg/myrepo" } }),
    ];
    const client = makeMockClient(sessions, archiveMock);

    const args: ArchiveCliArgs = {
      ...DEFAULT_ARGS,
      sourceFilter: "sources/github/myorg/myrepo",
      apply: true,
    };
    const result = await archiveStaleSessions(client, args);

    expect(result.archived).toHaveLength(1);
    expect(result.archived[0]!.sessionId).toBe("ok-session");
    expect(result.errors).toHaveLength(1);
    expect(result.errors[0]!.sessionId).toBe("error-session");
    expect(result.errors[0]!.error).toContain("archive failed");
  });

  test("envelope contains filter metadata", async () => {
    const client = makeMockClient([]);
    const args: ArchiveCliArgs = {
      state: "paused",
      olderThanDays: 14,
      sourceFilter: "sources/github/myorg/myrepo",
      repoAll: false,
      apply: false,
    };
    const result = await archiveStaleSessions(client, args);

    expect(result.filters.state).toBe("paused");
    expect(result.filters.olderThanDays).toBe(14);
    expect(result.filters.sourceFilter).toBe("sources/github/myorg/myrepo");
    expect(result.filters.repoAll).toBe(false);
    expect(result.ranAt).toBeString();
  });

  test("mixed-repo sessions: apply with source filter skips non-matching repos", async () => {
    const archiveMock = mock(async (_id: string) => {});
    const sessions = [
      makeSession({
        id: "knowledgebase-session",
        state: "inProgress",
        createTime: daysAgo(10),
        sourceContext: { source: CURRENT_REPO_SOURCE },
      }),
      makeSession({
        id: "other-repo-session",
        state: "inProgress",
        createTime: daysAgo(10),
        sourceContext: { source: "sources/github/wryenmeek/hot-springs-island" },
      }),
    ];
    const client = makeMockClient(sessions, archiveMock);

    const args: ArchiveCliArgs = {
      ...DEFAULT_ARGS,
      sourceFilter: CURRENT_REPO_SOURCE,
      apply: true,
    };
    const result = await archiveStaleSessions(client, args);

    expect(result.candidates).toHaveLength(1);
    expect(result.candidates[0]!.sessionId).toBe("knowledgebase-session");
    expect(result.archived).toHaveLength(1);
    expect(result.archived[0]!.sessionId).toBe("knowledgebase-session");
    expect(archiveMock).toHaveBeenCalledTimes(1);
  });

  test("--repo all (repoAll=true) archives across all sources", async () => {
    const archiveMock = mock(async (_id: string) => {});
    const sessions = [
      makeSession({
        id: "repo-a-session",
        state: "inProgress",
        createTime: daysAgo(10),
        sourceContext: { source: "sources/github/org/repo-a" },
      }),
      makeSession({
        id: "repo-b-session",
        state: "inProgress",
        createTime: daysAgo(10),
        sourceContext: { source: "sources/github/org/repo-b" },
      }),
    ];
    const client = makeMockClient(sessions, archiveMock);

    const args: ArchiveCliArgs = {
      ...DEFAULT_ARGS,
      sourceFilter: undefined,
      repoAll: true,
      apply: true,
    };
    const result = await archiveStaleSessions(client, args);

    expect(result.candidates).toHaveLength(2);
    expect(result.archived).toHaveLength(2);
    expect(result.filters.repoAll).toBe(true);
    expect(archiveMock).toHaveBeenCalledTimes(2);
  });

  test("no archive when candidates list is empty", async () => {
    const archiveMock = mock(async (_id: string) => {});
    const client = makeMockClient([], archiveMock);

    const args: ArchiveCliArgs = {
      ...DEFAULT_ARGS,
      sourceFilter: "sources/github/myorg/myrepo",
      apply: true,
    };
    const result = await archiveStaleSessions(client, args);

    expect(result.candidates).toHaveLength(0);
    expect(result.archived).toHaveLength(0);
    expect(archiveMock).not.toHaveBeenCalled();
  });

  test("apply mode fails closed when current-repo session has no task join", async () => {
    const sessions = [
      makeSession({
        id: "missing-join",
        state: "inProgress",
        createTime: daysAgo(10),
        sourceContext: { source: CURRENT_REPO_SOURCE },
      }),
    ];
    const client = makeMockClient(sessions);

    await expect(
      archiveStaleSessions(
        client,
        {
          ...DEFAULT_ARGS,
          sourceFilter: CURRENT_REPO_SOURCE,
          apply: true,
        },
        {
          issueResolver: {
            resolveIssuesForSession: () => null,
          },
        }
      )
    ).rejects.toThrow("No issue mapping found for archived session missing-join.");
  });
});

describe("buildSessionIssueIndexFromFleet", () => {
  test("indexes sessionId -> issue numbers through sessions/task join", () => {
    const tempRoot = fs.mkdtempSync(path.join(process.cwd(), "tmp-fleet-join-"));
    const dateDir = path.join(tempRoot, "2026_06_22");
    fs.mkdirSync(dateDir, { recursive: true });
    fs.writeFileSync(
      path.join(dateDir, "sessions.json"),
      JSON.stringify([{ taskId: "task-one", sessionId: "session-1" }])
    );
    fs.writeFileSync(
      path.join(dateDir, "issue_tasks.json"),
      JSON.stringify({
        tasks: [{ id: "task-one", issues: [350, 351] }],
      })
    );

    const index = buildSessionIssueIndexFromFleet(tempRoot);
    expect(index.get("session-1")).toEqual([350, 351]);
    fs.rmSync(tempRoot, { recursive: true, force: true });
  });
});
