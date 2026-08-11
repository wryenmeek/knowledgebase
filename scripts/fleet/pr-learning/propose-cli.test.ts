import { describe, expect, test } from "bun:test";
import { PRODUCER_WORKFLOW } from "./collect-and-report-cli.ts";
import { validateArtifactBindings } from "./propose-cli.ts";

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
    report: { complete: true, digest: "b".repeat(64), envelopes: [] },
    ...overrides,
  };
  const payload = JSON.stringify({
    report_digest: artifact.report.digest,
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
});
