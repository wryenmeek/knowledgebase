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
 * Deduplication for the Jules persona PR learning loop (U3). Implements
 * R8: compare a candidate against existing memory content, recent memory
 * history, open learning PR markers, and previously closed learning PR
 * markers before it may proceed to proposal validation (U4/U5).
 *
 * This module is pure and read-only. It never fetches memory content or PR
 * state itself - callers (a future U5 orchestrator) supply already-fetched
 * strings/markers - and it never deletes, retracts, or supersedes anything
 * automatically. Contradictions (the same `entry_id` associated with a
 * different fingerprint) are quarantined for human review, per the plan's
 * "Key Technical Decisions": deduplication updates are proposal decisions,
 * not arbitrary rewrites, and stale/contradicted evidence is reported, not
 * silently deleted or auto-retracted, in the MVP.
 */

import type { ProposalMarker } from "./types.ts";

/**
 * Regex for the trailing HTML comment marker every rendered `MemoryEntry`
 * carries (see `schema/jules-memory-entry-contract.md`, "Rendered
 * Markdown shape"):
 * `<!-- entry_id: <entry_id> | fingerprint: <candidate_fingerprint> -->`.
 * This is the only way memory content is inspected - it is a fixed,
 * structured marker, never a prose/free-text scan.
 */
const MEMORY_ENTRY_MARKER_RE =
  /<!--\s*entry_id:\s*(\S+)\s*\|\s*fingerprint:\s*([0-9a-f]{64})\s*-->/gi;

/** A single parsed `entry_id` / `candidate_fingerprint` marker found in memory content. */
export interface MemoryEntryMarker {
  entry_id: string;
  candidate_fingerprint: string;
}

/**
 * Extracts every entry marker from a `.jules/*.md` memory file's content
 * (or a historical snapshot of one). Malformed/partial comments that do
 * not match the fixed marker shape are ignored, never partially parsed.
 */
export function parseMemoryEntryMarkers(content: string): MemoryEntryMarker[] {
  const markers: MemoryEntryMarker[] = [];
  for (const match of content.matchAll(MEMORY_ENTRY_MARKER_RE)) {
    markers.push({ entry_id: match[1]!, candidate_fingerprint: match[2]!.toLowerCase() });
  }
  return markers;
}

/**
 * A subset of `ProposalMarker` sufficient for dedup comparison against
 * open/closed learning PRs. Callers may pass the full `ProposalMarker`
 * directly.
 */
export type ProposalMarkerLike = Pick<
  ProposalMarker,
  "candidate_fingerprint" | "target_memory_path"
>;

export interface DeduplicationInputs {
  /** The fingerprint of the candidate being evaluated (see `cluster.ts`). */
  candidateFingerprint: string;
  /** The stable entry id this candidate would be published under (first 12 hex chars of the fingerprint, per the memory entry contract). */
  entryId: string;
  targetMemoryPath: ".jules/bolt.md" | ".jules/sentinel.md";
  /** Current live content of the target memory file. */
  memoryContent: string;
  /** Historical snapshots of the target memory file (e.g. prior commits), most-recent first or in any order - all are checked. */
  memoryHistory: readonly string[];
  /** Markers for currently open learning proposal PRs. */
  openProposalMarkers: readonly ProposalMarkerLike[];
  /** Markers for previously closed (merged or rejected) learning proposal PRs. */
  closedProposalMarkers: readonly ProposalMarkerLike[];
}

export type DeduplicationStatus =
  | "novel"
  | "duplicate_current_memory"
  | "duplicate_memory_history"
  | "duplicate_open_proposal"
  | "duplicate_closed_proposal"
  | "contradiction_quarantined";

export interface DeduplicationResult {
  status: DeduplicationStatus;
  /** True only for `"novel"`; every other status means no new proposal may be created. */
  novel: boolean;
  /** Human-readable reason, always populated, never containing raw PR/memory prose beyond bounded identifiers. */
  reason: string;
}

function findMarkerForFingerprint(
  markers: readonly MemoryEntryMarker[],
  fingerprint: string
): MemoryEntryMarker | null {
  return markers.find((marker) => marker.candidate_fingerprint === fingerprint) ?? null;
}

function findMarkerForEntryId(
  markers: readonly MemoryEntryMarker[],
  entryId: string
): MemoryEntryMarker | null {
  return markers.find((marker) => marker.entry_id === entryId) ?? null;
}

/**
 * Decides whether a candidate is novel or must be suppressed, per R8. Order
 * of checks (all against the *same* candidate fingerprint/entry id, never a
 * fuzzy match):
 *
 * 1. Current memory content: exact fingerprint match -> already published,
 *    not novel. Same `entry_id` but a *different* fingerprint -> a
 *    contradiction (the published lesson and the new candidate disagree on
 *    what this entry means); quarantined for human review rather than
 *    silently overwritten or auto-retracted.
 * 2. Memory history: same checks against every historical snapshot, so a
 *    candidate cannot "resurrect" a lesson that was already published and
 *    later removed by a legitimate content-preserving edit.
 * 3. Open learning proposal markers for the same target file: an
 *    in-flight proposal for the same fingerprint means no second proposal
 *    should be created (idempotency, R11).
 * 4. Closed learning proposal markers for the same target file: a
 *    previously closed (rejected or superseded) proposal for the same
 *    fingerprint must not be silently recreated.
 *
 * Only when none of these match is the candidate `"novel"`.
 */
export function deduplicateCandidate(inputs: DeduplicationInputs): DeduplicationResult {
  const fingerprint = inputs.candidateFingerprint.toLowerCase();

  const currentMarkers = parseMemoryEntryMarkers(inputs.memoryContent);
  const currentFingerprintMatch = findMarkerForFingerprint(currentMarkers, fingerprint);
  if (currentFingerprintMatch !== null) {
    return {
      status: "duplicate_current_memory",
      novel: false,
      reason: `candidate fingerprint already published as entry_id ${currentFingerprintMatch.entry_id} in ${inputs.targetMemoryPath}`,
    };
  }
  const currentEntryIdMatch = findMarkerForEntryId(currentMarkers, inputs.entryId);
  if (currentEntryIdMatch !== null) {
    return {
      status: "contradiction_quarantined",
      novel: false,
      reason: `entry_id ${inputs.entryId} already exists in ${inputs.targetMemoryPath} with a different fingerprint (${currentEntryIdMatch.candidate_fingerprint}); quarantined for human review, not auto-retracted`,
    };
  }

  for (const historicalContent of inputs.memoryHistory) {
    const historyMarkers = parseMemoryEntryMarkers(historicalContent);
    if (findMarkerForFingerprint(historyMarkers, fingerprint) !== null) {
      return {
        status: "duplicate_memory_history",
        novel: false,
        reason: `candidate fingerprint previously appeared in memory history for ${inputs.targetMemoryPath}`,
      };
    }
    const historyEntryIdMatch = findMarkerForEntryId(historyMarkers, inputs.entryId);
    if (historyEntryIdMatch !== null && historyEntryIdMatch.candidate_fingerprint !== fingerprint) {
      return {
        status: "contradiction_quarantined",
        novel: false,
        reason: `entry_id ${inputs.entryId} previously appeared in memory history for ${inputs.targetMemoryPath} with a different fingerprint; quarantined for human review, not auto-retracted`,
      };
    }
  }

  const openMatch = inputs.openProposalMarkers.find(
    (marker) =>
      marker.target_memory_path === inputs.targetMemoryPath &&
      marker.candidate_fingerprint.toLowerCase() === fingerprint
  );
  if (openMatch !== undefined) {
    return {
      status: "duplicate_open_proposal",
      novel: false,
      reason: `an open learning proposal already targets ${inputs.targetMemoryPath} for this candidate fingerprint`,
    };
  }

  const closedMatch = inputs.closedProposalMarkers.find(
    (marker) =>
      marker.target_memory_path === inputs.targetMemoryPath &&
      marker.candidate_fingerprint.toLowerCase() === fingerprint
  );
  if (closedMatch !== undefined) {
    return {
      status: "duplicate_closed_proposal",
      novel: false,
      reason: `a previously closed learning proposal already exists for ${inputs.targetMemoryPath} and this candidate fingerprint`,
    };
  }

  return { status: "novel", novel: true, reason: "no matching memory content, history, or proposal marker found" };
}
