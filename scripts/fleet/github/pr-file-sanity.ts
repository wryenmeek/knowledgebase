import { getSanitizedErrorMessage } from "./mutation-diagnostics.js";

export interface PullRequestFileSanityOptions {
  apiBase: string;
  headers: Record<string, string>;
  prNumber: number;
  fetchImpl?: typeof fetch;
}

export interface PullRequestFileSanityResult {
  ok: boolean;
  file_count: number;
  message: string;
}

export async function inspectPullRequestChangedFiles(
  options: PullRequestFileSanityOptions
): Promise<PullRequestFileSanityResult> {
  const fetchImpl = options.fetchImpl ?? fetch;
  const filesRes = await fetchImpl(
    `${options.apiBase}/pulls/${options.prNumber}/files?per_page=1`,
    {
      headers: options.headers,
    }
  );
  if (!filesRes.ok) {
    const body = getSanitizedErrorMessage(await filesRes.text());
    return {
      ok: false,
      file_count: 0,
      message: `Failed to inspect PR #${options.prNumber} files (${filesRes.status}): ${body}`,
    };
  }

  let files: unknown;
  try {
    files = await filesRes.json();
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return {
      ok: false,
      file_count: 0,
      message: `Failed to parse PR #${options.prNumber} files response: ${message}`,
    };
  }
  if (!Array.isArray(files)) {
    return {
      ok: false,
      file_count: 0,
      message: `Failed to inspect PR #${options.prNumber} files: GitHub response was not an array.`,
    };
  }
  if (files.length === 0) {
    return {
      ok: false,
      file_count: 0,
      message: `Fleet pre-merge sanity check failed for PR #${options.prNumber}: 0/0/0 diff detected.`,
    };
  }

  return {
    ok: true,
    file_count: files.length,
    message: `Fleet pre-merge sanity check passed for PR #${options.prNumber}.`,
  };
}
