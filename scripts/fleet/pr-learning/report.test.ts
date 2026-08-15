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
import { buildCollectionReport } from "./report.ts";
import type { EvidenceEnvelope } from "./types.ts";

const REPO = "wryenmeek/knowledgebase";
const AS_OF = "2026-08-10T00:00:00.000Z";
const SHA = "a".repeat(40);
const DIGEST = "b".repeat(64);

function makeEnvelope(overrides: Partial<EvidenceEnvelope> = {}): EvidenceEnvelope {
  return {
    repo: REPO,
    pr_number: 1,
    persona: "bolt",
    outcome: "merged",
    closure_cause: null,
    base_sha: SHA,
    evaluated_head_sha: SHA,
    merge_sha: SHA,
    author_id: "google-labs-jules[bot]",
    session_id: "session-1",
    base_repo_full_name: REPO,
    head_repo_full_name: REPO,
    event_ids: ["event-1"],
    created_at: "2026-08-01T00:00:00.000Z",
    collected_at: "2026-08-09T00:00:00.000Z",
    as_of: AS_OF,
    reverted: false,
    taxonomy_version: 1,
    evidence_digest: DIGEST,
    ...overrides,
  };
}

function baseOptions() {
  return {
    repo: REPO,
    asOf: AS_OF,
    generatedAt: "2026-08-10T01:00:00.000Z",
    complete: true,
    collectionErrors: [],
  };
}

describe("buildCollectionReport determinism", () => {
  test("regenerating from the same envelope set (same order) yields an identical digest", () => {
    const envelopes = [makeEnvelope({ pr_number: 1 }), makeEnvelope({ pr_number: 2, persona: "sentinel" })];
    const first = buildCollectionReport(envelopes, baseOptions());
    const second = buildCollectionReport(envelopes, baseOptions());
    expect(first.digest).toBe(second.digest);
  });

  test("input array order never changes the digest", () => {
    const a = makeEnvelope({ pr_number: 1 });
    const b = makeEnvelope({ pr_number: 2, persona: "sentinel" });
    const forward = buildCollectionReport([a, b], baseOptions());
    const reversed = buildCollectionReport([b, a], baseOptions());
    expect(forward.digest).toBe(reversed.digest);
  });

  test("generated_at (a non-deterministic wall-clock field) does not affect the digest", () => {
    const envelopes = [makeEnvelope()];
    const first = buildCollectionReport(envelopes, { ...baseOptions(), generatedAt: "2026-08-10T01:00:00.000Z" });
    const second = buildCollectionReport(envelopes, { ...baseOptions(), generatedAt: "2027-01-01T00:00:00.000Z" });
    expect(first.digest).toBe(second.digest);
  });

  test("a changed envelope field changes the digest", () => {
    const withOne = buildCollectionReport([makeEnvelope({ outcome: "merged", closure_cause: null })], baseOptions());
    const withOther = buildCollectionReport(
      [makeEnvelope({ outcome: "closed_unmerged", closure_cause: "unknown" })],
      baseOptions()
    );
    expect(withOne.digest).not.toBe(withOther.digest);
  });
});

describe("buildCollectionReport summary views", () => {
  test("computes merge_rate as merged / (merged + closed_unmerged), excluding open/ambiguous", () => {
    const envelopes = [
      makeEnvelope({ pr_number: 1, outcome: "merged", closure_cause: null }),
      makeEnvelope({ pr_number: 2, outcome: "closed_unmerged", closure_cause: "scope_creep" }),
      makeEnvelope({ pr_number: 3, outcome: "open", closure_cause: null }),
      makeEnvelope({ pr_number: 4, outcome: "ambiguous", closure_cause: null }),
    ];
    const report = buildCollectionReport(envelopes, baseOptions());
    const bolt = report.personas.find((p) => p.persona === "bolt")!;
    expect(bolt.counts).toEqual({ merged: 1, closed_unmerged: 1, open: 1, ambiguous: 1 });
    expect(bolt.merge_rate).toBe(0.5);
  });

  test("merge_rate is null when there are zero merged+closed_unmerged records", () => {
    const report = buildCollectionReport(
      [makeEnvelope({ outcome: "open", closure_cause: null })],
      baseOptions()
    );
    expect(report.personas[0]?.merge_rate).toBeNull();
  });

  test("an incomplete collection is surfaced on the report and never silently treated as complete", () => {
    const report = buildCollectionReport([makeEnvelope()], {
      ...baseOptions(),
      complete: false,
      collectionErrors: ["pull list page 2 request failed: network error"],
    });
    expect(report.complete).toBe(false);
    expect(report.collection_errors.length).toBe(1);
  });

  test("aged_open_count separates old open records from the primary merge-rate signal", () => {
    const report = buildCollectionReport(
      [
        makeEnvelope({
          outcome: "open",
          closure_cause: null,
          created_at: "2026-06-01T00:00:00.000Z", // far older than the 14-day default threshold
        }),
      ],
      baseOptions()
    );
    expect(report.personas[0]?.aged_open_count).toBe(1);
  });

  test("aged_open_count uses created_at, not collected_at (which is always ~now in a real run)", () => {
    const report = buildCollectionReport(
      [
        makeEnvelope({
          outcome: "open",
          closure_cause: null,
          // collected_at pinned to the report's asOf instant, as in a real
          // collection run — must NOT be mistaken for an aged record.
          collected_at: AS_OF,
          created_at: "2026-06-01T00:00:00.000Z",
        }),
      ],
      baseOptions()
    );
    expect(report.personas[0]?.aged_open_count).toBe(1);
  });

  test("a recently opened record with a stale collected_at is not counted as aged", () => {
    const report = buildCollectionReport(
      [
        makeEnvelope({
          outcome: "open",
          closure_cause: null,
          collected_at: "2026-06-01T00:00:00.000Z", // would previously (wrongly) count as aged
          created_at: "2026-08-09T00:00:00.000Z", // actually recent
        }),
      ],
      baseOptions()
    );
    expect(report.personas[0]?.aged_open_count).toBe(0);
  });

  test("reverted_count separates reverted-merge signals from the primary merge counts", () => {
    const report = buildCollectionReport(
      [
        makeEnvelope({ pr_number: 1, outcome: "merged", closure_cause: null, reverted: true }),
        makeEnvelope({ pr_number: 2, outcome: "merged", closure_cause: null, reverted: false }),
      ],
      baseOptions()
    );
    const bolt = report.personas.find((p) => p.persona === "bolt")!;
    // The revert never changes the persisted merged outcome/counts...
    expect(bolt.counts.merged).toBe(2);
    expect(bolt.merge_rate).toBe(1);
    // ...but is still surfaced as its own separate signal.
    expect(bolt.reverted_count).toBe(1);
  });

  test("personas are reported in a stable sorted order regardless of insertion order", () => {
    const envelopes = [
      makeEnvelope({ persona: "sentinel", pr_number: 1 }),
      makeEnvelope({ persona: "bolt", pr_number: 2 }),
    ];
    const report = buildCollectionReport(envelopes, baseOptions());
    expect(report.personas.map((p) => p.persona)).toEqual(["bolt", "sentinel"]);
  });
});

describe("buildCollectionReport session_verification (collector/proposer contract boundary)", () => {
  test('defaults to "none" (fail-closed) when sessionVerification is not supplied', () => {
    const report = buildCollectionReport([makeEnvelope()], baseOptions());
    expect(report.session_verification).toBe("none");
  });

  test('records "none" explicitly when the collector used NullSessionVerifier', () => {
    const report = buildCollectionReport([makeEnvelope()], { ...baseOptions(), sessionVerification: "none" });
    expect(report.session_verification).toBe("none");
  });

  test('records "authoritative" when an authoritative session verifier was wired', () => {
    const report = buildCollectionReport([makeEnvelope()], {
      ...baseOptions(),
      sessionVerification: "authoritative",
    });
    expect(report.session_verification).toBe("authoritative");
  });

  test("session_verification does not affect the content digest", () => {
    const envelopes = [makeEnvelope()];
    const withNone = buildCollectionReport(envelopes, { ...baseOptions(), sessionVerification: "none" });
    const withAuthoritative = buildCollectionReport(envelopes, {
      ...baseOptions(),
      sessionVerification: "authoritative",
    });
    expect(withNone.digest).toBe(withAuthoritative.digest);
  });
});
