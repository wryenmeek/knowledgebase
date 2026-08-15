import { afterEach, describe, expect, test } from "bun:test";
import { PRODUCER_WORKFLOW } from "./collect-and-report-cli.ts";
import {
  RestProposeGitHubClient,
  authenticateProposalMarker,
  sessionVerifierFromArtifact,
  validateArtifactBindings,
} from "./propose-cli.ts";
import type { EvidenceEnvelope, ProposalMarker } from "./types.ts";
import type { ProposalPullRequestSummary } from "./propose.ts";

const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
});

const SHA = "a".repeat(40);
const REPO = "wryenmeek/knowledgebase";

function makeEnvelope(overrides: Partial<EvidenceEnvelope> = {}): EvidenceEnvelope {
  return {
    repo: REPO,
    pr_number: 100,
    persona: "bolt",
    outcome: "merged",
    closure_cause: null,
    base_sha: SHA,
    evaluated_head_sha: "b".repeat(40),
    merge_sha: SHA,
    author_id: "google-labs-jules[bot]",
    session_id: "session-1",
    base_repo_full_name: REPO,
    head_repo_full_name: REPO,
    event_ids: ["event-1"],
    created_at: "2026-08-01T00:00:00.000Z",
    collected_at: "2026-08-09T00:00:00.000Z",
    as_of: "2026-08-10T00:00:00.000Z",
    reverted: false,
    taxonomy_version: 1,
    evidence_digest: "d".repeat(64),
    ...overrides,
  };
}

function makeArtifact(overrides: Record<string, unknown> = {}) {
  const artifact = {
    producer_workflow: PRODUCER_WORKFLOW,
    collector_commit: SHA,
    collector_run_id: "123",
    base_sha: SHA,
    generated_at: new Date().toISOString(),
    expires_at: new Date(Date.now() + 60_000).toISOString(),
    artifact_digest: "",
    report: { complete: true, digest: "b".repeat(64), envelopes: [], session_verification: "authoritative" },
    ...overrides,
  };
  const payload = JSON.stringify({
    report_digest: artifact.report.digest,
    session_verification: artifact.report.session_verification ?? "none",
    producer_workflow: artifact.producer_workflow,
    collector_commit: artifact.collector_commit,
    collector_run_id: artifact.collector_run_id,
    base_sha: artifact.base_sha,
    generated_at: artifact.generated_at,
    expires_at: artifact.expires_at,
  });
  const hasher = new Bun.CryptoHasher("sha256");
  hasher.update(payload);
  artifact.artifact_digest = hasher.digest("hex");
  return artifact;
}

describe("validateArtifactBindings", () => {
  test("accepts a current complete artifact", () => {
    expect(() => validateArtifactBindings(makeArtifact(), SHA, "123")).not.toThrow();
  });

  test("rejects a foreign producer workflow", () => {
    expect(() =>
      validateArtifactBindings(makeArtifact({ producer_workflow: "other.yml" }), SHA, "123")
    ).toThrow(/producer_workflow mismatch/);
  });

  test("rejects a stale collector run", () => {
    expect(() => validateArtifactBindings(makeArtifact(), SHA, "999")).toThrow(/run_id mismatch/);
  });

  test("rejects a non-main base revision", () => {
    expect(() =>
      validateArtifactBindings(makeArtifact({ base_sha: "c".repeat(40) }), SHA, "123")
    ).toThrow(/base_sha mismatch/);
  });

  test("rejects incomplete evidence", () => {
    expect(() =>
      validateArtifactBindings(
        makeArtifact({ report: { complete: false, digest: "b".repeat(64), envelopes: [] } }),
        SHA,
        "123"
      )
    ).toThrow(/incomplete/);
  });

  test("rejects a tampered artifact digest", () => {
    const artifact = makeArtifact();
    artifact.artifact_digest = "d".repeat(64);
    expect(() => validateArtifactBindings(artifact, SHA, "123")).toThrow(/artifact_digest/);
  });

  test('rejects a "none" session_verification (collector used NullSessionVerifier)', () => {
    expect(() =>
      validateArtifactBindings(
        makeArtifact({
          report: { complete: true, digest: "b".repeat(64), envelopes: [], session_verification: "none" },
        }),
        SHA,
        "123"
      )
    ).toThrow(/propose mode is unavailable/);
  });

  test("rejects a missing session_verification field (older artifact schema)", () => {
    expect(() =>
      validateArtifactBindings(
        makeArtifact({ report: { complete: true, digest: "b".repeat(64), envelopes: [] } }),
        SHA,
        "123"
      )
    ).toThrow(/propose mode is unavailable/);
  });

  test('accepts "authoritative" session_verification', () => {
    expect(() =>
      validateArtifactBindings(
        makeArtifact({
          report: {
            complete: true,
            digest: "b".repeat(64),
            envelopes: [],
            session_verification: "authoritative",
          },
        }),
        SHA,
        "123"
      )
    ).not.toThrow();
  });

  test("rejects an artifact whose session_verification was mutated after artifact_digest was computed", () => {
    // Simulates an actor with artifact write access flipping a "none"
    // (honest, propose-unavailable) artifact to "authoritative" post-hoc,
    // without recomputing artifact_digest to match. Because
    // session_verification is bound into the digest payload, this must be
    // caught by the tamper-detection check, not accepted on the mutated
    // value alone.
    const artifact = makeArtifact({
      report: { complete: true, digest: "b".repeat(64), envelopes: [], session_verification: "none" },
    });
    artifact.report.session_verification = "authoritative";
    expect(() => validateArtifactBindings(artifact, SHA, "123")).toThrow(/artifact_digest/);
  });
});

describe("sessionVerifierFromArtifact (persona-scoped evidence reuse guard)", () => {
  test("returns the matching session when persona, repo, PR number, and head sha all agree", () => {
    const verifier = sessionVerifierFromArtifact([makeEnvelope({ persona: "bolt", session_id: "session-1" })]);
    const result = verifier.verify({
      repoFullName: REPO,
      prNumber: 100,
      authorId: "google-labs-jules[bot]",
      headRepoFullName: REPO,
      headSha: "b".repeat(40),
      persona: "bolt",
    });
    expect(result).toEqual({ sessionId: "session-1", persona: "bolt" });
  });

  test("refuses to reuse a session that was verified for a different persona (no cross-persona evidence reuse)", () => {
    const verifier = sessionVerifierFromArtifact([makeEnvelope({ persona: "sentinel", session_id: "session-1" })]);
    const result = verifier.verify({
      repoFullName: REPO,
      prNumber: 100,
      authorId: "google-labs-jules[bot]",
      headRepoFullName: REPO,
      headSha: "b".repeat(40),
      persona: "bolt",
    });
    expect(result).toBeNull();
  });
});

describe("RestProposeGitHubClient JSON body requests", () => {
  test("createBlob sends Content-Type: application/json", async () => {
    let capturedHeaders: Record<string, string> = {};
    globalThis.fetch = (async (_input: RequestInfo | URL, init?: RequestInit) => {
      capturedHeaders = Object.fromEntries(
        new Headers(init?.headers as HeadersInit | undefined).entries()
      );
      return new Response(JSON.stringify({ sha: "b".repeat(40) }), { status: 201 });
    }) as typeof fetch;

    const client = new RestProposeGitHubClient("https://api.github.test/repos/owner/repo", {
      Authorization: "******",
    });
    await client.createBlob("hello world");

    expect(capturedHeaders["content-type"]).toBe("application/json");
  });

  test("createPullRequest sends Content-Type: application/json", async () => {
    let capturedHeaders: Record<string, string> = {};
    globalThis.fetch = (async (_input: RequestInfo | URL, init?: RequestInit) => {
      capturedHeaders = Object.fromEntries(
        new Headers(init?.headers as HeadersInit | undefined).entries()
      );
      return new Response(JSON.stringify({ number: 1, state: "open", body: "body" }), { status: 201 });
    }) as typeof fetch;

    const client = new RestProposeGitHubClient("https://api.github.test/repos/owner/repo", {
      Authorization: "******",
    });
    await client.createPullRequest({
      title: "t",
      head: "h",
      base: "main",
      body: "body",
    });

    expect(capturedHeaders["content-type"]).toBe("application/json");
  });

  test("getRef (GET, no body) does not set Content-Type", async () => {
    let capturedHeaders: Record<string, string> = {};
    globalThis.fetch = (async (_input: RequestInfo | URL, init?: RequestInit) => {
      capturedHeaders = Object.fromEntries(
        new Headers(init?.headers as HeadersInit | undefined).entries()
      );
      return new Response(null, { status: 404 });
    }) as typeof fetch;

    const client = new RestProposeGitHubClient("https://api.github.test/repos/owner/repo", {
      Authorization: "******",
    });
    const result = await client.getRef("heads/main");

    expect(capturedHeaders["content-type"]).toBeUndefined();
    expect(result).toBeNull();
  });

  test("does not silently drop caller-supplied headers passed as a Headers instance", async () => {
    // request() is private, but privacy is compile-time only; exercise it
    // directly to guard the HeadersInit normalization regardless of
    // whether any current public method passes a Headers instance.
    let capturedHeaders: Record<string, string> = {};
    globalThis.fetch = (async (_input: RequestInfo | URL, init?: RequestInit) => {
      capturedHeaders = Object.fromEntries(
        new Headers(init?.headers as HeadersInit | undefined).entries()
      );
      return new Response(null, { status: 200 });
    }) as typeof fetch;

    const client = new RestProposeGitHubClient("https://api.github.test/repos/owner/repo", {
      Authorization: "******",
    });
    const callerHeaders = new Headers({ "X-Custom-Header": "custom-value" });
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    await (client as any).request("/some/path", { headers: callerHeaders });

    expect(capturedHeaders["x-custom-header"]).toBe("custom-value");
    // The instance-level Authorization header must still be present.
    expect(capturedHeaders["authorization"]).toBeDefined();
  });
});

describe("RestProposeGitHubClient.getTreeEntries truncated-response guard", () => {
  test("fails closed when the GitHub API reports a truncated recursive tree", async () => {
    globalThis.fetch = (async () =>
      new Response(
        JSON.stringify({
          truncated: true,
          tree: [{ path: ".jules/bolt.md", mode: "100644", type: "blob", sha: "a".repeat(40) }],
        }),
        { status: 200 }
      )) as typeof fetch;

    const client = new RestProposeGitHubClient("https://api.github.test/repos/owner/repo", {
      Authorization: "******",
    });

    await expect(client.getTreeEntries("c".repeat(40))).rejects.toThrow(/truncated/i);
  });

  test("returns entries normally when the tree is not truncated", async () => {
    globalThis.fetch = (async () =>
      new Response(
        JSON.stringify({
          truncated: false,
          tree: [{ path: ".jules/bolt.md", mode: "100644", type: "blob", sha: "a".repeat(40) }],
        }),
        { status: 200 }
      )) as typeof fetch;

    const client = new RestProposeGitHubClient("https://api.github.test/repos/owner/repo", {
      Authorization: "******",
    });

    const entries = await client.getTreeEntries("c".repeat(40));
    expect(entries).toEqual([
      { path: ".jules/bolt.md", mode: "100644", type: "blob", sha: "a".repeat(40) },
    ]);
  });
});

describe("RestProposeGitHubClient HTTP status preservation on mutation failure", () => {
  test("createBlob preserves the origin HTTP status on a failed response, instead of losing it in an opaque Error", async () => {
    globalThis.fetch = (async () => new Response("service unavailable", { status: 503 })) as typeof fetch;

    const client = new RestProposeGitHubClient("https://api.github.test/repos/owner/repo", {
      Authorization: "******",
    });

    let caught: unknown;
    try {
      await client.createBlob("hello world");
    } catch (error) {
      caught = error;
    }

    expect(caught).toBeInstanceOf(Error);
    // classifyMutationError (../github/mutation-diagnostics.ts) reads
    // error.status to classify retryability; a plain Error whose status
    // is only embedded in the message text is invisible to that check
    // and would be misclassified as the non-retryable "unknown" category.
    expect((caught as { status?: number }).status).toBe(503);
  });

  test("createPullRequest preserves a 429 status for rate-limit retry classification", async () => {
    globalThis.fetch = (async () => new Response("rate limited", { status: 429 })) as typeof fetch;

    const client = new RestProposeGitHubClient("https://api.github.test/repos/owner/repo", {
      Authorization: "******",
    });

    let caught: unknown;
    try {
      await client.createPullRequest({ title: "t", head: "h", base: "main", body: "body" });
    } catch (error) {
      caught = error;
    }

    expect((caught as { status?: number }).status).toBe(429);
  });

  test("createTree preserves a 502 status", async () => {
    globalThis.fetch = (async () => new Response("bad gateway", { status: 502 })) as typeof fetch;

    const client = new RestProposeGitHubClient("https://api.github.test/repos/owner/repo", {
      Authorization: "******",
    });

    let caught: unknown;
    try {
      await client.createTree("a".repeat(40), ".jules/bolt.md", "b".repeat(40));
    } catch (error) {
      caught = error;
    }

    expect((caught as { status?: number }).status).toBe(502);
  });

  test("createCommit and createRef also preserve the origin status", async () => {
    globalThis.fetch = (async () => new Response("bad gateway", { status: 502 })) as typeof fetch;
    const client = new RestProposeGitHubClient("https://api.github.test/repos/owner/repo", {
      Authorization: "******",
    });

    let commitCaught: unknown;
    try {
      await client.createCommit("msg", "a".repeat(40), "b".repeat(40));
    } catch (error) {
      commitCaught = error;
    }
    expect((commitCaught as { status?: number }).status).toBe(502);

    let refCaught: unknown;
    try {
      await client.createRef("jules-memory/x", "a".repeat(40));
    } catch (error) {
      refCaught = error;
    }
    expect((refCaught as { status?: number }).status).toBe(502);
  });
});

describe("authenticateProposalMarker (dedup marker forgery guard)", () => {
  function makeMarker(overrides: Partial<ProposalMarker> = {}): ProposalMarker {
    return {
      repo: REPO,
      target_memory_path: ".jules/bolt.md",
      candidate_fingerprint: "f".repeat(64),
      base_branch: "main",
      branch_name: "jules-memory/bolt-abc123",
      producer_workflow: PRODUCER_WORKFLOW,
      collector_commit: SHA,
      ...overrides,
    };
  }

  function makePr(
    overrides: Partial<Pick<ProposalPullRequestSummary, "headRef" | "headRepoFullName">> = {}
  ): Pick<ProposalPullRequestSummary, "headRef" | "headRepoFullName"> {
    return {
      headRef: "jules-memory/bolt-abc123",
      headRepoFullName: REPO,
      ...overrides,
    };
  }

  const expected = { repoFullName: REPO, producerWorkflow: PRODUCER_WORKFLOW };

  test("accepts a marker whose repo, branch, producer workflow, and same-repo origin all agree", () => {
    expect(authenticateProposalMarker(makeMarker(), makePr(), expected)).toBe(true);
  });

  test("rejects a marker whose PR originates from a fork (headRepoFullName mismatch)", () => {
    const pr = makePr({ headRepoFullName: "someone-else/knowledgebase" });
    expect(authenticateProposalMarker(makeMarker(), pr, expected)).toBe(false);
  });

  test("rejects a marker whose PR head repo is unknown/unresolvable (null)", () => {
    const pr = makePr({ headRepoFullName: null });
    expect(authenticateProposalMarker(makeMarker(), pr, expected)).toBe(false);
  });

  test("rejects a marker whose PR head repo was never populated by the caller (undefined)", () => {
    const pr = makePr({ headRepoFullName: undefined });
    expect(authenticateProposalMarker(makeMarker(), pr, expected)).toBe(false);
  });

  test("rejects a marker claiming a different repo than this run's own repo", () => {
    const marker = makeMarker({ repo: "someone-else/knowledgebase" });
    expect(authenticateProposalMarker(marker, makePr(), expected)).toBe(false);
  });

  test("rejects a marker whose branch_name disagrees with the PR it was actually read from", () => {
    const marker = makeMarker({ branch_name: "jules-memory/bolt-different" });
    expect(authenticateProposalMarker(marker, makePr(), expected)).toBe(false);
  });

  test("rejects a marker claiming a foreign producer_workflow", () => {
    const marker = makeMarker({ producer_workflow: ".github/workflows/some-other-workflow.yml" });
    expect(authenticateProposalMarker(marker, makePr(), expected)).toBe(false);
  });

  test("rejects a marker with a malformed collector_commit", () => {
    const marker = makeMarker({ collector_commit: "not-a-sha" });
    expect(authenticateProposalMarker(marker, makePr(), expected)).toBe(false);
  });
});
