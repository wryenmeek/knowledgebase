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
 * Classification for the Jules persona PR learning loop (U2). Implements
 * the outcome state machine, identity/evidence predicate (R1), and closure
 * taxonomy assignment (R3) from `schema/jules-pr-learning-contract.md`,
 * turning a `RawPullRecord` (see `collect.ts`) into an `EvidenceEnvelope`.
 *
 * This module takes no free-text input whatsoever (no title, body, comment,
 * review, or log text) — only the structured fields `collect.ts` gathers.
 * Label names are read for taxonomy assignment, but only ever compared
 * against a fixed allowlist of exact, case-insensitive strings; an
 * unrecognized or adversarially-crafted label value can only ever fall
 * through to `"unknown"`, never select a path, permission, or action.
 */

import { computeEvidenceDigest, isValidSha256Hex } from "./fingerprints.ts";
import {
  DEFAULT_STABILIZATION_CUTOFF_MS,
  type RawPullRecord,
} from "./collect.ts";
import {
  CLOSURE_CAUSES,
  TAXONOMY_VERSION,
  type ClosureCause,
  type EvidenceEnvelope,
  type OutcomeState,
  type Persona,
} from "./types.ts";

export interface ClassifyOptions {
  repoFullName: string;
  persona: Persona;
  asOf: string;
  collectedAt: string;
  stabilizationCutoffMs?: number;
}

/**
 * Fixed, structured-signal-only mapping from exact (case-insensitive) label
 * names to a `ClosureCause`. Only exact matches against this allowlist ever
 * select a cause; every other label value (including anything that looks
 * like a path, shell fragment, or workflow expression) is inert data that
 * simply does not match and falls through to `"unknown"`.
 */
const LABEL_CLOSURE_CAUSE_MAP: ReadonlyMap<string, ClosureCause> = new Map([
  ["duplicate", "duplicate_or_superseded"],
  ["superseded", "duplicate_or_superseded"],
  ["scope-creep", "scope_creep"],
  ["out-of-scope", "scope_creep"],
  ["unsupported-claim", "unsupported_claim"],
  ["unsafe", "unsafe_change"],
  ["unsafe-change", "unsafe_change"],
  ["security-risk", "unsafe_change"],
  ["stale", "stale_artifact"],
  ["stale-artifact", "stale_artifact"],
]);

function normalizeLabel(label: string): string {
  return label.trim().toLowerCase();
}

/**
 * Assigns a `ClosureCause` for a `closed_unmerged` record using only
 * structured signals (label allowlist, `mergeable_state`, check-run
 * conclusion) — never PR title/body/comment text. Falls back to
 * `"unknown"` whenever structured evidence is insufficient, per R3
 * ("unknown" and insufficient-evidence causes can never satisfy the
 * two-distinct-PR clustering threshold).
 */
export function classifyClosureCause(record: RawPullRecord): ClosureCause {
  for (const rawLabel of record.labels) {
    const mapped = LABEL_CLOSURE_CAUSE_MAP.get(normalizeLabel(rawLabel));
    if (mapped !== undefined) {
      return mapped;
    }
  }
  if (record.mergeable_state === "dirty") {
    return "conflict_or_rebase";
  }
  if (record.check_conclusion === "fail") {
    return "test_or_policy_failure";
  }
  return "unknown";
}

function isStillOpen(record: RawPullRecord, cutoffMs: number, asOfMs: number): boolean {
  if (record.state === "open") {
    return true;
  }
  if (record.draft) {
    return true;
  }
  if (record.check_conclusion === "pending") {
    return true;
  }
  if (record.reopened_at !== null) {
    const reopenedMs = Date.parse(record.reopened_at);
    if (Number.isFinite(reopenedMs) && asOfMs - reopenedMs < cutoffMs) {
      // Reopened but has not yet passed the stabilization cutoff: treat as
      // still moving, never as a stabilized closed_unmerged/ambiguous record.
      return true;
    }
  }
  return false;
}

/**
 * Identity/evidence predicate (R1). A PR may only leave `open` with a
 * non-`ambiguous` classification when author identity, verified session
 * linkage, exact base/head repository boundaries, and an immutable
 * evaluated head SHA are all present. Missing linkage is always
 * `ambiguous` — never an accepted fallback.
 */
export function passesIdentityPredicate(
  record: RawPullRecord,
  options: Pick<ClassifyOptions, "repoFullName">
): boolean {
  if (record.author_id === null) {
    return false;
  }
  if (record.session_link === null || record.session_link.sessionId.length === 0) {
    return false;
  }
  if (record.base_repo_full_name !== options.repoFullName) {
    return false;
  }
  if (record.head_repo_full_name !== options.repoFullName) {
    return false; // a fork head (head repo differs from base repo) is always ambiguous
  }
  if (!record.head_sha || record.head_sha.length !== 40) {
    return false;
  }
  if (record.evidence_inconsistent) {
    return false; // cross-endpoint reconciliation mismatch; never trust a moving target
  }
  return true;
}

function determineOutcome(
  record: RawPullRecord,
  options: ClassifyOptions
): { outcome: OutcomeState; closure_cause: ClosureCause | null } {
  const cutoffMs = options.stabilizationCutoffMs ?? DEFAULT_STABILIZATION_CUTOFF_MS;
  const asOfMs = Date.parse(options.asOf);

  // A merge timestamp is authoritative only after the same identity and
  // repository-boundary checks required for every terminal outcome.
  if (record.merged_at !== null && record.merged_at.length > 0) {
    if (!passesIdentityPredicate(record, options)) {
      return { outcome: "ambiguous", closure_cause: null };
    }
    return { outcome: "merged", closure_cause: null };
  }

  // Rule 2: still open (including draft, pending checks, or a reopen that
  // has not yet passed its stabilization cutoff).
  if (isStillOpen(record, cutoffMs, asOfMs)) {
    return { outcome: "open", closure_cause: null };
  }

  // Rule 3: identity/evidence predicate failure or internal inconsistency
  // quarantines the record rather than accepting it as a negative outcome.
  if (!passesIdentityPredicate(record, options)) {
    return { outcome: "ambiguous", closure_cause: null };
  }

  // Rule 4: stable, verified, non-merged, non-open -> closed_unmerged with a
  // fixed-taxonomy closure cause (never null; "unknown" when evidence is
  // insufficient to assign a more specific cause).
  return { outcome: "closed_unmerged", closure_cause: classifyClosureCause(record) };
}

/**
 * Turns a single `RawPullRecord` into a validated `EvidenceEnvelope`. Pure
 * and deterministic: the same record and options always produce the same
 * envelope (including `evidence_digest`), enabling report regeneration
 * from an unchanged GitHub snapshot to produce an identical digest.
 */
export function classifyPullRequest(
  record: RawPullRecord,
  options: ClassifyOptions
): EvidenceEnvelope {
  const { outcome, closure_cause } = determineOutcome(record, options);

  const eventIds = record.event_ids;
  const evidenceDigest = computeEvidenceDigest([
    options.repoFullName,
    String(record.number),
    outcome,
    closure_cause ?? "null",
    record.base_sha,
    record.head_sha,
    record.merge_commit_sha ?? "null",
    record.author_id ?? "null",
    record.session_link?.sessionId ?? "null",
    record.base_repo_full_name ?? "null",
    record.head_repo_full_name ?? "null",
    ...[...eventIds].sort(),
    options.asOf,
    String(TAXONOMY_VERSION),
  ]);

  return {
    repo: options.repoFullName,
    pr_number: record.number,
    persona: options.persona,
    outcome,
    closure_cause,
    base_sha: record.base_sha,
    evaluated_head_sha: record.head_sha,
    merge_sha: record.merge_commit_sha,
    author_id: record.author_id,
    session_id: record.session_link?.sessionId ?? null,
    base_repo_full_name: record.base_repo_full_name,
    head_repo_full_name: record.head_repo_full_name,
    event_ids: eventIds,
    collected_at: options.collectedAt,
    as_of: options.asOf,
    taxonomy_version: TAXONOMY_VERSION,
    evidence_digest: evidenceDigest,
  };
}

/**
 * Classifies a batch of records for one persona. Malformed input (a record
 * that would produce an envelope failing the contract's own validation
 * invariants) is a hard failure for that record — it is reported in
 * `errors` and excluded from `envelopes`, never partially trusted.
 */
export function classifyPullRequests(
  records: readonly RawPullRecord[],
  options: ClassifyOptions
): { envelopes: EvidenceEnvelope[]; errors: string[] } {
  const envelopes: EvidenceEnvelope[] = [];
  const errors: string[] = [];

  for (const record of records) {
    let envelope: EvidenceEnvelope;
    try {
      envelope = classifyPullRequest(record, options);
    } catch (error) {
      errors.push(
        `pull #${record.number} classification failed: ${
          error instanceof Error ? error.message : String(error)
        }`
      );
      continue;
    }

    const validationError = validateEnvelope(envelope);
    if (validationError !== null) {
      errors.push(`pull #${record.number} produced an invalid envelope: ${validationError}`);
      continue;
    }

    envelopes.push(envelope);
  }

  return { envelopes, errors };
}

/**
 * Structural validation mirroring "Validation" in
 * `schema/jules-pr-learning-contract.md`. Returns `null` when valid, or a
 * human-readable reason otherwise.
 */
export function validateEnvelope(envelope: EvidenceEnvelope): string | null {
  if (envelope.base_sha.length !== 40 || envelope.evaluated_head_sha.length !== 40) {
    return "base_sha/evaluated_head_sha must be 40-character hex SHAs";
  }
  if (!isValidSha256Hex(envelope.evidence_digest)) {
    return "evidence_digest must be a 64-character lowercase hex string";
  }
  if (envelope.outcome === "closed_unmerged") {
    if (envelope.closure_cause === null || !(CLOSURE_CAUSES as readonly string[]).includes(envelope.closure_cause)) {
      return "closed_unmerged envelope must carry a valid closure_cause";
    }
  } else if (envelope.closure_cause !== null) {
    return `${envelope.outcome} envelope must not carry a closure_cause`;
  }
  if (envelope.outcome !== "open" && envelope.event_ids.length === 0) {
    return "non-open envelope must carry at least one event_id";
  }
  if (envelope.taxonomy_version !== TAXONOMY_VERSION) {
    return "taxonomy_version does not match the current contract version";
  }
  return null;
}
