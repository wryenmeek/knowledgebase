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

/**
 * jules-account-probe.ts
 *
 * Read-only diagnostic that surfaces source/session/quota state for the
 * operator's Jules account. Use this to diagnose session-cap saturation
 * events without any side effects.
 *
 * Usage:
 *   bun run scripts/fleet/jules-account-probe.ts
 *
 * Output: structured JSON envelope written to stdout.
 */

import { jules } from "@google/jules-sdk";
import type { JulesClient, SessionResource, Source } from "@google/jules-sdk";
import { assertFleetEnvironment } from "./env.js";

// States that count as "active" (consuming quota)
const ACTIVE_STATES = new Set([
  "queued",
  "planning",
  "awaitingPlanApproval",
  "awaitingUserFeedback",
  "inProgress",
  "paused",
]);

export interface ProbeSource {
  name: string;
  id: string;
  type: string;
  githubRepo?: { owner: string; repo: string };
}

export interface SessionAgeEntry {
  sessionId: string;
  ageHuman: string;
  createdAt: string;
}

export interface SourceSessionSummary {
  sourceName: string;
  activeSessionCount: number;
  inProgressSessionCount: number;
  inProgressAges: SessionAgeEntry[];
}

export interface AccountProbeEnvelope {
  probedAt: string;
  sources: ProbeSource[];
  sessionsBySource: SourceSessionSummary[];
  totals: {
    sources: number;
    sessions: number;
    activeSessions: number;
    inProgressSessions: number;
  };
}

function formatAgeDuration(ageMs: number): string {
  const totalSeconds = Math.floor(ageMs / 1000);
  const days = Math.floor(totalSeconds / 86400);
  const hours = Math.floor((totalSeconds % 86400) / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  if (days > 0) {
    return `${days}d ${hours}h`;
  }
  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }
  return `${minutes}m`;
}

export async function runAccountProbe(client: JulesClient): Promise<AccountProbeEnvelope> {
  const probedAt = new Date().toISOString();

  // Collect registered sources (read-only)
  const sources: ProbeSource[] = [];
  for await (const source of client.sources()) {
    const entry: ProbeSource = {
      name: source.name,
      id: source.id,
      type: source.type,
    };
    if (source.type === "githubRepo") {
      entry.githubRepo = {
        owner: source.githubRepo.owner,
        repo: source.githubRepo.repo,
      };
    }
    sources.push(entry);
  }

  // Collect all sessions (read-only); scope to this repo per convention
  const sessions: SessionResource[] = [];
  for await (const session of client.sessions()) {
    sessions.push(session);
  }

  // Aggregate by source
  const now = Date.now();
  const bySource = new Map<
    string,
    { active: number; inProgress: number; inProgressAges: SessionAgeEntry[] }
  >();

  let totalActive = 0;
  let totalInProgress = 0;

  for (const session of sessions) {
    const sourceName = session.sourceContext?.source || "(no source)";
    if (!bySource.has(sourceName)) {
      bySource.set(sourceName, { active: 0, inProgress: 0, inProgressAges: [] });
    }
    const bucket = bySource.get(sourceName)!;

    if (ACTIVE_STATES.has(session.state)) {
      bucket.active++;
      totalActive++;
    }

    if (session.state === "inProgress") {
      bucket.inProgress++;
      totalInProgress++;
      const ageMs = now - new Date(session.createTime).getTime();
      bucket.inProgressAges.push({
        sessionId: session.id,
        ageHuman: formatAgeDuration(ageMs),
        createdAt: session.createTime,
      });
    }
  }

  const sessionsBySource: SourceSessionSummary[] = Array.from(bySource.entries()).map(
    ([sourceName, data]) => ({
      sourceName,
      activeSessionCount: data.active,
      inProgressSessionCount: data.inProgress,
      inProgressAges: data.inProgressAges,
    })
  );

  return {
    probedAt,
    sources,
    sessionsBySource,
    totals: {
      sources: sources.length,
      sessions: sessions.length,
      activeSessions: totalActive,
      inProgressSessions: totalInProgress,
    },
  };
}

async function main(): Promise<void> {
  assertFleetEnvironment({ requireJulesApiKey: true });
  const result = await runAccountProbe(jules);
  console.log(JSON.stringify(result, null, 2));
}

if (import.meta.main) {
  main().catch((error: unknown) => {
    console.error("❌ jules-account-probe failed:", String(error));
    process.exit(1);
  });
}
