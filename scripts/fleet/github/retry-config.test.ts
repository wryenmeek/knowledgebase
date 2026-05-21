import { describe, expect, test } from "bun:test";
import {
  DEFAULT_MAX_REDISPATCH_RETRIES,
  resolveMaxRedispatchRetries,
  validateMaxRedispatchRetries,
} from "./retry-config.ts";

describe("retry-config", () => {
  test("resolveMaxRedispatchRetries uses default for missing/blank values", () => {
    expect(resolveMaxRedispatchRetries(undefined)).toBe(DEFAULT_MAX_REDISPATCH_RETRIES);
    expect(resolveMaxRedispatchRetries("")).toBe(DEFAULT_MAX_REDISPATCH_RETRIES);
    expect(resolveMaxRedispatchRetries("   ")).toBe(DEFAULT_MAX_REDISPATCH_RETRIES);
  });

  test("resolveMaxRedispatchRetries parses numeric values", () => {
    expect(resolveMaxRedispatchRetries("0")).toBe(0);
    expect(resolveMaxRedispatchRetries("4")).toBe(4);
  });

  test("validateMaxRedispatchRetries accepts bounded integers", () => {
    expect(validateMaxRedispatchRetries(0)).toBeNull();
    expect(validateMaxRedispatchRetries(10)).toBeNull();
  });

  test("validateMaxRedispatchRetries rejects out-of-range or non-integer values", () => {
    expect(validateMaxRedispatchRetries(-1)).toContain(
      "FLEET_MAX_RETRIES must be an integer between 0 and 10"
    );
    expect(validateMaxRedispatchRetries(11)).toContain(
      "FLEET_MAX_RETRIES must be an integer between 0 and 10"
    );
    expect(validateMaxRedispatchRetries(Number("abc"))).toContain(
      "FLEET_MAX_RETRIES must be an integer between 0 and 10"
    );
    expect(validateMaxRedispatchRetries(1.5)).toContain(
      "FLEET_MAX_RETRIES must be an integer between 0 and 10"
    );
  });
});
