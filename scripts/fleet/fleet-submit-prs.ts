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
 * fleet-submit-prs.ts
 *
 * Sweeps all Jules sessions in `awaitingUserFeedback` state for this repository
 * and sends the canonical "Please submit your changes as a Pull Request now."
 * prompt to each one. Also applies the `awaiting-feedback` GitHub label to any
 * linked issue found via the session's working branch name.
 *
 * Usage:
 *   bun run scripts/fleet/fleet-submit-prs.ts [--dry-run]
 *
 * Options:
 *   --dry-run   Print what would be sent without making any API calls.
 *
 * Output: structured JSON envelope written to stdout.
 */

import { jules } from "@google/jules-sdk";
import type { JulesClient, SessionResource } from "@google/jules-sdk";
import { Octokit } from "octokit";
import { CURRENT_REPO_SOURCE } from "./archive-stale-sessions.js";
import {
  DEFAULT_MUTATION_MAX_ATTEMPTS,
  resolveMutationMaxAttempts,
  runMutationWithDiagnostics,
} from "./github/mutation-diagnostics.js";
import { assertFleetEnvironment } from "./env.js";
import {
  handleFleetFatalError,
  logMutationAttemptFailure,
} from "./_fleet_output.js";

/** Canonical prompt sent to each session in awaitingUserFeedback state. */
export const SUBMIT_PR_PROMPT =
  "Please submit your changes as a Pull Request now.";

/** GitHub label applied to the linked issue when a session is observed awaiting feedback. */
export const AWAITING_FEEDBACK_LABEL = "awaiting-feedback";

/** Minimal GitHub client interface for label operations (injectable for testing). */
export interface GitHubClient {
  addLabels(params: {
    owner: string;
    repo: string;
    issue_number: number;
    labels: string[];
  }): Promise<void>;
}

export interface SubmitPrsCliArgs {
  /** When true, prints planned actions without performing any API calls. */
  dryRun: boolean;
}

export interface SubmittedSessionEntry {
  sessionId: string;
  sourceName: string;
  state: string;
  linkedIssueNumber: number | null;
  promptSent: boolean;
  labelApplied: boolean;
}

export interface SubmitPrsEnvelope {
  ranAt: string;
  dryRun: boolean;
  sessionsFound: number;
  sessionsProcessed: SubmittedSessionEntry[];
  errors: Array<{ sessionId: string; error: string }>;
}

export function parseCliArgs(argv: string[]): SubmitPrsCliArgs {
  let dryRun = false;
  for (const arg of argv) {
    if (arg === "--dry-run") dryRun = true;
  }
  return { dryRun };
}

/**
 * Extracts a GitHub issue number from a Jules working branch name.
 *
 * Matches common branch naming patterns:
 *   jules-123-description
 *   jules/issue-123-description
 *   issue-123-description
 *   issue/123
 */
export function extractIssueNumberFromBranch(
  branch: string | undefined
): number | null {
  if (!branch) return null;
  const match = branch.match(/(?:issue[s]?[/-]|jules[/-])(\d+)/i);
  if (match?.[1]) {
    return parseInt(match[1], 10);
  }
  return null;
}

/**
 * Parses "owner" and "repo" from a source identifier such as
 * "sources/github/wryenmeek/knowledgebase".
 */
export function parseRepoFromSource(
  source: string
): { owner: string; repo: string } | null {
  const match = source.match(/^sources\/github\/([^/]+)\/([^/]+)$/);
  if (!match) return null;
  return { owner: match[1]!, repo: match[2]! };
}

/**
 * Core logic: iterates sessions, filters to this repo + awaitingUserFeedback,
 * and for each: sends the canonical PR prompt + applies the awaiting-feedback label.
 *
 * @param julesClient  Injected Jules client (real or mock).
 * @param githubClient Injected GitHub client for label ops (null skips label apply).
 * @param args         Parsed CLI arguments.
 * @param maxAttempts  Max attempts for runMutationWithDiagnostics (default: 3).
 */
export async function submitPrsForAwaitingSessions(
  julesClient: JulesClient,
  githubClient: GitHubClient | null,
  args: SubmitPrsCliArgs,
  maxAttempts: number = DEFAULT_MUTATION_MAX_ATTEMPTS
): Promise<SubmitPrsEnvelope> {
  const ranAt = new Date().toISOString();
  const repoInfo = parseRepoFromSource(CURRENT_REPO_SOURCE);

  const processed: SubmittedSessionEntry[] = [];
  const errors: Array<{ sessionId: string; error: string }> = [];
  let sessionsFound = 0;

  for await (const session of julesClient.sessions()) {
    // Filter: must belong to this repository.
    const sessionSource = session.sourceContext?.source ?? "";
    if (sessionSource !== CURRENT_REPO_SOURCE) continue;

    // Filter: must be awaiting user feedback.
    if (session.state !== "awaitingUserFeedback") continue;

    sessionsFound++;

    const linkedIssueNumber = extractIssueNumberFromBranch(
      session.sourceContext?.workingBranch
    );

    const entry: SubmittedSessionEntry = {
      sessionId: session.id,
      sourceName: sessionSource,
      state: session.state,
      linkedIssueNumber,
      promptSent: false,
      labelApplied: false,
    };

    if (args.dryRun) {
      console.log(
        `[dry-run] Would send to session ${session.id}: "${SUBMIT_PR_PROMPT}"`
      );
      if (linkedIssueNumber !== null) {
        console.log(
          `[dry-run] Would apply label "${AWAITING_FEEDBACK_LABEL}" to issue #${linkedIssueNumber}`
        );
      }
      processed.push(entry);
      continue;
    }

    // Send the PR-submission prompt, wrapped in mutation diagnostics for
    // quota-saturation soft-warn behavior (ADR-032).
    try {
      await runMutationWithDiagnostics({
        operation: `fleet-submit-prs:jules.session.send:${session.id}`,
        maxAttempts,
        run: () => julesClient.session(session.id).send(SUBMIT_PR_PROMPT),
        onAttemptFailure: (envelope) => {
          logMutationAttemptFailure(
            `⚠️ Mutation attempt failed for session "${session.id}".`,
            envelope
          );
        },
      });
      entry.promptSent = true;
      console.log(`✅ Sent PR prompt to session ${session.id}`);
    } catch (err) {
      errors.push({ sessionId: session.id, error: String(err) });
      processed.push(entry);
      continue;
    }

    // Apply the awaiting-feedback label to the linked issue, if determinable.
    if (linkedIssueNumber !== null && githubClient !== null && repoInfo !== null) {
      try {
        await githubClient.addLabels({
          owner: repoInfo.owner,
          repo: repoInfo.repo,
          issue_number: linkedIssueNumber,
          labels: [AWAITING_FEEDBACK_LABEL],
        });
        entry.labelApplied = true;
        console.log(
          `🏷️  Applied label "${AWAITING_FEEDBACK_LABEL}" to issue #${linkedIssueNumber}`
        );
      } catch (err) {
        console.error(
          `⚠️ Failed to apply label to issue #${linkedIssueNumber}: ${String(err)}`
        );
      }
    }

    processed.push(entry);
  }

  return {
    ranAt,
    dryRun: args.dryRun,
    sessionsFound,
    sessionsProcessed: processed,
    errors,
  };
}

async function main(): Promise<void> {
  assertFleetEnvironment({ requireJulesApiKey: true });

  const args = parseCliArgs(process.argv.slice(2));

  if (args.dryRun) {
    console.error(
      "ℹ️  Dry-run mode. Pass no flags to send real PR prompts."
    );
  }

  const mutationMaxAttempts = resolveMutationMaxAttempts(
    process.env.FLEET_MUTATION_MAX_ATTEMPTS
  );

  const octokit = new Octokit({ auth: process.env.GITHUB_TOKEN });
  const githubClient: GitHubClient = {
    addLabels: async (params) => {
      await octokit.rest.issues.addLabels(params);
    },
  };

  const result = await submitPrsForAwaitingSessions(
    jules,
    args.dryRun ? null : githubClient,
    args,
    mutationMaxAttempts
  );

  console.log(JSON.stringify(result, null, 2));

  if (result.errors.length > 0) {
    process.exit(1);
  }
}

export function handleFatalError(error: unknown): never {
  return handleFleetFatalError(error, {
    preflight: "❌ fleet-submit-prs: preflight check failed.",
    mutation: "❌ fleet-submit-prs: mutation failed after all retries.",
    genericPrefix: "❌ fleet-submit-prs failed: ",
  });
}

if (import.meta.main) {
  main().catch(handleFatalError);
}
