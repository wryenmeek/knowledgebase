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

import fs from "node:fs";
import { jules } from "@google/jules-sdk";
import { analyzeIssuesPrompt, getFleetDate } from "./prompts/analyze-issues.js";
import { getIssuesAsMarkdown } from "./github/markdown.js";
import { branchExists, getGitRepoInfo, getCurrentBranch } from "./github/git.js";
import { assertFleetEnvironment } from "./env.js";
import {
  assertMutationPreflight,
  MUTATION_EXECUTION_CONTRACT,
  PreflightFailureError,
  resolveMutationMaxAttempts,
  runMutationWithDiagnostics,
} from "./github/mutation-diagnostics.js";
import {
  handleFleetFatalError,
  logMutationAttemptFailure,
} from "./_fleet_output.js";
import { buildPreMergeSanityPromptBlock } from "./preMergeSanityCheck.js";

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

  assertMutationPreflight({
    operation: "fleet-plan:jules.run",
    repoFullName: repoInfo.fullName,
    baseBranch,
    maxAttempts: mutationMaxAttempts,
    requireGitHubToken: true,
  });
  if (!(await branchExists(baseBranch))) {
    throw new PreflightFailureError({
      contract: MUTATION_EXECUTION_CONTRACT,
      operation: "fleet-plan:jules.run",
      classification: "preflight",
      failures: [
        `Base branch "${baseBranch}" is not visible in local or origin refs.`,
      ],
    });
  }

  const issuesMarkdown = await getIssuesAsMarkdown();
  // Capture the fleet date at planning time so fleet-dispatch reads the same
  // dated directory even if Jules takes more than a day to post its PR.
  const fleetDate = getFleetDate();
  const expectedPlanningArtifactPaths = [
    `.fleet/${fleetDate}/issue_tasks.md`,
    `.fleet/${fleetDate}/issue_tasks.json`,
  ];
  const prompt = `${analyzeIssuesPrompt({
    issuesMarkdown,
    repoFullName: repoInfo.fullName,
  })}

${buildPreMergeSanityPromptBlock(expectedPlanningArtifactPaths)}`;

  console.log(
    `🔍 Planning fleet for ${repoInfo.fullName} (branch: ${baseBranch}, date: ${fleetDate})`
  );

  // jules.run() auto-approves the plan and auto-creates a PR (autoPr defaults to true).
  // jules.session() would pause waiting for manual plan approval — wrong for CI.
  const run = await runMutationWithDiagnostics({
    operation: "fleet-plan:jules.run",
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
      logMutationAttemptFailure("⚠️ Jules planning mutation attempt failed.", envelope);
    },
  });

  console.log(`✅ Planning run started: ${run.id}`);

  // Export session ID and fleet date for the downstream Store step.
  if (process.env.GITHUB_OUTPUT) {
    fs.appendFileSync(process.env.GITHUB_OUTPUT, `plan_session_id=${run.id}\n`);
    fs.appendFileSync(process.env.GITHUB_OUTPUT, `fleet_date=${fleetDate}\n`);
  }
}

export function handleFatalError(error: unknown): never {
  return handleFleetFatalError(error, {
    preflight: "❌ Fleet planning preflight failed.",
    mutation: "❌ Jules planning mutation hard-failed after bounded retries.",
    genericPrefix: "❌ Fleet planning failed: ",
  });
}

if (import.meta.main) {
  main().catch(handleFatalError);
}
