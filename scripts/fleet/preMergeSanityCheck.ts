import { spawnSync } from "node:child_process";

export interface SanityCheckResult {
  ok: boolean;
  staged_files: string[];
  unexpected_paths: string[];
  missing_expected_paths: string[];
  gitignore_status: Record<string, string>;
}

export interface PreMergeSanityCheckOptions {
  allowAdditional?: boolean;
  runGitCheckIgnore?: boolean;
}

interface GitResult {
  status: number;
  stdout: string;
  stderr: string;
}

interface StagedChange {
  status: string;
  path: string;
}

function runGit(args: string[]): GitResult {
  const result = spawnSync("git", args, {
    encoding: "utf8",
  });
  if (result.error) {
    throw result.error;
  }
  return {
    status: result.status ?? 1,
    stdout: String(result.stdout ?? ""),
    stderr: String(result.stderr ?? ""),
  };
}

function parseNameStatusZ(stdout: string): StagedChange[] {
  const parts = stdout.split("\0");
  const changes: StagedChange[] = [];

  for (let index = 0; index < parts.length; ) {
    const status = parts[index++];
    if (!status) {
      continue;
    }

    if (status.startsWith("R") || status.startsWith("C")) {
      index++;
      const path = parts[index++];
      if (path) {
        changes.push({ status, path });
      }
      continue;
    }

    const path = parts[index++];
    if (path) {
      changes.push({ status, path });
    }
  }

  return changes;
}

function isDeleted(change: StagedChange): boolean {
  return change.status.startsWith("D");
}

function gitCheckIgnoreStatus(expectedPath: string): string {
  const result = runGit(["check-ignore", "--verbose", "--", expectedPath]);
  if (result.status === 0) {
    return result.stdout.trim() || "ignored (git check-ignore exit 0)";
  }
  if (result.status === 1) {
    return "not ignored (git check-ignore exit 1)";
  }
  const detail = (result.stderr || result.stdout).trim();
  return detail
    ? `git check-ignore failed (exit ${result.status}): ${detail}`
    : `git check-ignore failed (exit ${result.status})`;
}

function gitignoreStatuses(expectedPaths: string[]): Record<string, string> {
  return Object.fromEntries(
    expectedPaths.map((expectedPath) => [
      expectedPath,
      gitCheckIgnoreStatus(expectedPath),
    ])
  );
}

export function preMergeSanityCheck(
  expectedPaths: string[],
  options: PreMergeSanityCheckOptions = {}
): SanityCheckResult {
  const diff = runGit(["diff", "--cached", "--name-status", "--no-renames", "-z"]);
  if (diff.status !== 0) {
    const detail = (diff.stderr || diff.stdout).trim();
    throw new Error(
      detail
        ? `git diff --cached --name-status --no-renames -z failed (exit ${diff.status}): ${detail}`
        : `git diff --cached --name-status --no-renames -z failed (exit ${diff.status})`
    );
  }

  const stagedChanges = parseNameStatusZ(diff.stdout);
  const stagedFiles = stagedChanges.map((change) => change.path);
  const expectedSet = new Set(expectedPaths);
  const stagedNonDeletedSet = new Set(
    stagedChanges
      .filter((change) => !isDeleted(change))
      .map((change) => change.path)
  );
  const missingExpectedPaths = expectedPaths.filter(
    (expectedPath) => !stagedNonDeletedSet.has(expectedPath)
  );
  const unexpectedPaths =
    expectedPaths.length > 0 && options.allowAdditional !== true
      ? stagedFiles.filter((stagedFile) => !expectedSet.has(stagedFile))
      : [];
  const ok =
    (expectedPaths.length > 0 || options.allowAdditional === true) &&
    stagedFiles.length > 0 &&
    missingExpectedPaths.length === 0 &&
    unexpectedPaths.length === 0;

  return {
    ok,
    staged_files: stagedFiles,
    unexpected_paths: unexpectedPaths,
    missing_expected_paths: missingExpectedPaths,
    gitignore_status:
      !ok && options.runGitCheckIgnore !== false && expectedPaths.length > 0
        ? gitignoreStatuses(expectedPaths)
        : {},
  };
}

export function formatPreMergeSanityFailure(
  result: SanityCheckResult,
  expectedPaths: string[]
): string {
  const lines = [
    "❌ Fleet pre-merge sanity check failed.",
    "0/0/0 staged-diff or path-scope drift detected before branch push.",
    "",
    `Staged files (${result.staged_files.length}):`,
    ...(result.staged_files.length > 0
      ? result.staged_files.map((filePath) => `  - ${filePath}`)
      : ["  - <none>"]),
  ];

  if (expectedPaths.length > 0) {
    lines.push("", "Expected paths:", ...expectedPaths.map((filePath) => `  - ${filePath}`));
  }
  if (result.missing_expected_paths.length > 0) {
    lines.push(
      "",
      "Missing expected paths:",
      ...result.missing_expected_paths.map((filePath) => `  - ${filePath}`)
    );
  }
  if (result.unexpected_paths.length > 0) {
    lines.push(
      "",
      "Unexpected staged paths:",
      ...result.unexpected_paths.map((filePath) => `  - ${filePath}`)
    );
  }
  if (Object.keys(result.gitignore_status).length > 0) {
    lines.push(
      "",
      "git check-ignore --verbose status:",
      ...Object.entries(result.gitignore_status).map(
        ([filePath, status]) => `  - ${filePath}: ${status}`
      )
    );
  }

  return lines.join("\n");
}

function shellArgsForPrompt(
  expectedPaths: string[],
  options: { allowAdditional?: boolean }
): string {
  const args = expectedPaths.flatMap((expectedPath) => [
    "--expected",
    shellQuote(expectedPath),
  ]);
  if (options.allowAdditional === true) {
    args.push("--allow-additional");
  }
  return args.join(" ");
}

function shellQuote(value: string): string {
  return `'${value.replaceAll("'", "'\\''")}'`;
}

function shellArgs(values: string[]): string {
  return values.map(shellQuote).join(" ");
}

export function buildPreMergeSanityPromptBlock(
  expectedPaths: string[],
  options: { allowAdditional?: boolean } = {}
): string {
  const expectedPathList =
    expectedPaths.length > 0
      ? expectedPaths.map((filePath) => `- \`${filePath}\``).join("\n")
      : "- <open per-task file scope>";
  const pathScopeRule =
    expectedPaths.length > 0 && options.allowAdditional !== true
      ? "Every staged path must be one of the expected paths, and every expected path must be staged."
      : "Per-task file scope is open: do not path-match, but at least one file must be staged.";
  const gitignoreDiagnostic =
    expectedPaths.length > 0
      ? `If the check fails, run \`git check-ignore --verbose -- ${shellArgs(expectedPaths)}\` and include its output in the failure message.`
      : "If the check fails, include `git status --short` output in the failure message.";
  const commandArgs = shellArgsForPrompt(expectedPaths, options);
  const command = `bun scripts/fleet/preMergeSanityCheck.ts${commandArgs ? ` ${commandArgs}` : ""}`;

  return `## Mandatory pre-merge sanity check

Before pushing a branch or finalizing a PR, run this from the repository root:

\`\`\`bash
${command}
\`\`\`

The helper checks \`git diff --cached --name-status --no-renames -z\`. Fail closed and do not push if the command exits non-zero. ${pathScopeRule}

Expected paths:
${expectedPathList}

${gitignoreDiagnostic}
This catches the Layer 2 gitignore-suppression trap where files were written but not staged.`;
}

function parseCliArgs(args: string[]): {
  expectedPaths: string[];
  options: PreMergeSanityCheckOptions;
} {
  const expectedPaths: string[] = [];
  const options: PreMergeSanityCheckOptions = {};

  for (let index = 0; index < args.length; index++) {
    const arg = args[index];
    if (arg === "--expected") {
      const expectedPath = args[++index];
      if (!expectedPath) {
        throw new Error("--expected requires a path value");
      }
      expectedPaths.push(expectedPath);
      continue;
    }
    if (arg === "--allow-additional") {
      options.allowAdditional = true;
      continue;
    }
    if (arg === "--no-git-check-ignore") {
      options.runGitCheckIgnore = false;
      continue;
    }
    throw new Error(`Unsupported argument: ${arg}`);
  }

  if (expectedPaths.length === 0 && options.allowAdditional !== true) {
    throw new Error(
      "expected paths are required unless --allow-additional explicitly selects open-scope mode"
    );
  }

  return { expectedPaths, options };
}

export function runPreMergeSanityCheckCli(args = process.argv.slice(2)): never {
  try {
    const { expectedPaths, options } = parseCliArgs(args);
    const result = preMergeSanityCheck(expectedPaths, options);
    if (result.ok) {
      console.log(
        `✅ Fleet pre-merge sanity check passed (${result.staged_files.length} staged file(s)).`
      );
      process.exit(0);
    }
    console.log(formatPreMergeSanityFailure(result, expectedPaths));
    process.exit(1);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.log(`❌ Fleet pre-merge sanity check failed: ${message}`);
    process.exit(1);
  }
}

if (import.meta.main) {
  runPreMergeSanityCheckCli();
}
