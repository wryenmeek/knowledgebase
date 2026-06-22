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
 * probe-tracking.ts
 *
 * Pure helper functions for the Jules account probe tracking-issue
 * notification path. No side effects; no network calls.
 *
 * Security contract: buildSanitizedEnvelope() extracts ONLY the four
 * allowlisted fields (timestamp, error class, summary, run URL) from an
 * unknown error. Raw error message strings — which may contain foreign
 * session IDs or source-context identifiers from other repositories —
 * are never included in the rendered output.
 */

// Import canonical constant — do not redefine; AGENTS.md §Constants.
import { CURRENT_REPO_SOURCE } from "./archive-stale-sessions.js";
export { CURRENT_REPO_SOURCE };

/** Prefix used for all failure comments posted to the tracking issue. */
export const FAILURE_COMMENT_PREFIX = "❌ Probe failed";

/** Prefix used for all recovery comments posted to the tracking issue. */
export const RECOVERY_COMMENT_PREFIX = "✅ Recovered";

// ---------------------------------------------------------------------------
// Sanitized failure envelope
// ---------------------------------------------------------------------------

/**
 * The four allowlisted fields that may appear in a public tracking-issue
 * comment. No other probe data is permitted.
 */
export interface SanitizedFailureEnvelope {
  /** ISO-8601 timestamp from when the notification step ran. */
  probedAt: string;
  /**
   * Error constructor name or HTTP status code.
   * Extracted from `error.name` / `error.constructor.name` only —
   * never from `error.message`, which may contain sensitive data.
   */
  errorClass: string;
  /**
   * Pre-defined operator-actionable one-liner.
   * Not derived from the raw error message string.
   */
  summary: string;
  /** GitHub Actions workflow run URL. */
  runUrl: string;
}

/**
 * Build a sanitized failure envelope from an unknown error value.
 *
 * SECURITY: Only `error.constructor.name` / `error.name` is read.
 * The raw `error.message` — which may contain foreign session IDs,
 * source-context identifiers (e.g. `sources/github/<org>/<repo>`), or
 * other cross-account data — is intentionally ignored.
 *
 * @param error   The caught error value (any type).
 * @param probedAt ISO-8601 timestamp for the notification run.
 * @param runUrl  GitHub Actions run URL.
 */
export function buildSanitizedEnvelope(
  error: unknown,
  probedAt: string,
  runUrl: string,
): SanitizedFailureEnvelope {
  let errorClass = "UnknownError";
  let summary = "Jules account probe failed; check workflow run logs for details";

  if (error !== null && typeof error === "object") {
    // Safe: read only the constructor/type name, never .message.
    const name: unknown = (error as { name?: unknown }).name;
    const ctorName: unknown = (error as { constructor?: { name?: unknown } }).constructor?.name;

    const rawClass = (typeof name === "string" && name) || (typeof ctorName === "string" && ctorName) || "Error";

    // Map known error class patterns to safe, pre-defined summaries.
    // None of these mappings include raw message content.
    if (/FAILED_PRECONDITION/i.test(rawClass)) {
      errorClass = "FAILED_PRECONDITION";
      summary = "Jules API FAILED_PRECONDITION — possible quota saturation or auth issue";
    } else if (/quota|saturat/i.test(rawClass)) {
      errorClass = rawClass;
      summary = "Jules API quota saturation — re-run after quota resets";
    } else if (/auth|permission|unauthenticated/i.test(rawClass)) {
      errorClass = rawClass;
      summary = "Jules API authentication or permission failure — check JULES_API_KEY";
    } else if (/network|timeout|connection/i.test(rawClass)) {
      errorClass = rawClass;
      summary = "Jules API network error — transient failure, will retry at next schedule slot";
    } else {
      errorClass = rawClass;
    }
  }

  return { probedAt, errorClass, summary, runUrl };
}

/**
 * Render the tracking-issue comment body for a probe failure.
 *
 * Emits only the four allowlisted fields; never includes raw error messages,
 * session IDs, or source identifiers from external repositories.
 */
export function renderFailureComment(envelope: SanitizedFailureEnvelope): string {
  return [
    `${FAILURE_COMMENT_PREFIX} at ${envelope.probedAt}`,
    ``,
    `| Field | Value |`,
    `|---|---|`,
    `| Error class | \`${envelope.errorClass}\` |`,
    `| Summary | ${envelope.summary} |`,
    `| Run | ${envelope.runUrl} |`,
  ].join("\n");
}

// ---------------------------------------------------------------------------
// Recovery detection
// ---------------------------------------------------------------------------

/** A single comment from the tracking issue. */
export interface IssueComment {
  body: string;
}

/** Result of the recovery-detection algorithm. */
export interface RecoveryDecision {
  /** Whether a recovery comment should be posted. */
  shouldPost: boolean;
  /** Number of consecutive failure comments since the last recovery (or beginning). */
  failureCount: number;
  /**
   * ISO-8601 timestamp extracted from the OLDEST failure comment in the
   * current run. Empty string when `shouldPost` is false.
   */
  firstFailureTimestamp: string;
}

/**
 * Determine whether to post a recovery comment based on the tracking issue's
 * comment history.
 *
 * Algorithm (per spec):
 *   - If the last comment does NOT start with FAILURE_COMMENT_PREFIX → no-op.
 *   - Otherwise, walk backward through comments counting consecutive failures
 *     (stopping at the last RECOVERY_COMMENT_PREFIX or the beginning).
 *   - The oldest failure timestamp in the current run becomes `firstFailureTimestamp`.
 *
 * This function is pure (no network calls). The caller fetches comments via
 * `gh issue view <n> --json comments` and passes them here.
 */
export function computeRecoveryDecision(comments: IssueComment[]): RecoveryDecision {
  if (comments.length === 0) {
    return { shouldPost: false, failureCount: 0, firstFailureTimestamp: "" };
  }

  const lastComment = comments[comments.length - 1]!;
  if (!lastComment.body.startsWith(FAILURE_COMMENT_PREFIX)) {
    return { shouldPost: false, failureCount: 0, firstFailureTimestamp: "" };
  }

  // Walk backward, counting consecutive failures until a recovery or start.
  let failureCount = 0;
  let firstFailureTimestamp = "";

  for (let i = comments.length - 1; i >= 0; i--) {
    const body = comments[i]!.body;

    if (body.startsWith(FAILURE_COMMENT_PREFIX)) {
      failureCount++;
      // Extract timestamp from "❌ Probe failed at <ts>"
      // Use the first line only; split on whitespace after the prefix.
      const firstLine = body.split("\n")[0] ?? "";
      const afterPrefix = firstLine.slice(FAILURE_COMMENT_PREFIX.length + " at ".length).trim();
      if (afterPrefix) {
        // Keep overwriting — so at the end this holds the OLDEST failure timestamp.
        firstFailureTimestamp = afterPrefix;
      }
    } else if (body.startsWith(RECOVERY_COMMENT_PREFIX)) {
      // Hit the last recovery; stop counting.
      break;
    }
    // Other (non-failure, non-recovery) comments are skipped but don't break the chain.
  }

  return { shouldPost: true, failureCount, firstFailureTimestamp };
}

/**
 * Render the tracking-issue comment body for a successful recovery.
 */
export function renderRecoveryComment(opts: {
  recoveredAt: string;
  failureCount: number;
  firstFailureTimestamp: string;
}): string {
  const runs = opts.failureCount === 1 ? "1 failed run" : `${opts.failureCount} failed runs`;
  return `${RECOVERY_COMMENT_PREFIX} at ${opts.recoveredAt} after ${runs} (since ${opts.firstFailureTimestamp})`;
}
