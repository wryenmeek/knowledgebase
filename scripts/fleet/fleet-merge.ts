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
import type { IssueAnalysis, Task } from "./types.js";
import { branchExists, getCurrentBranch, getGitRepoInfo } from "./github/git.js";
import { jules } from "@google/jules-sdk";
import { assertFleetEnvironment } from "./env.js";
import {
  assertMutationPreflight,
  getSanitizedErrorMessage,
  MUTATION_EXECUTION_CONTRACT,
  PreflightFailureError,
  resolveMutationMaxAttempts,
  runMutationWithDiagnostics,
} from "./github/mutation-diagnostics.js";
import { mapFleetPRs } from "./github/session-matching.js";
import { waitForCI } from "./github/merge-ci.js";
import {
  resolveMaxRedispatchRetries,
  validateMaxRedispatchRetries,
} from "./github/retry-config.js";
import {
  findRedispatchPullRequest,
  requireRedispatchAuthorLogin,
  resolveUpdateBranchFailure,
} from "./github/merge-runtime.js";
import { inspectPullRequestChangedFiles } from "./github/pr-file-sanity.js";
import { findFleetRepoRoot, resolveFleetDir } from "./github/fleet-paths.js";
import {
  handleFleetFatalError,
  logMutationAttemptFailure,
} from "./_fleet_output.js";

interface GitHubPR {
  number: number;
  created_at?: string | null;
  head: {
    ref: string;
    repo: {
      full_name: string | null;
    } | null;
  };
  body: string | null;
  user?: {
    login: string | null;
  } | null;
}

interface FleetMergePreMergeGateOptions {
  apiBase: string;
  headers: Record<string, string>;
  prNumber: number;
  allowNoChecks: boolean;
  inspectChangedFiles?: typeof inspectPullRequestChangedFiles;
  waitForCIImpl?: typeof waitForCI;
  log?: (message: string) => void;
}

export async function runFleetMergePreMergeGate(
  options: FleetMergePreMergeGateOptions
): Promise<boolean> {
  const inspectChangedFiles = options.inspectChangedFiles ?? inspectPullRequestChangedFiles;
  const waitForCIImpl = options.waitForCIImpl ?? waitForCI;
  const fileSanity = await inspectChangedFiles({
    apiBase: options.apiBase,
    headers: options.headers,
    prNumber: options.prNumber,
  });
  if (!fileSanity.ok) {
    throw new Error(fileSanity.message);
  }
  if (fileSanity.file_count <= 0) {
    throw new Error(
      `Fleet pre-merge sanity check failed for PR #${options.prNumber}: 0 changed files reported before CI.`
    );
  }

  const log = options.log ?? console.log;
  log(`  🧪 Waiting for CI on PR #${options.prNumber}...`);
  return waitForCIImpl({
    apiBase: options.apiBase,
    headers: options.headers,
    prNumber: options.prNumber,
    allowNoChecks: options.allowNoChecks,
  });
}

export async function main(): Promise<void> {
  assertFleetEnvironment({
    requireJulesApiKey: true,
    requireGitHubToken: true,
  });
  const repoInfo = await getGitRepoInfo();
  const OWNER = repoInfo.owner;
  const REPO = repoInfo.repo;
  const BASE_BRANCH = process.env.FLEET_BASE_BRANCH ?? (await getCurrentBranch());
  const GITHUB_TOKEN = process.env.GITHUB_TOKEN;

  // Re-dispatch configuration
  const MAX_RETRIES = resolveMaxRedispatchRetries(process.env.FLEET_MAX_RETRIES);
  const ALLOW_NO_CHECKS = process.env.FLEET_ALLOW_NO_CHECKS === "true";
  const PR_POLL_INTERVAL_MS = 30_000;
  const PR_POLL_TIMEOUT_MS = 15 * 60 * 1000;
  const MUTATION_MAX_ATTEMPTS = resolveMutationMaxAttempts(
    process.env.FLEET_MUTATION_MAX_ATTEMPTS
  );

  assertMutationPreflight({
    operation: "fleet-merge:redispatch",
    repoFullName: repoInfo.fullName,
    baseBranch: BASE_BRANCH,
    maxAttempts: MUTATION_MAX_ATTEMPTS,
    requireGitHubToken: true,
  });
  const preflightFailures: string[] = [];
  const retriesFailure = validateMaxRedispatchRetries(MAX_RETRIES);
  if (retriesFailure) {
    preflightFailures.push(retriesFailure);
  }
  if (!(await branchExists(BASE_BRANCH))) {
    preflightFailures.push(`Base branch "${BASE_BRANCH}" is not visible in local or origin refs.`);
  }
  if (preflightFailures.length > 0) {
    throw new PreflightFailureError({
      contract: MUTATION_EXECUTION_CONTRACT,
      operation: "fleet-merge:redispatch",
      classification: "preflight",
      failures: preflightFailures,
    });
  }

  const headers = {
    Authorization: `Bearer ${GITHUB_TOKEN}`,
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
  } as const;

  const API = `https://api.github.com/repos/${OWNER}/${REPO}`;

  const date =
    process.env.FLEET_PENDING_DATE ||
    new Intl.DateTimeFormat("en-CA", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    })
      .format(new Date())
      .replaceAll("-", "_");

  const root = findFleetRepoRoot();
  let fleetDir: string;
  try {
    fleetDir = resolveFleetDir(root, date);
  } catch (error) {
    throw new PreflightFailureError({
      contract: MUTATION_EXECUTION_CONTRACT,
      operation: "fleet-merge:redispatch",
      classification: "preflight",
      failures: [getSanitizedErrorMessage(error)],
    });
  }

  // Load task ordering (already sorted by risk in the analysis phase)
  const analysis = (await Bun.file(path.join(fleetDir, "issue_tasks.json")).json()) as IssueAnalysis;

  // Load session mapping written by fleet-dispatch.ts
  const sessions = (await Bun.file(path.join(fleetDir, "sessions.json")).json()) as Array<{
    taskId: string;
    sessionId: string;
  }>;

  // Find open PRs created by fleet sessions
  async function findFleetPRs() {
    const res = await fetch(`${API}/pulls?state=open&per_page=100`, { headers });
    const pulls = (await res.json()) as GitHubPR[];
    return mapFleetPRs(pulls, sessions, {
      expectedRepoFullName: repoInfo.fullName,
      allowBodyMatch: false,
    });
  }

  // Re-dispatch a task as a new Jules session against current main
  async function redispatchTask(
    task: Task,
    oldPr: GitHubPR
  ): Promise<{
    pr: GitHubPR;
    sessionId: string;
  }> {
    // Close the conflicting PR
    console.log(`  🔒 Closing conflicting PR #${oldPr.number}...`);
    const closeRes = await fetch(`${API}/pulls/${oldPr.number}`, {
      method: "PATCH",
      headers: { ...headers, "Content-Type": "application/json" },
      body: JSON.stringify({
        state: "closed",
        body: `${oldPr.body ?? ""}\n\n---\n⚠️ Closed by fleet-merge: merge conflict detected. Task re-dispatched as a new session.`,
      }),
    });
    if (!closeRes.ok) {
      const body = getSanitizedErrorMessage(await closeRes.text());
      throw new Error(`Failed to close conflicting PR #${oldPr.number} (${closeRes.status}): ${body}`);
    }

    // Create a new Jules session with the same prompt
    console.log(`  🚀 Re-dispatching task "${task.id}" against current ${BASE_BRANCH}...`);
    const redispatchRequestedAt = Date.now();
    const run = await runMutationWithDiagnostics({
      operation: `fleet-merge:jules.run:${task.id}`,
      maxAttempts: MUTATION_MAX_ATTEMPTS,
      run: () =>
        jules.run({
          prompt: task.prompt,
          source: {
            github: `${OWNER}/${REPO}`,
            baseBranch: BASE_BRANCH,
          },
        }),
      onAttemptFailure: (envelope) => {
        logMutationAttemptFailure(
          `⚠️ Jules re-dispatch mutation attempt failed for task "${task.id}".`,
          envelope
        );
      },
    });
    console.log(`  📝 New session: ${run.id}`);

    // Poll for the new PR
    console.log(`  ⏳ Waiting for new PR from session ${run.id}...`);
    const start = Date.now();
    const expectedAuthorLogin = requireRedispatchAuthorLogin(oldPr, task.id);
    while (Date.now() - start < PR_POLL_TIMEOUT_MS) {
      await new Promise((resolve) => setTimeout(resolve, PR_POLL_INTERVAL_MS));
      const res = await fetch(`${API}/pulls?state=open&per_page=100`, { headers });
      const pulls = (await res.json()) as GitHubPR[];
      const newPr = findRedispatchPullRequest(pulls, run.id, {
        expectedRepoFullName: repoInfo.fullName,
        expectedAuthorLogin,
        notBeforeEpochMs: redispatchRequestedAt,
      });
      if (newPr) {
        console.log(`  ✅ New PR #${newPr.number} found (${newPr.head.ref})`);
        return { pr: newPr, sessionId: run.id };
      }
      console.log(`  ⏳ No PR yet... polling again in 30s`);
    }
    throw new Error(`Timed out waiting for new PR from re-dispatched session ${run.id}`);
  }

  // Main: sequential merge in task order
  const prMap = await findFleetPRs();

  console.log(`Found ${prMap.size}/${analysis.tasks.length} fleet PRs`);
  for (const [taskId, pr] of prMap) {
    console.log(`  ${taskId} → PR #${pr.number} (${pr.head.ref})`);
  }

  if (prMap.size !== analysis.tasks.length) {
    console.error(
      `❌ Expected ${analysis.tasks.length} PRs but found ${prMap.size}. Waiting for all PRs before merging.`
    );
    process.exit(1);
  }

  for (const task of analysis.tasks) {
    let pr = prMap.get(task.id);
    if (!pr) {
      console.error(`❌ No PR found for task "${task.id}". Aborting.`);
      process.exit(1);
    }

    let retryCount = 0;
    let merged = false;

    while (!merged) {
      console.log(
        `\n📦 Processing Task "${task.id}" → PR #${pr.number}${retryCount > 0 ? ` (retry ${retryCount})` : ""}`
      );

      // Update branch from base before merging (skip for first PR on first attempt)
      if (analysis.tasks.indexOf(task) > 0 || retryCount > 0) {
        console.log(`  🔄 Updating PR #${pr.number} branch from ${BASE_BRANCH}...`);
        const updateRes = await fetch(`${API}/pulls/${pr.number}/update-branch`, {
          method: "PUT",
          headers: { ...headers, "Content-Type": "application/json" },
        });
        if (!updateRes.ok) {
          const body = getSanitizedErrorMessage(await updateRes.text());
          const resolution = await resolveUpdateBranchFailure({
            updateStatus: updateRes.status,
            retryCount,
            maxRetries: MAX_RETRIES,
            taskId: task.id,
            sessions,
            redispatch: async () => {
              const redispatch = await redispatchTask(task, pr);
              return {
                nextPr: redispatch.pr,
                nextSessionId: redispatch.sessionId,
              };
            },
            persistSessions: async (nextSessions) => {
              const sessionsPath = path.join(fleetDir, "sessions.json");
              await Bun.write(sessionsPath, JSON.stringify(nextSessions, null, 2));
            },
          });
          if (resolution.action === "abort") {
            console.error(
              `  ❌ Conflict persists after ${MAX_RETRIES} retries. Human intervention required.`
            );
            console.error(`  PR: https://github.com/${OWNER}/${REPO}/pull/${pr.number}`);
            process.exit(1);
          }
          if (resolution.action === "redispatch") {
            console.log(`  ⚠️ Merge conflict detected. Re-dispatching task "${task.id}"...`);
            pr = resolution.nextPr;
            retryCount = resolution.nextRetryCount;
            continue;
          }
          throw new Error(`Update branch failed (${updateRes.status}): ${body}`);
        }
        // Wait for the update to propagate
        await new Promise((resolve) => setTimeout(resolve, 5_000));
      }

      let ciPassed = false;
      try {
        ciPassed = await runFleetMergePreMergeGate({
          apiBase: API,
          headers,
          prNumber: pr.number,
          allowNoChecks: ALLOW_NO_CHECKS,
        });
      } catch (error) {
        console.error(`  ❌ ${getSanitizedErrorMessage(error)}`);
        process.exit(1);
      }

      if (!ciPassed) {
        console.error(`  ❌ CI failed for PR #${pr.number}. Aborting sequential merge.`);
        process.exit(1);
      }

      // Merge
      console.log(`  ✅ CI passed. Merging PR #${pr.number}...`);
      const mergeRes = await fetch(`${API}/pulls/${pr.number}/merge`, {
        method: "PUT",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({ merge_method: "squash" }),
      });
      if (!mergeRes.ok) {
        const body = getSanitizedErrorMessage(await mergeRes.text());
        console.error(`  ❌ Failed to merge PR #${pr.number}: ${body}`);
        process.exit(1);
      }
      console.log(`  🎉 PR #${pr.number} merged successfully.`);
      merged = true;
    }
  }

  console.log(`\n✅ All ${analysis.tasks.length} PRs merged sequentially. No conflicts.`);
}

export function handleFatalError(error: unknown): never {
  return handleFleetFatalError(error, {
    preflight: "❌ Fleet merge preflight failed.",
    mutation: "❌ Jules merge re-dispatch hard-failed after bounded retries.",
    genericPrefix: "❌ Fleet merge failed: ",
  });
}

if (import.meta.main) {
  main().catch(handleFatalError);
}
