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
import { clusterEnvelopes, determineEligibility, eligibleClusters, type ClusterMember } from "./cluster.ts";
import { computeCandidateFingerprintAtCurrentVersion } from "./fingerprints.ts";
import type { ClosureCause, EvidenceEnvelope, OutcomeState, Persona } from "./types.ts";

const REPO = "wryenmeek/knowledgebase";
const SHA_A = "a".repeat(40);
const SHA_B = "b".repeat(40);
const AS_OF = "2026-08-10T00:00:00.000Z";

function makeEnvelope(
  prNumber: number,
  outcome: OutcomeState,
  closureCause: ClosureCause | null,
  overrides: Partial<EvidenceEnvelope> = {}
): EvidenceEnvelope {
  return {
    repo: REPO,
    pr_number: prNumber,
    persona: "bolt",
    outcome,
    closure_cause: closureCause,
    base_sha: SHA_A,
    evaluated_head_sha: SHA_B,
    merge_sha: outcome === "merged" ? "c".repeat(40) : null,
    author_id: "google-labs-jules[bot]",
    session_id: "session-1",
    base_repo_full_name: REPO,
    head_repo_full_name: REPO,
    event_ids: outcome === "open" ? [] : ["event-1"],
    collected_at: AS_OF,
    as_of: AS_OF,
    taxonomy_version: 1,
    evidence_digest: "d".repeat(64),
    ...overrides,
  };
}

function makeMember(
  envelope: EvidenceEnvelope,
  overrides: Partial<Omit<ClusterMember, "envelope">> = {}
): ClusterMember {
  return {
    envelope,
    mechanism: "eager Path.resolve() in hot loop",
    affectedScope: ["scripts/kb/lint_wiki.py"],
    normalizedRule: "avoid eager resolve() calls in hot loops",
    ...overrides,
  };
}

describe("determineEligibility", () => {
  test("a single merged PR is eligible as a technical lesson", () => {
    const reason = determineEligibility([makeEnvelope(1, "merged", null)]);
    expect(reason).toBe("merged_lesson");
  });

  test("a single closed_unmerged PR is never eligible on its own", () => {
    const reason = determineEligibility([
      makeEnvelope(1, "closed_unmerged", "test_or_policy_failure"),
    ]);
    expect(reason).toBeNull();
  });

  test("two distinct closed_unmerged PRs with a non-unknown cause are eligible", () => {
    const reason = determineEligibility([
      makeEnvelope(1, "closed_unmerged", "test_or_policy_failure"),
      makeEnvelope(2, "closed_unmerged", "test_or_policy_failure"),
    ]);
    expect(reason).toBe("closed_cause_prevention");
  });

  test("two closed_unmerged records for the same PR number do not satisfy the distinct-PR requirement", () => {
    const reason = determineEligibility([
      makeEnvelope(1, "closed_unmerged", "test_or_policy_failure"),
      makeEnvelope(1, "closed_unmerged", "test_or_policy_failure"),
    ]);
    expect(reason).toBeNull();
  });

  test("unknown closure cause never counts toward the two-distinct-PR threshold", () => {
    const reason = determineEligibility([
      makeEnvelope(1, "closed_unmerged", "unknown"),
      makeEnvelope(2, "closed_unmerged", "unknown"),
    ]);
    expect(reason).toBeNull();
  });

  test("ambiguous records never count toward eligibility", () => {
    const reason = determineEligibility([
      makeEnvelope(1, "ambiguous", null),
      makeEnvelope(2, "ambiguous", null),
    ]);
    expect(reason).toBeNull();
  });

  test("a mix of one unknown-cause closure and one open PR is not eligible", () => {
    const reason = determineEligibility([
      makeEnvelope(1, "closed_unmerged", "unknown"),
      makeEnvelope(2, "open", null),
    ]);
    expect(reason).toBeNull();
  });

  test("merged_lesson takes precedence when both conditions hold", () => {
    const reason = determineEligibility([
      makeEnvelope(1, "merged", null),
      makeEnvelope(2, "closed_unmerged", "scope_creep"),
      makeEnvelope(3, "closed_unmerged", "scope_creep"),
    ]);
    expect(reason).toBe("merged_lesson");
  });

  test("duplicate_or_superseded closures are still a valid non-unknown cause for prevention-rule eligibility", () => {
    const reason = determineEligibility([
      makeEnvelope(1, "closed_unmerged", "duplicate_or_superseded"),
      makeEnvelope(2, "closed_unmerged", "duplicate_or_superseded"),
    ]);
    expect(reason).toBe("closed_cause_prevention");
  });
});

describe("clusterEnvelopes", () => {
  test("groups members sharing the same semantic key into one cluster", () => {
    const clusters = clusterEnvelopes([
      makeMember(makeEnvelope(1, "merged", null)),
      makeMember(makeEnvelope(2, "closed_unmerged", "scope_creep")),
    ]);
    expect(clusters).toHaveLength(1);
    expect(clusters[0]!.members).toHaveLength(2);
  });

  test("distinct mechanism/scope/rule produce distinct clusters", () => {
    const clusters = clusterEnvelopes([
      makeMember(makeEnvelope(1, "merged", null)),
      makeMember(makeEnvelope(2, "merged", null), { mechanism: "different mechanism" }),
    ]);
    expect(clusters).toHaveLength(2);
  });

  test("distinct persona produces a distinct cluster even for identical rule text", () => {
    const clusters = clusterEnvelopes([
      makeMember(makeEnvelope(1, "merged", null, { persona: "bolt" })),
      makeMember(makeEnvelope(2, "merged", null, { persona: "sentinel" })),
    ]);
    expect(clusters).toHaveLength(2);
    const personas = clusters.map((cluster) => cluster.persona).sort();
    expect(personas).toEqual(["bolt", "sentinel"]);
  });

  test("cluster fingerprint matches computeCandidateFingerprintAtCurrentVersion for the same components", () => {
    const clusters = clusterEnvelopes([makeMember(makeEnvelope(1, "merged", null))]);
    const expected = computeCandidateFingerprintAtCurrentVersion({
      persona: "bolt" as Persona,
      mechanism: "eager Path.resolve() in hot loop",
      affectedScope: ["scripts/kb/lint_wiki.py"],
      normalizedRule: "avoid eager resolve() calls in hot loops",
      taxonomyVersion: 1,
      targetMemoryPath: ".jules/bolt.md",
    });
    expect(clusters[0]!.candidate_fingerprint).toBe(expected);
  });

  test("cluster eligibility mirrors determineEligibility for the same member set", () => {
    const clusters = clusterEnvelopes([
      makeMember(makeEnvelope(1, "closed_unmerged", "test_or_policy_failure")),
    ]);
    expect(clusters[0]!.eligible).toBe(false);
    expect(clusters[0]!.eligibility_reason).toBeNull();

    const eligibleClustersResult = clusterEnvelopes([
      makeMember(makeEnvelope(1, "closed_unmerged", "test_or_policy_failure")),
      makeMember(makeEnvelope(2, "closed_unmerged", "test_or_policy_failure")),
    ]);
    expect(eligibleClustersResult[0]!.eligible).toBe(true);
    expect(eligibleClustersResult[0]!.eligibility_reason).toBe("closed_cause_prevention");
  });

  test("output order is deterministic and independent of input order", () => {
    const memberA = makeMember(makeEnvelope(1, "merged", null), { mechanism: "mechanism a" });
    const memberB = makeMember(makeEnvelope(2, "merged", null), { mechanism: "mechanism b" });

    const forward = clusterEnvelopes([memberA, memberB]).map((cluster) => cluster.candidate_fingerprint);
    const reversed = clusterEnvelopes([memberB, memberA]).map((cluster) => cluster.candidate_fingerprint);
    expect(forward).toEqual(reversed);
  });

  test("affected_scope input order does not change the resulting cluster (normalized before hashing)", () => {
    const clustersForward = clusterEnvelopes([
      makeMember(makeEnvelope(1, "merged", null), { affectedScope: ["a.py", "b.py"] }),
    ]);
    const clustersReversed = clusterEnvelopes([
      makeMember(makeEnvelope(1, "merged", null), { affectedScope: ["b.py", "a.py"] }),
    ]);
    expect(clustersForward[0]!.candidate_fingerprint).toBe(clustersReversed[0]!.candidate_fingerprint);
  });

  test("empty input yields an empty cluster list", () => {
    expect(clusterEnvelopes([])).toEqual([]);
  });
});

describe("eligibleClusters", () => {
  test("filters out ineligible clusters", () => {
    const clusters = clusterEnvelopes([
      makeMember(makeEnvelope(1, "merged", null), { mechanism: "eligible mechanism" }),
      makeMember(makeEnvelope(2, "closed_unmerged", "unknown"), { mechanism: "ineligible mechanism" }),
    ]);
    const result = eligibleClusters(clusters);
    expect(result).toHaveLength(1);
    expect(result[0]!.mechanism).toBe("eligible mechanism");
  });
});
