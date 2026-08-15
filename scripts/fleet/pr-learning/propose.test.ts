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

import { describe, expect, test } from "bun:test";
import {
  authenticateProposalMarker,
  buildAppendedMemoryContent,
  buildProposalCommitMessage,
  computeProposalBranchName,
  createMemoryProposal,
  DEFAULT_PROPOSAL_MAX_ATTEMPTS,
  findMatchingProposalPullRequest,
  parseProposalMarker,
  PROPOSAL_CONCURRENCY_CANCEL_IN_PROGRESS,
  proposalConcurrencyGroupName,
  renderProposalMarker,
  renderProposalPullRequestBody,
  type ContentsFileResult,
  type CreateMemoryProposalInput,
  type CreatePullRequestParams,
  type GitCommitResult,
  type GitRefResult,
  type ProposalPullRequestSummary,
  type ProposeGitHubClient,
} from "./propose.ts";
import { renderMemoryEntryMarkdown } from "./memory-validator.ts";
import type { GitHubTreeEntry } from "./proposal-validator.ts";
import { runMutationWithDiagnostics } from "../github/mutation-diagnostics.ts";
import type { Candidate, MemoryEntry, ProposalMarker } from "./types.ts";

const REPO = "wryenmeek/knowledgebase";
const BASE_BRANCH = "main";
const PRODUCER_WORKFLOW = "jules-persona-learning.yml";
const COLLECTOR_COMMIT = "f".repeat(40);
const FINGERPRINT = "e".repeat(64);
const BASE_HEAD_SHA = "1".repeat(40);
const BASE_TREE_SHA = "2".repeat(40);
const EXISTING_BLOB_SHA = "3".repeat(40);
const NEW_BLOB_SHA = "4".repeat(40);
const NEW_TREE_SHA = "5".repeat(40);
const NEW_COMMIT_SHA = "6".repeat(40);

const EXISTING_MEMORY_CONTENT = "# Bolt learnings\n\n## Existing entry\n\nSomething already recorded.\n";

function makeCandidate(overrides: Partial<Candidate> = {}): Pick<
  Candidate,
  "candidate_fingerprint" | "persona" | "target_memory_path"
> {
  return {
    candidate_fingerprint: FINGERPRINT,
    persona: "bolt",
    target_memory_path: ".jules/bolt.md",
    ...overrides,
  };
}

function makeMemoryEntry(overrides: Partial<MemoryEntry> = {}): MemoryEntry {
  return {
    entry_id: FINGERPRINT.slice(0, 12),
    persona: "bolt",
    rule: "Avoid eager Path.resolve() calls in hot loops.",
    evidence: ["PR #123 (merged)"],
    verification: "Reproducible benchmark showed 18% reduction.",
    scope: "scripts/kb/lint_wiki.py",
    retraction_condition: "If Path.resolve() semantics change upstream.",
    candidate_fingerprint: FINGERPRINT,
    memory_blob_sha: EXISTING_BLOB_SHA,
    generated_at: "2026-08-10T00:00:00.000Z",
    ...overrides,
  };
}

function makeInput(overrides: Partial<CreateMemoryProposalInput> = {}): CreateMemoryProposalInput {
  return {
    repo: REPO,
    baseBranch: BASE_BRANCH,
    producerWorkflow: PRODUCER_WORKFLOW,
    collectorCommit: COLLECTOR_COMMIT,
    candidate: makeCandidate(),
    entry: makeMemoryEntry(),
    ...overrides,
  };
}

/** In-memory fake of `ProposeGitHubClient` that records every call it receives. */
class FakeGitHubClient implements ProposeGitHubClient {
  calls: string[] = [];
  refs = new Map<string, GitRefResult>([[`heads/${BASE_BRANCH}`, { sha: BASE_HEAD_SHA }]]);
  commits = new Map<string, GitCommitResult>([[BASE_HEAD_SHA, { sha: BASE_HEAD_SHA, treeSha: BASE_TREE_SHA }]]);
  files = new Map<string, ContentsFileResult>([
    [`.jules/bolt.md@${BASE_HEAD_SHA}`, { content: EXISTING_MEMORY_CONTENT, sha: EXISTING_BLOB_SHA }],
  ]);
  treeEntries = new Map<string, readonly GitHubTreeEntry[]>([
    [
      BASE_TREE_SHA,
      [
        { path: ".jules/bolt.md", mode: "100644", type: "blob", sha: EXISTING_BLOB_SHA },
        { path: ".jules/sentinel.md", mode: "100644", type: "blob", sha: EXISTING_BLOB_SHA },
      ],
    ],
  ]);
  pullRequestsByBranch = new Map<string, ProposalPullRequestSummary[]>();
  nextPrNumber = 1001;
  failCreateRefTimes = 0;
  failCreatePullRequestTimes = 0;
  private createRefFailureIsRetryable = true;
  private createPullRequestFailureIsRetryable = true;

  configureCreateRefFailures(times: number, retryable = true): void {
    this.failCreateRefTimes = times;
    this.createRefFailureIsRetryable = retryable;
  }

  configureCreatePullRequestFailures(times: number, retryable = true): void {
    this.failCreatePullRequestTimes = times;
    this.createPullRequestFailureIsRetryable = retryable;
  }

  async getRef(ref: string): Promise<GitRefResult | null> {
    this.calls.push(`getRef:${ref}`);
    return this.refs.get(ref) ?? null;
  }

  async getCommit(sha: string): Promise<GitCommitResult | null> {
    this.calls.push(`getCommit:${sha}`);
    return this.commits.get(sha) ?? null;
  }

  async getFileContent(path: string, ref: string): Promise<ContentsFileResult | null> {
    this.calls.push(`getFileContent:${path}@${ref}`);
    return this.files.get(`${path}@${ref}`) ?? null;
  }

  async getTreeEntries(treeSha: string): Promise<readonly GitHubTreeEntry[]> {
    this.calls.push(`getTreeEntries:${treeSha}`);
    return this.treeEntries.get(treeSha) ?? [];
  }

  async createBlob(content: string): Promise<string> {
    this.calls.push(`createBlob:${content.length}`);
    return NEW_BLOB_SHA;
  }

  async createTree(baseTreeSha: string, path: string, blobSha: string): Promise<string> {
    this.calls.push(`createTree:${baseTreeSha}:${path}:${blobSha}`);
    return NEW_TREE_SHA;
  }

  async createCommit(message: string, treeSha: string, parentSha: string): Promise<string> {
    this.calls.push(`createCommit:${treeSha}:${parentSha}`);
    return NEW_COMMIT_SHA;
  }

  async createRef(branchName: string, sha: string): Promise<void> {
    this.calls.push(`createRef:${branchName}:${sha}`);
    if (this.failCreateRefTimes > 0) {
      this.failCreateRefTimes -= 1;
      throw this.createRefFailureIsRetryable
        ? new Error("ETIMEDOUT: request timed out")
        : new Error("PERMISSION_DENIED: forbidden");
    }
    this.refs.set(`heads/${branchName}`, { sha });
  }

  async listPullRequestsForBranch(branchName: string): Promise<ProposalPullRequestSummary[]> {
    this.calls.push(`listPullRequestsForBranch:${branchName}`);
    return this.pullRequestsByBranch.get(branchName) ?? [];
  }

  async createPullRequest(params: CreatePullRequestParams): Promise<ProposalPullRequestSummary> {
    this.calls.push(`createPullRequest:${params.head}:${params.base}`);
    if (this.failCreatePullRequestTimes > 0) {
      this.failCreatePullRequestTimes -= 1;
      throw this.createPullRequestFailureIsRetryable
        ? new Error("ECONNRESET: connection reset")
        : new Error("PERMISSION_DENIED: forbidden");
    }
    const pr: ProposalPullRequestSummary = {
      number: this.nextPrNumber++,
      state: "open",
      headRef: params.head,
      // This fake always simulates a same-repo (never a fork) PR creation,
      // so headRepoFullName must reflect that for authenticateProposalMarker
      // to accept the marker on a subsequent lookup-before-create call.
      headRepoFullName: REPO,
      body: params.body,
    };
    const existing = this.pullRequestsByBranch.get(params.head) ?? [];
    this.pullRequestsByBranch.set(params.head, [...existing, pr]);
    return pr;
  }
}

const noRetryDelayOptions = { retryBaseDelayMs: 0, retryMaxDelayMs: 0 };

function fastRunMutation<T>(options: {
  operation: string;
  maxAttempts: number;
  run: () => Promise<T>;
}): Promise<T> {
  return runMutationWithDiagnostics({ ...options, ...noRetryDelayOptions });
}

describe("computeProposalBranchName", () => {
  test("derives a deterministic branch name from persona and fingerprint prefix", () => {
    expect(computeProposalBranchName("bolt", FINGERPRINT)).toBe(
      `jules-memory/bolt/${FINGERPRINT.slice(0, 12)}`
    );
  });

  test("distinct fingerprints (and personas) never collide", () => {
    const other = "d".repeat(64);
    expect(computeProposalBranchName("bolt", FINGERPRINT)).not.toBe(
      computeProposalBranchName("sentinel", FINGERPRINT)
    );
    expect(computeProposalBranchName("bolt", FINGERPRINT)).not.toBe(
      computeProposalBranchName("bolt", other)
    );
  });
});

describe("proposalConcurrencyGroupName", () => {
  test("is deterministic per fingerprint and disjoint across fingerprints", () => {
    const other = "d".repeat(64);
    expect(proposalConcurrencyGroupName(FINGERPRINT)).toBe(
      proposalConcurrencyGroupName(FINGERPRINT)
    );
    expect(proposalConcurrencyGroupName(FINGERPRINT)).not.toBe(proposalConcurrencyGroupName(other));
  });

  test("the concurrency contract never cancels in-progress runs", () => {
    expect(PROPOSAL_CONCURRENCY_CANCEL_IN_PROGRESS).toBe(false);
  });
});

describe("renderProposalMarker / parseProposalMarker", () => {
  const marker: ProposalMarker = {
    repo: REPO,
    target_memory_path: ".jules/bolt.md",
    candidate_fingerprint: FINGERPRINT,
    base_branch: BASE_BRANCH,
    branch_name: computeProposalBranchName("bolt", FINGERPRINT),
    producer_workflow: PRODUCER_WORKFLOW,
    collector_commit: COLLECTOR_COMMIT,
  };

  test("round-trips every required field", () => {
    const rendered = renderProposalMarker(marker);
    expect(rendered).toContain("<!--");
    expect(rendered).toContain("-->");
    expect(parseProposalMarker(rendered)).toEqual(marker);
  });

  test("finds the marker embedded within a larger PR body", () => {
    const body = renderProposalPullRequestBody(makeMemoryEntry(), marker);
    expect(parseProposalMarker(body)).toEqual(marker);
  });

  test("returns null for a body with no marker", () => {
    expect(parseProposalMarker("just a regular PR body, no marker here")).toBeNull();
  });

  test("returns null for malformed JSON in the comment", () => {
    expect(parseProposalMarker("<!-- jules-memory-proposal: {not json} -->")).toBeNull();
  });

  test("returns null when required fields are missing", () => {
    const incomplete = { repo: REPO };
    expect(parseProposalMarker(`<!-- jules-memory-proposal: ${JSON.stringify(incomplete)} -->`)).toBeNull();
  });
});

describe("findMatchingProposalPullRequest", () => {
  const expected = { repoFullName: REPO, producerWorkflow: PRODUCER_WORKFLOW };

  test("matches only a PR whose marker carries the exact fingerprint", () => {
    const marker: ProposalMarker = {
      repo: REPO,
      target_memory_path: ".jules/bolt.md",
      candidate_fingerprint: FINGERPRINT,
      base_branch: BASE_BRANCH,
      branch_name: computeProposalBranchName("bolt", FINGERPRINT),
      producer_workflow: PRODUCER_WORKFLOW,
      collector_commit: COLLECTOR_COMMIT,
    };
    const matching: ProposalPullRequestSummary = {
      number: 42,
      state: "open",
      headRef: marker.branch_name,
      headRepoFullName: REPO,
      body: renderProposalMarker(marker),
    };
    const unrelated: ProposalPullRequestSummary = {
      number: 7,
      state: "closed",
      headRef: "some-other-branch",
      headRepoFullName: REPO,
      body: "no marker here",
    };
    expect(findMatchingProposalPullRequest([unrelated, matching], FINGERPRINT, expected)).toBe(matching);
    expect(findMatchingProposalPullRequest([unrelated], FINGERPRINT, expected)).toBeUndefined();
  });

  test("does not match a fingerprint-matching marker whose PR head repo is a fork (defense-in-depth via authenticateProposalMarker)", () => {
    const marker: ProposalMarker = {
      repo: REPO,
      target_memory_path: ".jules/bolt.md",
      candidate_fingerprint: FINGERPRINT,
      base_branch: BASE_BRANCH,
      branch_name: computeProposalBranchName("bolt", FINGERPRINT),
      producer_workflow: PRODUCER_WORKFLOW,
      collector_commit: COLLECTOR_COMMIT,
    };
    const forgedFromFork: ProposalPullRequestSummary = {
      number: 99,
      state: "open",
      headRef: marker.branch_name,
      headRepoFullName: "attacker/knowledgebase",
      body: renderProposalMarker(marker),
    };
    expect(findMatchingProposalPullRequest([forgedFromFork], FINGERPRINT, expected)).toBeUndefined();
  });

  test("does not match a fingerprint-matching marker claiming a foreign producer_workflow", () => {
    const marker: ProposalMarker = {
      repo: REPO,
      target_memory_path: ".jules/bolt.md",
      candidate_fingerprint: FINGERPRINT,
      base_branch: BASE_BRANCH,
      branch_name: computeProposalBranchName("bolt", FINGERPRINT),
      producer_workflow: "some-other-workflow.yml",
      collector_commit: COLLECTOR_COMMIT,
    };
    const forgedWorkflow: ProposalPullRequestSummary = {
      number: 100,
      state: "open",
      headRef: marker.branch_name,
      headRepoFullName: REPO,
      body: renderProposalMarker(marker),
    };
    expect(findMatchingProposalPullRequest([forgedWorkflow], FINGERPRINT, expected)).toBeUndefined();
  });

  test("is consistent with authenticateProposalMarker's own verdict for the same marker/PR/expected inputs", () => {
    const marker: ProposalMarker = {
      repo: REPO,
      target_memory_path: ".jules/bolt.md",
      candidate_fingerprint: FINGERPRINT,
      base_branch: BASE_BRANCH,
      branch_name: computeProposalBranchName("bolt", FINGERPRINT),
      producer_workflow: PRODUCER_WORKFLOW,
      collector_commit: COLLECTOR_COMMIT,
    };
    const pr: ProposalPullRequestSummary = {
      number: 1,
      state: "open",
      headRef: marker.branch_name,
      headRepoFullName: REPO,
      body: renderProposalMarker(marker),
    };
    expect(authenticateProposalMarker(marker, pr, expected)).toBe(true);
    expect(findMatchingProposalPullRequest([pr], FINGERPRINT, expected)).toBe(pr);
  });
});

describe("buildAppendedMemoryContent", () => {
  test("preserves existing bytes and appends exactly the rendered entry", () => {
    const entry = makeMemoryEntry();
    const result = buildAppendedMemoryContent(EXISTING_MEMORY_CONTENT, entry);
    expect(result.startsWith(EXISTING_MEMORY_CONTENT)).toBe(true);
    expect(result).toContain(renderMemoryEntryMarkdown(entry));
  });
});

describe("buildProposalCommitMessage", () => {
  test("embeds the candidate fingerprint and collector commit for traceability", () => {
    const marker: ProposalMarker = {
      repo: REPO,
      target_memory_path: ".jules/bolt.md",
      candidate_fingerprint: FINGERPRINT,
      base_branch: BASE_BRANCH,
      branch_name: computeProposalBranchName("bolt", FINGERPRINT),
      producer_workflow: PRODUCER_WORKFLOW,
      collector_commit: COLLECTOR_COMMIT,
    };
    const message = buildProposalCommitMessage(makeMemoryEntry(), marker);
    expect(message).toContain(FINGERPRINT);
    expect(message).toContain(COLLECTOR_COMMIT);
  });
});

describe("createMemoryProposal", () => {
  test("creates one branch and one PR changing only the selected memory file", async () => {
    const client = new FakeGitHubClient();
    const result = await createMemoryProposal(client, makeInput(), {
      maxAttempts: DEFAULT_PROPOSAL_MAX_ATTEMPTS,
      runMutation: fastRunMutation,
    });

    expect(result.status).toBe("created");
    if (result.status !== "created") throw new Error("expected created");
    expect(result.branchName).toBe(computeProposalBranchName("bolt", FINGERPRINT));
    expect(result.commitSha).toBe(NEW_COMMIT_SHA);
    expect(result.pullRequestNumber).toBeGreaterThan(0);

    // Exactly one blob/tree/commit/branch/PR creation call each.
    expect(client.calls.filter((c) => c.startsWith("createBlob:")).length).toBe(1);
    expect(client.calls.filter((c) => c.startsWith("createTree:")).length).toBe(1);
    expect(client.calls.filter((c) => c.startsWith("createCommit:")).length).toBe(1);
    expect(client.calls.filter((c) => c.startsWith("createRef:")).length).toBe(1);
    expect(client.calls.filter((c) => c.startsWith("createPullRequest:")).length).toBe(1);

    // Only the single target path is ever touched by the tree call.
    const treeCall = client.calls.find((c) => c.startsWith("createTree:"))!;
    expect(treeCall).toContain(":.jules/bolt.md:");
  });

  test("is idempotent: concurrent identical runs converge on one proposal", async () => {
    const client = new FakeGitHubClient();
    const first = await createMemoryProposal(client, makeInput(), { runMutation: fastRunMutation });
    expect(first.status).toBe("created");

    const second = await createMemoryProposal(client, makeInput(), { runMutation: fastRunMutation });
    expect(second.status).toBe("existing");
    if (second.status !== "existing") throw new Error("expected existing");
    if (first.status !== "created") throw new Error("expected created");
    expect(second.pullRequestNumber).toBe(first.pullRequestNumber);

    // No second blob/tree/commit/branch was ever created for the same fingerprint.
    expect(client.calls.filter((c) => c.startsWith("createBlob:")).length).toBe(1);
    expect(client.calls.filter((c) => c.startsWith("createRef:")).length).toBe(1);
  });

  test("disjoint personas/fingerprints proceed independently", async () => {
    const client = new FakeGitHubClient();
    client.refs.set(`heads/${BASE_BRANCH}`, { sha: BASE_HEAD_SHA });
    client.files.set(`.jules/sentinel.md@${BASE_HEAD_SHA}`, {
      content: "# Sentinel learnings\n",
      sha: "9".repeat(40),
    });

    const boltResult = await createMemoryProposal(client, makeInput(), { runMutation: fastRunMutation });
    const sentinelResult = await createMemoryProposal(
      client,
      makeInput({
        candidate: makeCandidate({
          persona: "sentinel",
          target_memory_path: ".jules/sentinel.md",
          candidate_fingerprint: "d".repeat(64),
        }),
        entry: makeMemoryEntry({
          persona: "sentinel",
          candidate_fingerprint: "d".repeat(64),
          memory_blob_sha: "9".repeat(40),
          entry_id: "d".repeat(64).slice(0, 12),
        }),
      }),
      { runMutation: fastRunMutation }
    );

    expect(boltResult.status).toBe("created");
    expect(sentinelResult.status).toBe("created");
    if (boltResult.status === "created" && sentinelResult.status === "created") {
      expect(boltResult.branchName).not.toBe(sentinelResult.branchName);
      expect(boltResult.pullRequestNumber).not.toBe(sentinelResult.pullRequestNumber);
    }
  });

  test("recovers from a branch-creation timeout via lookup rather than a blind duplicate mutation", async () => {
    const client = new FakeGitHubClient();
    client.configureCreateRefFailures(1, true);

    const result = await createMemoryProposal(client, makeInput(), { runMutation: fastRunMutation });

    expect(result.status).toBe("created");
    // createRef was attempted twice (first timed out, second succeeded/found),
    // but the branch only ends up created once and there is exactly one PR.
    expect(client.calls.filter((c) => c.startsWith("createRef:")).length).toBe(2);
    expect(client.calls.filter((c) => c.startsWith("createPullRequest:")).length).toBe(1);
  });

  test("recovers from a PR-creation timeout via lookup rather than creating a duplicate PR", async () => {
    const client = new FakeGitHubClient();
    client.configureCreatePullRequestFailures(1, true);

    const result = await createMemoryProposal(client, makeInput(), { runMutation: fastRunMutation });

    expect(result.status).toBe("created");
    expect(client.calls.filter((c) => c.startsWith("createPullRequest:")).length).toBe(2);
    // Only one PR object should ever have been recorded for the branch.
    const branchName = computeProposalBranchName("bolt", FINGERPRINT);
    expect(client.pullRequestsByBranch.get(branchName)?.length).toBe(1);
  });

  test("a non-retryable branch-creation failure is not recovered and hard-fails", async () => {
    const client = new FakeGitHubClient();
    client.configureCreateRefFailures(1, false);

    await expect(
      createMemoryProposal(client, makeInput(), { runMutation: fastRunMutation })
    ).rejects.toThrow();
  });

  test("rejects when the base branch cannot be found (live base revalidation)", async () => {
    const client = new FakeGitHubClient();
    client.refs.delete(`heads/${BASE_BRANCH}`);

    const result = await createMemoryProposal(client, makeInput(), { runMutation: fastRunMutation });
    expect(result.status).toBe("rejected");
    if (result.status === "rejected") {
      expect(result.reason).toContain("base branch");
    }
  });

  test("rejects a stale target where the live blob SHA no longer matches memory_blob_sha", async () => {
    const client = new FakeGitHubClient();
    client.files.set(`.jules/bolt.md@${BASE_HEAD_SHA}`, {
      content: EXISTING_MEMORY_CONTENT,
      sha: "7".repeat(40),
    });

    const result = await createMemoryProposal(client, makeInput(), { runMutation: fastRunMutation });
    expect(result.status).toBe("rejected");
    if (result.status === "rejected") {
      expect(result.reason).toContain("stale target");
    }
    // No mutation should ever be attempted once the stale-target guard fails.
    expect(client.calls.some((c) => c.startsWith("createBlob:"))).toBe(false);
  });

  test("rejects when the target memory file does not exist at the live base revision", async () => {
    const client = new FakeGitHubClient();
    client.files.delete(`.jules/bolt.md@${BASE_HEAD_SHA}`);

    const result = await createMemoryProposal(client, makeInput(), { runMutation: fastRunMutation });
    expect(result.status).toBe("rejected");
    if (result.status === "rejected") {
      expect(result.reason).toContain("does not exist");
    }
  });

  test("rejects a symlinked target tree entry (mode 120000) instead of silently converting it to a regular file", async () => {
    const client = new FakeGitHubClient();
    client.treeEntries.set(BASE_TREE_SHA, [
      { path: ".jules/bolt.md", mode: "120000", type: "blob", sha: EXISTING_BLOB_SHA },
    ]);

    const result = await createMemoryProposal(client, makeInput(), { runMutation: fastRunMutation });
    expect(result.status).toBe("rejected");
    if (result.status === "rejected") {
      expect(result.reason).toContain("not an ordinary regular file");
    }
    // No mutation should ever be attempted once the tree-mode guard fails.
    expect(client.calls.some((c) => c.startsWith("createBlob:"))).toBe(false);
  });

  test("rejects an executable target tree entry (mode 100755) instead of silently converting it to a regular file", async () => {
    const client = new FakeGitHubClient();
    client.treeEntries.set(BASE_TREE_SHA, [
      { path: ".jules/bolt.md", mode: "100755", type: "blob", sha: EXISTING_BLOB_SHA },
    ]);

    const result = await createMemoryProposal(client, makeInput(), { runMutation: fastRunMutation });
    expect(result.status).toBe("rejected");
    if (result.status === "rejected") {
      expect(result.reason).toContain("not an ordinary regular file");
    }
    expect(client.calls.some((c) => c.startsWith("createBlob:"))).toBe(false);
  });

  test("rejects when the target path is missing entirely from the base tree, even though the Contents API returned content", async () => {
    const client = new FakeGitHubClient();
    client.treeEntries.set(BASE_TREE_SHA, []);

    const result = await createMemoryProposal(client, makeInput(), { runMutation: fastRunMutation });
    expect(result.status).toBe("rejected");
    if (result.status === "rejected") {
      expect(result.reason).toContain("was not found in the base tree");
    }
    expect(client.calls.some((c) => c.startsWith("createBlob:"))).toBe(false);
  });

  test("accepts an ordinary regular file tree entry (mode 100644) and proceeds to mutation", async () => {
    const client = new FakeGitHubClient();
    const result = await createMemoryProposal(client, makeInput(), { runMutation: fastRunMutation });
    expect(result.status).toBe("created");
    expect(client.calls.some((c) => c.startsWith("getTreeEntries:"))).toBe(true);
    expect(client.calls.some((c) => c.startsWith("createBlob:"))).toBe(true);
  });

  test("rejects a malformed candidate fingerprint before any GitHub call", async () => {
    const client = new FakeGitHubClient();
    const result = await createMemoryProposal(
      client,
      makeInput({ candidate: makeCandidate({ candidate_fingerprint: "not-hex" }) }),
      { runMutation: fastRunMutation }
    );
    expect(result.status).toBe("rejected");
    expect(client.calls.length).toBe(0);
  });

  test("rejects a malformed collector_commit before any GitHub call", async () => {
    const client = new FakeGitHubClient();
    const result = await createMemoryProposal(client, makeInput({ collectorCommit: "not-a-sha" }), {
      runMutation: fastRunMutation,
    });
    expect(result.status).toBe("rejected");
    expect(client.calls.length).toBe(0);
  });

  test("rejects when entry.candidate_fingerprint disagrees with candidate.candidate_fingerprint", async () => {
    const client = new FakeGitHubClient();
    const result = await createMemoryProposal(
      client,
      makeInput({ entry: makeMemoryEntry({ candidate_fingerprint: "d".repeat(64) }) }),
      { runMutation: fastRunMutation }
    );
    expect(result.status).toBe("rejected");
    expect(client.calls.length).toBe(0);
  });

  test("rejects when entry.persona disagrees with candidate.persona", async () => {
    const client = new FakeGitHubClient();
    const result = await createMemoryProposal(
      client,
      makeInput({ entry: makeMemoryEntry({ persona: "sentinel" }) }),
      { runMutation: fastRunMutation }
    );
    expect(result.status).toBe("rejected");
    expect(client.calls.length).toBe(0);
  });

  test("handles an existing closed superseded proposal by treating it as existing, not re-creating", async () => {
    const client = new FakeGitHubClient();
    const marker: ProposalMarker = {
      repo: REPO,
      target_memory_path: ".jules/bolt.md",
      candidate_fingerprint: FINGERPRINT,
      base_branch: BASE_BRANCH,
      branch_name: computeProposalBranchName("bolt", FINGERPRINT),
      producer_workflow: PRODUCER_WORKFLOW,
      collector_commit: COLLECTOR_COMMIT,
    };
    client.pullRequestsByBranch.set(marker.branch_name, [
      {
        number: 555,
        state: "closed",
        headRef: marker.branch_name,
        headRepoFullName: REPO,
        body: renderProposalMarker(marker),
      },
    ]);

    const result = await createMemoryProposal(client, makeInput(), { runMutation: fastRunMutation });
    expect(result.status).toBe("existing");
    if (result.status === "existing") {
      expect(result.pullRequestNumber).toBe(555);
    }
    expect(client.calls.some((c) => c.startsWith("createBlob:"))).toBe(false);
    expect(client.calls.some((c) => c.startsWith("createRef:"))).toBe(false);
  });

  test("ignores a same-branch PR with no parseable marker (human-edited proposal) for lookup purposes", async () => {
    const client = new FakeGitHubClient();
    const branchName = computeProposalBranchName("bolt", FINGERPRINT);
    client.pullRequestsByBranch.set(branchName, [
      { number: 999, state: "open", headRef: branchName, body: "a human rewrote this PR body entirely" },
    ]);

    // The branch ref does not exist yet in this fixture (only the PR list
    // entry is a human artifact), so proposal creation should proceed and
    // not be fooled by the marker-less PR into skipping.
    const result = await createMemoryProposal(client, makeInput(), { runMutation: fastRunMutation });
    expect(result.status).toBe("created");
  });

  test("fails closed when the branch already exists without a matching PR marker", async () => {
    const client = new FakeGitHubClient();
    const branchName = computeProposalBranchName("bolt", FINGERPRINT);
    client.refs.set(`heads/${branchName}`, { sha: "already-there".padEnd(40, "0") });

    const result = await createMemoryProposal(client, makeInput(), { runMutation: fastRunMutation });
    expect(result.status).toBe("rejected");
    if (result.status === "rejected") {
      expect(result.reason).toContain("branch already exists");
    }
    expect(client.calls.some((c) => c.startsWith("createRef:"))).toBe(false);
  });

  test("never calls any merge, issue, label, or session-mutation API", async () => {
    const client = new FakeGitHubClient();
    await createMemoryProposal(client, makeInput(), { runMutation: fastRunMutation });

    const forbiddenSubstrings = ["merge", "issue", "label", "session", "checkout", "exec"];
    for (const call of client.calls) {
      for (const forbidden of forbiddenSubstrings) {
        expect(call.toLowerCase()).not.toContain(forbidden);
      }
    }

    // Structural guarantee: the client interface itself has no such methods.
    const clientMethodNames = Object.getOwnPropertyNames(FakeGitHubClient.prototype);
    for (const forbidden of forbiddenSubstrings) {
      expect(clientMethodNames.some((name) => name.toLowerCase().includes(forbidden))).toBe(false);
    }
  });
});
