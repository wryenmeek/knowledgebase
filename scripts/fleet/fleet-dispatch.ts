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

import path from "node:path";
import { findUpSync } from "find-up";
import { Octokit } from "octokit";
import type { IssueAnalysis } from "./types.js";
import { jules } from "@google/jules-sdk";
import "./env.js";
import { branchExists, getGitRepoInfo, getCurrentBranch } from "./github/git.js";
import {
  assertMutationPreflight,
  getSanitizedErrorMessage,
  MUTATION_EXECUTION_CONTRACT,
  MutationFailureError,
  PreflightFailureError,
  resolveMutationMaxAttempts,
  runMutationWithDiagnostics,
} from "./github/mutation-diagnostics.js";
import { validateTaskOwnership } from "./github/task-manifest-validation.js";
import { resolveFleetDir } from "./github/fleet-paths.js";

async function mapWithConcurrency<T, R>(
  items: T[],
  maxParallel: number,
  mapper: (item: T) => Promise<R>
): Promise<R[]> {
  if (!Number.isInteger(maxParallel) || maxParallel < 1) {
    throw new Error(`FLEET_MAX_PARALLEL must be an integer >= 1; received "${String(maxParallel)}".`);
  }

  if (items.length === 0) {
    return [];
  }

  const results = new Array<R>(items.length);
  let nextIndex = 0;
  const workers = Array.from({ length: Math.min(maxParallel, items.length) }, async () => {
    while (true) {
      const currentIndex = nextIndex++;
      if (currentIndex >= items.length) {
        return;
      }
      results[currentIndex] = await mapper(items[currentIndex]!);
    }
  });

  await Promise.all(workers);
  return results;
}

export async function main(): Promise<void> {
  const repoInfo = await getGitRepoInfo();
  const baseBranch = process.env.FLEET_BASE_BRANCH ?? (await getCurrentBranch());
  const mutationMaxAttempts = resolveMutationMaxAttempts(
    process.env.FLEET_MUTATION_MAX_ATTEMPTS
  );
  const githubToken = process.env.GITHUB_TOKEN;

  assertMutationPreflight({
    operation: "fleet-dispatch:jules.run",
    repoFullName: repoInfo.fullName,
    baseBranch,
    maxAttempts: mutationMaxAttempts,
    requireGitHubToken: true,
  });
  if (!(await branchExists(baseBranch))) {
    throw new PreflightFailureError({
      contract: MUTATION_EXECUTION_CONTRACT,
      operation: "fleet-dispatch:jules.run",
      classification: "preflight",
      failures: [
        `Base branch "${baseBranch}" is not visible in local or origin refs.`,
      ],
    });
  }

  const octokit = new Octokit({ auth: githubToken });

  // SECURITY: read date from env var only — argv exposure eliminated so a crafted
  // value cannot be injected via shell word-splitting if this script ever shells out.
  const date =
    process.env.FLEET_PENDING_DATE ||
    new Intl.DateTimeFormat("en-CA", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    })
      .format(new Date())
      .replaceAll("-", "_");

  const root = path.dirname(findUpSync(".git", { type: "directory" })!);
  let fleetDir: string;
  try {
    fleetDir = resolveFleetDir(root, date);
  } catch (error) {
    throw new PreflightFailureError({
      contract: MUTATION_EXECUTION_CONTRACT,
      operation: "fleet-dispatch:jules.run",
      classification: "preflight",
      failures: [getSanitizedErrorMessage(error)],
    });
  }
  const tasksPath = path.join(fleetDir, "issue_tasks.json");

  if (!(await Bun.file(tasksPath).exists())) {
    console.error("❌ Manifest not found: " + tasksPath);
    process.exit(1);
  }

  const analysis = (await Bun.file(tasksPath).json()) as IssueAnalysis;
  const { tasks } = analysis;
  const maxParallel = process.env.FLEET_MAX_PARALLEL
    ? Number(process.env.FLEET_MAX_PARALLEL)
    : Math.max(tasks.length, 1);

  validateTaskOwnership(analysis);
  console.log("✅ Ownership validated: " + analysis.tasks.length + " tasks, no conflicts.");

  console.log(
    "🚀 Dispatching " +
      tasks.length +
      " parallel Jules sessions for " +
      date +
      ` (max parallel: ${maxParallel})...`
  );

  const dispatchedSessions = await mapWithConcurrency(tasks, maxParallel, async (task) => {
      const session = await runMutationWithDiagnostics({
        operation: `fleet-dispatch:jules.run:${task.id}`,
        maxAttempts: mutationMaxAttempts,
        run: () =>
          jules.run({
            prompt: task.prompt,
            source: {
              github: repoInfo.fullName,
              baseBranch,
            },
          }),
        onAttemptFailure: (envelope) => {
          console.error(`⚠️ Jules dispatch mutation attempt failed for task "${task.id}".`);
          console.error(JSON.stringify(envelope));
        },
      });

      return { task, sessionId: session.id };
    });

  const sessionResults: Array<{ taskId: string; sessionId: string }> = [];

  for (const { task, sessionId } of dispatchedSessions) {
    sessionResults.push({ taskId: task.id, sessionId });
    console.log("Task " + task.id + " → Session " + sessionId);

    // Update associated GitHub issues
    if (task.issues.length > 0) {
      console.log("  💬 Updating " + task.issues.length + " issue(s) for task " + task.id + "...");
      for (const issueNumber of task.issues) {
        try {
          await octokit.rest.issues.createComment({
            owner: repoInfo.owner,
            repo: repoInfo.repo,
            issue_number: issueNumber,
            body:
              "🚀 This issue is being handled by parallel fleet task **" +
              task.title +
              "**.\n\nTrack progress in Jules session: [" +
              sessionId +
              "](https://jules.google.com/task/" +
              sessionId +
              ")",
          });
        } catch (error) {
          console.error(
            "  ❌ Failed to update issue #" + issueNumber + ": " + getSanitizedErrorMessage(error)
          );
        }
      }
    }
  }

  // Write session mapping for fleet-merge.ts
  const sessionsPath = path.join(fleetDir, "sessions.json");
  await Bun.write(sessionsPath, JSON.stringify(sessionResults, null, 2));
  console.log("📝 Session mapping written to " + sessionsPath);
}

export function handleFatalError(error: unknown): never {
  if (error instanceof PreflightFailureError) {
    console.error("❌ Fleet dispatch preflight failed.");
    console.error(JSON.stringify(error.envelope));
    process.exit(1);
  }

  if (error instanceof MutationFailureError) {
    console.error("❌ Jules dispatch mutation hard-failed after bounded retries.");
    console.error(JSON.stringify(error.terminalEnvelope));
    process.exit(1);
  }

  console.error(`❌ Fleet dispatch failed: ${getSanitizedErrorMessage(error)}`);
  process.exit(1);
}

if (import.meta.main) {
  main().catch(handleFatalError);
}
