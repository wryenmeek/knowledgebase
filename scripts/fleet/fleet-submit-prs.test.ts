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
import type { JulesClient, SessionResource } from "@google/jules-sdk";
import {
  MutationFailureError,
  MUTATION_EXECUTION_CONTRACT,
  type SanitizedErrorEnvelope,
} from "./github/mutation-diagnostics.ts";
import {
  CURRENT_REPO_SOURCE,
} from "./archive-stale-sessions.ts";
import {
  extractIssueNumberFromBranch,
  handleFatalError,
  parseCliArgs,
  parseRepoFromSource,
  submitPrsForAwaitingSessions,
  SUBMIT_PR_PROMPT,
  AWAITING_FEEDBACK_LABEL,
  type GitHubClient,
} from "./fleet-submit-prs.ts";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeSession(
  overrides: Partial<SessionResource & { workingBranch?: string }> = {}
): SessionResource {
  const { workingBranch, ...sessionOverrides } = overrides;
  const now = new Date().toISOString();
  return {
    name: "sessions/abc123",
    id: "abc123",
    title: "Test session",
    prompt: "Do something",
    state: "inProgress",
    url: "https://jules.google.com/sessions/abc123",
    createTime: now,
    updateTime: now,
    sourceContext: {
      source: CURRENT_REPO_SOURCE,
      ...(workingBranch ? { workingBranch } : {}),
    },
    ...sessionOverrides,
  } as unknown as SessionResource;
}

async function* asyncFrom<T>(items: T[]): AsyncIterable<T> {
  for (const item of items) {
    yield item;
  }
}

interface MockSendRecord {
  sessionId: string;
  prompt: string;
}

interface MockLabelRecord {
  owner: string;
  repo: string;
  issue_number: number;
  labels: string[];
}

function makeMockClient(
  sessions: SessionResource[],
  sendFn?: (sessionId: string, prompt: string) => Promise<void>
): JulesClient {
  const defaultSend = async (_id: string, _prompt: string) => {};
  const actualSend = sendFn ?? defaultSend;
  return {
    sessions: (_options?: unknown) => ({
      [Symbol.asyncIterator]: () =>
        asyncFrom(sessions)[Symbol.asyncIterator](),
      then: (onfulfilled: any) =>
        Promise.resolve({ sessions, nextPageToken: undefined }).then(
          onfulfilled
        ),
      all: async () => sessions,
    } as any),
    session: (idOrConfig: any) => {
      const id =
        typeof idOrConfig === "string" ? idOrConfig : (idOrConfig?.id ?? "");
      return {
        send: (prompt: string) => actualSend(id, prompt),
        archive: async () => {},
      } as any;
    },
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

function makeMockGitHubClient(
  labelRecords: MockLabelRecord[]
): GitHubClient {
  return {
    addLabels: async (params) => {
      labelRecords.push(params);
    },
  };
}

function makeQuotaSaturationFailure(operation: string): MutationFailureError {
  const envelope: SanitizedErrorEnvelope = {
    contract: MUTATION_EXECUTION_CONTRACT,
    operation,
    attempt: 1,
    max_attempts: 1,
    classification: "quota_saturation",
    retryable: false,
    retrying: false,
    retry_delay_ms: null,
    status_code: 400,
    error_code: "FAILED_PRECONDITION",
    message: "FAILED_PRECONDITION",
    hint: "Jules per-account session quota saturated.",
    root_cause_path: ["Re-run after quota resets."],
  };
  return new MutationFailureError(operation, [envelope]);
}

/** Captures console output and intercepts process.exit for fatal-handler tests. */
function withFatalCapture(run: () => void): { output: string } {
  const messages: string[] = [];
  const originalError = console.error;
  const originalLog = console.log;
  const originalExit = process.exit;

  console.error = (...args: unknown[]) => {
    messages.push(args.map(String).join(" "));
  };
  console.log = (...args: unknown[]) => {
    messages.push(args.map(String).join(" "));
  };
  process.exit = ((code?: number) => {
    throw new Error(`EXIT_${code ?? 0}`);
  }) as typeof process.exit;

  try {
    run();
  } finally {
    console.error = originalError;
    console.log = originalLog;
    process.exit = originalExit;
  }

  return { output: messages.join("\n") };
}

// ---------------------------------------------------------------------------
// parseCliArgs tests
// ---------------------------------------------------------------------------

describe("parseCliArgs", () => {
  test("defaults to non-dry-run", () => {
    const args = parseCliArgs([]);
    expect(args.dryRun).toBe(false);
  });

  test("--dry-run sets dryRun=true", () => {
    const args = parseCliArgs(["--dry-run"]);
    expect(args.dryRun).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// extractIssueNumberFromBranch tests
// ---------------------------------------------------------------------------

describe("extractIssueNumberFromBranch", () => {
  test("returns null for undefined", () => {
    expect(extractIssueNumberFromBranch(undefined)).toBeNull();
  });

  test("returns null for empty string", () => {
    expect(extractIssueNumberFromBranch("")).toBeNull();
  });

  test("returns null for branch without issue pattern", () => {
    expect(extractIssueNumberFromBranch("main")).toBeNull();
    expect(extractIssueNumberFromBranch("feature/my-feature")).toBeNull();
  });

  test("extracts issue number from jules-123-description", () => {
    expect(extractIssueNumberFromBranch("jules-123-description")).toBe(123);
  });

  test("extracts issue number from jules/issue-456-description", () => {
    expect(extractIssueNumberFromBranch("jules/issue-456-description")).toBe(
      456
    );
  });

  test("extracts issue number from issue-789-description", () => {
    expect(extractIssueNumberFromBranch("issue-789-description")).toBe(789);
  });
});

// ---------------------------------------------------------------------------
// parseRepoFromSource tests
// ---------------------------------------------------------------------------

describe("parseRepoFromSource", () => {
  test("parses owner/repo from source identifier", () => {
    const result = parseRepoFromSource(CURRENT_REPO_SOURCE);
    expect(result).toEqual({ owner: "wryenmeek", repo: "knowledgebase" });
  });

  test("returns null for unrecognized format", () => {
    expect(parseRepoFromSource("not-a-source-id")).toBeNull();
    expect(parseRepoFromSource("")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// submitPrsForAwaitingSessions — core behavior tests
// ---------------------------------------------------------------------------

describe("submitPrsForAwaitingSessions", () => {
  test("empty session list → no send() calls, no errors, exit-0-safe result", async () => {
    const sendRecords: MockSendRecord[] = [];
    const client = makeMockClient([], async (id, prompt) => {
      sendRecords.push({ sessionId: id, prompt });
    });
    const labelRecords: MockLabelRecord[] = [];
    const ghClient = makeMockGitHubClient(labelRecords);

    const result = await submitPrsForAwaitingSessions(client, ghClient, {
      dryRun: false,
    });

    expect(sendRecords).toHaveLength(0);
    expect(labelRecords).toHaveLength(0);
    expect(result.sessionsFound).toBe(0);
    expect(result.sessionsProcessed).toHaveLength(0);
    expect(result.errors).toHaveLength(0);
  });

  test("session with non-matching source is skipped", async () => {
    const sendRecords: MockSendRecord[] = [];
    const client = makeMockClient(
      [
        makeSession({
          id: "other-repo",
          state: "awaitingUserFeedback",
          sourceContext: {
            source: "sources/github/other/repo",
          },
        }),
      ],
      async (id, prompt) => {
        sendRecords.push({ sessionId: id, prompt });
      }
    );
    const labelRecords: MockLabelRecord[] = [];
    const ghClient = makeMockGitHubClient(labelRecords);

    const result = await submitPrsForAwaitingSessions(client, ghClient, {
      dryRun: false,
    });

    expect(sendRecords).toHaveLength(0);
    expect(result.sessionsFound).toBe(0);
  });

  test("session with matching source but non-awaiting state is skipped", async () => {
    const sendRecords: MockSendRecord[] = [];
    const client = makeMockClient(
      [makeSession({ id: "in-progress", state: "inProgress" })],
      async (id, prompt) => {
        sendRecords.push({ sessionId: id, prompt });
      }
    );
    const labelRecords: MockLabelRecord[] = [];
    const ghClient = makeMockGitHubClient(labelRecords);

    const result = await submitPrsForAwaitingSessions(client, ghClient, {
      dryRun: false,
    });

    expect(sendRecords).toHaveLength(0);
    expect(result.sessionsFound).toBe(0);
  });

  test("matching session → exactly one send() with canonical prompt + one addLabels()", async () => {
    const sendRecords: MockSendRecord[] = [];
    const client = makeMockClient(
      [
        makeSession({
          id: "session-awaiting",
          state: "awaitingUserFeedback",
          workingBranch: "jules-348-port-submit-prs",
        }),
      ],
      async (id, prompt) => {
        sendRecords.push({ sessionId: id, prompt });
      }
    );
    const labelRecords: MockLabelRecord[] = [];
    const ghClient = makeMockGitHubClient(labelRecords);

    const result = await submitPrsForAwaitingSessions(client, ghClient, {
      dryRun: false,
    });

    expect(sendRecords).toHaveLength(1);
    expect(sendRecords[0]!.sessionId).toBe("session-awaiting");
    expect(sendRecords[0]!.prompt).toBe(SUBMIT_PR_PROMPT);

    expect(labelRecords).toHaveLength(1);
    expect(labelRecords[0]!.issue_number).toBe(348);
    expect(labelRecords[0]!.labels).toEqual([AWAITING_FEEDBACK_LABEL]);
    expect(labelRecords[0]!.owner).toBe("wryenmeek");
    expect(labelRecords[0]!.repo).toBe("knowledgebase");

    expect(result.sessionsFound).toBe(1);
    expect(result.sessionsProcessed[0]!.promptSent).toBe(true);
    expect(result.sessionsProcessed[0]!.labelApplied).toBe(true);
    expect(result.errors).toHaveLength(0);
  });

  test("matching session without workingBranch → send() called, addLabels skipped", async () => {
    const sendRecords: MockSendRecord[] = [];
    const client = makeMockClient(
      [makeSession({ id: "no-branch", state: "awaitingUserFeedback" })],
      async (id, prompt) => {
        sendRecords.push({ sessionId: id, prompt });
      }
    );
    const labelRecords: MockLabelRecord[] = [];
    const ghClient = makeMockGitHubClient(labelRecords);

    const result = await submitPrsForAwaitingSessions(client, ghClient, {
      dryRun: false,
    });

    expect(sendRecords).toHaveLength(1);
    expect(sendRecords[0]!.prompt).toBe(SUBMIT_PR_PROMPT);
    // No label applied — can't extract issue number
    expect(labelRecords).toHaveLength(0);
    expect(result.sessionsProcessed[0]!.promptSent).toBe(true);
    expect(result.sessionsProcessed[0]!.labelApplied).toBe(false);
  });

  test("--dry-run → zero send(), zero addLabels(), stdout contains prompt", async () => {
    const sendRecords: MockSendRecord[] = [];
    const client = makeMockClient(
      [
        makeSession({
          id: "dry-session",
          state: "awaitingUserFeedback",
          workingBranch: "jules-100-some-task",
        }),
      ],
      async (id, prompt) => {
        sendRecords.push({ sessionId: id, prompt });
      }
    );
    const labelRecords: MockLabelRecord[] = [];
    const ghClient = makeMockGitHubClient(labelRecords);

    // Capture console.log to check dry-run output
    const logged: string[] = [];
    const origLog = console.log;
    console.log = (...args: unknown[]) => {
      logged.push(args.map(String).join(" "));
    };

    try {
      const result = await submitPrsForAwaitingSessions(
        client,
        ghClient,
        { dryRun: true }
      );

      expect(sendRecords).toHaveLength(0);
      expect(labelRecords).toHaveLength(0);

      const combinedOutput = logged.join("\n");
      expect(combinedOutput).toContain(SUBMIT_PR_PROMPT);

      expect(result.dryRun).toBe(true);
      expect(result.sessionsFound).toBe(1);
      // Dry-run: promptSent and labelApplied stay false
      expect(result.sessionsProcessed[0]!.promptSent).toBe(false);
      expect(result.sessionsProcessed[0]!.labelApplied).toBe(false);
    } finally {
      console.log = origLog;
    }
  });
});

// ---------------------------------------------------------------------------
// quota-saturation soft-warn via handleFatalError
// ---------------------------------------------------------------------------

describe("handleFatalError quota-saturation routing", () => {
  test("quota_saturation → ::warning:: annotation + exits 0", () => {
    process.env.JULES_API_KEY ??= "test-jules-api-key";
    const error = makeQuotaSaturationFailure(
      "fleet-submit-prs:jules.session.send:test-session"
    );
    const capture = withFatalCapture(() => {
      expect(() => handleFatalError(error)).toThrow("EXIT_0");
    });

    expect(capture.output).toContain("::warning::");
    expect(capture.output).toContain("quota");
    expect(capture.output).toContain('"classification":"quota_saturation"');
  });
});
