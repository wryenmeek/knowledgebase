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
