import { afterEach, describe, expect, test } from "bun:test";
import { PRODUCER_WORKFLOW } from "./collect-and-report-cli.ts";
import { RestProposeGitHubClient, validateArtifactBindings } from "./propose-cli.ts";

const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
});

const SHA = "a".repeat(40);

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
