import { afterEach, describe, expect, test } from "bun:test";
import { spawnSync } from "node:child_process";
import {
  mkdirSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import path from "node:path";
import {
  buildPreMergeSanityPromptBlock,
  preMergeSanityCheck,
} from "./preMergeSanityCheck.js";

const SCRATCH_ROOT = path.join(import.meta.dir, ".test-scratch", "pre-merge-sanity");
const ORIGINAL_CWD = process.cwd();
let fixtureCounter = 0;

function runGit(repo: string, ...args: string[]): void {
  const result = spawnSync("git", args, {
    cwd: repo,
    encoding: "utf8",
  });
  if (result.status !== 0) {
    throw new Error(
      `git ${args.join(" ")} failed with exit ${result.status}: ${result.stderr}`
    );
  }
}

function createFixtureRepo(name: string): string {
  const repo = path.join(
    SCRATCH_ROOT,
    `${name}-${process.pid}-${fixtureCounter++}`
  );
  rmSync(repo, { recursive: true, force: true });
  mkdirSync(repo, { recursive: true });

  runGit(repo, "init", "-b", "main");
  runGit(repo, "config", "user.name", "Pre Merge Sanity");
  runGit(repo, "config", "user.email", "pre-merge-sanity@example.invalid");

  writeFileSync(path.join(repo, "README.md"), "# fixture\n");
  runGit(repo, "add", "README.md");
  runGit(repo, "commit", "-m", "fixture: initial commit");

  return repo;
}

function writeAndStage(repo: string, relPath: string, contents: string): void {
  const target = path.join(repo, relPath);
  mkdirSync(path.dirname(target), { recursive: true });
  writeFileSync(target, contents);
  runGit(repo, "add", "--", relPath);
}

afterEach(() => {
  process.chdir(ORIGINAL_CWD);
  rmSync(SCRATCH_ROOT, { recursive: true, force: true });
});

describe("preMergeSanityCheck", () => {
  test("passes when staged files match the expected paths", () => {
    const repo = createFixtureRepo("happy-path");
    writeAndStage(repo, ".fleet/2026_06_21/issue_tasks.json", "{}\n");
    process.chdir(repo);

    const result = preMergeSanityCheck([
      ".fleet/2026_06_21/issue_tasks.json",
    ]);

    expect(result.ok).toBe(true);
    expect(result.staged_files).toEqual([
      ".fleet/2026_06_21/issue_tasks.json",
    ]);
    expect(result.unexpected_paths).toEqual([]);
    expect(result.missing_expected_paths).toEqual([]);
    expect(result.gitignore_status).toEqual({});
  });

  test("fails closed and reports gitignore status when nothing is staged", () => {
    const repo = createFixtureRepo("empty-diff");
    writeFileSync(path.join(repo, ".gitignore"), ".fleet/\n");
    runGit(repo, "add", ".gitignore");
    runGit(repo, "commit", "-m", "fixture: ignore fleet artifacts");

    const expectedPath = ".fleet/2026_06_21/issue_tasks.json";
    const ignoredTarget = path.join(repo, expectedPath);
    mkdirSync(path.dirname(ignoredTarget), { recursive: true });
    writeFileSync(ignoredTarget, "{}\n");
    process.chdir(repo);

    const result = preMergeSanityCheck([expectedPath]);

    expect(result.ok).toBe(false);
    expect(result.staged_files).toEqual([]);
    expect(result.unexpected_paths).toEqual([]);
    expect(result.missing_expected_paths).toEqual([expectedPath]);
    expect(result.gitignore_status[expectedPath]).toContain(".gitignore");
    expect(result.gitignore_status[expectedPath]).toContain(".fleet/");
  });

  test("CLI exits non-zero with clear stdout when nothing is staged", () => {
    const repo = createFixtureRepo("empty-diff-cli");
    writeFileSync(path.join(repo, ".gitignore"), ".fleet/\n");
    runGit(repo, "add", ".gitignore");
    runGit(repo, "commit", "-m", "fixture: ignore fleet artifacts");

    const expectedPath = ".fleet/2026_06_21/issue_tasks.md";
    const ignoredTarget = path.join(repo, expectedPath);
    mkdirSync(path.dirname(ignoredTarget), { recursive: true });
    writeFileSync(ignoredTarget, "# ignored planning artifact\n");

    const result = spawnSync(
      "bun",
      [path.join(import.meta.dir, "preMergeSanityCheck.ts"), "--expected", expectedPath],
      {
        cwd: repo,
        encoding: "utf8",
      }
    );

    expect(result.status).not.toBe(0);
    expect(result.stdout).toContain("Fleet pre-merge sanity check failed");
    expect(result.stdout).toContain("0/0/0 staged-diff");
    expect(result.stdout).toContain("git check-ignore --verbose status");
    expect(result.stdout).toContain(expectedPath);
    expect(result.stdout).toContain(".gitignore");
  });

  test("fails closed when a staged file is outside the expected paths", () => {
    const repo = createFixtureRepo("wrong-path");
    writeAndStage(repo, "unexpected.txt", "wrong path\n");
    process.chdir(repo);

    const result = preMergeSanityCheck(["expected.txt"]);

    expect(result.ok).toBe(false);
    expect(result.staged_files).toEqual(["unexpected.txt"]);
    expect(result.unexpected_paths).toEqual(["unexpected.txt"]);
    expect(result.missing_expected_paths).toEqual(["expected.txt"]);
    expect(result.gitignore_status["expected.txt"]).toContain("not ignored");
  });

  test("fails closed when an expected path is staged as a deletion", () => {
    const repo = createFixtureRepo("deleted-expected-path");
    writeAndStage(repo, "expected.txt", "expected contents\n");
    runGit(repo, "commit", "-m", "fixture: add expected file");
    runGit(repo, "rm", "expected.txt");
    process.chdir(repo);

    const result = preMergeSanityCheck(["expected.txt"]);

    expect(result.ok).toBe(false);
    expect(result.staged_files).toEqual(["expected.txt"]);
    expect(result.missing_expected_paths).toEqual(["expected.txt"]);
    expect(result.gitignore_status["expected.txt"]).toContain("not ignored");
  });

  test("fails closed when a rename moves an unexpected source into an expected path", () => {
    const repo = createFixtureRepo("rename-into-expected-path");
    writeAndStage(repo, "source.txt", "source contents\n");
    runGit(repo, "commit", "-m", "fixture: add source file");
    runGit(repo, "mv", "source.txt", "expected.txt");
    process.chdir(repo);

    const result = preMergeSanityCheck(["expected.txt"]);

    expect(result.ok).toBe(false);
    expect(result.staged_files.toSorted()).toEqual(["expected.txt", "source.txt"]);
    expect(result.unexpected_paths).toEqual(["source.txt"]);
    expect(result.missing_expected_paths).toEqual([]);
  });

  test("passes in open-scope mode when any file is staged", () => {
    const repo = createFixtureRepo("open-scope");
    writeAndStage(repo, "src/change.ts", "export const changed = true;\n");
    process.chdir(repo);

    const result = preMergeSanityCheck([], { allowAdditional: true });

    expect(result.ok).toBe(true);
    expect(result.staged_files).toEqual(["src/change.ts"]);
    expect(result.unexpected_paths).toEqual([]);
    expect(result.missing_expected_paths).toEqual([]);
    expect(result.gitignore_status).toEqual({});
  });

  test("open-scope CLI fails closed on an empty staged diff", () => {
    const repo = createFixtureRepo("open-scope-empty-cli");

    const result = spawnSync(
      "bun",
      [path.join(import.meta.dir, "preMergeSanityCheck.ts"), "--allow-additional"],
      {
        cwd: repo,
        encoding: "utf8",
      }
    );

    expect(result.status).not.toBe(0);
    expect(result.stdout).toContain("Fleet pre-merge sanity check failed");
    expect(result.stdout).toContain("0/0/0 staged-diff");
    expect(result.stdout).toContain("Staged files (0):");
    expect(result.stdout).toContain("<none>");
  });

  test("CLI requires explicit open-scope mode when expected paths are omitted", () => {
    const repo = createFixtureRepo("missing-scope-cli");
    writeAndStage(repo, "src/change.ts", "export const changed = true;\n");

    const result = spawnSync(
      "bun",
      [path.join(import.meta.dir, "preMergeSanityCheck.ts")],
      {
        cwd: repo,
        encoding: "utf8",
      }
    );

    expect(result.status).not.toBe(0);
    expect(result.stdout).toContain("expected paths are required");
    expect(result.stdout).toContain("--allow-additional");
  });

  test("prompt block uses strict expected paths for fleet-plan", () => {
    const block = buildPreMergeSanityPromptBlock([
      ".fleet/2026_06_21/issue_tasks.md",
      ".fleet/2026_06_21/issue_tasks.json",
    ]);

    expect(block).toContain("bun scripts/fleet/preMergeSanityCheck.ts");
    expect(block).toContain("--expected '.fleet/2026_06_21/issue_tasks.md'");
    expect(block).toContain("--expected '.fleet/2026_06_21/issue_tasks.json'");
    expect(block).not.toContain("--allow-additional");
    expect(block).toContain("Every staged path must be one of the expected paths");
  });

  test("prompt block shell-quotes paths with metacharacters", () => {
    const block = buildPreMergeSanityPromptBlock([
      "docs/path with spaces/it's-$afe.md",
    ]);

    expect(block).toContain("--expected 'docs/path with spaces/it'\\''s-$afe.md'");
    expect(block).toContain(
      "git check-ignore --verbose -- 'docs/path with spaces/it'\\''s-$afe.md'"
    );
  });

  test("prompt block uses explicit open-scope mode for fleet-dispatch", () => {
    const block = buildPreMergeSanityPromptBlock([], { allowAdditional: true });

    expect(block).toContain(
      "bun scripts/fleet/preMergeSanityCheck.ts --allow-additional"
    );
    expect(block).toContain("<open per-task file scope>");
    expect(block).toContain("Per-task file scope is open");
  });
});
