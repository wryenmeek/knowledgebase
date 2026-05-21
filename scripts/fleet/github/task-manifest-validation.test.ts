import { describe, expect, test } from "bun:test";
import type { IssueAnalysis } from "../types.ts";
import { validateTaskOwnership } from "./task-manifest-validation.ts";

function makeAnalysis(tasks: IssueAnalysis["tasks"]): IssueAnalysis {
  return {
    repo: "owner/repo",
    analyzed_at: new Date().toISOString(),
    root_causes: [],
    tasks,
    unaddressable: [],
    file_ownership: {},
  };
}

describe("validateTaskOwnership", () => {
  test("passes for unique task IDs and disjoint files", () => {
    const analysis = makeAnalysis([
      {
        id: "task-a",
        title: "Task A",
        root_cause: "root-a",
        issues: [1],
        files: ["a.ts"],
        new_files: [],
        test_files: [],
        risk: "low",
        prompt: "do a",
      },
      {
        id: "task-b",
        title: "Task B",
        root_cause: "root-b",
        issues: [2],
        files: ["b.ts"],
        new_files: [],
        test_files: [],
        risk: "low",
        prompt: "do b",
      },
    ]);

    expect(() => validateTaskOwnership(analysis)).not.toThrow();
  });

  test("fails for duplicate task IDs", () => {
    const analysis = makeAnalysis([
      {
        id: "task-a",
        title: "Task A",
        root_cause: "root-a",
        issues: [1],
        files: ["a.ts"],
        new_files: [],
        test_files: [],
        risk: "low",
        prompt: "do a",
      },
      {
        id: "task-a",
        title: "Task A duplicate",
        root_cause: "root-b",
        issues: [2],
        files: ["b.ts"],
        new_files: [],
        test_files: [],
        risk: "low",
        prompt: "do b",
      },
    ]);

    expect(() => validateTaskOwnership(analysis)).toThrow(/Duplicate task id/);
  });

  test("fails for file ownership conflicts", () => {
    const analysis = makeAnalysis([
      {
        id: "task-a",
        title: "Task A",
        root_cause: "root-a",
        issues: [1],
        files: ["shared.ts"],
        new_files: [],
        test_files: [],
        risk: "low",
        prompt: "do a",
      },
      {
        id: "task-b",
        title: "Task B",
        root_cause: "root-b",
        issues: [2],
        files: ["shared.ts"],
        new_files: [],
        test_files: [],
        risk: "low",
        prompt: "do b",
      },
    ]);

    expect(() => validateTaskOwnership(analysis)).toThrow(/Ownership conflict/);
  });

  test("fails for ownership conflicts in new_files and test_files", () => {
    const analysis = makeAnalysis([
      {
        id: "task-a",
        title: "Task A",
        root_cause: "root-a",
        issues: [1],
        files: [],
        new_files: ["shared-new.ts"],
        test_files: [],
        risk: "low",
        prompt: "do a",
      },
      {
        id: "task-b",
        title: "Task B",
        root_cause: "root-b",
        issues: [2],
        files: [],
        new_files: [],
        test_files: ["shared-new.ts"],
        risk: "low",
        prompt: "do b",
      },
    ]);

    expect(() => validateTaskOwnership(analysis)).toThrow(/Ownership conflict/);
  });
});
