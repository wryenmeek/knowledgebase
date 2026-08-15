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
 * Governed proposal creation for the Jules persona PR learning loop (U5).
 *
 * Implements the "Proposal marker" section of
 * `schema/jules-memory-entry-contract.md` and R8, R10, R11, R12, R13 of
 * `schema/jules-pr-learning-contract.md`: given a validated `Candidate` and
 * `MemoryEntry` (already approved by `memory-validator.ts`), create exactly
 * one branch + one commit + one pull request that appends the entry to its
 * single allowlisted `.jules/*.md` target — never touching any other path,
 * never checking out or executing PR code, and never calling merge, issue,
 * label, or session-mutation APIs.
 *
 * This module is a pure orchestrator over an injected `ProposeGitHubClient`
 * (see `fleet-submit-prs.ts`'s `GitHubClient` for the same
 * dependency-injection pattern). It performs no GitHub API calls of its
 * own and requires no credentials to import — a caller wires a concrete
 * client (Octokit-backed) only inside a `main()`/CLI entrypoint guarded by
 * `import.meta.main`, matching every other `scripts/fleet/**` entrypoint.
 *
 * Concurrency: proposal creation is idempotent across concurrent runs via
 * a deterministic branch name, a marker embedded in the PR body, a
 * lookup-before-create check, an immediate second lookup right before the
 * branch is created, and a non-canceling GitHub Actions concurrency group
 * (see `PROPOSAL_CONCURRENCY_CANCEL_IN_PROGRESS` /
 * `proposalConcurrencyGroupName`, mirrored by the U6 workflow's
 * human-readable input tuple). Local
 * filesystem locks (ADR-005) do not coordinate separate Actions runners —
 * GitHub-visible markers and live base-tree revalidation are the actual
 * cross-runner concurrency contract, per the plan's Key Technical
 * Decisions.
 */

import {
  classifyMutationError,
  runMutationWithDiagnostics,
  type RunMutationWithDiagnosticsOptions,
} from "../github/mutation-diagnostics.js";
import {
  GIT_BLOB_SHA_RE,
  renderMemoryEntryMarkdown,
  requiredAppendSeparator,
  validateMemoryEntry,
} from "./memory-validator.js";
import { isValidSha256Hex } from "./fingerprints.js";
import { validateBaseTreeEntryMode } from "./proposal-validator.js";
import type { GitHubTreeEntry } from "./proposal-validator.js";
import { memoryPathForPersona } from "./types.js";
import type { Candidate, MemoryEntry, ProposalMarker } from "./types.js";

/** Branch prefix for every proposal branch (R8/R11 deterministic naming). */
export const PROPOSAL_BRANCH_PREFIX = "jules-memory";

/**
 * The proposal marker is rendered as this HTML comment prefix followed by
 * a single-line JSON object, so `parseProposalMarker` can find and parse
 * it without treating the rest of the PR body as structured data. Never
 * rendered as visible Markdown (HTML comments are already invisible),
 * matching the `entry_id`/`fingerprint` comment convention in
 * `renderMemoryEntryMarkdown`.
 */
const MARKER_COMMENT_PREFIX = "jules-memory-proposal";
const MARKER_LINE_RE = /<!--\s*jules-memory-proposal:\s*(\{[^}]*\})\s*-->/;
const MAX_MARKER_BODY_LENGTH = 4096;

/**
 * Non-canceling concurrency contract (R11): two concurrent runs for the
 * same candidate fingerprint must converge on at most one proposal PR,
 * never cancel a partially-applied mutation mid-flight. The U6 workflow
 * must set `concurrency: { group: proposalConcurrencyGroupName(fingerprint),
 * cancel-in-progress: PROPOSAL_CONCURRENCY_CANCEL_IN_PROGRESS }` — mirrors
 * `jules-archive-stale.yml`'s `cancel-in-progress: false` pattern.
 */
export const PROPOSAL_CONCURRENCY_CANCEL_IN_PROGRESS = false as const;

/** Fixed number of leading fingerprint hex characters used in identifiers. */
const FINGERPRINT_ID_LENGTH = 12;

/** Default bounded retry attempts for each individual mutation call. */
export const DEFAULT_PROPOSAL_MAX_ATTEMPTS = 3;

/**
 * Deterministic GitHub Actions concurrency group name for a given
 * candidate fingerprint. Distinct fingerprints (including distinct
 * personas, since the fingerprint already encodes persona) always produce
 * distinct groups, so disjoint candidates can proceed independently while
 * concurrent runs for the *same* candidate serialize on one group.
 */
export function proposalConcurrencyGroupName(candidateFingerprint: string): string {
  return `${PROPOSAL_BRANCH_PREFIX}-proposal-${candidateFingerprint.slice(0, FINGERPRINT_ID_LENGTH)}`;
}

/**
 * Deterministic proposal branch name: `jules-memory/<persona>/<fingerprint[:12]>`,
 * exactly as specified by `schema/jules-memory-entry-contract.md`'s
 * "Proposal marker" section.
 */
export function computeProposalBranchName(
  persona: Candidate["persona"],
  candidateFingerprint: string
): string {
  return `${PROPOSAL_BRANCH_PREFIX}/${persona}/${candidateFingerprint.slice(0, FINGERPRINT_ID_LENGTH)}`;
}

/** Renders a `ProposalMarker` as the bounded HTML-comment JSON block embedded in the PR body. */
export function renderProposalMarker(marker: ProposalMarker): string {
  return `<!-- ${MARKER_COMMENT_PREFIX}: ${JSON.stringify(marker)} -->`;
}

function isProposalMarkerShape(value: unknown): value is ProposalMarker {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const record = value as Record<string, unknown>;
  return (
    typeof record.repo === "string" &&
    (record.target_memory_path === ".jules/bolt.md" || record.target_memory_path === ".jules/sentinel.md") &&
    typeof record.candidate_fingerprint === "string" &&
    typeof record.base_branch === "string" &&
    typeof record.branch_name === "string" &&
    typeof record.producer_workflow === "string" &&
    typeof record.collector_commit === "string"
  );
}

/**
 * Parses a `ProposalMarker` out of an existing PR body, or `null` if the
 * body carries no well-formed marker. Used for lookup-before-create: an
 * existing PR without a parseable marker is never trusted as a match.
 */
export function parseProposalMarker(prBody: string): ProposalMarker | null {
  const match = MARKER_LINE_RE.exec(prBody.slice(0, MAX_MARKER_BODY_LENGTH));
  if (!match) {
    return null;
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(match[1]!);
  } catch {
    return null;
  }
  return isProposalMarkerShape(parsed) ? parsed : null;
}

/** Renders the full PR body: bounded human-readable summary followed by the marker. */
export function renderProposalPullRequestBody(entry: MemoryEntry, marker: ProposalMarker): string {
  const lines = [
    `Automated Jules persona learning proposal for \`${marker.target_memory_path}\`.`,
    "",
    "This PR was generated by a read-only collector/classifier and validated proposal",
    "writer. It appends exactly one bounded memory entry and changes no other file.",
    "It is never auto-merged; human review and merge are required (R12).",
    "",
    "```markdown",
    renderMemoryEntryMarkdown(entry),
    "```",
    "",
    renderProposalMarker(marker),
  ];
  return lines.join("\n");
}

/** Builds the deterministic commit message for a proposal commit. */
export function buildProposalCommitMessage(entry: MemoryEntry, marker: ProposalMarker): string {
  return `jules-memory: append ${entry.persona} learning entry ${entry.entry_id}\n\nCandidate-Fingerprint: ${marker.candidate_fingerprint}\nCollector-Commit: ${marker.collector_commit}`;
}

/** Builds the new full file content: existing bytes, required separator, then the rendered entry. */
export function buildAppendedMemoryContent(existingContent: string, entry: MemoryEntry): string {
  return existingContent + requiredAppendSeparator(existingContent) + renderMemoryEntryMarkdown(entry);
}

/** A single Git ref lookup result (Git Data API `GET /repos/{owner}/{repo}/git/ref/{ref}`). */
export interface GitRefResult {
  sha: string;
}

/** A single Git commit lookup result (Git Data API `GET /repos/{owner}/{repo}/git/commits/{sha}`). */
export interface GitCommitResult {
  sha: string;
  treeSha: string;
}

/** A single file read via the Contents API (`GET /repos/{owner}/{repo}/contents/{path}`). */
export interface ContentsFileResult {
  content: string;
  sha: string;
}

/** The subset of a GitHub pull request needed for marker-based lookup and reporting. */
export interface ProposalPullRequestSummary {
  number: number;
  state: "open" | "closed";
  headRef: string;
  body: string;
  /**
   * The PR's actual head repository full name (`owner/repo`), or `null`
   * when the head repo was deleted/unknown. Used to authenticate a parsed
   * `ProposalMarker` against the PR it was actually read from — a marker
   * embedded in a fork PR's body can otherwise be forged to spoof a
   * same-repo proposal binding it never earned. `undefined` (not
   * populated by the caller) is treated identically to `null`
   * (untrusted) by marker authentication, never as "trusted by default".
   */
  headRepoFullName?: string | null;
}

export interface CreatePullRequestParams {
  title: string;
  body: string;
  head: string;
  base: string;
}

/**
 * Minimal GitHub client surface required to create one governed learning
 * proposal, expressed purely in terms of the Git Data and Contents APIs
 * plus branch/PR creation and lookup. Deliberately excludes any merge,
 * issue, label, workflow, or session-mutation capability (R11, R12) — the
 * type itself is the enforcement boundary for "no merge/issues/labels/
 * session mutation" in this module. Injectable for testing with a fake
 * implementation; no concrete (Octokit-backed) implementation is
 * constructed at import time.
 */
export interface ProposeGitHubClient {
  /** Git Data API: resolve a ref (e.g. `heads/main`) to its current commit SHA, or `null` if it does not exist. */
  getRef(ref: string): Promise<GitRefResult | null>;
  /** Git Data API: resolve a commit SHA to its tree SHA, or `null` if it does not exist. */
  getCommit(sha: string): Promise<GitCommitResult | null>;
  /** Contents API: read a file at a specific ref/SHA, or `null` if it does not exist at that revision. */
  getFileContent(path: string, ref: string): Promise<ContentsFileResult | null>;
  /**
   * Git Data API: lists the full recursive tree entries at `treeSha`
   * (`GET /git/trees/{tree_sha}?recursive=1`). Used to independently
   * verify the target path's existing tree-entry mode/type (ordinary
   * regular blob, never symlink/submodule/executable) before mutation —
   * the Contents API alone cannot prove this, since it happily returns
   * byte content for a symlink or executable file too.
   */
  getTreeEntries(treeSha: string): Promise<readonly GitHubTreeEntry[]>;
  /** Git Data API: create a blob, returning its SHA. */
  createBlob(content: string): Promise<string>;
  /** Git Data API: create a tree that replaces exactly one path under `baseTreeSha`, returning the new tree SHA. */
  createTree(baseTreeSha: string, path: string, blobSha: string): Promise<string>;
  /** Git Data API: create a commit, returning its SHA. */
  createCommit(message: string, treeSha: string, parentSha: string): Promise<string>;
  /** Git Data API: create a branch ref pointing at `sha`. Must fail (never overwrite) if the ref already exists. */
  createRef(branchName: string, sha: string): Promise<void>;
  /** Lists open and closed pull requests whose head branch is `branchName` (used for lookup-before-create and the second/timeout-recovery lookup). */
  listPullRequestsForBranch(branchName: string): Promise<ProposalPullRequestSummary[]>;
  /** Creates a pull request. */
  createPullRequest(params: CreatePullRequestParams): Promise<ProposalPullRequestSummary>;
}

export interface CreateMemoryProposalInput {
  /** Repository the proposal targets, `owner/repo`. */
  repo: string;
  /** Base branch the proposal PR will target (must be the repository's governed base branch). */
  baseBranch: string;
  /** Workflow file name that produced this proposal (for later verification, U6). */
  producerWorkflow: string;
  /** 40-char hex commit SHA of the collector run that produced the underlying evidence. */
  collectorCommit: string;
  /** The candidate driving this proposal; only the fingerprint/persona/target fields are read. */
  candidate: Pick<Candidate, "candidate_fingerprint" | "persona" | "target_memory_path">;
  /** The already-generated memory entry to append (validated here again before any mutation). */
  entry: MemoryEntry;
}

export type CreateMemoryProposalResult =
  | {
      status: "created";
      branchName: string;
      commitSha: string;
      pullRequestNumber: number;
    }
  | {
      status: "existing";
      branchName: string;
      pullRequestNumber: number;
      reason: string;
    }
  | {
      status: "rejected";
      branchName: string;
      reason: string;
    };

export interface CreateMemoryProposalOptions {
  /** Bounded retry attempts per individual mutation call. Default: `DEFAULT_PROPOSAL_MAX_ATTEMPTS`. */
  maxAttempts?: number;
  /** Injectable for tests: overrides the retry/backoff wrapper used for each mutation. */
  runMutation?: <T>(options: RunMutationWithDiagnosticsOptions<T>) => Promise<T>;
}

/**
 * Authenticates a parsed `ProposalMarker` against the PR it was actually
 * read from and this run's own repo/producer-workflow bindings, before
 * the marker is ever trusted for dedup lookup-before-create. A marker's
 * JSON content is caller-controlled (embedded in a PR body): without
 * this check, a fork PR whose branch happens to match the
 * `jules-memory/*` prefix could carry a forged marker claiming
 * `repo`/`branch_name`/`producer_workflow` bindings it never earned,
 * either faking an "already proposed" duplicate to suppress a legitimate
 * proposal, or faking a "previously rejected" marker to permanently block
 * one (see `deduplicateCandidate` in `deduplicate.ts`).
 *
 * `collector_commit` is intentionally not compared against *this* run's
 * collector commit — a legitimate marker can originate from an earlier
 * collection run — but its shape is verified so an unresolvable/malformed
 * value can never masquerade as a resolved commit reference.
 */
export function authenticateProposalMarker(
  marker: ProposalMarker,
  pr: Pick<ProposalPullRequestSummary, "headRef" | "headRepoFullName">,
  expected: { repoFullName: string; producerWorkflow: string }
): boolean {
  if (marker.repo !== expected.repoFullName) {
    return false;
  }
  if (marker.producer_workflow !== expected.producerWorkflow) {
    return false;
  }
  if (marker.branch_name !== pr.headRef) {
    return false; // marker content must describe the exact branch it was actually read from
  }
  // A marker can only ever be trusted from a same-repo PR. `undefined`
  // (caller did not populate headRepoFullName) is treated identically to
  // `null` (unknown) — both fail closed, never "trusted by default".
  if (pr.headRepoFullName !== expected.repoFullName) {
    return false; // a fork PR (or one with an unresolvable head repo) can never authenticate a marker
  }
  if (!/^[0-9a-f]{40}$/i.test(marker.collector_commit)) {
    return false;
  }
  return true;
}

/**
 * Finds an existing proposal PR whose marker matches the given candidate
 * fingerprint, if any. The marker is also authenticated (via
 * `authenticateProposalMarker`) against `expected` before it can match —
 * a fingerprint collision alone is not sufficient, since a forged marker
 * embedded in a fork PR's body could otherwise fake an "already
 * proposed"/"already rejected" duplicate for lookup-before-create.
 */
export function findMatchingProposalPullRequest(
  pullRequests: readonly ProposalPullRequestSummary[],
  candidateFingerprint: string,
  expected: { repoFullName: string; producerWorkflow: string }
): ProposalPullRequestSummary | undefined {
  return pullRequests.find((pr) => {
    const marker = parseProposalMarker(pr.body);
    return (
      marker !== null &&
      marker.candidate_fingerprint === candidateFingerprint &&
      authenticateProposalMarker(marker, pr, expected)
    );
  });
}

function rejected(branchName: string, reason: string): CreateMemoryProposalResult {
  return { status: "rejected", branchName, reason };
}

function buildMarker(
  input: CreateMemoryProposalInput,
  branchName: string
): ProposalMarker {
  return {
    repo: input.repo,
    target_memory_path: input.candidate.target_memory_path,
    candidate_fingerprint: input.candidate.candidate_fingerprint,
    base_branch: input.baseBranch,
    branch_name: branchName,
    producer_workflow: input.producerWorkflow,
    collector_commit: input.collectorCommit,
  };
}

/**
 * Wraps a branch-ref creation so a client-observed timeout/network error
 * does not automatically trigger a blind duplicate mutation retry: on any
 * retryable-classified failure, this first performs a fresh `getRef`
 * lookup to check whether the ref was actually created server-side despite
 * the client-side error, and treats that as success (idempotent recovery)
 * instead of re-attempting the mutation. A non-retryable failure, or a
 * retryable failure where the lookup does not confirm the expected SHA,
 * is rethrown so the outer `runMutationWithDiagnostics` bounded-retry loop
 * can decide the next step.
 */
async function createRefWithTimeoutRecovery(
  client: ProposeGitHubClient,
  branchName: string,
  commitSha: string
): Promise<void> {
  try {
    await client.createRef(branchName, commitSha);
    return;
  } catch (error) {
    const classification = classifyMutationError(error);
    if (classification.retryable) {
      const existing = await client.getRef(`heads/${branchName}`);
      if (existing !== null && existing.sha === commitSha) {
        // The branch was created before the client observed the failure
        // (e.g. a response timeout after the server-side write succeeded).
        // Recognize this via lookup rather than retrying the mutation.
        return;
      }
    }
    throw error;
  }
}

/**
 * Wraps pull request creation with the same timeout-lookup-recovery
 * pattern as `createRefWithTimeoutRecovery`: on a retryable-classified
 * failure, look up whether a PR with the expected marker now exists for
 * this branch before deciding to retry.
 */
async function createPullRequestWithTimeoutRecovery(
  client: ProposeGitHubClient,
  branchName: string,
  candidateFingerprint: string,
  params: CreatePullRequestParams,
  expected: { repoFullName: string; producerWorkflow: string }
): Promise<ProposalPullRequestSummary> {
  try {
    return await client.createPullRequest(params);
  } catch (error) {
    const classification = classifyMutationError(error);
    if (classification.retryable) {
      const existing = await client.listPullRequestsForBranch(branchName);
      const match = findMatchingProposalPullRequest(existing, candidateFingerprint, expected);
      if (match !== undefined) {
        return match;
      }
    }
    throw error;
  }
}

/**
 * Creates one governed learning proposal PR for a validated candidate and
 * memory entry, or reports why creation was skipped/rejected. This is the
 * only mutation entrypoint in the Jules persona PR learning loop pipeline
 * (U5): it never checks out or executes PR code, never calls merge,
 * auto-merge, issue, label, or session-mutation APIs, and only ever
 * touches the single allowlisted `.jules/*.md` path recorded in the
 * candidate.
 *
 * Sequence (see module docstring for the concurrency contract):
 *   1. Lookup-before-create: skip if an open/closed proposal PR already
 *      carries a marker for this candidate fingerprint.
 *   2. Live base revalidation: re-fetch the base branch head and the
 *      current target-file blob SHA; reject on a stale target rather than
 *      overwrite newer memory content.
 *   3. Validate the (already-approved) entry once more against the live
 *      blob SHA and the exact byte-for-byte appended content.
 *   4. Create blob -> tree -> commit against the freshly revalidated base.
 *   5. Immediate second lookup right before branch creation (race guard).
 *   6. Create the branch (with timeout-lookup recovery) and the PR (with
 *      timeout-lookup recovery), embedding the proposal marker in the body.
 */
export async function createMemoryProposal(
  client: ProposeGitHubClient,
  input: CreateMemoryProposalInput,
  options: CreateMemoryProposalOptions = {}
): Promise<CreateMemoryProposalResult> {
  const maxAttempts = options.maxAttempts ?? DEFAULT_PROPOSAL_MAX_ATTEMPTS;
  const runMutation = options.runMutation ?? runMutationWithDiagnostics;
  const fingerprint = input.candidate.candidate_fingerprint;
  const branchName = computeProposalBranchName(input.candidate.persona, fingerprint);

  if (!isValidSha256Hex(fingerprint)) {
    return rejected(branchName, "candidate_fingerprint is not a well-formed 64-char hex SHA-256 digest");
  }
  if (!GIT_BLOB_SHA_RE.test(input.collectorCommit)) {
    return rejected(branchName, "collectorCommit is not a well-formed 40-char hex Git commit SHA");
  }
  if (input.entry.candidate_fingerprint !== fingerprint) {
    return rejected(branchName, "entry.candidate_fingerprint does not match candidate.candidate_fingerprint");
  }
  if (input.entry.persona !== input.candidate.persona) {
    return rejected(branchName, "entry.persona does not match candidate.persona");
  }
  if (input.candidate.target_memory_path !== memoryPathForPersona(input.candidate.persona)) {
    return rejected(branchName, "candidate.target_memory_path does not match candidate.persona");
  }

  // Step 1: lookup-before-create.
  const initialPullRequests = await client.listPullRequestsForBranch(branchName);
  const initialMatch = findMatchingProposalPullRequest(initialPullRequests, fingerprint, {
    repoFullName: input.repo,
    producerWorkflow: input.producerWorkflow,
  });
  if (initialMatch !== undefined) {
    return {
      status: "existing",
      branchName,
      pullRequestNumber: initialMatch.number,
      reason: "lookup-before-create found an existing open or closed proposal for this candidate fingerprint",
    };
  }

  // Step 2: live base revalidation.
  const baseRef = await client.getRef(`heads/${input.baseBranch}`);
  if (baseRef === null) {
    return rejected(branchName, `base branch "${input.baseBranch}" was not found at proposal time`);
  }
  const baseCommit = await client.getCommit(baseRef.sha);
  if (baseCommit === null) {
    return rejected(branchName, `base commit "${baseRef.sha}" could not be resolved to a tree`);
  }
  const currentFile = await client.getFileContent(input.candidate.target_memory_path, baseRef.sha);
  if (currentFile === null) {
    return rejected(
      branchName,
      `target file "${input.candidate.target_memory_path}" does not exist at the live base revision; this pipeline only appends to existing memory files, never creates them`
    );
  }

  // Step 2b: independently verify the target's existing tree-entry mode
  // is an ordinary regular file (never symlink/submodule/executable)
  // before forcing a replacement to mode `100644`. The Contents API
  // above happily returns byte content for a symlink or executable file
  // too, so it alone cannot prove the target is safe to overwrite as a
  // plain blob.
  const baseTreeEntries = await client.getTreeEntries(baseCommit.treeSha);
  const treeModeResult = validateBaseTreeEntryMode(baseTreeEntries, input.candidate.target_memory_path);
  if (!treeModeResult.ok) {
    return rejected(branchName, treeModeResult.reason);
  }

  const newContent = buildAppendedMemoryContent(currentFile.content, input.entry);
  const validation = validateMemoryEntry(input.entry, {
    liveBlobSha: currentFile.sha,
    existingContent: currentFile.content,
    newContent,
  });
  if (!validation.ok) {
    return rejected(branchName, validation.reason);
  }

  // Step 3/4: create blob -> tree -> commit against the revalidated base.
  const blobSha = await runMutation({
    operation: `pr-learning:propose:create-blob:${fingerprint.slice(0, FINGERPRINT_ID_LENGTH)}`,
    maxAttempts,
    run: () => client.createBlob(newContent),
  });
  const treeSha = await runMutation({
    operation: `pr-learning:propose:create-tree:${fingerprint.slice(0, FINGERPRINT_ID_LENGTH)}`,
    maxAttempts,
    run: () => client.createTree(baseCommit.treeSha, input.candidate.target_memory_path, blobSha),
  });
  const marker = buildMarker(input, branchName);
  const commitSha = await runMutation({
    operation: `pr-learning:propose:create-commit:${fingerprint.slice(0, FINGERPRINT_ID_LENGTH)}`,
    maxAttempts,
    run: () => client.createCommit(buildProposalCommitMessage(input.entry, marker), treeSha, baseCommit.sha),
  });

  // Step 5: immediate second lookup right before branch creation (race guard).
  const secondPullRequests = await client.listPullRequestsForBranch(branchName);
  const secondMatch = findMatchingProposalPullRequest(secondPullRequests, fingerprint, {
    repoFullName: input.repo,
    producerWorkflow: input.producerWorkflow,
  });
  if (secondMatch !== undefined) {
    return {
      status: "existing",
      branchName,
      pullRequestNumber: secondMatch.number,
      reason: "second lookup (immediately before branch creation) found a concurrently created proposal for this candidate fingerprint",
    };
  }
  const secondBranchCheck = await client.getRef(`heads/${branchName}`);
  if (secondBranchCheck !== null) {
    return rejected(
      branchName,
      "branch already exists without a matching proposal PR marker; failing closed rather than force-pushing or overwriting"
    );
  }

  // Step 6: create branch, then PR (each with timeout-lookup recovery).
  await runMutation({
    operation: `pr-learning:propose:create-branch:${fingerprint.slice(0, FINGERPRINT_ID_LENGTH)}`,
    maxAttempts,
    run: () => createRefWithTimeoutRecovery(client, branchName, commitSha),
  });

  const pullRequest = await runMutation({
    operation: `pr-learning:propose:create-pr:${fingerprint.slice(0, FINGERPRINT_ID_LENGTH)}`,
    maxAttempts,
    run: () =>
      createPullRequestWithTimeoutRecovery(
        client,
        branchName,
        fingerprint,
        {
          title: `jules-memory: ${input.entry.persona} learning — ${input.entry.scope}`,
          body: renderProposalPullRequestBody(input.entry, marker),
          head: branchName,
          base: input.baseBranch,
        },
        { repoFullName: input.repo, producerWorkflow: input.producerWorkflow }
      ),
  });

  return {
    status: "created",
    branchName,
    commitSha,
    pullRequestNumber: pullRequest.number,
  };
}
