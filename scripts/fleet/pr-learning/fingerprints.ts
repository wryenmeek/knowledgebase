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
 * Normalization and fingerprinting for the Jules persona PR learning loop
 * (U1). Implements the "Normalization / canonicalization" and "Candidate
 * fingerprint" sections of `schema/jules-pr-learning-contract.md`.
 */

import { CANONICALIZATION_VERSION, type CandidateFingerprintComponents } from "./types.ts";

/** ASCII unit separator used to join fingerprint components before hashing. */
const FINGERPRINT_JOIN_CHAR = "\u001f";

function sha256Hex(input: string): string {
  const hasher = new Bun.CryptoHasher("sha256");
  hasher.update(input);
  return hasher.digest("hex");
}

/**
 * Canonicalizes a single text component per
 * `schema/jules-pr-learning-contract.md` ("Normalization /
 * canonicalization"): NFC-normalize, trim, collapse interior whitespace
 * runs to a single space, then lowercase.
 *
 * This is used only for fingerprint/dedup comparison. The original
 * (non-normalized) text must be preserved wherever it is rendered into a
 * published memory entry.
 */
export function normalizeText(value: string): string {
  return value
    .normalize("NFC")
    .trim()
    .replace(/\s+/g, " ")
    .toLowerCase();
}

/**
 * Canonicalizes an unordered list-valued component: normalizes each item,
 * drops empties, sorts lexicographically, and joins with `,` so input
 * order never affects the resulting fingerprint.
 */
export function normalizeScopeList(values: readonly string[]): string {
  return values
    .map((value) => normalizeText(value))
    .filter((value) => value.length > 0)
    .sort()
    .join(",");
}

/**
 * Computes the candidate fingerprint for a semantic cluster key:
 * `persona | mechanism | affected_scope (sorted) | normalized_rule |
 * taxonomy_version | canonicalization_version | target_memory_path`,
 * SHA-256 hex-encoded. See "Candidate fingerprint" in
 * `schema/jules-pr-learning-contract.md`.
 *
 * Two candidates produce the same fingerprint if and only if every
 * normalized component is identical, including `taxonomyVersion` and
 * `canonicalizationVersion` — changing either version always yields a
 * distinct fingerprint, even for textually identical input.
 */
export function computeCandidateFingerprint(
  components: CandidateFingerprintComponents
): string {
  const joined = [
    normalizeText(components.persona),
    normalizeText(components.mechanism),
    normalizeScopeList(components.affectedScope),
    normalizeText(components.normalizedRule),
    String(components.taxonomyVersion),
    String(components.canonicalizationVersion),
    normalizeText(components.targetMemoryPath),
  ].join(FINGERPRINT_JOIN_CHAR);

  return sha256Hex(joined);
}

/**
 * Convenience wrapper that fills in the current
 * `CANONICALIZATION_VERSION` for callers that only need to vary the
 * taxonomy version explicitly (e.g. tests asserting version-sensitivity).
 */
export function computeCandidateFingerprintAtCurrentVersion(
  components: Omit<CandidateFingerprintComponents, "canonicalizationVersion">
): string {
  return computeCandidateFingerprint({
    ...components,
    canonicalizationVersion: CANONICALIZATION_VERSION,
  });
}

/**
 * Computes the `evidence_digest` for a set of canonicalized evidence
 * strings (e.g. serialized `EvidenceEnvelope` fields relevant to a
 * classification decision). Order-independent: inputs are normalized and
 * sorted before hashing so re-collection in a different order produces the
 * same digest for the same underlying evidence.
 */
export function computeEvidenceDigest(evidenceFields: readonly string[]): string {
  const normalized = evidenceFields
    .map((field) => normalizeText(field))
    .sort()
    .join(FINGERPRINT_JOIN_CHAR);
  return sha256Hex(normalized);
}

/** True when a string is a well-formed lowercase 64-char hex SHA-256 digest. */
export function isValidSha256Hex(value: string): boolean {
  return /^[0-9a-f]{64}$/.test(value);
}
