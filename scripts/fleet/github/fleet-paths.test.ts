import { describe, expect, test } from "bun:test";
import fs from "node:fs";
import path from "node:path";
import { findFleetRepoRoot, resolveFleetDir } from "./fleet-paths.ts";

const TEST_WORKDIR_ROOT = path.resolve(import.meta.dir, "..", ".test-workdirs");

function withRepoFixture(
  name: string,
  setupGitEntry: (repoRoot: string) => void,
  assertFixture: (nestedPath: string, repoRoot: string) => void
): void {
  const repoRoot = path.join(
    TEST_WORKDIR_ROOT,
    `${name}-${process.pid}-${Date.now()}`
  );
  const nestedPath = path.join(repoRoot, "scripts", "fleet");
  fs.mkdirSync(nestedPath, { recursive: true });
  setupGitEntry(repoRoot);

  try {
    assertFixture(nestedPath, repoRoot);
  } finally {
    fs.rmSync(repoRoot, { recursive: true, force: true });
    try {
      fs.rmdirSync(TEST_WORKDIR_ROOT);
    } catch {
      // Another fixture may still be using the shared test workdir root.
    }
  }
}

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

describe("findFleetRepoRoot", () => {
  test("resolves standard checkouts where .git is a directory", () => {
    withRepoFixture(
      "git-directory",
      (repoRoot) => {
        fs.mkdirSync(path.join(repoRoot, ".git"));
      },
      (nestedPath, repoRoot) => {
        expect(findFleetRepoRoot(nestedPath)).toBe(repoRoot);
      }
    );
  });

  test("resolves linked worktrees where .git is a file", () => {
    withRepoFixture(
      "git-file",
      (repoRoot) => {
        fs.writeFileSync(path.join(repoRoot, ".git"), "gitdir: ../.git/worktrees/example\n");
      },
      (nestedPath, repoRoot) => {
        expect(findFleetRepoRoot(nestedPath)).toBe(repoRoot);
      }
    );
  });
});
