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
import { Octokit } from "octokit";
import type { IssueAnalysis } from "./types.js";
import { jules } from "@google/jules-sdk";
import { assertFleetEnvironment } from "./env.js";
import { branchExists, getGitRepoInfo, getCurrentBranch } from "./github/git.js";
import {
  assertMutationPreflight,
  getSanitizedErrorMessage,
  MUTATION_EXECUTION_CONTRACT,
  PreflightFailureError,
  resolveMutationMaxAttempts,
  runMutationWithDiagnostics,
} from "./github/mutation-diagnostics.js";
import { validateTaskOwnership } from "./github/task-manifest-validation.js";
import { findFleetRepoRoot, resolveFleetDir } from "./github/fleet-paths.js";
import {
  handleFleetFatalError,
  logMutationAttemptFailure,
} from "./_fleet_output.js";
import { buildPreMergeSanityPromptBlock } from "./preMergeSanityCheck.js";

export const READY_FOR_AGENT_LABEL = "ready-for-agent";
export const IN_PROGRESS_LABEL = "in-progress";
export const AWAITING_FEEDBACK_LABEL = "awaiting-feedback";
export const NEEDS_TRIAGE_LABEL = "needs-triage";
const LOOKBACK_WINDOW_DAYS = 30;
const FAILURE_ABORT_THRESHOLD = 3;

interface IssueEventActor {
  login?: string | null;
  type?: string | null;
}

interface IssueEventLabel {
  name?: string | null;
}

interface IssueEvent {
  event?: string | null;
  created_at?: string | null;
  commit_id?: string | null;
  verified_merged_pr?: boolean;
  actor?: IssueEventActor | null;
  label?: IssueEventLabel | null;
}

interface FleetIssuesClient {
  rest: {
    issues: {
      addLabels(params: {
        owner: string;
        repo: string;
        issue_number: number;
        labels: string[];
      }): Promise<unknown>;
      removeLabel(params: {
        owner: string;
        repo: string;
        issue_number: number;
        name: string;
      }): Promise<unknown>;
      createComment(params: {
        owner: string;
        repo: string;
        issue_number: number;
        body: string;
      }): Promise<unknown>;
      listEvents(params: {
        owner: string;
        repo: string;
        issue_number: number;
        per_page?: number;
      }): Promise<unknown>;
    };
    repos: {
      listPullRequestsAssociatedWithCommit(params: {
        owner: string;
        repo: string;
        commit_sha: string;
        per_page?: number;
      }): Promise<{ data: Array<{ merged_at?: string | null }> }>;
    };
  };
  paginate<T>(fn: unknown, params: Record<string, unknown>): Promise<T[]>;
}

function isHumanActor(actor: IssueEventActor | null | undefined): boolean {
  if (!actor) {
    return false;
  }
  const login = (actor.login ?? "").toLowerCase();
  const type = (actor.type ?? "").toLowerCase();
  if (type === "bot" || login === "github-actions[bot]" || login.endsWith("[bot]")) {
    return false;
  }
  return login.length > 0;
}

export function countRecentInProgressAttempts(
  events: IssueEvent[],
  now: Date = new Date()
): number {
  const cutoffMs = now.getTime() - LOOKBACK_WINDOW_DAYS * 24 * 60 * 60 * 1000;
  const sorted = [...events].sort((a, b) =>
    (a.created_at ?? "").localeCompare(b.created_at ?? "")
  );
  let resetAnchorMs = Number.NEGATIVE_INFINITY;

  for (const event of sorted) {
    const ts = Date.parse(event.created_at ?? "");
    if (
      event.event === "labeled" &&
      event.label?.name === READY_FOR_AGENT_LABEL &&
      isHumanActor(event.actor)
    ) {
      if (Number.isFinite(ts)) {
        resetAnchorMs = ts;
      }
    }
    if (
      event.event === "closed" &&
      event.commit_id &&
      event.verified_merged_pr &&
      Number.isFinite(ts)
    ) {
      resetAnchorMs = ts;
    }
  }

  return sorted.filter((event) => {
    if (event.event !== "labeled" || event.label?.name !== IN_PROGRESS_LABEL) {
      return false;
    }
    const ts = Date.parse(event.created_at ?? "");
    if (!Number.isFinite(ts)) {
      return false;
    }
    return ts >= cutoffMs && ts >= resetAnchorMs;
  }).length;
}

export function selectRecoveryLabelFromEvents(
  events: IssueEvent[],
  now: Date = new Date()
): string {
  return countRecentInProgressAttempts(events, now) >= FAILURE_ABORT_THRESHOLD
    ? NEEDS_TRIAGE_LABEL
    : READY_FOR_AGENT_LABEL;
}

async function loadIssueEventsWithMergeEvidence(
  octokit: FleetIssuesClient,
  owner: string,
  repo: string,
  issueNumber: number
): Promise<IssueEvent[]> {
  const events = await octokit.paginate<IssueEvent>(octokit.rest.issues.listEvents, {
    owner,
    repo,
    issue_number: issueNumber,
    per_page: 100,
  });

  return Promise.all(
    events.map(async (event) => {
      if (event.event !== "closed" || !event.commit_id) {
        return event;
      }
      const associatedPullRequests =
        await octokit.rest.repos.listPullRequestsAssociatedWithCommit({
          owner,
          repo,
          commit_sha: event.commit_id,
          per_page: 100,
        });
      return {
        ...event,
        verified_merged_pr: associatedPullRequests.data.some(
          (pullRequest) =>
            Boolean(
              pullRequest.merged_at &&
                Number.isFinite(Date.parse(pullRequest.merged_at))
            )
        ),
      };
    })
  );
}

export function buildDispatchCommentBody(
  taskTitle: string,
  sessionId: string,
  taskPrompt: string
): string {
  // Wrap taskPrompt in a fenced code block so that any markdown / HTML inside
  // the prompt (e.g., `</details>` closing-tag injection, `@user` mention
  // spam, `[`alt`](url)` link or image rendering) is rendered literally and
  // cannot escape the dispatch envelope. The prompt is LLM-generated from
  // issue-body content that an external contributor could craft, so treat it
  // as untrusted text for rendering purposes. The triple-backtick fence is
  // sufficient because GitHub markdown does not honor inner triple-backticks
  // unless preceded by enough leading backticks; the four-backtick wrapper
  // defends against the rare case where the prompt itself contains ```.
  return (
    "🚀 This issue is being handled by parallel fleet task **" +
    taskTitle +
    "**.\n\nTrack progress in Jules session: [" +
    sessionId +
    "](https://jules.google.com/task/" +
    sessionId +
    ")\n\n<details>\n<summary>Dispatch prompt</summary>\n\n````\n" +
    taskPrompt +
    "\n````\n\n</details>"
  );
}

async function removeLabelIfPresent(
  octokit: FleetIssuesClient,
  owner: string,
  repo: string,
  issueNumber: number,
  label: string
): Promise<void> {
  try {
    await octokit.rest.issues.removeLabel({
      owner,
      repo,
      issue_number: issueNumber,
      name: label,
    });
  } catch (error) {
    const message = getSanitizedErrorMessage(error);
    if (!message.includes("404")) {
      throw error;
    }
  }
}

async function addLabel(
  octokit: FleetIssuesClient,
  owner: string,
  repo: string,
  issueNumber: number,
  label: string
): Promise<void> {
  await octokit.rest.issues.addLabels({
    owner,
    repo,
    issue_number: issueNumber,
    labels: [label],
  });
}

export async function markIssueInProgress(
  octokit: FleetIssuesClient,
  owner: string,
  repo: string,
  issueNumber: number
): Promise<void> {
  await addLabel(octokit, owner, repo, issueNumber, IN_PROGRESS_LABEL);
  await removeLabelIfPresent(octokit, owner, repo, issueNumber, READY_FOR_AGENT_LABEL);
}

export async function restoreIssueAfterFailure(
  octokit: FleetIssuesClient,
  owner: string,
  repo: string,
  issueNumber: number,
  now: Date = new Date()
): Promise<string> {
  const events = await loadIssueEventsWithMergeEvidence(
    octokit,
    owner,
    repo,
    issueNumber
  );
  const nextLabel = selectRecoveryLabelFromEvents(events, now);
  await removeLabelIfPresent(octokit, owner, repo, issueNumber, IN_PROGRESS_LABEL);
  await removeLabelIfPresent(octokit, owner, repo, issueNumber, AWAITING_FEEDBACK_LABEL);
  await removeLabelIfPresent(octokit, owner, repo, issueNumber, READY_FOR_AGENT_LABEL);
  await removeLabelIfPresent(octokit, owner, repo, issueNumber, NEEDS_TRIAGE_LABEL);
  await addLabel(octokit, owner, repo, issueNumber, nextLabel);
  return nextLabel;
}

export async function runWithIssueRecovery<T>(
  octokit: FleetIssuesClient,
  owner: string,
  repo: string,
  issueNumbers: number[],
  operation: () => Promise<T>
): Promise<T> {
  try {
    return await operation();
  } catch (error) {
    for (const issueNumber of issueNumbers) {
      try {
        const restoredLabel = await restoreIssueAfterFailure(
          octokit,
          owner,
          repo,
          issueNumber
        );
        console.error(`  ↩️ Restored issue #${issueNumber} to label "${restoredLabel}".`);
      } catch (restoreError) {
        console.error(
          "  ❌ Failed to restore labels for issue #" +
            issueNumber +
            ": " +
            getSanitizedErrorMessage(restoreError)
        );
      }
    }
    throw error;
  }
}

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
  assertFleetEnvironment({
    requireJulesApiKey: true,
    requireGitHubToken: true,
  });
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

  const octokit = new Octokit({ auth: githubToken }) as unknown as FleetIssuesClient;

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

  const root = findFleetRepoRoot();
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

  const dispatchedSessions = await mapWithConcurrency(tasks, maxParallel, async (task) =>
    runWithIssueRecovery(
      octokit,
      repoInfo.owner,
      repoInfo.repo,
      task.issues,
      async () => {
        // Restore every issue uniformly if any mutation fails; recovery derives
        // each issue's label from fresh event history rather than loop position.
        for (const issueNumber of task.issues) {
          await markIssueInProgress(octokit, repoInfo.owner, repoInfo.repo, issueNumber);
        }

        // Per-task PR scope is intentionally open: the manifest bounds the prompt,
        // but implementation agents may stage any owned source/test path. This
        // sanity block only catches the 0/0/0 staged-diff hallucination signature.
        const prompt = `${task.prompt}

${buildPreMergeSanityPromptBlock([], { allowAdditional: true })}`;

        const session = await runMutationWithDiagnostics({
          operation: `fleet-dispatch:jules.run:${task.id}`,
          maxAttempts: mutationMaxAttempts,
          run: () =>
            jules.run({
              prompt,
              source: {
                github: repoInfo.fullName,
                baseBranch,
              },
            }),
          onAttemptFailure: (envelope) => {
            logMutationAttemptFailure(
              `⚠️ Jules dispatch mutation attempt failed for task "${task.id}".`,
              envelope
            );
          },
        });

        return { task, sessionId: session.id };
      }
    )
  );

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
            body: buildDispatchCommentBody(task.title, sessionId, task.prompt),
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
  return handleFleetFatalError(error, {
    preflight: "❌ Fleet dispatch preflight failed.",
    mutation: "❌ Jules dispatch mutation hard-failed after bounded retries.",
    genericPrefix: "❌ Fleet dispatch failed: ",
  });
}

if (import.meta.main) {
  main().catch(handleFatalError);
}
