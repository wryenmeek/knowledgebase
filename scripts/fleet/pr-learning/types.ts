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
 * Canonical types for the Jules persona PR learning loop (U1).
 *
 * This module is the TypeScript implementation of
 * `schema/jules-pr-learning-contract.md` and
 * `schema/jules-memory-entry-contract.md`. Those two documents are
 * authoritative when this file and the schema docs disagree; later units
 * (U2-U6) must import from here rather than redefining equivalent shapes.
 */

/** Bumped whenever the closure taxonomy (`ClosureCause`) changes. */
export const TAXONOMY_VERSION = 1;

/** Bumped whenever the normalization/canonicalization algorithm changes. */
export const CANONICALIZATION_VERSION = 1;

/** Schema version for `EvidenceEnvelope` / `Candidate` shapes in this file. */
export const CONTRACT_SCHEMA_VERSION = 1;

/**
 * Terminal and quarantine states for a collected PR. `merged` is the only
 * state authorized solely by `merged_at` being non-null; a non-null
 * `merge_sha` alone never implies `merged`. See
 * `schema/jules-pr-learning-contract.md` for the full precedence rules.
 */
export type OutcomeState = "merged" | "closed_unmerged" | "open" | "ambiguous";

/**
 * Fixed closure taxonomy (`taxonomy_version: 1`). Required (non-null) when
 * `outcome === "closed_unmerged"`; must be `null` otherwise.
 */
export type ClosureCause =
  | "duplicate_or_superseded"
  | "scope_creep"
  | "unsupported_claim"
  | "test_or_policy_failure"
  | "unsafe_change"
  | "stale_artifact"
  | "conflict_or_rebase"
  | "unknown";

export const CLOSURE_CAUSES: readonly ClosureCause[] = Object.freeze([
  "duplicate_or_superseded",
  "scope_creep",
  "unsupported_claim",
  "test_or_policy_failure",
  "unsafe_change",
  "stale_artifact",
  "conflict_or_rebase",
  "unknown",
]);

/** Jules personas currently in scope for the learning loop. */
export type Persona = "bolt" | "sentinel";

/**
 * Provenance/evidence envelope for a single collected PR record. See
 * `schema/jules-pr-learning-contract.md` ("Evidence / provenance envelope")
 * for the full field-by-field contract.
 */
export interface EvidenceEnvelope {
  repo: string;
  pr_number: number;
  persona: Persona;
  outcome: OutcomeState;
  closure_cause: ClosureCause | null;
  base_sha: string;
  evaluated_head_sha: string;
  merge_sha: string | null;
  author_id: string | null;
  session_id: string | null;
  base_repo_full_name: string | null;
  head_repo_full_name: string | null;
  event_ids: string[];
  collected_at: string;
  as_of: string;
  taxonomy_version: number;
  evidence_digest: string;
}

/**
 * The ordered, canonicalized components hashed to produce a
 * `CandidateFingerprint`. See "Candidate fingerprint" in
 * `schema/jules-pr-learning-contract.md`.
 */
export interface CandidateFingerprintComponents {
  persona: Persona;
  mechanism: string;
  affectedScope: string[];
  normalizedRule: string;
  taxonomyVersion: number;
  canonicalizationVersion: number;
  targetMemoryPath: string;
}

/**
 * A clustered, deduplicated learning candidate produced by U3, consumed by
 * U4/U5. `candidate_fingerprint` is the semantic cluster key
 * (`persona | mechanism | affected-scope | normalized-rule`, scoped by
 * taxonomy/canonicalization version); `evidence_digest` and
 * `target_memory_path` additionally scope proposal-time validation.
 */
export interface Candidate {
  candidate_fingerprint: string;
  persona: Persona;
  target_memory_path: ".jules/bolt.md" | ".jules/sentinel.md";
  mechanism: string;
  affected_scope: string[];
  normalized_rule: string;
  supporting_evidence: EvidenceEnvelope[];
  evidence_digest: string;
  memory_blob_sha: string;
  taxonomy_version: number;
  canonicalization_version: number;
}

/**
 * A bounded, structured memory entry ready for proposal validation (U4).
 * See "Memory entry shape" in `schema/jules-memory-entry-contract.md`.
 */
export interface MemoryEntry {
  entry_id: string;
  persona: Persona;
  rule: string;
  evidence: string[];
  verification: string;
  scope: string;
  retraction_condition: string;
  candidate_fingerprint: string;
  memory_blob_sha: string;
  generated_at: string;
}

/**
 * Idempotency marker for proposal branch/PR creation (U5). See "Proposal
 * marker" in `schema/jules-memory-entry-contract.md`.
 */
export interface ProposalMarker {
  repo: string;
  target_memory_path: ".jules/bolt.md" | ".jules/sentinel.md";
  candidate_fingerprint: string;
  base_branch: string;
  branch_name: string;
  producer_workflow: string;
  collector_commit: string;
}

/** Size limits enforced by `schema/jules-memory-entry-contract.md`. */
export const MEMORY_ENTRY_LIMITS = Object.freeze({
  RULE_MAX_LENGTH: 500,
  EVIDENCE_ITEM_MAX_LENGTH: 200,
  EVIDENCE_MAX_ITEMS: 3,
  VERIFICATION_MAX_LENGTH: 300,
  SCOPE_MAX_LENGTH: 200,
  RETRACTION_CONDITION_MAX_LENGTH: 300,
  RENDERED_BLOCK_MAX_LENGTH: 2000,
} as const);

/** The only two paths a proposal may ever modify (R10). */
export const WRITABLE_MEMORY_PATHS: readonly [".jules/bolt.md", ".jules/sentinel.md"] =
  Object.freeze([".jules/bolt.md", ".jules/sentinel.md"]);

export function memoryPathForPersona(persona: Persona): ".jules/bolt.md" | ".jules/sentinel.md" {
  return persona === "bolt" ? ".jules/bolt.md" : ".jules/sentinel.md";
}

/**
 * Redaction-boundary patterns applied to every `MemoryEntry` string field
 * before it may be validated as writable. Any match hard-fails the entire
 * proposal (R9, R13). See "Redaction boundary" in
 * `schema/jules-memory-entry-contract.md`.
 */
export const REDACTION_PATTERNS: readonly RegExp[] = Object.freeze([
  /-----BEGIN [A-Z ]*PRIVATE KEY-----/,
  /\bgh[pousr]_[A-Za-z0-9]{20,}\b/,
  /\bAKIA[0-9A-Z]{16}\b/,
  /\bBearer\s+[A-Za-z0-9._-]{10,}\b/i,
  /\b(?:key|token|password|secret)\s*[:=]\s*['"]?[A-Za-z0-9._-]{6,}/i,
  /https?:\/\/[^\s/]+:[^\s/@]+@[^\s/]+/i,
  // Backtick command-substitution shape: only flags backticked spans that
  // look like an actual shell command (contains whitespace plus a shell
  // metacharacter or a well-known dangerous command word), not ordinary
  // inline-code formatting such as `foo.py` or `Path.is_relative_to()`.
  /`[^`]*\s(?:[|;&]|rm\s|curl\s|wget\s|bash\s|sh\s|eval\s|chmod\s)[^`]*`/i,
  /\$\([^)]*\)/,
  /\$\{\{[^}]*\}\}/,
  /;\s*rm\s+-rf\b/i,
]);
