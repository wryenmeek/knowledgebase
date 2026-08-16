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
 * Narrowly write-capable CLI entrypoint for the Jules persona PR learning
 * loop's governed proposal-creation stage (U5), invoked exclusively by the
 * `propose` job of `.github/workflows/jules-persona-learning.yml` (U6).
 *
 * Because fully-automated semantic clustering/rule generation is out of
 * scope for the MVP (see the plan's "Deferred to Follow-Up Work" —
 * automated LLM classification is explicitly deferred), this script does
 * **not** invent a candidate on its own. A human operator reviews the
 * `collect` job's report artifact, chooses specific supporting PR numbers
 * and a bounded rule/evidence/verification/scope/retraction description,
 * and supplies them as `workflow_dispatch` inputs. This script:
 *
 *   1. Validates the collector artifact's bindings (producer workflow,
 *      commit, run id, expiry, digest) against the *current* run — never
 *      trusting a stale or foreign artifact (R11, R13).
 *   2. Re-collects and re-classifies only the operator-referenced PRs for
 *      the chosen persona (reusing the same trusted `collect.ts` /
 *      `classify.ts` logic as the read-only collector) and checks that
 *      they actually satisfy R6 eligibility (one verified merge, or two
 *      distinct known-cause closures) — never trusting operator-asserted
 *      eligibility.
 *   3. Computes the candidate fingerprint from the operator-supplied
 *      mechanism/scope/rule fields (never accepts a pre-computed
 *      fingerprint from the caller).
 *   4. Runs deduplication against live memory content and open/closed
 *      proposal PR markers (R8).
 *   5. Builds and validates a bounded `MemoryEntry` from the
 *      operator-supplied text (R9), then delegates the one governed
 *      mutation — branch + commit + PR creation — to
 *      `createMemoryProposal` (`propose.ts`, U5).
 *
 * Never calls a merge, auto-merge, issue, label, workflow, or
 * session-mutation API — the `ProposeGitHubClient` surface implemented
 * below has no such methods.
 */

import { determineEligibility } from "./cluster.ts";
import { classifyPullRequests } from "./classify.ts";
import {
  collectPersonaPullRequests,
  JULES_AUTHOR_LOGINS,
  type JulesSessionVerifier,
} from "./collect.ts";
import {
  deduplicateCandidate,
  type ProposalMarkerLike,
} from "./deduplicate.ts";
import { computeCandidateFingerprintAtCurrentVersion } from "./fingerprints.ts";
import { validateMemoryEntry } from "./memory-validator.ts";
import {
  authenticateProposalMarker,
  createMemoryProposal,
  parseProposalMarker,
  type ContentsFileResult,
  type CreatePullRequestParams,
  type GitCommitResult,
  type GitRefResult,
  type ProposalPullRequestSummary,
  type ProposeGitHubClient,
} from "./propose.ts";

// Re-exported for backward compatibility: `authenticateProposalMarker` now
// lives in `propose.ts` (so `findMatchingProposalPullRequest` can use it
// without an import cycle back into this CLI module), but existing
// consumers/tests import it from here too.
export { authenticateProposalMarker };
import { PRODUCER_WORKFLOW } from "./collect-and-report-cli.ts";
import { computeCollectionReportDigest } from "./report.ts";
import {
  TAXONOMY_VERSION,
  memoryPathForPersona,
  type Candidate,
  type EvidenceEnvelope,
  type MemoryEntry,
  type Persona,
  type ProposalMarker,
} from "./types.ts";
import type { GitHubTreeEntry, GitTreeEntryMode } from "./proposal-validator.ts";

/** Same short artifact validity window as the collector — see `collect-and-report-cli.ts`. */
const MAX_EVIDENCE_PR_COUNT = 10;
const MAX_PROPOSAL_LIST_PAGES = 50;

/**
 * An `Error` carrying the origin HTTP status code as a first-class,
 * numeric `status` property. `classifyMutationError`
 * (`../github/mutation-diagnostics.ts`) reads `error.status` (among other
 * shapes) to classify retryability; a plain `Error` whose status is only
 * embedded in the message string is invisible to that classifier and
 * always falls through to the non-retryable `"unknown"` category, even
 * for a transient 502/429/503 that should be retried.
 */
class HttpStatusError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "HttpStatusError";
    this.status = status;
  }
}

/** Builds an `HttpStatusError` for a failed REST call, preserving `response.status` for retry classification. */
function httpError(context: string, response: Response): HttpStatusError {
  return new HttpStatusError(`${context} failed: ${response.status}`, response.status);
}

function requireEnv(name: string): string {
  const value = process.env[name];
  if (value === undefined || value.length === 0) {
    throw new Error(`missing required environment variable: ${name}`);
  }
  return value;
}

function decodeBase64(content: string): string {
  return Buffer.from(content.replace(/\n/g, ""), "base64").toString("utf-8");
}

function encodeBase64(content: string): string {
  return Buffer.from(content, "utf-8").toString("base64");
}

interface ArtifactBindings {
  producer_workflow: string;
  collector_commit: string;
  collector_run_id: string;
  base_sha: string;
  generated_at: string;
  expires_at: string;
  artifact_digest: string;
  report: {
    schema_version: number;
    repo: string;
    as_of: string;
    complete: boolean;
    digest: string;
    envelopes: EvidenceEnvelope[];
    session_verification?: "authoritative" | "none";
  };
}

/**
 * Validates that the downloaded collector artifact was produced by *this*
 * workflow run, on *this* commit, has not expired, and its recomputed
 * digest matches — never proceeding on a stale, foreign, or tampered
 * artifact (R11, R13).
 */
export function validateArtifactBindings(
  artifact: ArtifactBindings,
  currentSha: string,
  currentRunId: string
): void {
  if (artifact.producer_workflow !== PRODUCER_WORKFLOW) {
    throw new Error(
      `artifact producer_workflow mismatch: expected "${PRODUCER_WORKFLOW}", got "${artifact.producer_workflow}"`
    );
  }
  if (artifact.collector_commit !== currentSha) {
    throw new Error(
      `artifact collector_commit mismatch: expected "${currentSha}", got "${artifact.collector_commit}"`
    );
  }
  if (artifact.collector_run_id !== currentRunId) {
    throw new Error(
      `artifact collector_run_id mismatch: expected "${currentRunId}", got "${artifact.collector_run_id}"`
    );
  }
  if (artifact.base_sha !== currentSha) {
    throw new Error(`artifact base_sha mismatch: expected "${currentSha}", got "${artifact.base_sha}"`);
  }
  const expiresAtMs = Date.parse(artifact.expires_at);
  if (!Number.isFinite(expiresAtMs) || Date.now() > expiresAtMs) {
    throw new Error(`artifact has expired (expires_at=${artifact.expires_at}); re-run the collector`);
  }
  if (!artifact.report.complete) {
    throw new Error("collector report is incomplete (complete=false); refusing to propose from partial evidence");
  }
  if (
    artifact.report.schema_version === undefined ||
    artifact.report.repo === undefined ||
    artifact.report.as_of === undefined
  ) {
    throw new Error(
      "collector artifact is missing report.schema_version, report.repo, or report.as_of; " +
        "regenerate the artifact with the current collector"
    );
  }
  const recomputedReportDigest = computeCollectionReportDigest(
    artifact.report.schema_version,
    artifact.report.repo,
    artifact.report.as_of,
    artifact.report.envelopes
  );
  if (recomputedReportDigest !== artifact.report.digest) {
    throw new Error("report.digest does not match the validated evidence envelopes; refusing malformed evidence");
  }
  // Fail-closed collector/proposer contract boundary (R1, R6, R13): if the
  // collector artifact was produced with no authoritative Jules session
  // verifier wired up (`"none"`, or absent on an older artifact schema),
  // every candidate's `session_id` is quarantined `ambiguous` by
  // construction and can never satisfy R6 eligibility. Refuse explicitly
  // here — before re-collection and eligibility re-derivation even run —
  // rather than allowing the caller to hit a misleading "does not satisfy
  // R6 eligibility" error deep in the propose flow.
  if (artifact.report.session_verification !== "authoritative") {
    throw new Error(
      "propose mode is unavailable: the collector artifact was produced with no authoritative Jules " +
        'session verifier wired up (session_verification is "' +
        (artifact.report.session_verification ?? "none") +
        '", not "authoritative"). Every candidate is quarantined ambiguous under NullSessionVerifier and ' +
        "cannot satisfy R6 eligibility; wire an authoritative JulesSessionVerifier into the collector before " +
        "using propose mode."
    );
  }

  const digestPayload = JSON.stringify({
    report_digest: artifact.report.digest,
    // Bound into artifact_digest (not just checked above) so that an
    // artifact whose session_verification was flipped post-hoc — e.g. by
    // an actor with artifact write access mutating "none" to
    // "authoritative" after collection — fails the digest recomputation
    // below rather than sailing through on the mutated value alone. The
    // check above and this binding are complementary, not redundant: the
    // check above gives a clear "propose unavailable" error on an honest
    // "none" artifact; this binding is the tamper-detection boundary for
    // a dishonest one. Both sides of this digest (here and in
    // collect-and-report-cli.ts's computation) must change together.
    session_verification: artifact.report.session_verification ?? "none",
    producer_workflow: artifact.producer_workflow,
    collector_commit: artifact.collector_commit,
    collector_run_id: artifact.collector_run_id,
    base_sha: artifact.base_sha,
    generated_at: artifact.generated_at,
    expires_at: artifact.expires_at,
  });
  const hasher = new Bun.CryptoHasher("sha256");
  hasher.update(digestPayload);
  const recomputed = hasher.digest("hex");
  if (recomputed !== artifact.artifact_digest) {
    throw new Error("artifact_digest does not match recomputed digest; refusing a tampered or malformed artifact");
  }
}

export function sessionVerifierFromArtifact(
  envelopes: readonly EvidenceEnvelope[]
): JulesSessionVerifier {
  return {
    verify(candidate) {
      const match = envelopes.find(
        (envelope) =>
          envelope.repo === candidate.repoFullName &&
          envelope.pr_number === candidate.prNumber &&
          envelope.evaluated_head_sha === candidate.headSha &&
          envelope.head_repo_full_name === candidate.headRepoFullName &&
          envelope.persona === candidate.persona &&
          envelope.session_id !== null
      );
      return match?.session_id ? { sessionId: match.session_id, persona: match.persona } : null;
    },
  };
}

/** Minimal fetch-based GitHub REST client implementing `ProposeGitHubClient` (U5/U6). */
export class RestProposeGitHubClient implements ProposeGitHubClient {
  constructor(
    private readonly apiBase: string,
    private readonly headers: Record<string, string>
  ) {}

  private async request(path: string, init?: RequestInit): Promise<Response> {
    // Every mutation call in this client passes a JSON string as `body`
    // (see createBlob/createTree/createCommit/createRef/createPullRequest
    // below); GitHub's REST API requires an explicit `Content-Type:
    // application/json` header for those requests. Add it whenever a
    // body is present, but never override a caller-supplied header.
    const headers: Record<string, string> = { ...this.headers };
    if (init?.body !== undefined) {
      headers["Content-Type"] = "application/json";
    }
    // Normalize HeadersInit (which may be a Headers instance, a
    // [string, string][] array, or a plain object) into a plain object
    // before merging. `Object.assign` on a `Headers` instance copies
    // nothing — `Headers` has no own enumerable properties, its entries
    // live in an internal slot — which would silently drop every
    // caller-supplied header if one were ever passed that way.
    if (init?.headers !== undefined) {
      Object.assign(headers, Object.fromEntries(new Headers(init.headers).entries()));
    }
    return fetch(`${this.apiBase}${path}`, {
      ...init,
      headers,
    });
  }

  async getRef(ref: string): Promise<GitRefResult | null> {
    const response = await this.request(`/git/ref/${ref}`);
    if (response.status === 404) return null;
    if (!response.ok) throw httpError(`getRef(${ref})`, response);
    const body = (await response.json()) as { object: { sha: string } };
    return { sha: body.object.sha };
  }

  async getCommit(sha: string): Promise<GitCommitResult | null> {
    const response = await this.request(`/git/commits/${sha}`);
    if (response.status === 404) return null;
    if (!response.ok) throw httpError(`getCommit(${sha})`, response);
    const body = (await response.json()) as { sha: string; tree: { sha: string } };
    return { sha: body.sha, treeSha: body.tree.sha };
  }

  async getFileContent(path: string, ref: string): Promise<ContentsFileResult | null> {
    const response = await this.request(`/contents/${path}?ref=${encodeURIComponent(ref)}`);
    if (response.status === 404) return null;
    if (!response.ok) throw httpError(`getFileContent(${path}@${ref})`, response);
    const body = (await response.json()) as { content: string; sha: string };
    return { content: decodeBase64(body.content), sha: body.sha };
  }

  async getTreeEntries(treeSha: string): Promise<readonly GitHubTreeEntry[]> {
    const response = await this.request(`/git/trees/${treeSha}?recursive=1`);
    if (!response.ok) throw httpError(`getTreeEntries(${treeSha})`, response);
    const body = (await response.json()) as {
      truncated: boolean;
      tree: Array<{ path: string; mode: GitTreeEntryMode; type: "blob" | "tree" | "commit"; sha: string }>;
    };
    if (body.truncated) {
      // A truncated recursive tree cannot be proven to contain (or omit)
      // the target path; failing closed here is safer than silently
      // trusting an incomplete listing for a mode/symlink safety check.
      throw new Error(`getTreeEntries(${treeSha}) result was truncated by the GitHub API; failing closed`);
    }
    return body.tree.map((entry) => ({ path: entry.path, mode: entry.mode, type: entry.type, sha: entry.sha }));
  }

  async createBlob(content: string): Promise<string> {
    const response = await this.request(`/git/blobs`, {
      method: "POST",
      body: JSON.stringify({ content: encodeBase64(content), encoding: "base64" }),
    });
    if (!response.ok) throw httpError("createBlob", response);
    const body = (await response.json()) as { sha: string };
    return body.sha;
  }

  async createTree(baseTreeSha: string, path: string, blobSha: string): Promise<string> {
    const response = await this.request(`/git/trees`, {
      method: "POST",
      body: JSON.stringify({
        base_tree: baseTreeSha,
        tree: [{ path, mode: "100644", type: "blob", sha: blobSha }],
      }),
    });
    if (!response.ok) throw httpError("createTree", response);
    const body = (await response.json()) as { sha: string };
    return body.sha;
  }

  async createCommit(message: string, treeSha: string, parentSha: string): Promise<string> {
    const response = await this.request(`/git/commits`, {
      method: "POST",
      body: JSON.stringify({ message, tree: treeSha, parents: [parentSha] }),
    });
    if (!response.ok) throw httpError("createCommit", response);
    const body = (await response.json()) as { sha: string };
    return body.sha;
  }

  async createRef(branchName: string, sha: string): Promise<void> {
    const response = await this.request(`/git/refs`, {
      method: "POST",
      body: JSON.stringify({ ref: `refs/heads/${branchName}`, sha }),
    });
    if (!response.ok) {
      throw httpError(`createRef(${branchName})`, response);
    }
  }

  async listPullRequestsForBranch(branchName: string): Promise<ProposalPullRequestSummary[]> {
    const owner = this.apiBase.split("/repos/")[1]?.split("/")[0] ?? "";
    const response = await this.request(
      `/pulls?head=${encodeURIComponent(`${owner}:${branchName}`)}&state=all&per_page=20`
    );
    if (!response.ok) throw httpError(`listPullRequestsForBranch(${branchName})`, response);
    const body = (await response.json()) as Array<{
      number: number;
      state: "open" | "closed";
      head: { ref: string; repo: { full_name: string } | null };
      body: string | null;
    }>;
    return body.map((pr) => ({
      number: pr.number,
      state: pr.state,
      headRef: pr.head.ref,
      body: pr.body ?? "",
      headRepoFullName: pr.head.repo?.full_name ?? null,
    }));
  }

  async createPullRequest(params: CreatePullRequestParams): Promise<ProposalPullRequestSummary> {
    const response = await this.request(`/pulls`, {
      method: "POST",
      body: JSON.stringify(params),
    });
    if (!response.ok) throw httpError("createPullRequest", response);
    const body = (await response.json()) as {
      number: number;
      state: "open" | "closed";
      body: string | null;
      head: { repo: { full_name: string } | null };
    };
    return {
      number: body.number,
      state: body.state,
      headRef: params.head,
      body: body.body ?? params.body,
      headRepoFullName: body.head?.repo?.full_name ?? null,
    };
  }

  /** Lists open+closed PRs whose head branch starts with the learning-proposal prefix, for dedup marker collection. */
  async listAllProposalPullRequests(): Promise<ProposalPullRequestSummary[]> {
    const proposals: ProposalPullRequestSummary[] = [];
    let nextPath: string | null = "/pulls?state=all&per_page=100";
    let pages = 0;
    while (nextPath !== null) {
      if (pages >= MAX_PROPOSAL_LIST_PAGES) {
        throw new Error("listAllProposalPullRequests exceeded pagination safety limit");
      }
      pages += 1;
      const response = await this.request(nextPath);
      if (!response.ok) throw httpError("listAllProposalPullRequests", response);
      const body = (await response.json()) as Array<{
        number: number;
        state: "open" | "closed";
        head: { ref: string; repo: { full_name: string } | null };
        body: string | null;
      }>;
      proposals.push(
        ...body
          .filter((pr) => pr.head.ref.startsWith("jules-memory/"))
          .map((pr) => ({
            number: pr.number,
            state: pr.state,
            headRef: pr.head.ref,
            body: pr.body ?? "",
            headRepoFullName: pr.head.repo?.full_name ?? null,
          }))
      );
      const link = response.headers.get("link") ?? "";
      const nextMatch = link.match(/<([^>]+)>;\s*rel="next"/i);
      nextPath = nextMatch ? new URL(nextMatch[1]!).pathname + new URL(nextMatch[1]!).search : null;
    }
    return proposals;
  }
}

async function main(): Promise<void> {
  const repoFullName = requireEnv("GITHUB_REPOSITORY");
  const token = requireEnv("GH_TOKEN");
  const currentSha = requireEnv("GITHUB_SHA");
  const currentRunId = requireEnv("GITHUB_RUN_ID");
  const repositoryOwner = requireEnv("GITHUB_REPOSITORY_OWNER");
  const artifactPath = requireEnv("PR_LEARNING_ARTIFACT_PATH");
  const baseBranch = process.env.PR_LEARNING_BASE_BRANCH || "main";
  if (baseBranch !== "main") {
    throw new Error(`PR_LEARNING_BASE_BRANCH must be "main", got: ${baseBranch}`);
  }

  const persona = requireEnv("PR_LEARNING_PERSONA") as Persona;
  if (persona !== "bolt" && persona !== "sentinel") {
    throw new Error(`PR_LEARNING_PERSONA must be "bolt" or "sentinel", got: ${persona}`);
  }
  const mechanism = requireEnv("PR_LEARNING_MECHANISM");
  const affectedScope = requireEnv("PR_LEARNING_AFFECTED_SCOPE")
    .split("|")
    .map((value) => value.trim())
    .filter((value) => value.length > 0);
  const normalizedRule = requireEnv("PR_LEARNING_NORMALIZED_RULE");
  for (const [name, value] of [
    ["PR_LEARNING_MECHANISM", mechanism],
    ["PR_LEARNING_NORMALIZED_RULE", normalizedRule],
  ] as const) {
    if (!/^[a-z0-9][a-z0-9-]{0,63}$/.test(value)) {
      throw new Error(`${name} must be lowercase kebab-case, at most 64 characters`);
    }
  }
  const evidencePrNumbers = requireEnv("PR_LEARNING_EVIDENCE_PR_NUMBERS")
    .split(",")
    .map((value) => value.trim())
    .filter((value) => value.length > 0)
    .map((value) => {
      if (!/^[1-9]\d*$/.test(value)) {
        throw new Error(`PR_LEARNING_EVIDENCE_PR_NUMBERS contains an invalid entry: "${value}"`);
      }
      const parsed = Number(value);
      if (!Number.isInteger(parsed) || parsed <= 0) {
        throw new Error(`PR_LEARNING_EVIDENCE_PR_NUMBERS contains a non-positive-integer entry: "${value}"`);
      }
      return parsed;
    });
  if (evidencePrNumbers.length === 0 || evidencePrNumbers.length > MAX_EVIDENCE_PR_COUNT) {
    throw new Error(
      `PR_LEARNING_EVIDENCE_PR_NUMBERS must list between 1 and ${MAX_EVIDENCE_PR_COUNT} PR numbers`
    );
  }

  const rule = requireEnv("PR_LEARNING_RULE");
  const verification = requireEnv("PR_LEARNING_VERIFICATION");
  const scope = requireEnv("PR_LEARNING_SCOPE");
  const retractionCondition = requireEnv("PR_LEARNING_RETRACTION_CONDITION");

  const targetMemoryPath = memoryPathForPersona(persona);

  // Step 1: validate the collector artifact's bindings before trusting
  // anything derived from it (R11, R13).
  const artifactFile = Bun.file(artifactPath);
  if (!(await artifactFile.exists())) {
    throw new Error(`collector artifact not found at ${artifactPath}`);
  }
  const artifact = (await artifactFile.json()) as ArtifactBindings;
  validateArtifactBindings(artifact, currentSha, currentRunId);
  if (!Array.isArray(artifact.report.envelopes)) {
    throw new Error(
      "collector artifact does not contain evidence envelopes; regenerate the report with the current collector"
    );
  }
  const sessionVerifier = sessionVerifierFromArtifact(artifact.report.envelopes);

  const apiBase = `https://api.github.com/repos/${repoFullName}`;
  const headers: Record<string, string> = {
    Authorization: `Bearer ${token}`,
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "jules-persona-learning-propose",
  };

  // Step 2: re-collect and re-classify only this persona, then filter
  // down to the operator-referenced PR numbers. Reuses the exact same
  // identity/session-verification and reconciliation logic as the
  // read-only collector — never trusts an operator's eligibility claim
  // without independently re-deriving it.
  const asOf = new Date().toISOString();
  const lookbackWatermark = new Date(Date.now() - 180 * 24 * 60 * 60 * 1000).toISOString();
  const collected = await collectPersonaPullRequests({
    apiBase,
    headers,
    repoFullName,
    persona,
    authorLogins: [...JULES_AUTHOR_LOGINS, repositoryOwner],
    asOf,
    lookbackWatermark,
    // Only session linkage already verified by the collector artifact is
    // trusted; missing linkage remains ambiguous and is never inferred.
    sessionVerifier,
  });
  if (!collected.complete) {
    throw new Error(
      `re-collection for persona "${persona}" was incomplete (${collected.errors.join("; ")}); refusing to propose`
    );
  }
  const { envelopes, errors: classifyErrors } = classifyPullRequests(collected.records, {
    repoFullName,
    persona,
    asOf,
    collectedAt: asOf,
  });
  if (classifyErrors.length > 0) {
    throw new Error(`re-classification for persona "${persona}" reported errors: ${classifyErrors.join("; ")}`);
  }

  const referencedNumbers = new Set(evidencePrNumbers);
  const matchedEnvelopes: EvidenceEnvelope[] = envelopes.filter((envelope) =>
    referencedNumbers.has(envelope.pr_number)
  );
  if (matchedEnvelopes.length !== evidencePrNumbers.length) {
    const found = new Set(matchedEnvelopes.map((envelope) => envelope.pr_number));
    const missing = evidencePrNumbers.filter((number) => !found.has(number));
    throw new Error(
      `PR(s) ${missing.join(", ")} were not found as verified, in-scope evidence for persona "${persona}"`
    );
  }

  // Step 3: independently re-derive eligibility (R6) — never trust the
  // operator's assertion that the referenced PRs qualify.
  const eligibility = determineEligibility(matchedEnvelopes);
  if (eligibility === null) {
    throw new Error(
      "referenced evidence does not satisfy R6 eligibility: need one independently verified merged PR, " +
        "or two distinct closed_unmerged PRs sharing a non-unknown closure cause"
    );
  }
  const evidence = matchedEnvelopes.map(
    (envelope) => `PR #${envelope.pr_number} (${envelope.outcome})`
  );

  // Step 4: compute the candidate fingerprint server-side from the
  // operator-supplied structured fields — never accept a pre-computed
  // fingerprint from the caller.
  const fingerprint = computeCandidateFingerprintAtCurrentVersion({
    persona,
    mechanism,
    affectedScope,
    normalizedRule,
    taxonomyVersion: TAXONOMY_VERSION,
    targetMemoryPath,
  });
  const entryId = `${persona}-${fingerprint.slice(0, 12)}`;

  const client = new RestProposeGitHubClient(apiBase, headers);

  // Step 5: fetch live memory content + blob SHA, then run deduplication
  // (R8) against current memory, memory history is intentionally omitted
  // here (bounded MVP: only current content + open/closed proposal
  // markers are checked; historical-snapshot dedup is deferred alongside
  // automatic retraction/supersession per the plan's scope boundary).
  const targetFile = await client.getFileContent(targetMemoryPath, `heads/${baseBranch}`);
  if (targetFile === null) {
    throw new Error(`target memory file ${targetMemoryPath} was not found on ${baseBranch}`);
  }
  const proposalPrs = await client.listAllProposalPullRequests();
  const openMarkers: ProposalMarkerLike[] = [];
  const closedMarkers: ProposalMarkerLike[] = [];
  for (const pr of proposalPrs) {
    const marker = parseProposalMarker(pr.body);
    if (marker === null) continue;
    // A well-formed marker is not automatically trustworthy: it must be
    // authenticated against the exact PR it was read from (same-repo
    // origin, matching branch, matching producer workflow) before it can
    // influence dedup lookup-before-create (see `authenticateProposalMarker`).
    if (!authenticateProposalMarker(marker, pr, { repoFullName, producerWorkflow: PRODUCER_WORKFLOW })) {
      continue;
    }
    (pr.state === "open" ? openMarkers : closedMarkers).push({
      candidate_fingerprint: marker.candidate_fingerprint,
      target_memory_path: marker.target_memory_path,
    });
  }

  const dedup = deduplicateCandidate({
    candidateFingerprint: fingerprint,
    entryId,
    targetMemoryPath,
    memoryContent: targetFile.content,
    memoryHistory: [],
    openProposalMarkers: openMarkers,
    closedProposalMarkers: closedMarkers,
  });
  if (!dedup.novel) {
    console.log(`Skipping: ${dedup.status} — ${dedup.reason}`);
    return;
  }

  // Step 6: build and pre-validate the bounded memory entry from
  // operator-supplied text (R9) before any mutation is attempted.
  const entry: MemoryEntry = {
    entry_id: entryId,
    persona,
    rule,
    evidence,
    verification,
    scope,
    retraction_condition: retractionCondition,
    candidate_fingerprint: fingerprint,
    memory_blob_sha: targetFile.sha,
    generated_at: asOf,
  };
  const validation = validateMemoryEntry(entry, { liveBlobSha: targetFile.sha });
  if (!validation.ok) {
    throw new Error(`memory entry failed validation: ${validation.reason}`);
  }

  const candidate: Pick<Candidate, "candidate_fingerprint" | "persona" | "target_memory_path"> = {
    candidate_fingerprint: fingerprint,
    persona,
    target_memory_path: targetMemoryPath,
  };

  // Step 7: the only mutation in this pipeline — governed branch/commit/PR
  // creation. `createMemoryProposal` performs its own live revalidation,
  // lookup-before-create, and timeout-safe retries (U5).
  const result = await createMemoryProposal(client, {
    repo: repoFullName,
    baseBranch,
    producerWorkflow: PRODUCER_WORKFLOW,
    collectorCommit: currentSha,
    candidate,
    entry,
  });

  if (result.status === "rejected") {
    throw new Error(`proposal rejected: ${result.reason}`);
  }
  if (result.status === "existing") {
    console.log(`Existing proposal PR #${result.pullRequestNumber} on branch ${result.branchName}: ${result.reason}`);
    return;
  }
  console.log(
    `Created human-reviewed proposal PR #${result.pullRequestNumber} on branch ${result.branchName} (commit ${result.commitSha}). Awaiting human review and merge — no auto-merge path exists for this branch prefix.`
  );

  const githubOutput = process.env.GITHUB_OUTPUT;
  if (githubOutput) {
    (await import("node:fs")).appendFileSync(
      githubOutput,
      `pull_request_number=${result.pullRequestNumber}\nbranch_name=${result.branchName}\n`
    );
  }
}

if (import.meta.main) {
  main().catch((error) => {
    console.error(`::error::${error instanceof Error ? error.message : String(error)}`);
    process.exit(1);
  });
}
