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

import {
  MUTATION_EXECUTION_CONTRACT,
  PreflightFailureError,
} from "./mutation-diagnostics.js";
import {
  matchesRedispatchSession,
  type FleetPullRef,
} from "./session-matching.js";

export interface MergeSessionRef {
  taskId: string;
  sessionId: string;
}

export interface MergePullRef extends FleetPullRef {
  number: number;
}

export type UpdateBranchAction = "ok" | "redispatch" | "abort" | "error";

export function decideUpdateBranchAction(options: {
  updateOk: boolean;
  updateStatus: number;
  retryCount: number;
  maxRetries: number;
}): UpdateBranchAction {
  if (options.updateOk) {
    return "ok";
  }
  if (options.updateStatus !== 422) {
    return "error";
  }
  if (options.retryCount >= options.maxRetries) {
    return "abort";
  }
  return "redispatch";
}

export function updateSessionMapping(
  sessions: MergeSessionRef[],
  taskId: string,
  nextSessionId: string
): boolean {
  const sessionEntry = sessions.find((session) => session.taskId === taskId);
  if (!sessionEntry) {
    return false;
  }
  sessionEntry.sessionId = nextSessionId;
  return true;
}

export function requireRedispatchAuthorLogin(
  pr: Pick<MergePullRef, "number" | "user">,
  taskId: string
): string {
  const login = pr.user?.login;
  if (login) {
    return login;
  }

  throw new PreflightFailureError({
    contract: MUTATION_EXECUTION_CONTRACT,
    operation: `fleet-merge:redispatch:${taskId}`,
    classification: "preflight",
    failures: [
      `Conflicting PR #${pr.number} is missing an author login; cannot safely bind redispatch session.`,
    ],
  });
}

export function findRedispatchPullRequest(
  pulls: MergePullRef[],
  sessionId: string,
  options: {
    expectedRepoFullName: string;
    expectedAuthorLogin: string;
    notBeforeEpochMs: number;
  }
): MergePullRef | undefined {
  return pulls.find((pr) =>
    matchesRedispatchSession(pr, sessionId, {
      expectedRepoFullName: options.expectedRepoFullName,
      expectedAuthorLogin: options.expectedAuthorLogin,
      notBeforeEpochMs: options.notBeforeEpochMs,
    })
  );
}

export type UpdateBranchFailureResolution =
  | {
      action: "redispatch";
      nextPr: MergePullRef;
      nextRetryCount: number;
    }
  | {
      action: "abort";
    }
  | {
      action: "error";
    };

export interface RedispatchResult {
  nextPr: MergePullRef;
  nextSessionId: string;
}

export async function resolveUpdateBranchFailure(options: {
  updateStatus: number;
  retryCount: number;
  maxRetries: number;
  taskId: string;
  sessions: MergeSessionRef[];
  redispatch: () => Promise<RedispatchResult>;
  persistSessions: (sessions: MergeSessionRef[]) => Promise<void>;
}): Promise<UpdateBranchFailureResolution> {
  const action = decideUpdateBranchAction({
    updateOk: false,
    updateStatus: options.updateStatus,
    retryCount: options.retryCount,
    maxRetries: options.maxRetries,
  });

  if (action === "abort") {
    return { action: "abort" };
  }

  if (action !== "redispatch") {
    return { action: "error" };
  }

  const redispatch = await options.redispatch();
  if (updateSessionMapping(options.sessions, options.taskId, redispatch.nextSessionId)) {
    await options.persistSessions(options.sessions);
  }

  return {
    action: "redispatch",
    nextPr: redispatch.nextPr,
    nextRetryCount: options.retryCount + 1,
  };
}
