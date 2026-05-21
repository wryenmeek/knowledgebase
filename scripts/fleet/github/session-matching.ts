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

export interface SessionRef {
  taskId: string;
  sessionId: string;
}

export interface FleetPullRef {
  number: number;
  head: {
    ref: string;
    repo?: {
      full_name: string | null;
    } | null;
  };
  body: string | null;
  user?: {
    login: string | null;
  } | null;
  created_at?: string | null;
}

export interface SessionMatchOptions {
  expectedRepoFullName: string;
  allowBodyMatch?: boolean;
}

export interface RedispatchMatchOptions {
  expectedRepoFullName: string;
  expectedAuthorLogin: string;
  notBeforeEpochMs: number;
}

function escapeRegex(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function includesSessionId(text: string | null | undefined, sessionId: string): boolean {
  if (!text) {
    return false;
  }
  const escaped = escapeRegex(sessionId);
  const pattern = new RegExp(`(^|[^A-Za-z0-9_-])${escaped}($|[^A-Za-z0-9_-])`);
  return pattern.test(text);
}

export function collectMatchedSessions(
  pr: FleetPullRef,
  sessions: SessionRef[],
  options: SessionMatchOptions
): SessionRef[] {
  const pullRepo = pr.head.repo?.full_name;
  if (pullRepo !== options.expectedRepoFullName) {
    return [];
  }

  return sessions.filter(
    (session) =>
      includesSessionId(pr.head.ref, session.sessionId) ||
      (options.allowBodyMatch === true && includesSessionId(pr.body, session.sessionId))
  );
}

export function mapFleetPRs(
  pulls: FleetPullRef[],
  sessions: SessionRef[],
  options: SessionMatchOptions
): Map<string, FleetPullRef> {
  const prMap = new Map<string, FleetPullRef>();
  for (const pr of pulls) {
    const matchedSessions = collectMatchedSessions(pr, sessions, options);
    if (matchedSessions.length === 1) {
      const taskId = matchedSessions[0]!.taskId;
      const existing = prMap.get(taskId);
      if (existing) {
        throw new Error(
          `Ambiguous mapping for task "${taskId}": PR #${existing.number} and PR #${pr.number} both match.`
        );
      }
      prMap.set(taskId, pr);
    }
  }
  return prMap;
}

export function matchesSession(
  pr: FleetPullRef,
  sessionId: string,
  options: SessionMatchOptions
): boolean {
  return collectMatchedSessions(pr, [{ taskId: "task", sessionId }], options).length === 1;
}

export function matchesRedispatchSession(
  pr: FleetPullRef,
  sessionId: string,
  options: RedispatchMatchOptions
): boolean {
  if (
    !matchesSession(pr, sessionId, {
      expectedRepoFullName: options.expectedRepoFullName,
      allowBodyMatch: false,
    })
  ) {
    return false;
  }
  if (pr.user?.login !== options.expectedAuthorLogin) {
    return false;
  }
  if (!Number.isFinite(options.notBeforeEpochMs)) {
    return false;
  }
  const createdAt = Date.parse(pr.created_at ?? "");
  const notBeforeFloorMs = Math.floor(options.notBeforeEpochMs / 1000) * 1000;
  if (!Number.isFinite(createdAt) || createdAt < notBeforeFloorMs) {
    return false;
  }
  return true;
}
