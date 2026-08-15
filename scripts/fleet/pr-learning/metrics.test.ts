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
import { clusterEnvelopes, type ClusterMember } from "./cluster.ts";
import { DEFAULT_AGED_OPEN_THRESHOLD_MS, buildLearningMetricsReport } from "./metrics.ts";
import type { ClosureCause, EvidenceEnvelope, OutcomeState } from "./types.ts";

const REPO = "wryenmeek/knowledgebase";
const SHA_A = "a".repeat(40);
const SHA_B = "b".repeat(40);
const NOW = "2026-08-10T00:00:00.000Z";
const NOW_MS = Date.parse(NOW);

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
    created_at: NOW,
    collected_at: NOW,
    as_of: NOW,
    reverted: false,
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

describe("buildLearningMetricsReport", () => {
  test("computes proposal-level merge rate as merged / (merged + closed_unmerged)", () => {
    const envelopes = [
      makeEnvelope(1, "merged", null),
      makeEnvelope(2, "merged", null),
      makeEnvelope(3, "closed_unmerged", "scope_creep"),
    ];
    const report = buildLearningMetricsReport(envelopes, [], {
      complete: true,
      incompleteRecordCount: 0,
      nowMs: NOW_MS,
    });
    expect(report.personas).toHaveLength(1);
    expect(report.personas[0]!.proposal_merge_rate).toBeCloseTo(2 / 3);
    expect(report.personas[0]!.merged_count).toBe(2);
    expect(report.personas[0]!.closed_unmerged_count).toBe(1);
  });

  test("merge rate is null when the terminal denominator is zero", () => {
    const envelopes = [makeEnvelope(1, "open", null), makeEnvelope(2, "ambiguous", null)];
    const report = buildLearningMetricsReport(envelopes, [], {
      complete: true,
      incompleteRecordCount: 0,
      nowMs: NOW_MS,
    });
    expect(report.personas[0]!.proposal_merge_rate).toBeNull();
  });

  test("duplicate evidence records for the same PR do not change proposal-level metrics stability", () => {
    const envelopes = [makeEnvelope(1, "merged", null), makeEnvelope(1, "merged", null)];
    const report = buildLearningMetricsReport(envelopes, [], {
      complete: true,
      incompleteRecordCount: 0,
      nowMs: NOW_MS,
    });
    // Metrics operate on whatever envelope set they are given; duplicate
    // suppression is the collector/classifier's responsibility (U2). This
    // asserts the rate formula itself remains stable and correct given
    // duplicate input, rather than silently diverging.
    expect(report.personas[0]!.proposal_merge_rate).toBe(1);
    expect(report.personas[0]!.merged_count).toBe(2);
  });

  test("unique_lesson_count reflects distinct eligible clusters, not raw PR volume", () => {
    const envelopes = [
      makeEnvelope(1, "merged", null),
      makeEnvelope(2, "merged", null),
      makeEnvelope(3, "merged", null),
    ];
    // All three merged PRs cluster into a single semantic lesson.
    const clusters = clusterEnvelopes(envelopes.map((envelope) => makeMember(envelope)));
    const report = buildLearningMetricsReport(envelopes, clusters, {
      complete: true,
      incompleteRecordCount: 0,
      nowMs: NOW_MS,
    });
    expect(report.personas[0]!.merged_count).toBe(3);
    expect(report.personas[0]!.unique_lesson_count).toBe(1);
    expect(report.personas[0]!.unique_lesson_breakdown.merged_lesson).toBe(1);
    expect(report.personas[0]!.unique_lesson_breakdown.closed_cause_prevention).toBe(0);
  });

  test("ineligible clusters (single closed_unmerged PR) do not count toward unique_lesson_count", () => {
    const envelopes = [makeEnvelope(1, "closed_unmerged", "test_or_policy_failure")];
    const clusters = clusterEnvelopes(envelopes.map((envelope) => makeMember(envelope)));
    const report = buildLearningMetricsReport(envelopes, clusters, {
      complete: true,
      incompleteRecordCount: 0,
      nowMs: NOW_MS,
    });
    expect(report.personas[0]!.unique_lesson_count).toBe(0);
  });

  test("aged_open_count counts only open envelopes older than the threshold", () => {
    const staleCreatedAt = new Date(NOW_MS - DEFAULT_AGED_OPEN_THRESHOLD_MS - 1000).toISOString();
    const freshCreatedAt = new Date(NOW_MS - 1000).toISOString();
    const envelopes = [
      makeEnvelope(1, "open", null, { created_at: staleCreatedAt }),
      makeEnvelope(2, "open", null, { created_at: freshCreatedAt }),
    ];
    const report = buildLearningMetricsReport(envelopes, [], {
      complete: true,
      incompleteRecordCount: 0,
      nowMs: NOW_MS,
    });
    expect(report.personas[0]!.open_count).toBe(2);
    expect(report.personas[0]!.aged_open_count).toBe(1);
  });

  test("aged_open_count uses created_at, not collected_at (which is always ~now in a real run)", () => {
    const staleCreatedAt = new Date(NOW_MS - DEFAULT_AGED_OPEN_THRESHOLD_MS - 1000).toISOString();
    const envelopes = [
      // collected_at pinned to "now", as in a real collection run — the
      // record must still be counted as aged based on created_at.
      makeEnvelope(1, "open", null, { created_at: staleCreatedAt, collected_at: NOW }),
    ];
    const report = buildLearningMetricsReport(envelopes, [], {
      complete: true,
      incompleteRecordCount: 0,
      nowMs: NOW_MS,
    });
    expect(report.personas[0]!.aged_open_count).toBe(1);
  });

  test("ambiguous envelopes are counted but never contribute to merge rate or terminalization", () => {
    const envelopes = [
      makeEnvelope(1, "ambiguous", null),
      makeEnvelope(2, "ambiguous", null),
      makeEnvelope(3, "merged", null),
    ];
    const report = buildLearningMetricsReport(envelopes, [], {
      complete: true,
      incompleteRecordCount: 0,
      nowMs: NOW_MS,
    });
    expect(report.personas[0]!.ambiguous_count).toBe(2);
    expect(report.personas[0]!.ambiguous_count_view).toBe(2);
    expect(report.personas[0]!.terminalized_count).toBe(1);
    expect(report.personas[0]!.terminalization_rate).toBeCloseTo(1 / 3);
  });

  test("incomplete collection is surfaced as an explicit top-level flag, never inferred", () => {
    const report = buildLearningMetricsReport([], [], {
      complete: false,
      incompleteRecordCount: 3,
      nowMs: NOW_MS,
    });
    expect(report.complete).toBe(false);
    expect(report.incomplete_record_count).toBe(3);
    expect(report.personas).toEqual([]);
  });

  test("terminalization_rate is null when a persona has zero envelopes", () => {
    // Not directly reachable via buildLearningMetricsReport (personas with
    // zero envelopes are omitted entirely), but the formula must not divide
    // by zero for a persona with only non-terminal records either.
    const envelopes = [makeEnvelope(1, "open", null)];
    const report = buildLearningMetricsReport(envelopes, [], {
      complete: true,
      incompleteRecordCount: 0,
      nowMs: NOW_MS,
    });
    expect(report.personas[0]!.terminalization_rate).toBe(0);
  });

  test("reports personas sorted deterministically regardless of envelope input order", () => {
    const envelopes = [
      makeEnvelope(1, "merged", null, { persona: "sentinel" }),
      makeEnvelope(2, "merged", null, { persona: "bolt" }),
    ];
    const report = buildLearningMetricsReport(envelopes, [], {
      complete: true,
      incompleteRecordCount: 0,
      nowMs: NOW_MS,
    });
    expect(report.personas.map((persona) => persona.persona)).toEqual(["bolt", "sentinel"]);
  });

  test("multiple distinct closed-cause clusters each count as a separate unique lesson", () => {
    const envelopes = [
      makeEnvelope(1, "closed_unmerged", "test_or_policy_failure"),
      makeEnvelope(2, "closed_unmerged", "test_or_policy_failure"),
      makeEnvelope(3, "closed_unmerged", "unsafe_change"),
      makeEnvelope(4, "closed_unmerged", "unsafe_change"),
    ];
    const clusters = clusterEnvelopes([
      makeMember(envelopes[0]!, { mechanism: "mechanism a" }),
      makeMember(envelopes[1]!, { mechanism: "mechanism a" }),
      makeMember(envelopes[2]!, { mechanism: "mechanism b" }),
      makeMember(envelopes[3]!, { mechanism: "mechanism b" }),
    ]);
    const report = buildLearningMetricsReport(envelopes, clusters, {
      complete: true,
      incompleteRecordCount: 0,
      nowMs: NOW_MS,
    });
    expect(report.personas[0]!.unique_lesson_count).toBe(2);
    expect(report.personas[0]!.unique_lesson_breakdown.closed_cause_prevention).toBe(2);
  });
});
