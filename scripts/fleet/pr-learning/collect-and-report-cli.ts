#!/usr/bin/env bun
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
 * Read-only CLI entrypoint for the Jules persona PR learning loop's
 * collection + classification + report stage (U2), invoked exclusively by
 * the `collect` job of `.github/workflows/jules-persona-learning.yml`
 * (U6). This script never mutates repository or GitHub state: it only
 * performs GitHub REST reads (`contents: read` is sufficient) and writes a
 * single JSON artifact file to local disk for the workflow to upload.
 *
 * This is the collector half of the two-job trust boundary described in
 * `docs/plans/2026-08-10-001-feat-jules-persona-learning-loop-plan.md`:
 * the emitted artifact is bound to this run's commit/workflow/run-id and
 * carries a short expiry plus a content digest, so the write-capable
 * `propose` job (see `propose-cli.ts`) can validate it was produced by
 * *this* run before acting on it (R11, R13).
 *
 * Never reads PR title/body/comment/review/log text (see `collect.ts`'s
 * module docstring) — only structured fields.
 *
 * Usage: `bun run pr-learning/collect-and-report-cli.ts [output-path]`
 * Required env: `GH_TOKEN`, `GITHUB_REPOSITORY`, `GITHUB_REPOSITORY_OWNER`,
 * `GITHUB_SHA`, `GITHUB_RUN_ID`.
 */

import { appendFileSync } from "node:fs";

import { collectPersonaPullRequests, JULES_AUTHOR_LOGINS, NullSessionVerifier } from "./collect.ts";
import { classifyPullRequests } from "./classify.ts";
import { buildCollectionReport } from "./report.ts";
import type { EvidenceEnvelope, Persona } from "./types.ts";

/** Must match the workflow file name so `propose-cli.ts` can verify producer identity. */
export const PRODUCER_WORKFLOW = "jules-persona-learning.yml";

/** How long a collection artifact remains valid for a same-run `propose` job (R11, R13). */
export const ARTIFACT_TTL_MS = 60 * 60 * 1000; // 1 hour

/** How far back to paginate PR history; bounded so a misconfigured watermark cannot run forever. */
const DEFAULT_LOOKBACK_DAYS = 180;

const PERSONAS: readonly Persona[] = ["bolt", "sentinel"];

function requireEnv(name: string): string {
  const value = process.env[name];
  if (value === undefined || value.length === 0) {
    throw new Error(`missing required environment variable: ${name}`);
  }
  return value;
}

function sha256Hex(input: string): string {
  const hasher = new Bun.CryptoHasher("sha256");
  hasher.update(input);
  return hasher.digest("hex");
}

async function main(): Promise<void> {
  const repoFullName = requireEnv("GITHUB_REPOSITORY");
  const token = requireEnv("GH_TOKEN");
  const collectorCommit = requireEnv("GITHUB_SHA");
  const collectorRunId = requireEnv("GITHUB_RUN_ID");
  const repositoryOwner = requireEnv("GITHUB_REPOSITORY_OWNER");
  const outputPath = process.argv[2] ?? "pr-learning-report.json";

  if (!/^[0-9a-f]{40}$/i.test(collectorCommit)) {
    throw new Error(`GITHUB_SHA must be a 40-character hex commit SHA, got: ${collectorCommit}`);
  }

  const now = new Date();
  const asOf = now.toISOString();
  const lookbackWatermark = new Date(
    now.getTime() - DEFAULT_LOOKBACK_DAYS * 24 * 60 * 60 * 1000
  ).toISOString();

  const apiBase = `https://api.github.com/repos/${repoFullName}`;
  const headers: HeadersInit = {
    Authorization: `Bearer ${token}`,
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "jules-persona-learning-collector",
  };

  // Both historical Jules author-login forms (see fleet-dispatch.yml's
  // identity-check comment): the legacy bot login, and the repository
  // owner (current PAT-based posting model). This is a scope-narrowing
  // list only — `collectPersonaPullRequests` still requires independently
  // verified session linkage before any record can leave `ambiguous`.
  const authorLogins = [...JULES_AUTHOR_LOGINS, repositoryOwner];

  const collectionErrors: string[] = [];
  let complete = true;
  const allEnvelopes: EvidenceEnvelope[] = [];
  const personaCounts: Record<string, number> = {};

  for (const persona of PERSONAS) {
    const result = await collectPersonaPullRequests({
      apiBase,
      headers,
      repoFullName,
      persona,
      authorLogins,
      asOf,
      lookbackWatermark,
      // No session registry is wired up in this environment yet (deferred
      // follow-up work). Every candidate is therefore quarantined
      // `ambiguous` rather than accepted on identity alone — fail-closed
      // per R1/R13, not a bypass.
      sessionVerifier: NullSessionVerifier,
    });
    if (!result.complete) {
      complete = false;
    }
    collectionErrors.push(...result.errors.map((message) => `${persona}: ${message}`));

    const { envelopes, errors: classifyErrors } = classifyPullRequests(result.records, {
      repoFullName,
      persona,
      asOf,
      collectedAt: asOf,
    });
    collectionErrors.push(...classifyErrors.map((message) => `${persona}: ${message}`));
    allEnvelopes.push(...envelopes);
    personaCounts[persona] = envelopes.length;
  }

  const report = buildCollectionReport(allEnvelopes, {
    repo: repoFullName,
    asOf,
    generatedAt: asOf,
    complete,
    collectionErrors,
    // No authoritative Jules session registry is wired up in this
    // environment yet (deferred follow-up work) — every candidate above
    // was collected under NullSessionVerifier and is therefore
    // quarantined `ambiguous` by construction. Recording this explicitly
    // lets `propose-cli.ts` refuse to proceed with a clear, fail-closed
    // error instead of failing deep in eligibility checks (R6).
    sessionVerification: "none",
  });

  const expiresAt = new Date(now.getTime() + ARTIFACT_TTL_MS).toISOString();

  // Fixed key order so this digest is reproducible without a generic
  // canonical-JSON serializer; `report.digest` already summarizes the
  // full envelope set deterministically (see `report.ts`).
  //
  // session_verification is deliberately included here even though it is
  // excluded from `report.digest` itself: `report.digest` covers *evidence
  // content* only, but `artifact_digest` is the tamper-detection boundary
  // that `propose-cli.ts`'s fail-closed session_verification gate relies
  // on. Without binding session_verification into `artifact_digest`, an
  // attacker with artifact write access could flip a `"none"` artifact to
  // `"authoritative"` post-hoc and pass both digest checks unchanged,
  // defeating the fail-closed contract (R1, R6, R13). Both sides of this
  // digest (here and in propose-cli.ts's recomputation) must change
  // together.
  const digestPayload = JSON.stringify({
    report_digest: report.digest,
    session_verification: report.session_verification,
    producer_workflow: PRODUCER_WORKFLOW,
    collector_commit: collectorCommit,
    collector_run_id: collectorRunId,
    base_sha: collectorCommit,
    generated_at: asOf,
    expires_at: expiresAt,
  });
  const artifactDigest = sha256Hex(digestPayload);

  const artifact = {
    producer_workflow: PRODUCER_WORKFLOW,
    collector_commit: collectorCommit,
    collector_run_id: collectorRunId,
    base_sha: collectorCommit,
    generated_at: asOf,
    expires_at: expiresAt,
    artifact_digest: artifactDigest,
    report,
  };

  await Bun.write(outputPath, `${JSON.stringify(artifact, null, 2)}\n`);

  console.log(
    `Collected ${report.total_envelope_count} envelope(s) across ${PERSONAS.length} persona(s); complete=${report.complete}.`
  );
  for (const [persona, count] of Object.entries(personaCounts)) {
    console.log(`  ${persona}: ${count} envelope(s)`);
  }
  if (!report.complete) {
    console.log(
      `::warning::Collection reported incomplete=true (${collectionErrors.length} error(s)); see collection_errors in the artifact. A propose run built on this artifact will refuse to proceed.`
    );
  }

  const githubOutput = process.env.GITHUB_OUTPUT;
  if (githubOutput) {
    appendFileSync(githubOutput, `digest=${artifactDigest}\nexpires_at=${expiresAt}\ncomplete=${report.complete}\n`);
  }
}

if (import.meta.main) {
  main().catch((error) => {
    console.error(`::error::${error instanceof Error ? error.message : String(error)}`);
    process.exit(1);
  });
}
