import { expect, test, describe, mock } from "bun:test";
import * as git from "./git.ts";

describe("git utils", () => {
  test("parseGitRemoteUrl handles HTTPS", () => {
    const info = git.parseGitRemoteUrl("https://github.com/owner/repo.git");
    expect(info.owner).toBe("owner");
    expect(info.repo).toBe("repo");
    expect(info.fullName).toBe("owner/repo");
  });

  test("parseGitRemoteUrl handles SSH", () => {
    const info = git.parseGitRemoteUrl("git@github.com:owner/repo.git");
    expect(info.owner).toBe("owner");
    expect(info.repo).toBe("repo");
    expect(info.fullName).toBe("owner/repo");
  });

  test("parseGitRemoteUrl rejects unsupported URL formats", () => {
    expect(() => git.parseGitRemoteUrl("ssh://example.com/not-github/repo")).toThrow(
      /Unable to parse git remote URL/
    );
  });

  test("getGitRepoInfo calls git remote get-url with correct arguments", async () => {
    const mockExecFileAsync = mock((file: string, args: string[]) => {
      if (file === "git" && args[0] === "remote" && args[1] === "get-url") {
        return Promise.resolve({ stdout: "https://github.com/owner/repo.git\n" });
      }
      return Promise.reject(new Error("Unknown command"));
    });

    git.gitCommands.execFileAsync = mockExecFileAsync as any;

    const info = await git.getGitRepoInfo("origin");

    expect(mockExecFileAsync).toHaveBeenCalledWith("git", ["remote", "get-url", "--", "origin"]);
    expect(info.fullName).toBe("owner/repo");
  });

  test("getCurrentBranch calls git rev-parse with correct arguments", async () => {
    const mockExecFileAsync = mock((file: string, args: string[]) => {
      if (file === "git" && args[0] === "rev-parse") {
        return Promise.resolve({ stdout: "main\n" });
      }
      return Promise.reject(new Error("Unknown command"));
    });

    git.gitCommands.execFileAsync = mockExecFileAsync as any;

    const branch = await git.getCurrentBranch();

    expect(mockExecFileAsync).toHaveBeenCalledWith("git", ["rev-parse", "--abbrev-ref", "HEAD"]);
    expect(branch).toBe("main");
  });

  test("branchExists checks local refs first", async () => {
    const mockExecFileAsync = mock((file: string, args: string[]) => {
      if (
        file === "git" &&
        args[0] === "show-ref" &&
        args[4] === "refs/heads/main"
      ) {
        return Promise.resolve({ stdout: "" });
      }
      return Promise.reject(new Error("Unknown command"));
    });
    git.gitCommands.execFileAsync = mockExecFileAsync as any;

    const exists = await git.branchExists("main");

    expect(exists).toBe(true);
    expect(mockExecFileAsync).toHaveBeenCalledWith("git", [
      "show-ref",
      "--verify",
      "--quiet",
      "--",
      "refs/heads/main",
    ]);
  });

  test("branchExists falls back to origin refs when local ref is missing", async () => {
    const mockExecFileAsync = mock((file: string, args: string[]) => {
      if (
        file === "git" &&
        args[0] === "show-ref" &&
        args[4] === "refs/heads/main"
      ) {
        return Promise.reject(new Error("not found"));
      }
      if (
        file === "git" &&
        args[0] === "show-ref" &&
        args[4] === "refs/remotes/origin/main"
      ) {
        return Promise.resolve({ stdout: "" });
      }
      return Promise.reject(new Error("Unknown command"));
    });
    git.gitCommands.execFileAsync = mockExecFileAsync as any;

    const exists = await git.branchExists("main");

    expect(exists).toBe(true);
    expect(mockExecFileAsync).toHaveBeenCalledWith("git", [
      "show-ref",
      "--verify",
      "--quiet",
      "--",
      "refs/remotes/origin/main",
    ]);
  });

  test("branchExists returns false when local and origin refs are both missing", async () => {
    const mockExecFileAsync = mock((file: string, args: string[]) => {
      if (
        file === "git" &&
        args[0] === "show-ref" &&
        (args[4] === "refs/heads/missing" || args[4] === "refs/remotes/origin/missing")
      ) {
        return Promise.reject(new Error("not found"));
      }
      return Promise.reject(new Error("Unknown command"));
    });
    git.gitCommands.execFileAsync = mockExecFileAsync as any;

    const exists = await git.branchExists("missing");

    expect(exists).toBe(false);
    expect(mockExecFileAsync).toHaveBeenCalledWith("git", [
      "show-ref",
      "--verify",
      "--quiet",
      "--",
      "refs/heads/missing",
    ]);
    expect(mockExecFileAsync).toHaveBeenCalledWith("git", [
      "show-ref",
      "--verify",
      "--quiet",
      "--",
      "refs/remotes/origin/missing",
    ]);
  });
});

describe("security regressions", () => {
  test("getGitRepoInfo handles malicious remote names safely (no shell injection)", async () => {
    const mockExecFileAsync = mock((file: string, args: string[]) => {
      return Promise.resolve({ stdout: "https://github.com/owner/repo.git\n" });
    });
    git.gitCommands.execFileAsync = mockExecFileAsync as any;

    const malicious = "origin; echo pwned";
    const info = await git.getGitRepoInfo(malicious);

    expect(mockExecFileAsync).toHaveBeenCalledWith("git", ["remote", "get-url", "--", malicious]);
    expect(info.fullName).toBe("owner/repo");
  });

  test("getGitRepoInfo handles malicious remote names safely (no option injection)", async () => {
    const mockExecFileAsync = mock((file: string, args: string[]) => {
      return Promise.resolve({ stdout: "https://github.com/owner/repo.git\n" });
    });
    git.gitCommands.execFileAsync = mockExecFileAsync as any;

    const malicious = "--help";
    const info = await git.getGitRepoInfo(malicious);

    expect(mockExecFileAsync).toHaveBeenCalledWith("git", ["remote", "get-url", "--", malicious]);
    expect(info.fullName).toBe("owner/repo");
  });
});
