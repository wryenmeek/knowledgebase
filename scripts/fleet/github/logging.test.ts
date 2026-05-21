import { describe, expect, test } from "bun:test";
import { redactToken } from "./logging.ts";

type FleetSecretKey = "JULES_API_KEY" | "GITHUB_TOKEN";

function withSecrets(
  updates: Partial<Record<FleetSecretKey, string | undefined>>,
  run: () => void
): void {
  const previous = {
    JULES_API_KEY: process.env.JULES_API_KEY,
    GITHUB_TOKEN: process.env.GITHUB_TOKEN,
  };

  for (const [key, value] of Object.entries(updates)) {
    if (value === undefined) {
      delete process.env[key];
      continue;
    }
    process.env[key] = value;
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

describe("logging redaction", () => {
  test("redacts token values from log strings", () => {
    withSecrets(
      {
        JULES_API_KEY: "jules-secret-value", // pragma: allowlist secret
        GITHUB_TOKEN: "ghp-secret-value", // pragma: allowlist secret
      },
      () => {
        const output = redactToken(
          "JULES_API_KEY=jules-secret-value GITHUB_TOKEN=ghp-secret-value Authorization: Bearer ghp-secret-value" // pragma: allowlist secret
        );
        expect(output).toContain("***REDACTED***");
        expect(output).not.toContain("jules-secret-value");
        expect(output).not.toContain("ghp-secret-value");
      }
    );
  });

  test("does not truncate non-secret long output", () => {
    const longOutput = "a".repeat(1201);
    const redacted = redactToken(longOutput);
    expect(redacted).toBe(longOutput);
    expect(redacted).not.toContain("<truncated>");
  });
});
