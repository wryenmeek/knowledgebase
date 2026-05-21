import { describe, expect, test } from "bun:test";
import { handleFatalError as handlePlanFatal } from "./fleet-plan.ts";
import { handleFatalError as handleDispatchFatal } from "./fleet-dispatch.ts";
import { handleFatalError as handleMergeFatal } from "./fleet-merge.ts";
import {
  MutationFailureError,
  MUTATION_EXECUTION_CONTRACT,
  type SanitizedErrorEnvelope,
} from "./github/mutation-diagnostics.ts";

function withFatalCapture(run: () => void): { output: string } {
  const messages: string[] = [];
  const originalError = console.error;
  const originalExit = process.exit;

  console.error = (...args: unknown[]) => {
    messages.push(args.map((value) => String(value)).join(" "));
  };
  process.exit = ((code?: number) => {
    throw new Error(`EXIT_${code ?? 0}`);
  }) as typeof process.exit;

  try {
    run();
  } finally {
    console.error = originalError;
    process.exit = originalExit;
  }

  return { output: messages.join("\n") };
}

function makeMutationFailure(operation: string): MutationFailureError {
  const envelope: SanitizedErrorEnvelope = {
    contract: MUTATION_EXECUTION_CONTRACT,
    operation,
    attempt: 1,
    max_attempts: 1,
    classification: "auth",
    retryable: false,
    retrying: false,
    retry_delay_ms: null,
    status_code: 401,
    error_code: "UNAUTHENTICATED",
    message: "Authentication failed for token ***REDACTED***",
    hint: "Check credentials.",
    root_cause_path: ["verify token"],
  };
  return new MutationFailureError(operation, [envelope]);
}

describe("fleet entrypoint mutation fatal handling", () => {
  test("fleet-plan fatal handler emits mutation envelope and exits non-zero", () => {
    const error = makeMutationFailure("fleet-plan:jules.run");
    const capture = withFatalCapture(() => {
      expect(() => handlePlanFatal(error)).toThrow("EXIT_1");
    });

    expect(capture.output).toContain("Jules planning mutation hard-failed after bounded retries");
    expect(capture.output).toContain('"contract"');
    expect(capture.output).toContain("***REDACTED***");
  });

  test("fleet-dispatch fatal handler emits mutation envelope and exits non-zero", () => {
    const error = makeMutationFailure("fleet-dispatch:jules.run");
    const capture = withFatalCapture(() => {
      expect(() => handleDispatchFatal(error)).toThrow("EXIT_1");
    });

    expect(capture.output).toContain("Jules dispatch mutation hard-failed after bounded retries");
    expect(capture.output).toContain('"contract"');
    expect(capture.output).toContain("***REDACTED***");
  });

  test("fleet-merge fatal handler emits mutation envelope and exits non-zero", () => {
    const error = makeMutationFailure("fleet-merge:jules.run:task-1");
    const capture = withFatalCapture(() => {
      expect(() => handleMergeFatal(error)).toThrow("EXIT_1");
    });

    expect(capture.output).toContain("Jules merge re-dispatch hard-failed after bounded retries");
    expect(capture.output).toContain('"contract"');
    expect(capture.output).toContain("***REDACTED***");
  });
});
