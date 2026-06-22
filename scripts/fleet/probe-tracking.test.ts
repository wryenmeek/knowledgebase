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
import {
  CURRENT_REPO_SOURCE,
  FAILURE_COMMENT_PREFIX,
  RECOVERY_COMMENT_PREFIX,
  buildSanitizedEnvelope,
  computeRecoveryDecision,
  renderFailureComment,
  renderRecoveryComment,
  type IssueComment,
  type SanitizedFailureEnvelope,
} from "./probe-tracking.ts";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const PROBED_AT = "2026-06-22T00:00:00.000Z";
const RUN_URL = "https://github.com/wryenmeek/knowledgebase/actions/runs/99999";

function makeFailureComment(probedAt = PROBED_AT, runUrl = RUN_URL): string {
  return renderFailureComment(
    buildSanitizedEnvelope(new Error("generic failure"), probedAt, runUrl),
  );
}

// ---------------------------------------------------------------------------
// Sanitization tests
// ---------------------------------------------------------------------------

describe("probe-tracking — sanitization", () => {
  test("rendered failure payload does not contain a foreign session ID", () => {
    const foreignSessionId = "13840077902252741245";
    const foreignSourceName = "sources/github/wryenmeek/hot-springs-island";

    // Synthetic error whose message contains cross-account sensitive data.
    const error = new Error(
      `Request failed for session ${foreignSessionId} on source ${foreignSourceName}: FAILED_PRECONDITION`,
    );

    const envelope = buildSanitizedEnvelope(error, PROBED_AT, RUN_URL);
    const rendered = renderFailureComment(envelope);

    // Must not contain the foreign session ID or source name.
    expect(rendered).not.toContain(foreignSessionId);
    expect(rendered).not.toContain(foreignSourceName);
  });

  test("rendered failure payload does not contain any raw error message", () => {
    const sensitiveMessage = "session=abc123&source=sources/github/other/repo&token=secret";
    const error = new Error(sensitiveMessage);

    const envelope = buildSanitizedEnvelope(error, PROBED_AT, RUN_URL);
    const rendered = renderFailureComment(envelope);

    expect(rendered).not.toContain(sensitiveMessage);
    expect(rendered).not.toContain("abc123");
    expect(rendered).not.toContain("secret");
  });

  test("rendered failure payload contains exactly the four allowlisted fields", () => {
    const error = new Error("some error with session 99887766554433221100");
    const envelope = buildSanitizedEnvelope(error, PROBED_AT, RUN_URL);
    const rendered = renderFailureComment(envelope);

    // (a) probe timestamp
    expect(rendered).toContain(PROBED_AT);
    // (b) error class (sanitized — just the class name)
    expect(rendered).toContain(envelope.errorClass);
    // (c) summary (pre-defined, not from error message)
    expect(rendered).toContain(envelope.summary);
    // (d) run URL
    expect(rendered).toContain(RUN_URL);
  });

  test("rendered payload starts with FAILURE_COMMENT_PREFIX", () => {
    const envelope = buildSanitizedEnvelope(new Error("x"), PROBED_AT, RUN_URL);
    const rendered = renderFailureComment(envelope);
    expect(rendered.startsWith(FAILURE_COMMENT_PREFIX)).toBe(true);
  });

  test("FAILED_PRECONDITION error maps to safe class and summary", () => {
    class FAILED_PRECONDITIONError extends Error {
      override name = "FAILED_PRECONDITIONError";
    }
    const error = new FAILED_PRECONDITIONError(
      `session 13840077902252741245 sources/github/wryenmeek/hot-springs-island`,
    );
    const envelope = buildSanitizedEnvelope(error, PROBED_AT, RUN_URL);

    expect(envelope.errorClass).toBe("FAILED_PRECONDITION");
    expect(envelope.summary).toContain("quota saturation or auth issue");
    // Sensitive data must not bleed through.
    expect(envelope.errorClass).not.toContain("13840077902252741245");
    expect(envelope.summary).not.toContain("hot-springs-island");
  });

  test("non-Error values produce UnknownError class with safe summary", () => {
    const envelope = buildSanitizedEnvelope("some string error", PROBED_AT, RUN_URL);
    expect(envelope.errorClass).toBe("UnknownError");
    expect(envelope.summary).toContain("workflow run logs");
  });

  test("CURRENT_REPO_SOURCE is the canonical knowledgebase source identifier", () => {
    expect(CURRENT_REPO_SOURCE).toBe("sources/github/wryenmeek/knowledgebase");
  });
});

// ---------------------------------------------------------------------------
// Idempotency tests
// ---------------------------------------------------------------------------

describe("probe-tracking — idempotency", () => {
  test("two consecutive failure invocations produce two distinct comments", () => {
    const comment1 = makeFailureComment("2026-06-22T00:00:00.000Z", `${RUN_URL}/100`);
    const comment2 = makeFailureComment("2026-06-22T09:00:00.000Z", `${RUN_URL}/101`);

    // Both comments start with the prefix.
    expect(comment1.startsWith(FAILURE_COMMENT_PREFIX)).toBe(true);
    expect(comment2.startsWith(FAILURE_COMMENT_PREFIX)).toBe(true);

    // They are distinct (different timestamps and run URLs).
    expect(comment1).not.toBe(comment2);
    expect(comment1).not.toContain("09:00");
    expect(comment2).not.toContain("00:00:00");
  });

  test("each failure comment stands alone — second does not mutate the first", () => {
    const comment1 = makeFailureComment("2026-06-22T00:00:00.000Z");
    const comment2 = makeFailureComment("2026-06-22T09:00:00.000Z");

    // Recovery check: with both comments in history, last IS a failure.
    const comments: IssueComment[] = [{ body: comment1 }, { body: comment2 }];
    const decision = computeRecoveryDecision(comments);

    expect(decision.shouldPost).toBe(true);
    expect(decision.failureCount).toBe(2);
    // First failure timestamp must reference comment1's timestamp.
    expect(decision.firstFailureTimestamp).toBe("2026-06-22T00:00:00.000Z");
  });

  test("consecutive failures accumulate correctly — N failures counted as N", () => {
    const bodies: IssueComment[] = Array.from({ length: 5 }, (_, i) =>
      ({ body: makeFailureComment(`2026-06-22T0${i}:00:00.000Z`) }),
    );

    const decision = computeRecoveryDecision(bodies);
    expect(decision.shouldPost).toBe(true);
    expect(decision.failureCount).toBe(5);
  });
});

// ---------------------------------------------------------------------------
// Recovery tests
// ---------------------------------------------------------------------------

describe("probe-tracking — recovery", () => {
  test("failure-comment history followed by success produces a recovery comment", () => {
    const failure1 = makeFailureComment("2026-06-22T00:00:00.000Z");
    const failure2 = makeFailureComment("2026-06-22T09:00:00.000Z");
    const comments: IssueComment[] = [{ body: failure1 }, { body: failure2 }];

    const decision = computeRecoveryDecision(comments);
    expect(decision.shouldPost).toBe(true);
    expect(decision.failureCount).toBe(2);
    expect(decision.firstFailureTimestamp).toBe("2026-06-22T00:00:00.000Z");

    const recovery = renderRecoveryComment({
      recoveredAt: "2026-06-22T18:00:00.000Z",
      failureCount: decision.failureCount,
      firstFailureTimestamp: decision.firstFailureTimestamp,
    });

    expect(recovery.startsWith(RECOVERY_COMMENT_PREFIX)).toBe(true);
    expect(recovery).toContain("2 failed runs");
    expect(recovery).toContain("2026-06-22T00:00:00.000Z");
    expect(recovery).toContain("2026-06-22T18:00:00.000Z");
  });

  test("single failure followed by success produces '1 failed run' (singular)", () => {
    const failure = makeFailureComment("2026-06-22T00:00:00.000Z");
    const decision = computeRecoveryDecision([{ body: failure }]);

    expect(decision.failureCount).toBe(1);

    const recovery = renderRecoveryComment({
      recoveredAt: "2026-06-22T09:00:00.000Z",
      failureCount: decision.failureCount,
      firstFailureTimestamp: decision.firstFailureTimestamp,
    });

    expect(recovery).toContain("1 failed run");
    expect(recovery).not.toContain("1 failed runs");
  });

  test("no recovery comment when last comment is not a failure", () => {
    const recovery = renderRecoveryComment({
      recoveredAt: "2026-06-22T09:00:00.000Z",
      failureCount: 1,
      firstFailureTimestamp: "2026-06-22T00:00:00.000Z",
    });
    const comments: IssueComment[] = [{ body: recovery }];
    const decision = computeRecoveryDecision(comments);
    expect(decision.shouldPost).toBe(false);
  });

  test("no recovery comment when comment history is empty", () => {
    const decision = computeRecoveryDecision([]);
    expect(decision.shouldPost).toBe(false);
    expect(decision.failureCount).toBe(0);
    expect(decision.firstFailureTimestamp).toBe("");
  });

  test("recovery resets the failure count — failures before prior recovery are excluded", () => {
    // History: 3 older failures → 1 recovery → 2 new failures.
    const oldFailure = makeFailureComment("2026-06-21T00:00:00.000Z");
    const priorRecovery = renderRecoveryComment({
      recoveredAt: "2026-06-21T12:00:00.000Z",
      failureCount: 3,
      firstFailureTimestamp: "2026-06-21T00:00:00.000Z",
    });
    const newFailure1 = makeFailureComment("2026-06-22T00:00:00.000Z");
    const newFailure2 = makeFailureComment("2026-06-22T09:00:00.000Z");

    const comments: IssueComment[] = [
      { body: oldFailure },
      { body: priorRecovery },
      { body: newFailure1 },
      { body: newFailure2 },
    ];

    const decision = computeRecoveryDecision(comments);
    expect(decision.shouldPost).toBe(true);
    // Only the 2 NEW failures should be counted (pre-recovery failures excluded).
    expect(decision.failureCount).toBe(2);
    expect(decision.firstFailureTimestamp).toBe("2026-06-22T00:00:00.000Z");
  });

  test("non-failure non-recovery comments do not break the consecutive-failure chain", () => {
    const failure1 = makeFailureComment("2026-06-22T00:00:00.000Z");
    const manualComment = { body: "Operator investigating — see Slack thread." };
    const failure2 = makeFailureComment("2026-06-22T09:00:00.000Z");

    const comments: IssueComment[] = [
      { body: failure1 },
      manualComment,
      { body: failure2 },
    ];

    const decision = computeRecoveryDecision(comments);
    expect(decision.shouldPost).toBe(true);
    // Both failures counted even with a non-failure comment between them.
    expect(decision.failureCount).toBe(2);
  });
});

// ---------------------------------------------------------------------------
// SanitizedFailureEnvelope shape contract
// ---------------------------------------------------------------------------

describe("probe-tracking — SanitizedFailureEnvelope shape", () => {
  test("envelope always contains all four allowlisted fields", () => {
    const envelope: SanitizedFailureEnvelope = buildSanitizedEnvelope(
      new Error("test"),
      PROBED_AT,
      RUN_URL,
    );
    expect(envelope.probedAt).toBe(PROBED_AT);
    expect(typeof envelope.errorClass).toBe("string");
    expect(typeof envelope.summary).toBe("string");
    expect(envelope.runUrl).toBe(RUN_URL);
  });
});
