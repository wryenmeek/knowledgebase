import { describe, expect, test } from "bun:test";
import path from "node:path";

const ENTRYPOINTS = [
  "fleet-plan.ts",
  "fleet-dispatch.ts",
  "fleet-merge.ts",
] as const;

describe("fleet entrypoint wiring", () => {
  const entrypointPath = (entrypoint: string): string =>
    path.join(import.meta.dir, entrypoint);

  for (const entrypoint of ENTRYPOINTS) {
    test(`${entrypoint} keeps fail-closed mutation wiring`, async () => {
      const source = await Bun.file(entrypointPath(entrypoint)).text();
      expect(source).toContain("assertFleetEnvironment(");
      expect(source).toContain("assertMutationPreflight(");
      expect(source).toContain("branchExists(");
      expect(source).toContain("runMutationWithDiagnostics(");
      expect(source).toContain("main().catch(handleFatalError);");
    });
  }

  test("dispatch and merge honor FLEET_PENDING_DATE for cross-day runs", async () => {
    const dispatchSource = await Bun.file(entrypointPath("fleet-dispatch.ts")).text();
    const mergeSource = await Bun.file(entrypointPath("fleet-merge.ts")).text();
    expect(dispatchSource).toContain("process.env.FLEET_PENDING_DATE");
    expect(mergeSource).toContain("process.env.FLEET_PENDING_DATE");
  });

  test("plan and dispatch append pre-merge sanity guard prompts", async () => {
    const planSource = await Bun.file(entrypointPath("fleet-plan.ts")).text();
    const dispatchSource = await Bun.file(entrypointPath("fleet-dispatch.ts")).text();

    expect(planSource).toContain('from "./preMergeSanityCheck.js"');
    expect(planSource).toContain("expectedPlanningArtifactPaths");
    expect(planSource).toContain("buildPreMergeSanityPromptBlock(expectedPlanningArtifactPaths)");
    expect(planSource).toContain("issue_tasks.md");
    expect(planSource).toContain("issue_tasks.json");

    expect(dispatchSource).toContain('from "./preMergeSanityCheck.js"');
    expect(dispatchSource).toContain("buildPreMergeSanityPromptBlock([], { allowAdditional: true })");
  });

  test("merge inspects per-task PR file lists before CI and merge", async () => {
    const mergeSource = await Bun.file(entrypointPath("fleet-merge.ts")).text();
    expect(mergeSource).toContain('from "./github/pr-file-sanity.js"');
    expect(mergeSource).toContain("options.inspectChangedFiles ?? inspectPullRequestChangedFiles");
    expect(mergeSource).toContain("inspectChangedFiles({");
    expect(mergeSource).toContain("if (!fileSanity.ok)");
    expect(mergeSource.indexOf("inspectChangedFiles({")).toBeLessThan(
      mergeSource.indexOf("waitForCIImpl({")
    );
    expect(mergeSource).toContain("ciPassed = await runFleetMergePreMergeGate({");
    expect(mergeSource.indexOf("ciPassed = await runFleetMergePreMergeGate({")).toBeLessThan(
      mergeSource.indexOf("if (!ciPassed)")
    );
    expect(mergeSource.indexOf("ciPassed = await runFleetMergePreMergeGate({")).toBeLessThan(
      mergeSource.indexOf("  ✅ CI passed. Merging PR")
    );
  });

  test("merge enforces fail-closed no-checks policy with explicit override", async () => {
    const mergeSource = await Bun.file(entrypointPath("fleet-merge.ts")).text();
    const mergeCiSource = await Bun.file(path.join(import.meta.dir, "github/merge-ci.ts")).text();
    expect(mergeSource).toContain(
      'const ALLOW_NO_CHECKS = process.env.FLEET_ALLOW_NO_CHECKS === "true"'
    );
    expect(mergeSource).toContain('from "./github/merge-ci.js"');
    expect(mergeCiSource).toContain("No check runs found for PR");
    expect(mergeCiSource).toContain("FLEET_ALLOW_NO_CHECKS=true");
  });

  test("merge validates redispatch retry bounds", async () => {
    const mergeSource = await Bun.file(entrypointPath("fleet-merge.ts")).text();
    expect(mergeSource).toContain('from "./github/retry-config.js"');
    expect(mergeSource).toContain("resolveMaxRedispatchRetries(process.env.FLEET_MAX_RETRIES)");
    expect(mergeSource).toContain("validateMaxRedispatchRetries(MAX_RETRIES)");
  });

  test("merge redispatch PR matching does not trust PR body text", async () => {
    const mergeSource = await Bun.file(entrypointPath("fleet-merge.ts")).text();
    expect(mergeSource).toContain("allowBodyMatch: false");
    expect(mergeSource).not.toContain("allowBodyMatch: true");
  });

  test("fleet-analyze remains read-only without mutation env bootstrap", async () => {
    const analyzeSource = await Bun.file(entrypointPath("fleet-analyze.ts")).text();
    expect(analyzeSource).not.toContain('./env.js');
    expect(analyzeSource).not.toContain("assertFleetEnvironment(");
  });
});
