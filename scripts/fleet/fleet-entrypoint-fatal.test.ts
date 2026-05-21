import { describe, expect, test } from "bun:test";
import {
  MutationFailureError,
  MUTATION_EXECUTION_CONTRACT,
  type SanitizedErrorEnvelope,
} from "./github/mutation-diagnostics.ts";

const fatalHandlersPromise = (async () => {
  process.env.JULES_API_KEY ??= "test-jules-api-key";
  process.env.GITHUB_TOKEN ??= "test-github-token";
  const [planModule, dispatchModule, mergeModule] = await Promise.all([
    import("./fleet-plan.ts"),
    import("./fleet-dispatch.ts"),
    import("./fleet-merge.ts"),
  ]);
  return {
    handlePlanFatal: planModule.handleFatalError,
    handleDispatchFatal: dispatchModule.handleFatalError,
    handleMergeFatal: mergeModule.handleFatalError,
  };
})();

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
  test("fleet-plan fatal handler emits mutation envelope and exits non-zero", async () => {
    const { handlePlanFatal } = await fatalHandlersPromise;
    const error = makeMutationFailure("fleet-plan:jules.run");
    const capture = withFatalCapture(() => {
      expect(() => handlePlanFatal(error)).toThrow("EXIT_1");
    });

    expect(capture.output).toContain("Jules planning mutation hard-failed after bounded retries");
    expect(capture.output).toContain('"contract"');
    expect(capture.output).toContain("***REDACTED***");
  });

  test("fleet-dispatch fatal handler emits mutation envelope and exits non-zero", async () => {
    const { handleDispatchFatal } = await fatalHandlersPromise;
    const error = makeMutationFailure("fleet-dispatch:jules.run");
    const capture = withFatalCapture(() => {
      expect(() => handleDispatchFatal(error)).toThrow("EXIT_1");
    });

    expect(capture.output).toContain("Jules dispatch mutation hard-failed after bounded retries");
    expect(capture.output).toContain('"contract"');
    expect(capture.output).toContain("***REDACTED***");
  });

  test("fleet-merge fatal handler emits mutation envelope and exits non-zero", async () => {
    const { handleMergeFatal } = await fatalHandlersPromise;
    const error = makeMutationFailure("fleet-merge:jules.run:task-1");
    const capture = withFatalCapture(() => {
      expect(() => handleMergeFatal(error)).toThrow("EXIT_1");
    });

    expect(capture.output).toContain("Jules merge re-dispatch hard-failed after bounded retries");
    expect(capture.output).toContain('"contract"');
    expect(capture.output).toContain("***REDACTED***");
  });
});
