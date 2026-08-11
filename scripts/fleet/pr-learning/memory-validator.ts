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
 * Memory entry validator for the Jules persona PR learning loop (U4).
 *
 * Implements the "Memory entry shape", "Redaction boundary", "Rendered
 * Markdown shape", and "Stale-snapshot guard" sections of
 * `schema/jules-memory-entry-contract.md` (R9, R13). This module is pure
 * and read-only: it never fetches memory content, never mutates a file,
 * and never truncates or redacts-and-passes an offending value — every
 * check either passes unchanged input or hard-fails the whole entry,
 * mirroring the fail-closed posture of `scripts/kb/write_utils.py` and
 * `scripts/hooks/check_locality_ratchet.py`.
 *
 * `proposal-validator.ts` (this same unit) performs the complementary
 * diff/tree-level checks (single file, no rename/delete/mode-change,
 * base-tree stale guard) once a rendered entry has passed here.
 */

import { isValidSha256Hex } from "./fingerprints.ts";
import { MEMORY_ENTRY_LIMITS, REDACTION_PATTERNS, type MemoryEntry, type Persona } from "./types.ts";

/**
 * A 40-char lowercase-or-mixed-case hex Git blob SHA (SHA-1). Exported so
 * `propose.ts` (U5) can validate `collector_commit` and live blob SHAs
 * without duplicating this pattern, per the repository's "constants:
 * import, don't duplicate" convention.
 */
export const GIT_BLOB_SHA_RE = /^[0-9a-f]{40}$/i;

const PERSONA_TITLE: Record<Persona, string> = {
  bolt: "⚡ Bolt learning",
  sentinel: "🛡️ Sentinel learning",
};

/**
 * Uniform pass/fail decision surface used by every check in this module
 * and by `proposal-validator.ts`. `reason` is always populated (even on
 * success) and never contains raw PR/memory prose beyond bounded,
 * already-validated identifiers.
 */
export interface ValidationResult {
  ok: boolean;
  reason: string;
}

function pass(reason: string): ValidationResult {
  return { ok: true, reason };
}

function fail(reason: string): ValidationResult {
  return { ok: false, reason };
}

/** Fields scanned by the redaction boundary and reported by field name on failure. */
const MEMORY_ENTRY_TEXT_FIELDS: ReadonlyArray<{
  readonly name: string;
  readonly values: (entry: MemoryEntry) => readonly string[];
}> = Object.freeze([
  { name: "rule", values: (e) => [e.rule] },
  { name: "evidence", values: (e) => e.evidence },
  { name: "verification", values: (e) => [e.verification] },
  { name: "scope", values: (e) => [e.scope] },
  { name: "retraction_condition", values: (e) => [e.retraction_condition] },
]);

/**
 * Validates the required-field shape and format invariants of a
 * `MemoryEntry` (persona enum, hex identifiers, non-empty/non-wildcard
 * scope, parseable timestamp). This is distinct from the size-limit and
 * redaction-boundary checks below so callers can report exactly which
 * category of problem occurred.
 */
export function validateMemoryEntryShape(entry: MemoryEntry): ValidationResult {
  if (entry.persona !== "bolt" && entry.persona !== "sentinel") {
    return fail(`unsupported persona: ${String(entry.persona)}`);
  }
  if (typeof entry.entry_id !== "string" || entry.entry_id.trim().length === 0) {
    return fail("entry_id is missing or empty");
  }
  if (!isValidSha256Hex(entry.candidate_fingerprint)) {
    return fail("candidate_fingerprint is missing or is not a well-formed 64-char hex SHA-256 digest");
  }
  if (!GIT_BLOB_SHA_RE.test(entry.memory_blob_sha)) {
    return fail("memory_blob_sha is missing or is not a well-formed 40-char hex Git blob SHA");
  }
  if (Number.isNaN(Date.parse(entry.generated_at))) {
    return fail("generated_at is missing or is not a parseable ISO-8601 timestamp");
  }
  if (typeof entry.rule !== "string" || entry.rule.trim().length === 0) {
    return fail("rule is missing or empty");
  }
  if (typeof entry.verification !== "string" || entry.verification.trim().length === 0) {
    return fail("verification is missing or empty");
  }
  if (typeof entry.retraction_condition !== "string" || entry.retraction_condition.trim().length === 0) {
    return fail("retraction_condition is missing or empty");
  }
  if (typeof entry.scope !== "string" || entry.scope.trim().length === 0) {
    return fail("scope is missing or empty");
  }
  if (entry.scope.trim() === "*") {
    return fail('scope must be bounded and cannot be the unbounded literal "*"');
  }
  if (!Array.isArray(entry.evidence) || entry.evidence.length === 0) {
    return fail("evidence must contain at least one bounded reference");
  }
  if (entry.evidence.length > MEMORY_ENTRY_LIMITS.EVIDENCE_MAX_ITEMS) {
    return fail(
      `evidence has ${entry.evidence.length} items, exceeding the ${MEMORY_ENTRY_LIMITS.EVIDENCE_MAX_ITEMS}-item limit`
    );
  }
  if (entry.evidence.some((item) => typeof item !== "string" || item.trim().length === 0)) {
    return fail("evidence contains an empty or non-string reference");
  }
  return pass("entry shape is well-formed");
}

/** Renders a validated `MemoryEntry` to the exact bounded Markdown block defined by the contract. */
export function renderMemoryEntryMarkdown(entry: MemoryEntry): string {
  const title = PERSONA_TITLE[entry.persona] ?? entry.persona;
  const lines = [
    `## ${title}: ${entry.scope}`,
    "",
    `**Learning:** ${entry.rule}`,
    `**Evidence:** ${entry.evidence.join(", ")}`,
    `**Verification:** ${entry.verification}`,
    `**Scope:** ${entry.scope}`,
    `**Retraction condition:** ${entry.retraction_condition}`,
    `<!-- entry_id: ${entry.entry_id} | fingerprint: ${entry.candidate_fingerprint} -->`,
  ];
  return lines.join("\n");
}

/**
 * Validates every documented size limit, including the fully rendered
 * Markdown block. The validator never truncates on overflow — an
 * oversized entry is a hard failure that must be fixed upstream by the
 * generator (U3).
 */
export function validateMemoryEntrySizes(entry: MemoryEntry): ValidationResult {
  if (entry.rule.length > MEMORY_ENTRY_LIMITS.RULE_MAX_LENGTH) {
    return fail(`rule exceeds ${MEMORY_ENTRY_LIMITS.RULE_MAX_LENGTH} characters`);
  }
  if (entry.evidence.length > MEMORY_ENTRY_LIMITS.EVIDENCE_MAX_ITEMS) {
    return fail(`evidence exceeds ${MEMORY_ENTRY_LIMITS.EVIDENCE_MAX_ITEMS} items`);
  }
  for (const [index, item] of entry.evidence.entries()) {
    if (item.length > MEMORY_ENTRY_LIMITS.EVIDENCE_ITEM_MAX_LENGTH) {
      return fail(`evidence[${index}] exceeds ${MEMORY_ENTRY_LIMITS.EVIDENCE_ITEM_MAX_LENGTH} characters`);
    }
  }
  if (entry.verification.length > MEMORY_ENTRY_LIMITS.VERIFICATION_MAX_LENGTH) {
    return fail(`verification exceeds ${MEMORY_ENTRY_LIMITS.VERIFICATION_MAX_LENGTH} characters`);
  }
  if (entry.scope.length > MEMORY_ENTRY_LIMITS.SCOPE_MAX_LENGTH) {
    return fail(`scope exceeds ${MEMORY_ENTRY_LIMITS.SCOPE_MAX_LENGTH} characters`);
  }
  if (entry.retraction_condition.length > MEMORY_ENTRY_LIMITS.RETRACTION_CONDITION_MAX_LENGTH) {
    return fail(
      `retraction_condition exceeds ${MEMORY_ENTRY_LIMITS.RETRACTION_CONDITION_MAX_LENGTH} characters`
    );
  }
  const rendered = renderMemoryEntryMarkdown(entry);
  if (rendered.length > MEMORY_ENTRY_LIMITS.RENDERED_BLOCK_MAX_LENGTH) {
    return fail(
      `rendered Markdown block is ${rendered.length} characters, exceeding the ${MEMORY_ENTRY_LIMITS.RENDERED_BLOCK_MAX_LENGTH}-character limit`
    );
  }
  return pass("entry is within all documented size limits");
}

/**
 * Scans every textual field of a `MemoryEntry` against the shared
 * `REDACTION_PATTERNS` (secrets, shell/command-substitution shapes,
 * workflow expressions, prompt-injection-shaped imperatives). Any match
 * hard-fails the entire entry (R9, R13) - there is no partial redaction.
 */
export function scanMemoryEntryForRedactedContent(entry: MemoryEntry): ValidationResult {
  for (const field of MEMORY_ENTRY_TEXT_FIELDS) {
    for (const value of field.values(entry)) {
      for (const pattern of REDACTION_PATTERNS) {
        if (pattern.test(value)) {
          return fail(`field "${field.name}" matches a redaction-boundary pattern and must be rejected`);
        }
      }
    }
  }
  return pass("no redaction-boundary pattern matched");
}

/**
 * Compares the entry's recorded `memory_blob_sha` against the live blob
 * SHA of the target memory file. A mismatch means the target changed
 * since generation; the caller must reject or regenerate, never overwrite
 * the newer content or attempt automatic conflict resolution.
 */
export function validateMemoryEntryStaleTarget(entry: MemoryEntry, liveBlobSha: string): ValidationResult {
  if (!GIT_BLOB_SHA_RE.test(liveBlobSha)) {
    return fail("liveBlobSha is not a well-formed 40-char hex Git blob SHA");
  }
  if (entry.memory_blob_sha.toLowerCase() !== liveBlobSha.toLowerCase()) {
    return fail(
      "stale target: memory_blob_sha does not match the live target blob; the target changed since generation and must be regenerated, never overwritten"
    );
  }
  return pass("memory_blob_sha matches the live target blob");
}

/**
 * Computes the separator required between existing file bytes and a
 * newly appended block so the result has exactly one blank line before
 * the new heading, per the "Append-only / byte-preservation rule" in
 * `schema/jules-memory-entry-contract.md`.
 */
/**
 * Exported so `propose.ts` (U5) can construct the exact `newContent` it
 * must pass to `validateAppendOnlyByteRange`/`validateMemoryEntry` before
 * creating a blob — this is the single canonical implementation of the
 * append-separator rule; propose.ts must never reimplement it.
 */
export function requiredAppendSeparator(existingContent: string): string {
  if (existingContent.length === 0) {
    return "";
  }
  const trailingNewlines = existingContent.match(/\n*$/)?.[0].length ?? 0;
  if (trailingNewlines >= 2) {
    return "";
  }
  if (trailingNewlines === 1) {
    return "\n";
  }
  return "\n\n";
}

/**
 * Validates that `newContent` is exactly `existingContent` with the
 * rendered entry appended after exactly one blank line of separation,
 * and that not a single existing byte was altered. This is the
 * append-only / byte-preservation guarantee (R9): any deviation - a
 * changed byte anywhere in the existing prefix, a missing/extra
 * separator, or a rendering mismatch - is a hard failure.
 */
export function validateAppendOnlyByteRange(
  existingContent: string,
  renderedBlock: string,
  newContent: string
): ValidationResult {
  if (!newContent.startsWith(existingContent)) {
    return fail(
      "append-only violation: newContent does not begin with the unmodified existing file bytes"
    );
  }
  const expected = existingContent + requiredAppendSeparator(existingContent) + renderedBlock;
  if (newContent !== expected) {
    return fail(
      "append-only violation: appended content does not match the expected separator plus rendered Markdown block exactly"
    );
  }
  return pass("existing bytes are preserved and the new entry is a well-formed single append");
}

/** Optional inputs for the composed `validateMemoryEntry` check. */
export interface MemoryEntryValidationOptions {
  /** Live blob SHA of the target memory file, for the stale-snapshot guard. */
  liveBlobSha?: string;
  /** Full current content of the target memory file, for the append-only check. */
  existingContent?: string;
  /** Full proposed content of the target memory file after the append, for the append-only check. */
  newContent?: string;
}

/**
 * Runs every applicable check in the documented validation order (shape,
 * size, redaction boundary, then the optional stale-target and
 * append-only checks when their inputs are supplied) and returns the
 * first failure, or a final success. This is a pure decision surface:
 * it never reads or writes a file itself.
 */
export function validateMemoryEntry(
  entry: MemoryEntry,
  options: MemoryEntryValidationOptions = {}
): ValidationResult {
  const shape = validateMemoryEntryShape(entry);
  if (!shape.ok) {
    return shape;
  }
  const sizes = validateMemoryEntrySizes(entry);
  if (!sizes.ok) {
    return sizes;
  }
  const redaction = scanMemoryEntryForRedactedContent(entry);
  if (!redaction.ok) {
    return redaction;
  }
  if (options.liveBlobSha !== undefined) {
    const stale = validateMemoryEntryStaleTarget(entry, options.liveBlobSha);
    if (!stale.ok) {
      return stale;
    }
  }
  if (options.existingContent !== undefined && options.newContent !== undefined) {
    const appendOnly = validateAppendOnlyByteRange(
      options.existingContent,
      renderMemoryEntryMarkdown(entry),
      options.newContent
    );
    if (!appendOnly.ok) {
      return appendOnly;
    }
  }
  return pass("memory entry passes all applicable validation checks");
}
