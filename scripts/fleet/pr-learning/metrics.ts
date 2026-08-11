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
 * Per-persona learning-loop metrics for the Jules persona PR learning loop
 * (U3). Implements R5: report proposal-level merge rate alongside separate
 * unique-lesson, aged-open, ambiguous, incomplete, and terminalization
 * views so a growing backlog cannot be hidden behind a single optimistic
 * number.
 *
 * This module is pure: it consumes already-classified `EvidenceEnvelope`s
 * (see `classify.ts`) and already-clustered `Cluster`s (see `cluster.ts`)
 * and performs no I/O of its own. Incompleteness is an explicit input
 * (mirroring `report.ts`'s `complete`/`collection_errors` fields) rather
 * than something this module infers, so a metrics view can never silently
 * claim completeness it was not told is true.
 */

import type { Cluster } from "./cluster.ts";
import type { EvidenceEnvelope, Persona } from "./types.ts";

/** Default "aged open" threshold: 14 days, matching `report.ts`. */
export const DEFAULT_AGED_OPEN_THRESHOLD_MS = 14 * 24 * 60 * 60 * 1000;

export interface MetricsOptions {
  /** Reference instant for "aged open" calculation; defaults to `Date.now()`. */
  nowMs?: number;
  agedOpenThresholdMs?: number;
  /**
   * Whether the underlying evidence set is complete (no pagination
   * failure, no unresolved cross-endpoint inconsistency). Mirrors
   * `report.ts`'s `complete` field; this module does not compute it.
   */
  complete: boolean;
  /** Count of distinct collection/classification errors contributing to this metrics view. */
  incompleteRecordCount: number;
}

export interface PersonaMetrics {
  persona: Persona;
  /** Total classified envelopes observed for this persona (all outcomes). */
  total_count: number;
  merged_count: number;
  closed_unmerged_count: number;
  open_count: number;
  ambiguous_count: number;
  /**
   * Proposal-level merge rate: `merged / (merged + closed_unmerged)`.
   * `null` when the denominator is zero (no terminal PRs observed yet).
   * This is a per-PR/proposal rate, deliberately distinct from
   * `unique_lesson_count` below so duplicate or superseded PRs cannot
   * inflate (or, symmetrically, deflate) the apparent learning yield.
   */
  proposal_merge_rate: number | null;
  /**
   * Count of distinct eligible semantic clusters (R6) attributable to this
   * persona - i.e. unique lessons, not raw PR volume. A persona can have a
   * low `proposal_merge_rate` and still contribute unique lessons, or a
   * high volume of merged PRs that all cluster into very few lessons; both
   * are reported so neither can be mistaken for the other.
   */
  unique_lesson_count: number;
  /** Count of the eligible clusters broken down by eligibility reason. */
  unique_lesson_breakdown: {
    merged_lesson: number;
    closed_cause_prevention: number;
  };
  /** Open envelopes whose `collected_at` is older than the aged-open threshold. */
  aged_open_count: number;
  /** Envelopes quarantined as `ambiguous` (never a negative outcome, always reported). */
  ambiguous_count_view: number;
  /**
   * Envelopes that reached a stable terminal state (`merged` or
   * `closed_unmerged`), as a fraction of all classified envelopes for this
   * persona. Distinguishes "backlog fully adjudicated" from "backlog
   * growing but nothing has been decided yet". `null` when `total_count`
   * is zero.
   */
  terminalization_rate: number | null;
  terminalized_count: number;
}

export interface LearningMetricsReport {
  complete: boolean;
  incomplete_record_count: number;
  personas: PersonaMetrics[];
}

function computePersonaMetrics(
  persona: Persona,
  envelopes: readonly EvidenceEnvelope[],
  clusters: readonly Cluster[],
  options: Required<Pick<MetricsOptions, "nowMs" | "agedOpenThresholdMs">>
): PersonaMetrics {
  let merged = 0;
  let closedUnmerged = 0;
  let open = 0;
  let ambiguous = 0;
  let agedOpen = 0;

  for (const envelope of envelopes) {
    switch (envelope.outcome) {
      case "merged":
        merged += 1;
        break;
      case "closed_unmerged":
        closedUnmerged += 1;
        break;
      case "open": {
        open += 1;
        const collectedMs = Date.parse(envelope.collected_at);
        if (Number.isFinite(collectedMs) && options.nowMs - collectedMs >= options.agedOpenThresholdMs) {
          agedOpen += 1;
        }
        break;
      }
      case "ambiguous":
        ambiguous += 1;
        break;
    }
  }

  const denominator = merged + closedUnmerged;
  const proposalMergeRate = denominator > 0 ? merged / denominator : null;

  const personaClusters = clusters.filter((cluster) => cluster.persona === persona && cluster.eligible);
  const mergedLessonCount = personaClusters.filter(
    (cluster) => cluster.eligibility_reason === "merged_lesson"
  ).length;
  const closedCausePreventionCount = personaClusters.filter(
    (cluster) => cluster.eligibility_reason === "closed_cause_prevention"
  ).length;

  const totalCount = envelopes.length;
  const terminalizedCount = merged + closedUnmerged;
  const terminalizationRate = totalCount > 0 ? terminalizedCount / totalCount : null;

  return {
    persona,
    total_count: totalCount,
    merged_count: merged,
    closed_unmerged_count: closedUnmerged,
    open_count: open,
    ambiguous_count: ambiguous,
    proposal_merge_rate: proposalMergeRate,
    unique_lesson_count: personaClusters.length,
    unique_lesson_breakdown: {
      merged_lesson: mergedLessonCount,
      closed_cause_prevention: closedCausePreventionCount,
    },
    aged_open_count: agedOpen,
    ambiguous_count_view: ambiguous,
    terminalization_rate: terminalizationRate,
    terminalized_count: terminalizedCount,
  };
}

/**
 * Builds the full per-persona metrics view (R5) from classified evidence
 * and clustered candidates. Personas with zero envelopes are omitted
 * (there is nothing to report); callers wanting a fixed persona list
 * should pre-seed `envelopes` accordingly or handle the omission
 * explicitly.
 */
export function buildLearningMetricsReport(
  envelopes: readonly EvidenceEnvelope[],
  clusters: readonly Cluster[],
  options: MetricsOptions
): LearningMetricsReport {
  const nowMs = options.nowMs ?? Date.now();
  const agedOpenThresholdMs = options.agedOpenThresholdMs ?? DEFAULT_AGED_OPEN_THRESHOLD_MS;

  const byPersona = new Map<Persona, EvidenceEnvelope[]>();
  for (const envelope of envelopes) {
    const bucket = byPersona.get(envelope.persona);
    if (bucket) {
      bucket.push(envelope);
    } else {
      byPersona.set(envelope.persona, [envelope]);
    }
  }

  const personas = [...byPersona.keys()]
    .sort()
    .map((persona) =>
      computePersonaMetrics(persona, byPersona.get(persona)!, clusters, {
        nowMs,
        agedOpenThresholdMs,
      })
    );

  return {
    complete: options.complete,
    incomplete_record_count: options.incompleteRecordCount,
    personas,
  };
}
