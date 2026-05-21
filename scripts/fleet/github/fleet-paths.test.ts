import { describe, expect, test } from "bun:test";
import path from "node:path";
import { resolveFleetDir } from "./fleet-paths.ts";

describe("resolveFleetDir", () => {
  test("returns fleet date directory for valid date format", () => {
    const root = path.resolve("/tmp/knowledgebase");
    const fleetDir = resolveFleetDir(root, "2026_05_21");
    expect(fleetDir).toBe(path.resolve(root, ".fleet", "2026_05_21"));
  });

  test("fails closed for invalid fleet date format", () => {
    expect(() => resolveFleetDir("/tmp/knowledgebase", "../bad")).toThrow(
      "Invalid FLEET_PENDING_DATE"
    );
    expect(() => resolveFleetDir("/tmp/knowledgebase", "2026-05-21")).toThrow(
      "Invalid FLEET_PENDING_DATE"
    );
  });
});

