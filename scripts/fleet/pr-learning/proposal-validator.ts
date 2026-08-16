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
 * Diff/tree-level proposal validator for the Jules persona PR learning
 * loop (U4). Implements R10 and R13's structural half of
 * `schema/jules-memory-entry-contract.md` ("Writable target allowlist") -
 * the complement to `memory-validator.ts`'s field-level checks.
 *
 * This module is pure and read-only: given already-fetched GitHub diff
 * and tree fixtures (never fetched here), it decides whether a proposed
 * change set may proceed to mutation. It never calls the GitHub API,
 * never checks out or executes PR code, and never writes anything -
 * matching the `pr-file-sanity.ts` / `mutation-diagnostics.ts` pattern of
 * inspect-then-decide with no side effects.
 */

import type { ValidationResult } from "./memory-validator.ts";
import { REDACTION_PATTERNS, WRITABLE_MEMORY_PATHS } from "./types.ts";

export type { ValidationResult } from "./memory-validator.ts";

/** Git tree entry file modes, as returned by the Git Trees API. */
export type GitTreeEntryMode = "100644" | "100755" | "120000" | "160000" | "040000";

/** The only mode an "ordinary regular file" may carry (R10: reject symlink/submodule/executable). */
const ORDINARY_REGULAR_FILE_MODE: GitTreeEntryMode = "100644";

/** A single entry from a GitHub Git Trees API response. */
export interface GitHubTreeEntry {
  path: string;
  mode: GitTreeEntryMode;
  type: "blob" | "tree" | "commit";
  sha: string;
  size?: number;
}

/** A single entry from a GitHub Contents/Blob API response. */
export interface GitHubBlob {
  sha: string;
  content: string;
  encoding: "base64" | "utf-8";
  size: number;
}

/** The file-level status values GitHub's compare/PR-files API may report. */
export type GitHubDiffFileStatus =
  | "added"
  | "removed"
  | "modified"
  | "renamed"
  | "copied"
  | "changed"
  | "unchanged";

/** A single entry from a GitHub PR/compare "files" API response. */
export interface GitHubDiffFile {
  filename: string;
  status: GitHubDiffFileStatus;
  additions: number;
  deletions: number;
  changes: number;
  sha: string;
  previous_filename?: string;
  patch?: string;
}

/** Statuses that represent a content-preserving in-place edit, never an add/delete/rename/copy. */
const MODIFIED_STATUSES: ReadonlySet<GitHubDiffFileStatus> = new Set(["modified", "changed"]);

function pass(reason: string): ValidationResult {
  return { ok: true, reason };
}

function fail(reason: string): ValidationResult {
  return { ok: false, reason };
}

function isWritableMemoryPath(path: string): path is ".jules/bolt.md" | ".jules/sentinel.md" {
  return (WRITABLE_MEMORY_PATHS as readonly string[]).includes(path);
}

/**
 * Extracts only the added-line text (lines beginning with a single `+`,
 * excluding the `+++` file header) from a unified diff patch, for
 * redaction-boundary scanning. Removed/context lines are irrelevant here
 * because the append-only guard already rejects any deletion.
 */
export function extractAddedLines(patch: string): string[] {
  const added: string[] = [];
  for (const line of patch.split("\n")) {
    if (line.startsWith("+++")) {
      continue;
    }
    if (line.startsWith("+")) {
      added.push(line.slice(1));
    }
  }
  return added;
}

/**
 * Scans the added lines of a patch for secret-shaped, shell/command-
 * injection-shaped, workflow-expression, or prompt-injection-shaped
 * content, using the same `REDACTION_PATTERNS` applied to structured
 * `MemoryEntry` fields. Any match hard-fails the whole proposal (R9, R13)
 * - this is a second, diff-level line of defense in case a rendered
 * block was tampered with after `memory-validator.ts` approved it.
 */
export function scanPatchForRedactedContent(patch: string): ValidationResult {
  const addedLines = extractAddedLines(patch);
  for (const line of addedLines) {
    for (const pattern of REDACTION_PATTERNS) {
      if (pattern.test(line)) {
        return fail("added diff content matches a redaction-boundary pattern and must be rejected");
      }
    }
  }
  return pass("no redaction-boundary pattern matched in added diff content");
}

/** Inputs sufficient to validate a proposed single-file memory diff before any mutation. */
export interface ProposalDiffInput {
  /** The full changed-file list for the proposal (or PR). Must contain exactly one entry. */
  files: readonly GitHubDiffFile[];
  /** The base tree entries the diff is computed against (used for mode + stale-target checks). */
  baseTreeEntries: readonly GitHubTreeEntry[];
  /** The blob SHA recorded at candidate/entry generation time (`memory_blob_sha`). */
  expectedBaseBlobSha: string;
}

/**
 * Validates that the base tree entry for `path` exists, is an ordinary
 * regular file (Git blob, mode `100644`), and (when `expectedBlobSha` is
 * supplied) matches the recorded blob SHA. This is the reusable core of
 * `validateProposalDiff`'s tree-mode check, factored out so mutation
 * paths that do not have a full GitHub diff available (e.g. the
 * content-API-based append flow in `propose.ts`) can still reject a
 * currently-executable or currently-symlinked target before forcing a
 * replacement to mode `100644` — never trusting the Contents API's
 * ability to return byte content as proof the target is an ordinary file.
 */
export function validateBaseTreeEntryMode(
  baseTreeEntries: readonly GitHubTreeEntry[],
  path: string,
  expectedBlobSha?: string
): ValidationResult {
  const baseEntry = baseTreeEntries.find((entry) => entry.path === path);
  if (baseEntry === undefined) {
    return fail(`target file "${path}" was not found in the base tree`);
  }
  if (baseEntry.type !== "blob") {
    return fail(`target path "${path}" is not an ordinary regular file (tree entry type: ${baseEntry.type})`);
  }
  if (baseEntry.mode !== ORDINARY_REGULAR_FILE_MODE) {
    return fail(
      `target path "${path}" is not an ordinary regular file (mode ${baseEntry.mode}; symlink, submodule, and executable modes are rejected)`
    );
  }
  if (expectedBlobSha !== undefined && baseEntry.sha.toLowerCase() !== expectedBlobSha.toLowerCase()) {
    return fail(
      `stale target: base tree blob SHA for ${path} does not match the recorded memory_blob_sha; regenerate against the new content, never overwrite`
    );
  }
  return pass(`base tree entry for ${path} is an ordinary regular file`);
}

/**
 * Validates that a proposal's file-level diff satisfies every structural
 * constraint from R10 before any GitHub mutation is attempted:
 *
 * - Exactly one file is changed (never zero, never more than one).
 * - The file is not an empty/`0/0/0` diff (unrelated or no-op change).
 * - The file's path is one of the two allowlisted memory targets.
 * - The change is a content-preserving edit (`modified`/`changed`), never
 *   an add, delete, rename, or copy.
 * - The file is not append-only-violating: it may not remove any
 *   existing lines (`deletions === 0`).
 * - The base tree entry for the path exists, is a regular blob, and
 *   carries mode `100644` - never a symlink (`120000`), submodule
 *   (`160000`), or executable (`100755`) mode.
 * - The base tree blob SHA for the path matches `expectedBaseBlobSha`
 *   (the stale-target guard at the diff/tree level, mirroring
 *   `validateMemoryEntryStaleTarget` in `memory-validator.ts`).
 * - The patch content (required - a missing patch cannot be proven safe
 *   and fails closed) contains no redaction-boundary matches in its
 *   added lines.
 */
export function validateProposalDiff(input: ProposalDiffInput): ValidationResult {
  if (input.files.length === 0) {
    return fail("empty diff: no files changed");
  }
  if (input.files.length > 1) {
    return fail(
      `proposal must change exactly one file, found ${input.files.length}: ${input.files
        .map((f) => f.filename)
        .join(", ")}`
    );
  }

  const file = input.files[0]!;

  if (file.additions === 0 && file.deletions === 0 && file.changes === 0) {
    return fail(`0/0/0 diff detected for ${file.filename}: empty or unrelated change rejected`);
  }

  if (!isWritableMemoryPath(file.filename)) {
    return fail(
      `target path "${file.filename}" is not allowlisted; only ${WRITABLE_MEMORY_PATHS.join(" or ")} may be modified`
    );
  }

  if (file.previous_filename !== undefined && file.previous_filename !== file.filename) {
    return fail(
      `rename detected (${file.previous_filename} -> ${file.filename}); renames are rejected`
    );
  }

  if (!MODIFIED_STATUSES.has(file.status)) {
    return fail(`file status "${file.status}" is not a content-preserving edit; only modification is allowed`);
  }

  if (file.deletions > 0) {
    return fail(
      `append-only violation: diff removes ${file.deletions} existing line(s) from ${file.filename}`
    );
  }

  const modeResult = validateBaseTreeEntryMode(input.baseTreeEntries, file.filename, input.expectedBaseBlobSha);
  if (!modeResult.ok) {
    return modeResult;
  }

  if (file.patch === undefined || file.patch.length === 0) {
    return fail(`no patch content available for ${file.filename}; diff safety cannot be verified, failing closed`);
  }

  const redactionResult = scanPatchForRedactedContent(file.patch);
  if (!redactionResult.ok) {
    return redactionResult;
  }

  return pass(`single-file append-only diff for ${file.filename} passes all structural checks`);
}
