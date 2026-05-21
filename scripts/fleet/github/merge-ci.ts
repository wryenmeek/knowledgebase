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

import { evaluateCheckRuns, type CheckRunStatus } from "./ci-checks.js";

interface FetchResponseLike {
  json(): Promise<unknown>;
}

type FetchLike = (url: string, init?: { headers?: HeadersInit }) => Promise<FetchResponseLike>;

interface CheckRunsPage {
  check_runs: CheckRunStatus[];
}

interface PullHeadResponse {
  head: {
    sha: string;
  };
}

async function fetchAllCheckRuns(options: {
  apiBase: string;
  headSha: string;
  headers: HeadersInit;
  fetchImpl: FetchLike;
}): Promise<CheckRunStatus[]> {
  const allRuns: CheckRunStatus[] = [];
  let page = 1;

  while (true) {
    const response = await options.fetchImpl(
      `${options.apiBase}/commits/${options.headSha}/check-runs?per_page=100&page=${page}`,
      { headers: options.headers }
    );
    const data = (await response.json()) as CheckRunsPage;
    allRuns.push(...data.check_runs);
    if (data.check_runs.length < 100) {
      break;
    }
    page += 1;
  }

  return allRuns;
}

export async function waitForCI(options: {
  apiBase: string;
  headers: HeadersInit;
  prNumber: number;
  allowNoChecks: boolean;
  maxWaitMs?: number;
  pollIntervalMs?: number;
  fetchImpl?: FetchLike;
  sleep?: (ms: number) => Promise<void>;
  now?: () => number;
  log?: (message: string) => void;
}): Promise<boolean> {
  const fetchImpl = options.fetchImpl ?? (fetch as FetchLike);
  const sleep =
    options.sleep ??
    ((ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms)));
  const now = options.now ?? Date.now;
  const log = options.log ?? console.log;
  const maxWaitMs = options.maxWaitMs ?? 10 * 60 * 1000;
  const pollIntervalMs = options.pollIntervalMs ?? 30_000;

  const start = now();
  const prResponse = await fetchImpl(`${options.apiBase}/pulls/${options.prNumber}`, {
    headers: options.headers,
  });
  const prData = (await prResponse.json()) as PullHeadResponse;
  const headSha = prData.head.sha;

  while (now() - start < maxWaitMs) {
    const checkRuns = await fetchAllCheckRuns({
      apiBase: options.apiBase,
      headSha,
      headers: options.headers,
      fetchImpl,
    });
    const evaluation = evaluateCheckRuns(checkRuns, {
      allowNoChecks: options.allowNoChecks,
    });

    if (checkRuns.length === 0 && !options.allowNoChecks) {
      log(
        `  ❌ No check runs found for PR #${options.prNumber}. Failing closed (set FLEET_ALLOW_NO_CHECKS=true to override).`
      );
    }
    if (checkRuns.length === 0 && options.allowNoChecks) {
      log(`  ℹ️  No check runs found for PR #${options.prNumber}. Override enabled; proceeding.`);
    }

    if (evaluation === "pass") {
      return true;
    }
    if (evaluation === "fail") {
      return false;
    }

    log(`  ⏳ CI still running for PR #${options.prNumber}... waiting 30s`);
    await sleep(pollIntervalMs);
  }

  log(`  ⏰ CI timeout for PR #${options.prNumber}`);
  return false;
}

