import { expect, test, describe } from "bun:test";
import { getGitRepoInfo, getCurrentBranch, parseGitRemoteUrl } from "./git.ts";

describe("git utils", () => {
  test("parseGitRemoteUrl handles HTTPS", () => {
    const info = parseGitRemoteUrl("https://github.com/owner/repo.git");
    expect(info.owner).toBe("owner");
    expect(info.repo).toBe("repo");
    expect(info.fullName).toBe("owner/repo");
  });

  test("parseGitRemoteUrl handles SSH", () => {
    const info = parseGitRemoteUrl("git@github.com:owner/repo.git");
    expect(info.owner).toBe("owner");
    expect(info.repo).toBe("repo");
    expect(info.fullName).toBe("owner/repo");
  });

  test("getGitRepoInfo works", async () => {
    const info = await getGitRepoInfo("origin");
    expect(info.owner).toBeDefined();
    expect(info.repo).toBeDefined();
  });

  test("getCurrentBranch works", async () => {
    const branch = await getCurrentBranch();
    expect(branch).toBeDefined();
    expect(branch.length).toBeGreaterThan(0);
  });
});
