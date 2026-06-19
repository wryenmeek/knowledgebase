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
  assertMutationPreflight,
  classifyMutationError,
  MutationFailureError,
  MUTATION_EXECUTION_CONTRACT,
  PreflightFailureError,
  resolveMutationMaxAttempts,
  runMutationWithDiagnostics,
  sanitizeErrorText,
} from "./mutation-diagnostics.ts";

function withEnv(
  updates: Partial<Record<"JULES_API_KEY" | "GITHUB_TOKEN", string | undefined>>,
  run: () => void
): void {
  const previous = {
    JULES_API_KEY: process.env.JULES_API_KEY,
    GITHUB_TOKEN: process.env.GITHUB_TOKEN,
  };

  if (updates.JULES_API_KEY === undefined) {
    delete process.env.JULES_API_KEY;
  } else {
    process.env.JULES_API_KEY = updates.JULES_API_KEY;
  }

  if (updates.GITHUB_TOKEN === undefined) {
    delete process.env.GITHUB_TOKEN;
  } else {
    process.env.GITHUB_TOKEN = updates.GITHUB_TOKEN;
  }

  try {
    run();
  } finally {
    if (previous.JULES_API_KEY === undefined) {
      delete process.env.JULES_API_KEY;
    } else {
      process.env.JULES_API_KEY = previous.JULES_API_KEY;
    }

    if (previous.GITHUB_TOKEN === undefined) {
      delete process.env.GITHUB_TOKEN;
    } else {
      process.env.GITHUB_TOKEN = previous.GITHUB_TOKEN;
    }
  }
}

async function withEnvAsync(
  updates: Partial<Record<"JULES_API_KEY" | "GITHUB_TOKEN", string | undefined>>,
  run: () => Promise<void>
): Promise<void> {
  const previous = {
    JULES_API_KEY: process.env.JULES_API_KEY,
    GITHUB_TOKEN: process.env.GITHUB_TOKEN,
  };

  if (updates.JULES_API_KEY === undefined) {
    delete process.env.JULES_API_KEY;
  } else {
    process.env.JULES_API_KEY = updates.JULES_API_KEY;
  }

  if (updates.GITHUB_TOKEN === undefined) {
    delete process.env.GITHUB_TOKEN;
  } else {
    process.env.GITHUB_TOKEN = updates.GITHUB_TOKEN;
  }

  try {
    await run();
  } finally {
    if (previous.JULES_API_KEY === undefined) {
      delete process.env.JULES_API_KEY;
    } else {
      process.env.JULES_API_KEY = previous.JULES_API_KEY;
    }

    if (previous.GITHUB_TOKEN === undefined) {
      delete process.env.GITHUB_TOKEN;
    } else {
      process.env.GITHUB_TOKEN = previous.GITHUB_TOKEN;
    }
  }
}

describe("mutation diagnostics classification", () => {
  test("classifies account-binding FAILED_PRECONDITION as retryable failed_precondition", () => {
    const classified = classifyMutationError({
      status: 400,
      message: "FAILED_PRECONDITION: Google Account not registered — source precondition not met",
    });

    expect(classified.category).toBe("failed_precondition");
    expect(classified.retryable).toBe(true);
    expect(classified.statusCode).toBe(400);
  });

  test("classifies auth/permission/rate-limit/network distinctly", () => {
    const auth = classifyMutationError({ status: 401, message: "UNAUTHENTICATED token invalid" });
    const permission = classifyMutationError({
      status: 403,
      message: "PERMISSION_DENIED repo access denied",
    });
    const rateLimit = classifyMutationError({
      status: 429,
      message: "RESOURCE_EXHAUSTED rate_limit exceeded",
    });
    const network = classifyMutationError(new Error("fetch failed: ETIMEDOUT"));

    expect(auth.category).toBe("auth");
    expect(auth.retryable).toBe(false);
    expect(permission.category).toBe("permission");
    expect(permission.retryable).toBe(false);
    expect(rateLimit.category).toBe("rate_limit");
    expect(rateLimit.retryable).toBe(true);
    expect(network.category).toBe("network");
    expect(network.retryable).toBe(true);
  });

  test("classifies bare FAILED_PRECONDITION code (generic message) as quota_saturation", () => {
    const classified = classifyMutationError({
      code: "FAILED_PRECONDITION",
      message: "request failed",
    });

    expect(classified.category).toBe("quota_saturation");
    expect(classified.retryable).toBe(false);
    expect(classified.errorCode).toBe("FAILED_PRECONDITION");
  });

  test("classifies bare FAILED_PRECONDITION body as quota_saturation (soft-warn)", () => {
    const classified = classifyMutationError({
      status: 400,
      message: "FAILED_PRECONDITION",
    });

    expect(classified.category).toBe("quota_saturation");
    expect(classified.retryable).toBe(false);
  });

  test("classifies explicit quota-signal FAILED_PRECONDITION body as quota_saturation", () => {
    const classified = classifyMutationError({
      status: 400,
      message: "FAILED_PRECONDITION: Quota exceeded for Jules sessions",
    });

    expect(classified.category).toBe("quota_saturation");
    expect(classified.retryable).toBe(false);
  });

  test("classifies account-binding FAILED_PRECONDITION body as failed_precondition (hard-fail)", () => {
    const classified = classifyMutationError({
      status: 400,
      message:
        "FAILED_PRECONDITION: This Google Account is not registered. Please register your GitHub App.",
    });

    expect(classified.category).toBe("failed_precondition");
    expect(classified.retryable).toBe(true);
  });

  test("classifies mixed (quota signal + account nouns) FAILED_PRECONDITION as quota_saturation (quota wins)", () => {
    // quota signals win before account-binding checks (HSI #595 final ordering).
    // A message that references a Google Account or GitHub App in the context of
    // a quota error is still a quota saturation event, not a config fault.
    const classified = classifyMutationError({
      status: 400,
      message:
        "FAILED_PRECONDITION: Google Account quota exceeded — GitHub App not authorized.",
    });

    expect(classified.category).toBe("quota_saturation");
    expect(classified.retryable).toBe(false);
  });

  // Real upstream Jules API bare-JSON error shapes (wryenmeek/hot-springs-island#595).
  // The SDK may return: {"code":400,"message":"Precondition check failed.","status":"FAILED_PRECONDITION"}
  test("classifies bare upstream JSON shape (code+status) as quota_saturation", () => {
    const classified = classifyMutationError({
      code: 400,
      message: "Precondition check failed.",
      status: "FAILED_PRECONDITION",
    });

    expect(classified.category).toBe("quota_saturation");
    expect(classified.retryable).toBe(false);
    expect(classified.errorCode).toBe("FAILED_PRECONDITION");
  });

  // gRPC error envelope: {"error":{"code":9,"message":"FAILED_PRECONDITION","status":"FAILED_PRECONDITION"}}
  test("classifies nested gRPC error envelope as quota_saturation", () => {
    const classified = classifyMutationError({
      error: { code: 9, message: "FAILED_PRECONDITION", status: "FAILED_PRECONDITION" },
    });

    expect(classified.category).toBe("quota_saturation");
    expect(classified.retryable).toBe(false);
    expect(classified.errorCode).toBe("FAILED_PRECONDITION");
  });

  // gRPC envelope with generic message but FAILED_PRECONDITION in status field
  test("classifies nested gRPC bare body (generic message, FAILED_PRECONDITION status) as quota_saturation", () => {
    const classified = classifyMutationError({
      error: { code: 9, message: "Precondition check failed.", status: "FAILED_PRECONDITION" },
    });

    expect(classified.category).toBe("quota_saturation");
    expect(classified.retryable).toBe(false);
    expect(classified.errorCode).toBe("FAILED_PRECONDITION");
  });
});

describe("mutation diagnostics redaction", () => {
  test("redacts JULES_API_KEY and GITHUB_TOKEN from error strings", () => {
    withEnv(
      {
        JULES_API_KEY: "jules-secret-value", // pragma: allowlist secret
        GITHUB_TOKEN: "ghp_secret_token", // pragma: allowlist secret
      },
      () => {
        const message =
          "FAILED_PRECONDITION JULES_API_KEY=jules-secret-value GITHUB_TOKEN=ghp_secret_token Authorization: Bearer ghp_secret_token"; // pragma: allowlist secret
        const sanitized = sanitizeErrorText(message);

        expect(sanitized).not.toContain("jules-secret-value");
        expect(sanitized).not.toContain("ghp_secret_token");
        expect(sanitized).toContain("***REDACTED***");
      }
    );
  });
});

describe("mutation retry behavior", () => {
  test("retries account-binding FAILED_PRECONDITION once and then succeeds", async () => {
    let attempts = 0;
    const envelopes = [] as Array<{ retrying: boolean }>;

    const value = await runMutationWithDiagnostics({
      operation: "fleet-dispatch:jules.run:task-1",
      maxAttempts: 3,
      run: async () => {
        attempts++;
        if (attempts === 1) {
          throw {
            status: 400,
            message: "FAILED_PRECONDITION: Google Account not registered — source precondition not met",
          };
        }
        return "ok";
      },
      sleep: async () => {},
      onAttemptFailure: (envelope) => {
        envelopes.push({ retrying: envelope.retrying });
      },
    });

    expect(value).toBe("ok");
    expect(attempts).toBe(2);
    expect(envelopes).toHaveLength(1);
    expect(envelopes[0]?.retrying).toBe(true);
  });

  test("hard-fails deterministically after bounded retries with sanitized envelope", async () => {
    let attempts = 0;

    try {
      await runMutationWithDiagnostics({
        operation: "fleet-merge:jules.run:task-2",
        maxAttempts: 2,
        run: async () => {
          attempts++;
          throw {
            status: 400,
            message: "FAILED_PRECONDITION: GitHub App not registered — account mismatch detected",
          };
        },
        sleep: async () => {},
      });
      throw new Error("Expected mutation run to fail.");
    } catch (error) {
      expect(error).toBeInstanceOf(MutationFailureError);
      const terminal = (error as MutationFailureError).terminalEnvelope;
      expect(attempts).toBe(2);
      expect(terminal.attempt).toBe(2);
      expect(terminal.max_attempts).toBe(2);
      expect(terminal.retrying).toBe(false);
      expect(terminal.classification).toBe("failed_precondition");
      expect(terminal.contract).toEqual(MUTATION_EXECUTION_CONTRACT);
    }
  });

  test("non-retryable classifications fail on first attempt", async () => {
    let attempts = 0;
    let sleepCalls = 0;

    try {
      await runMutationWithDiagnostics({
        operation: "fleet-plan:jules.run",
        maxAttempts: 4,
        run: async () => {
          attempts++;
          throw {
            status: 403,
            message: "PERMISSION_DENIED",
          };
        },
        sleep: async () => {
          sleepCalls++;
        },
      });
      throw new Error("Expected non-retryable failure.");
    } catch (error) {
      expect(error).toBeInstanceOf(MutationFailureError);
      const terminal = (error as MutationFailureError).terminalEnvelope;
      expect(terminal.classification).toBe("permission");
      expect(terminal.retrying).toBe(false);
    }

    expect(attempts).toBe(1);
    expect(sleepCalls).toBe(0);
  });

  test("retry delays are deterministic and capped", async () => {
    const retryDelays: number[] = [];
    let attempts = 0;

    try {
      await runMutationWithDiagnostics({
        operation: "fleet-dispatch:jules.run:task-delays",
        maxAttempts: 5,
        run: async () => {
          attempts++;
          throw {
            status: 400,
            message: "FAILED_PRECONDITION: Google Account not registered — persistent account mismatch",
          };
        },
        sleep: async () => {},
        onAttemptFailure: (envelope) => {
          if (envelope.retry_delay_ms !== null) {
            retryDelays.push(envelope.retry_delay_ms);
          }
        },
      });
      throw new Error("Expected retry exhaustion.");
    } catch (error) {
      expect(error).toBeInstanceOf(MutationFailureError);
      expect((error as MutationFailureError).attempts).toHaveLength(5);
    }

    expect(attempts).toBe(5);
    expect(retryDelays).toEqual([2000, 4000, 6000, 8000]);
  });

  test("terminal envelopes redact secrets from runtime errors", async () => {
    await withEnvAsync(
      {
        JULES_API_KEY: "super-secret-jules", // pragma: allowlist secret
        GITHUB_TOKEN: "super-secret-gh", // pragma: allowlist secret
      },
      async () => {
        try {
          await runMutationWithDiagnostics({
            operation: "fleet-merge:jules.run:task-redaction",
            maxAttempts: 1,
            run: async () => {
              throw {
                status: 400,
                message:
                  "FAILED_PRECONDITION JULES_API_KEY=super-secret-jules GITHUB_TOKEN=super-secret-gh", // pragma: allowlist secret
              };
            },
          });
          throw new Error("Expected redaction failure.");
        } catch (error) {
          expect(error).toBeInstanceOf(MutationFailureError);
          const terminal = (error as MutationFailureError).terminalEnvelope;
          expect(terminal.message).not.toContain("super-secret-jules");
          expect(terminal.message).not.toContain("super-secret-gh");
          expect(terminal.message).toContain("***REDACTED***");
        }
      }
    );
  });
});

describe("max attempt parsing and guards", () => {
  test("resolveMutationMaxAttempts uses defaults and parses numbers", () => {
    expect(resolveMutationMaxAttempts(undefined)).toBe(3);
    expect(resolveMutationMaxAttempts("4")).toBe(4);
    expect(resolveMutationMaxAttempts("  ")).toBe(3);
  });

  test("runMutationWithDiagnostics rejects invalid maxAttempts", async () => {
    try {
      await runMutationWithDiagnostics({
        operation: "fleet-dispatch:jules.run:invalid-max",
        maxAttempts: 0,
        run: async () => "ok",
      });
      throw new Error("Expected invalid maxAttempts to throw.");
    } catch (error) {
      expect(String(error)).toContain("FLEET_MUTATION_MAX_ATTEMPTS");
    }
  });
});

describe("preflight checks", () => {
  test("passes with valid required token configuration", () => {
    withEnv(
      {
        JULES_API_KEY: "present", // pragma: allowlist secret
        GITHUB_TOKEN: "present", // pragma: allowlist secret
      },
      () => {
        expect(() =>
          assertMutationPreflight({
            operation: "fleet-dispatch:jules.run",
            repoFullName: "owner/repo",
            baseBranch: "main",
            maxAttempts: 3,
            requireGitHubToken: true,
          })
        ).not.toThrow();
      }
    );
  });

  test("passes without GitHub token when requireGitHubToken is false", () => {
    withEnv(
      {
        JULES_API_KEY: "present", // pragma: allowlist secret
        GITHUB_TOKEN: undefined, // pragma: allowlist secret
      },
      () => {
        expect(() =>
          assertMutationPreflight({
            operation: "fleet-plan:jules.run",
            repoFullName: "owner/repo",
            baseBranch: "main",
            maxAttempts: 3,
            requireGitHubToken: false,
          })
        ).not.toThrow();
      }
    );
  });

  test("fails closed for invalid branch format before mutation", () => {
    withEnv(
      {
        JULES_API_KEY: "present", // pragma: allowlist secret
        GITHUB_TOKEN: "present", // pragma: allowlist secret
      },
      () => {
        expect(() =>
          assertMutationPreflight({
            operation: "fleet-dispatch:jules.run",
            repoFullName: "owner/repo",
            baseBranch: "main branch",
            maxAttempts: 2,
            requireGitHubToken: true,
          })
        ).toThrow(PreflightFailureError);
      }
    );
  });

  test("fails closed when required tokens are missing", () => {
    withEnv(
      {
        JULES_API_KEY: undefined, // pragma: allowlist secret
        GITHUB_TOKEN: undefined, // pragma: allowlist secret
      },
      () => {
        expect(() =>
          assertMutationPreflight({
            operation: "fleet-plan:jules.run",
            repoFullName: "owner/repo",
            baseBranch: "main",
            maxAttempts: 2,
            requireGitHubToken: true,
          })
        ).toThrow(PreflightFailureError);
      }
    );
  });

  test("fails closed for invalid repo or maxAttempts", () => {
    withEnv(
      {
        JULES_API_KEY: "present", // pragma: allowlist secret
        GITHUB_TOKEN: "present", // pragma: allowlist secret
      },
      () => {
        expect(() =>
          assertMutationPreflight({
            operation: "fleet-dispatch:jules.run",
            repoFullName: "invalid-repo-format",
            baseBranch: "main",
            maxAttempts: 2,
            requireGitHubToken: true,
          })
        ).toThrow(PreflightFailureError);

        expect(() =>
          assertMutationPreflight({
            operation: "fleet-dispatch:jules.run",
            repoFullName: "owner/repo",
            baseBranch: "main",
            maxAttempts: 0,
            requireGitHubToken: true,
          })
        ).toThrow(PreflightFailureError);
      }
    );
  });
});
