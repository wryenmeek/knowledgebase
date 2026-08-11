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
 * Semantic clustering and eligibility for the Jules persona PR learning
 * loop (U3). Implements the "Candidate fingerprint" (R7) and "Candidate
 * eligibility" (R6) sections of `schema/jules-pr-learning-contract.md`,
 * grouping already-classified `EvidenceEnvelope`s (see `classify.ts`) into
 * semantic clusters keyed by `persona | mechanism | affected-scope |
 * normalized-rule` and deciding whether each cluster has enough
 * independently verified evidence to become a learning candidate.
 *
 * This module is pure and read-only: it never fetches memory content, PR
 * state, or session data, and it never writes anything. Callers supply a
 * structured (non-free-text) semantic descriptor for each envelope -
 * `mechanism`, `affectedScope`, and `normalizedRule` - derived upstream from
 * bounded, low-cardinality signals (e.g. closure taxonomy, module/path
 * scope, a fixed rule template) rather than raw PR title/body/comment
 * text. This module does not itself decide how that descriptor is derived;
 * it only clusters and evaluates eligibility once one is supplied.
 */

import { computeCandidateFingerprint } from "./fingerprints.ts";
import {
  CANONICALIZATION_VERSION,
  TAXONOMY_VERSION,
  memoryPathForPersona,
  type EvidenceEnvelope,
  type Persona,
} from "./types.ts";

/**
 * A single envelope plus the structured semantic descriptor used to place
 * it into a cluster. `mechanism`, `affectedScope`, and `normalizedRule`
 * must already be bounded, structured values - never raw PR text - per the
 * canonicalization rules in `schema/jules-pr-learning-contract.md`.
 */
export interface ClusterMember {
  envelope: EvidenceEnvelope;
  mechanism: string;
  affectedScope: readonly string[];
  normalizedRule: string;
}

/** Reason a cluster satisfies candidate eligibility (R6), or `null` if it does not. */
export type EligibilityReason = "merged_lesson" | "closed_cause_prevention" | null;

/**
 * One semantic cluster: every member shares the same candidate fingerprint
 * (`persona | mechanism | affected_scope | normalized_rule`, scoped by the
 * current taxonomy/canonicalization versions and target memory path).
 */
export interface Cluster {
  candidate_fingerprint: string;
  persona: Persona;
  target_memory_path: ".jules/bolt.md" | ".jules/sentinel.md";
  mechanism: string;
  affected_scope: string[];
  normalized_rule: string;
  taxonomy_version: number;
  canonicalization_version: number;
  /** All classified evidence supporting this cluster, in insertion order. */
  members: EvidenceEnvelope[];
  eligible: boolean;
  eligibility_reason: EligibilityReason;
}

/**
 * True when at least one member is an independently verified `merged`
 * envelope (R6, "technical lesson"). Every `EvidenceEnvelope` reaching this
 * function has already passed `classify.ts`'s identity/evidence predicate
 * (`ambiguous` and unverified records never carry `outcome: "merged"`), so
 * no additional verification is performed here - re-verifying identity
 * would duplicate `classify.ts` rather than composing with it.
 */
function hasVerifiedMergedLesson(members: readonly EvidenceEnvelope[]): boolean {
  return members.some((member) => member.outcome === "merged");
}

/**
 * True when at least two *distinct* PRs (different `pr_number`) in the
 * cluster share `outcome: "closed_unmerged"` with a non-`unknown` closure
 * cause (R6, "closed-cause prevention rule"). A single closed PR, or any
 * number of `unknown`/`ambiguous` records, never satisfies this.
 */
function hasTwoDistinctClosedCauses(members: readonly EvidenceEnvelope[]): boolean {
  const distinctPrNumbers = new Set<number>();
  for (const member of members) {
    if (member.outcome !== "closed_unmerged") {
      continue;
    }
    if (member.closure_cause === null || member.closure_cause === "unknown") {
      continue;
    }
    distinctPrNumbers.add(member.pr_number);
  }
  return distinctPrNumbers.size >= 2;
}

/**
 * Determines eligibility for a cluster's member set per R6. Returns the
 * satisfied reason, preferring `"merged_lesson"` when both conditions hold
 * (a single verified merge is sufficient on its own and takes precedence
 * as the stronger, more direct signal).
 */
export function determineEligibility(members: readonly EvidenceEnvelope[]): EligibilityReason {
  if (hasVerifiedMergedLesson(members)) {
    return "merged_lesson";
  }
  if (hasTwoDistinctClosedCauses(members)) {
    return "closed_cause_prevention";
  }
  return null;
}

/**
 * Groups classified evidence into semantic clusters and evaluates
 * eligibility for each. Clustering key equality is defined solely by
 * fingerprint identity (byte-identical SHA-256 hex), never by loose text
 * similarity, so re-running clustering on the same evidence set always
 * produces the same clusters in the same grouping regardless of input
 * order.
 */
export function clusterEnvelopes(members: readonly ClusterMember[]): Cluster[] {
  const clustersByFingerprint = new Map<string, Cluster>();

  for (const member of members) {
    const targetMemoryPath = memoryPathForPersona(member.envelope.persona);
    const fingerprint = computeCandidateFingerprint({
      persona: member.envelope.persona,
      mechanism: member.mechanism,
      affectedScope: [...member.affectedScope],
      normalizedRule: member.normalizedRule,
      taxonomyVersion: TAXONOMY_VERSION,
      canonicalizationVersion: CANONICALIZATION_VERSION,
      targetMemoryPath,
    });

    let cluster = clustersByFingerprint.get(fingerprint);
    if (!cluster) {
      cluster = {
        candidate_fingerprint: fingerprint,
        persona: member.envelope.persona,
        target_memory_path: targetMemoryPath,
        mechanism: member.mechanism,
        affected_scope: [...member.affectedScope],
        normalized_rule: member.normalizedRule,
        taxonomy_version: TAXONOMY_VERSION,
        canonicalization_version: CANONICALIZATION_VERSION,
        members: [],
        eligible: false,
        eligibility_reason: null,
      };
      clustersByFingerprint.set(fingerprint, cluster);
    }
    cluster.members.push(member.envelope);
  }

  const clusters = [...clustersByFingerprint.values()];
  for (const cluster of clusters) {
    const reason = determineEligibility(cluster.members);
    cluster.eligibility_reason = reason;
    cluster.eligible = reason !== null;
  }

  // Deterministic, order-independent output: sort by fingerprint so the
  // same input set always yields the same array order regardless of the
  // original iteration/collection order of `members`.
  clusters.sort((a, b) => (a.candidate_fingerprint < b.candidate_fingerprint ? -1 : 1));
  return clusters;
}

/** Convenience filter returning only clusters that satisfy eligibility (R6). */
export function eligibleClusters(clusters: readonly Cluster[]): Cluster[] {
  return clusters.filter((cluster) => cluster.eligible);
}
