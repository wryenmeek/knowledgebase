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

// Regression test for the silent fleet-plan failure mode where `.gitignore`
// excluded every per-date planning subdirectory under `.fleet/`. Jules's
// planning agent wrote `.fleet/YYYY_MM_DD/issue_tasks.{md,json}` to disk,
// `git add .` skipped them, and the resulting PR had an empty diff while
// the body confidently described a 15-issue / 7-task analysis. fleet-dispatch.ts
// then read an empty (or stale) tasks file and produced no dispatch.
//
// Origin: .gitignore line `.fleet/` was added in commit 50e9d68 on 2026-05-23
// without negation lines for the canonical planning artifacts. Diagnosis trail
// is on Issue #82 / PR #307 (2026-06-20).
//
// Oracle: `git check-ignore` (without `--no-index` for real files) returns
// exit code 0 if the path IS ignored, 1 if it is NOT ignored. We avoid `-v`
// because its output combines positive and negation rule matches, and exit
// codes are easier to assert against than parsed verbose output. We also
// avoid `git status`, which collapses untracked-directory listings and would
// hide individual-file ignore decisions.

import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, test, beforeAll, afterAll } from "bun:test";

const REPO_ROOT = resolve(import.meta.dir, "..", "..");

// Canonical planning artifact filenames produced by Jules per the
// analyze-issues.ts prompt template (Phase 3 output) and consumed by
// fleet-dispatch.ts (`path.join(fleetDir, "issue_tasks.json")`).
const PLANNING_ARTIFACT_FILENAMES = [
  "issue_tasks.json",
  "issue_tasks.md",
  "sessions.json",
] as const;

// Use a far-future date that will never collide with a real fleet run so the
// test is deterministic regardless of when it executes. We materialize the
// path on disk because `git check-ignore` resolves paths relative to the
// working tree and gives the most reliable signal for real files.
const PROBE_FLEET_DATE = "2099_01_01";
const PROBE_DIR = resolve(REPO_ROOT, ".fleet", PROBE_FLEET_DATE);

function isIgnored(relPath: string): boolean {
  const result = Bun.spawnSync({
    cmd: ["git", "check-ignore", relPath],
    cwd: REPO_ROOT,
    stdout: "pipe",
    stderr: "pipe",
  });
  // git check-ignore exit codes (without -v / --non-matching):
  //   0  → path IS ignored
  //   1  → path is NOT ignored
  //   >1 → fatal error
  if (result.exitCode !== 0 && result.exitCode !== 1) {
    const stderr = new TextDecoder().decode(
      result.stderr ?? new Uint8Array()
    );
    throw new Error(
      `git check-ignore failed with exit ${result.exitCode}: ${stderr}`
    );
  }
  return result.exitCode === 0;
}

describe("fleet planning artifacts must be committable (not gitignored)", () => {
  beforeAll(() => {
    mkdirSync(PROBE_DIR, { recursive: true });
    for (const filename of PLANNING_ARTIFACT_FILENAMES) {
      writeFileSync(resolve(PROBE_DIR, filename), "test-probe\n");
    }
    writeFileSync(resolve(PROBE_DIR, "scratch.txt"), "test-probe\n");
  });

  afterAll(() => {
    rmSync(PROBE_DIR, { recursive: true, force: true });
  });

  for (const filename of PLANNING_ARTIFACT_FILENAMES) {
    const probePath = `.fleet/${PROBE_FLEET_DATE}/${filename}`;
    test(`${probePath} is committable`, () => {
      expect(isIgnored(probePath)).toBe(false);
    });
  }

  test("non-canonical paths under .fleet/<date>/ ARE still gitignored (negation is scoped)", () => {
    // Sanity check: the negations are intentionally narrow — only the three
    // planning artifact filenames are allowed back in. Any other path under
    // .fleet/ (e.g. cached SDK responses, scratch files) should remain ignored
    // so fleet runs cannot accidentally commit transient state.
    expect(isIgnored(`.fleet/${PROBE_FLEET_DATE}/scratch.txt`)).toBe(true);
  });
});

