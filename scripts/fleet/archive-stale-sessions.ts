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
 * archive-stale-sessions.ts
 *
 * Bulk-archive stale Jules sessions with safety defaults:
 *   - Dry-run by default; pass --apply to actually archive.
 *   - --older-than-days N is required (no default) to avoid mass-archive.
 *   - --state inProgress is the default state filter.
 *   - Source scope is REQUIRED when --apply is used (deny-by-default):
 *       --repo current          shorthand for sources/github/wryenmeek/knowledgebase
 *       --repo all              account-wide (explicit opt-in for cross-repo operations)
 *       --source-filter <id>    explicit source ID
 *     Omitting a source scope with --apply exits with a non-zero status.
 *     Dry-run without a source scope is allowed for read-only inspection.
 *
 * Usage:
 *   bun run scripts/fleet/archive-stale-sessions.ts \
 *     --older-than-days 7 --repo current [--state inProgress] [--apply]
 *
 *   bun run scripts/fleet/archive-stale-sessions.ts \
 *     --older-than-days 7 --source-filter sources/github/owner/repo [--apply]
 *
 * Output: structured JSON envelope written to stdout.
 *
 * NOTE: Jules has no "cancel" endpoint. Use archive to remove zombie sessions
 * from the active session list. Archived sessions are still accessible by ID.
 */

import { jules } from "@google/jules-sdk";
import type { JulesClient, SessionResource, SessionState } from "@google/jules-sdk";
import fs from "node:fs";
import path from "node:path";
import { Octokit } from "octokit";
import { assertFleetEnvironment } from "./env.js";
import { restoreIssueAfterFailure } from "./fleet-dispatch.js";

/** Canonical source identifier for this repository. */
export const CURRENT_REPO_SOURCE = "sources/github/wryenmeek/knowledgebase";

export interface ArchiveCliArgs {
  /** Session state to filter on. Default: "inProgress". */
  state: SessionState;
  /** Only archive sessions older than this many days. Required. */
  olderThanDays: number;
  /** Source filter (e.g. "sources/github/owner/repo"). Undefined means no source filter. */
  sourceFilter: string | undefined;
  /**
   * When true, the operator explicitly opted in to account-wide archive via
   * `--repo all`. Required alongside `apply` if `sourceFilter` is undefined.
   */
  repoAll: boolean;
  /** If false (default), dry-run only — no actual archive calls. */
  apply: boolean;
}

export interface ArchivedSessionEntry {
  sessionId: string;
  sourceName: string;
  state: string;
  createdAt: string;
  ageHuman: string;
}

export interface ArchiveEnvelope {
  ranAt: string;
  dryRun: boolean;
  filters: {
    state: string;
    olderThanDays: number;
    sourceFilter: string | undefined;
    repoAll: boolean;
  };
  candidates: ArchivedSessionEntry[];
  archived: ArchivedSessionEntry[];
  archivedCount: number;
  errors: Array<{ sessionId: string; error: string }>;
  /**
   * Per-session warnings for non-fatal pre-flight skip conditions (e.g.,
   * current-repo session whose `sessionId → issue` join cannot be resolved
   * because `.fleet/<date>/sessions.json` was never persisted to `main` for
   * that dispatch date). The session is skipped from archive instead of
   * mass-aborting the batch. See ADR-033 (label-driven dispatch adoption).
   */
  skipped: Array<{ sessionId: string; reason: string }>;
}

export interface SessionIssueResolver {
  resolveIssuesForSession(sessionId: string): number[] | null;
}

export interface ArchiveApplyHooks {
  issueResolver?: SessionIssueResolver;
  restoreIssueLabels?: (issueNumber: number) => Promise<void>;
}

export function buildSessionIssueIndexFromFleet(fleetRoot: string): Map<string, number[]> {
  const index = new Map<string, number[]>();
  if (!fs.existsSync(fleetRoot)) {
    return index;
  }

  const dateDirs = fs
    .readdirSync(fleetRoot, { withFileTypes: true })
    .filter((entry) => entry.isDirectory());

  for (const dateDir of dateDirs) {
    const sessionsPath = path.join(fleetRoot, dateDir.name, "sessions.json");
    const tasksPath = path.join(fleetRoot, dateDir.name, "issue_tasks.json");
    if (!fs.existsSync(sessionsPath) || !fs.existsSync(tasksPath)) {
      continue;
    }

    const sessions = JSON.parse(fs.readFileSync(sessionsPath, "utf8")) as Array<{
      taskId?: unknown;
      sessionId?: unknown;
    }>;
    const tasksPayload = JSON.parse(fs.readFileSync(tasksPath, "utf8")) as {
      tasks?: Array<{ id?: unknown; issues?: unknown }>;
    };
    const taskIssueMap = new Map<string, number[]>();
    for (const task of tasksPayload.tasks ?? []) {
      if (!Array.isArray(task.issues) || typeof task.id !== "string") {
        continue;
      }
      const issueNumbers = task.issues.filter(
        (value): value is number => typeof value === "number" && Number.isInteger(value)
      );
      taskIssueMap.set(task.id, issueNumbers);
    }

    for (const session of sessions) {
      if (typeof session.taskId !== "string" || typeof session.sessionId !== "string") {
        continue;
      }
      const issues = taskIssueMap.get(session.taskId);
      if (issues && issues.length > 0) {
        index.set(session.sessionId, issues);
      }
    }
  }

  return index;
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

export function parseCliArgs(argv: string[]): ArchiveCliArgs {
  let state: SessionState = "inProgress";
  let olderThanDays: number | undefined;
  let sourceFilter: string | undefined;
  let repoAll = false;
  let apply = false;

  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === "--state" && argv[i + 1]) {
      state = argv[++i] as SessionState;
    } else if (arg === "--older-than-days" && argv[i + 1]) {
      const parsed = Number(argv[++i]);
      if (!Number.isInteger(parsed) || parsed < 1) {
        throw new Error(
          `--older-than-days must be a positive integer; got: "${argv[i]}"`
        );
      }
      olderThanDays = parsed;
    } else if (arg === "--source-filter") {
      const value = argv[++i];
      if (value === undefined || value.trim().length === 0) {
        throw new Error("--source-filter requires a non-empty value");
      }
      // Trim to defend against accidental copy-paste whitespace
      sourceFilter = value.trim();
    } else if (arg === "--repo" && argv[i + 1]) {
      const repoVal = argv[++i];
      if (repoVal === "current") {
        sourceFilter = CURRENT_REPO_SOURCE;
      } else if (repoVal === "all") {
        repoAll = true;
      } else {
        throw new Error(
          `--repo must be "current" or "all"; got: "${repoVal}"`
        );
      }
    } else if (arg === "--apply") {
      apply = true;
    }
  }

  if (olderThanDays === undefined) {
    throw new Error(
      "--older-than-days is required. Specify the minimum age in days to avoid mass-archive."
    );
  }

  if (apply && sourceFilter === undefined && !repoAll) {
    throw new Error(
      "--apply requires an explicit source scope to prevent accidental account-wide archive. " +
        "Use --repo current (this repo), --source-filter <source-id>, or --repo all (account-wide)."
    );
  }

  return { state, olderThanDays, sourceFilter, repoAll, apply };
}

export async function archiveStaleSessions(
  client: JulesClient,
  args: ArchiveCliArgs,
  hooks: ArchiveApplyHooks = {}
): Promise<ArchiveEnvelope> {
  const ranAt = new Date().toISOString();
  const now = Date.now();
  const cutoffMs = args.olderThanDays * 24 * 60 * 60 * 1000;

  const candidates: ArchivedSessionEntry[] = [];

  for await (const session of client.sessions()) {
    if (session.state !== args.state) {
      continue;
    }

    // Apply optional source filter
    if (args.sourceFilter !== undefined) {
      const sessionSource = session.sourceContext?.source ?? "";
      if (sessionSource !== args.sourceFilter) {
        continue;
      }
    }

    // Apply age filter
    const ageMs = now - new Date(session.createTime).getTime();
    if (ageMs < cutoffMs) {
      continue;
    }

    candidates.push({
      sessionId: session.id,
      sourceName: session.sourceContext?.source ?? "(no source)",
      state: session.state,
      createdAt: session.createTime,
      ageHuman: formatAgeDuration(ageMs),
    });
  }

  const archived: ArchivedSessionEntry[] = [];
  const errors: Array<{ sessionId: string; error: string }> = [];
  const skipped: Array<{ sessionId: string; reason: string }> = [];

  if (args.apply) {
    // PRE-FLIGHT: Resolve issue joins for all current-repo candidates BEFORE
    // any archive() mutation runs. ADR-033 requires that archived current-repo
    // sessions restore their linked issues' labels — but the join lookup
    // depends on `.fleet/<date>/sessions.json` being available locally, which
    // depends on prior dispatch runs having persisted it. When the index is
    // sparse (a known structural gap pre-Tier-3), skip the affected session
    // with a recorded warning instead of mid-batch throwing. This preserves
    // partial progress and surfaces the gap in the envelope for operator
    // follow-up.
    type ApplyCandidate = ArchivedSessionEntry & {
      linkedIssues: number[];
    };
    const applyCandidates: ApplyCandidate[] = [];
    for (const candidate of candidates) {
      let linkedIssues: number[] = [];
      if (candidate.sourceName === CURRENT_REPO_SOURCE && hooks.issueResolver) {
        const resolved = hooks.issueResolver.resolveIssuesForSession(candidate.sessionId);
        if (resolved === null || resolved.length === 0) {
          skipped.push({
            sessionId: candidate.sessionId,
            reason:
              `No issue mapping found for current-repo session ${candidate.sessionId}. ` +
              "This typically means the dispatch-date `.fleet/<date>/sessions.json` is " +
              "not available locally (it is not persisted to `main` post-dispatch — see " +
              "issue #305 follow-up). Session skipped to avoid label-state drift.",
          });
          continue;
        }
        linkedIssues = resolved;
      }
      applyCandidates.push({ ...candidate, linkedIssues });
    }

    for (const candidate of applyCandidates) {
      try {
        await client.session(candidate.sessionId).archive();
        for (const issueNumber of candidate.linkedIssues) {
          if (hooks.restoreIssueLabels) {
            await hooks.restoreIssueLabels(issueNumber);
          }
        }
        // Strip the internal linkedIssues field from the public envelope shape.
        const { linkedIssues: _linked, ...publicEntry } = candidate;
        archived.push(publicEntry);
      } catch (err) {
        errors.push({
          sessionId: candidate.sessionId,
          error: String(err),
        });
      }
    }
  }

  return {
    ranAt,
    dryRun: !args.apply,
    filters: {
      state: args.state,
      olderThanDays: args.olderThanDays,
      sourceFilter: args.sourceFilter,
      repoAll: args.repoAll,
    },
    candidates,
    archived,
    archivedCount: archived.length,
    errors,
    skipped,
  };
}

async function main(): Promise<void> {
  let args: ArchiveCliArgs;
  try {
    args = parseCliArgs(process.argv.slice(2));
  } catch (err) {
    console.error("❌ archive-stale-sessions: argument error:", String(err));
    process.exit(1);
  }
  assertFleetEnvironment({
    requireJulesApiKey: true,
    requireGitHubToken: args.apply,
  });

  if (!args.apply) {
    console.error(
      "ℹ️  Dry-run mode (default). Pass --apply to actually archive sessions."
    );
  }

  const repoRoot = path.resolve(import.meta.dir, "..", "..");
  const issueIndex = buildSessionIssueIndexFromFleet(path.join(repoRoot, ".fleet"));
  const [, , owner, repo] = CURRENT_REPO_SOURCE.split("/");
  const octokit = process.env.GITHUB_TOKEN
    ? (new Octokit({ auth: process.env.GITHUB_TOKEN }) as never)
    : null;

  const result = await archiveStaleSessions(jules, args, {
    issueResolver: {
      resolveIssuesForSession(sessionId) {
        return issueIndex.get(sessionId) ?? null;
      },
    },
    restoreIssueLabels: async (issueNumber) => {
      if (!octokit) {
        throw new Error("GITHUB_TOKEN is required for issue label restoration.");
      }
      await restoreIssueAfterFailure(
        octokit,
        owner ?? "wryenmeek",
        repo ?? "knowledgebase",
        issueNumber
      );
    },
  });
  console.log(JSON.stringify(result, null, 2));

  if (!args.apply && result.candidates.length > 0) {
    console.error(
      `ℹ️  ${result.candidates.length} session(s) would be archived. Re-run with --apply to proceed.`
    );
  }
}

if (import.meta.main) {
  main().catch((error: unknown) => {
    console.error("❌ archive-stale-sessions failed:", String(error));
    process.exit(1);
  });
}
