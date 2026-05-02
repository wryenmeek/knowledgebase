// @bun
var __create = Object.create;
var __getProtoOf = Object.getPrototypeOf;
var __defProp = Object.defineProperty;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __toESM = (mod, isNodeMode, target) => {
  target = mod != null ? __create(__getProtoOf(mod)) : {};
  const to = isNodeMode || !mod || !mod.__esModule ? __defProp(target, "default", { value: mod, enumerable: true }) : target;
  for (let key of __getOwnPropNames(mod))
    if (!__hasOwnProp.call(to, key))
      __defProp(to, key, {
        get: () => mod[key],
        enumerable: true
      });
  return to;
};
var __commonJS = (cb, mod) => () => (mod || cb((mod = { exports: {} }).exports, mod), mod.exports);

// fleet-merge.ts
import path4 from "path";

// node_modules/find-up/index.js
import path2 from "path";

// node_modules/locate-path/index.js
import process2 from "process";
import path from "path";
import fs, { promises as fsPromises } from "fs";
import { fileURLToPath } from "url";
var typeMappings = {
  directory: "isDirectory",
  file: "isFile"
};
function checkType(type) {
  if (Object.hasOwnProperty.call(typeMappings, type)) {
    return;
  }
  throw new Error(`Invalid type specified: ${type}`);
}
var matchType = (type, stat) => stat[typeMappings[type]]();
var toPath = (urlOrPath) => urlOrPath instanceof URL ? fileURLToPath(urlOrPath) : urlOrPath;
function locatePathSync(paths, {
  cwd = process2.cwd(),
  type = "file",
  allowSymlinks = true
} = {}) {
  checkType(type);
  cwd = toPath(cwd);
  const statFunction = allowSymlinks ? fs.statSync : fs.lstatSync;
  for (const path_ of paths) {
    try {
      const stat = statFunction(path.resolve(cwd, path_), {
        throwIfNoEntry: false
      });
      if (!stat) {
        continue;
      }
      if (matchType(type, stat)) {
        return path_;
      }
    } catch {}
  }
}

// node_modules/unicorn-magic/node.js
import { fileURLToPath as fileURLToPath2 } from "url";
function toPath2(urlOrPath) {
  return urlOrPath instanceof URL ? fileURLToPath2(urlOrPath) : urlOrPath;
}

// node_modules/find-up/index.js
var findUpStop = Symbol("findUpStop");
function findUpMultipleSync(name, options = {}) {
  let directory = path2.resolve(toPath2(options.cwd) ?? "");
  const { root } = path2.parse(directory);
  const stopAt = path2.resolve(directory, toPath2(options.stopAt) ?? root);
  const limit = options.limit ?? Number.POSITIVE_INFINITY;
  const paths = [name].flat();
  const runMatcher = (locateOptions) => {
    if (typeof name !== "function") {
      return locatePathSync(paths, locateOptions);
    }
    const foundPath = name(locateOptions.cwd);
    if (typeof foundPath === "string") {
      return locatePathSync([foundPath], locateOptions);
    }
    return foundPath;
  };
  const matches = [];
  while (true) {
    const foundPath = runMatcher({ ...options, cwd: directory });
    if (foundPath === findUpStop) {
      break;
    }
    if (foundPath) {
      matches.push(path2.resolve(directory, foundPath));
    }
    if (directory === stopAt || matches.length >= limit) {
      break;
    }
    directory = path2.dirname(directory);
  }
  return matches;
}
function findUpSync(name, options = {}) {
  const matches = findUpMultipleSync(name, { ...options, limit: 1 });
  return matches[0];
}

// env.ts
import util from "util";
var JULES_API_KEY = process.env.JULES_API_KEY;
var GITHUB_TOKEN = process.env.GITHUB_TOKEN;
if (!JULES_API_KEY) {
  process.stderr.write(`\u274C JULES_API_KEY environment variable is required.
`);
  process.exit(1);
}
if (!GITHUB_TOKEN) {
  process.stderr.write(`\u274C GITHUB_TOKEN environment variable is required.
`);
  process.exit(1);
}
function redactToken(str) {
  let redacted = str;
  if (GITHUB_TOKEN) {
    redacted = redacted.replaceAll(GITHUB_TOKEN, "***REDACTED***");
  }
  if (JULES_API_KEY) {
    redacted = redacted.replaceAll(JULES_API_KEY, "***REDACTED***");
  }
  return redacted;
}
console.log = (...args) => {
  process.stdout.write(redactToken(util.format(...args)) + `
`);
};
console.error = (...args) => {
  process.stderr.write(redactToken(util.format(...args)) + `
`);
};
console.warn = (...args) => {
  process.stderr.write(redactToken(util.format(...args)) + `
`);
};

// github/git.ts
import { execFile } from "child_process";
import { promisify } from "util";
var gitCommands = {
  execFileAsync: promisify(execFile)
};
async function getGitRepoInfo(remoteName = "origin") {
  const { stdout } = await gitCommands.execFileAsync("git", ["remote", "get-url", "--", remoteName]);
  const remoteUrl = stdout.trim();
  return parseGitRemoteUrl(remoteUrl);
}
function parseGitRemoteUrl(remoteUrl) {
  const sshMatch = remoteUrl.match(/git@github\.com:([^/]+)\/(.+?)(\.git)?$/);
  if (sshMatch) {
    const [, owner, repo] = sshMatch;
    return {
      owner,
      repo: repo.replace(/\.git$/, ""),
      fullName: `${owner}/${repo.replace(/\.git$/, "")}`
    };
  }
  const httpsMatch = remoteUrl.match(/https?:\/\/github\.com\/([^/]+)\/(.+?)(\.git)?$/);
  if (httpsMatch) {
    const [, owner, repo] = httpsMatch;
    return {
      owner,
      repo: repo.replace(/\.git$/, ""),
      fullName: `${owner}/${repo.replace(/\.git$/, "")}`
    };
  }
  throw new Error(`Unable to parse git remote URL: ${remoteUrl}`);
}
async function getCurrentBranch() {
  const { stdout } = await gitCommands.execFileAsync("git", ["rev-parse", "--abbrev-ref", "HEAD"]);
  return stdout.trim();
}

// node_modules/@google/jules-sdk/dist/index.mjs
import * as path3 from "path";
import { join as join2 } from "path";
import { homedir } from "os";
import { existsSync, accessSync, constants } from "fs";
import * as fs2 from "fs/promises";
import * as path$1 from "path";
import { createReadStream, createWriteStream } from "fs";
import * as readline from "readline";
import { writeFile as writeFile2, readFile as readFile2, rm as rm2 } from "fs/promises";
import { Buffer as Buffer$1 } from "buffer";
import { setTimeout as setTimeout$1 } from "timers/promises";
import * as crypto from "crypto";

class JulesError extends Error {
  cause;
  constructor(message, options) {
    super(message);
    this.name = this.constructor.name;
    this.cause = options?.cause;
  }
}

class JulesNetworkError extends JulesError {
  url;
  constructor(url, options) {
    super(`Network request to ${url} failed`, options);
    this.url = url;
  }
}

class JulesApiError extends JulesError {
  url;
  status;
  statusText;
  constructor(url, status, statusText, message, options) {
    const finalMessage = message ?? `[${status} ${statusText}] Request to ${url} failed`;
    super(finalMessage, options);
    this.url = url;
    this.status = status;
    this.statusText = statusText;
  }
}

class JulesAuthenticationError extends JulesApiError {
  constructor(url, status, statusText) {
    super(url, status, statusText, `[${status} ${statusText}] Authentication to ${url} failed. Ensure your API key is correct.`);
  }
}

class JulesRateLimitError extends JulesApiError {
  constructor(url, status, statusText) {
    super(url, status, statusText, `[${status} ${statusText}] API rate limit exceeded for ${url}.`);
  }
}

class MissingApiKeyError extends JulesError {
  constructor() {
    super("Jules API key is missing. Pass it to the constructor or set the JULES_API_KEY environment variable.");
  }
}

class SourceNotFoundError extends JulesError {
  constructor(sourceIdentifier) {
    super(`Could not get source '${sourceIdentifier}'`);
  }
}

class AutomatedSessionFailedError extends JulesError {
  constructor(reason) {
    let message = "The Jules automated session terminated with a FAILED state.";
    if (reason) {
      message += ` Reason: ${reason}`;
    }
    super(message);
  }
}

class TimeoutError extends JulesError {
  constructor(message) {
    super(message);
  }
}

class SyncInProgressError extends JulesError {
  constructor() {
    super("A sync operation is already in progress. Wait for it to complete before starting another.");
  }
}
class ApiClient {
  apiKey;
  baseUrl;
  requestTimeoutMs;
  rateLimitConfig;
  semaphore;
  constructor(options) {
    this.apiKey = options.apiKey;
    this.baseUrl = options.baseUrl;
    this.requestTimeoutMs = options.requestTimeoutMs;
    this.rateLimitConfig = {
      maxRetryTimeMs: options.rateLimitRetry?.maxRetryTimeMs ?? 300000,
      baseDelayMs: options.rateLimitRetry?.baseDelayMs ?? 1000,
      maxDelayMs: options.rateLimitRetry?.maxDelayMs ?? 30000
    };
    this.semaphore = new Semaphore(options.maxConcurrentRequests ?? 50);
  }
  async request(endpoint, options = {}) {
    const {
      method = "GET",
      body,
      query,
      headers: customHeaders,
      _isRetry
    } = options;
    const url = this.resolveUrl(endpoint);
    if (query) {
      Object.entries(query).forEach(([key, value]) => {
        url.searchParams.append(key, String(value));
      });
    }
    const headers = {
      "Content-Type": "application/json",
      ...customHeaders
    };
    if (this.apiKey) {
      headers["X-Goog-Api-Key"] = this.apiKey;
    } else {
      throw new MissingApiKeyError;
    }
    let response;
    try {
      await this.semaphore.acquire();
      response = await this.fetchWithTimeout(url.toString(), {
        method,
        headers,
        body: body ? JSON.stringify(body) : undefined
      });
    } finally {
      this.semaphore.release();
    }
    if (!response.ok) {
      if (response.status === 429 || [500, 502, 503, 504].includes(response.status)) {
        const startTime = options._rateLimitStartTime || Date.now();
        const elapsed = Date.now() - startTime;
        const retryCount = options._rateLimitRetryCount || 0;
        if (elapsed < this.rateLimitConfig.maxRetryTimeMs) {
          const rawDelay = this.rateLimitConfig.baseDelayMs * Math.pow(2, retryCount);
          const delay = Math.min(rawDelay, this.rateLimitConfig.maxDelayMs);
          await new Promise((resolve2) => setTimeout(resolve2, delay));
          return this.request(endpoint, {
            ...options,
            _rateLimitStartTime: startTime,
            _rateLimitRetryCount: retryCount + 1
          });
        }
        if (response.status === 429) {
          throw new JulesRateLimitError(url.toString(), response.status, response.statusText);
        }
      }
      switch (response.status) {
        case 401:
        case 403:
          throw new JulesAuthenticationError(url.toString(), response.status, response.statusText);
        default:
          const errorBody = await response.text().catch(() => "Could not read error body");
          const message = `[${response.status} ${response.statusText}] ${method} ${url.toString()} - ${errorBody}`;
          throw new JulesApiError(url.toString(), response.status, response.statusText, message);
      }
    }
    const responseText = await response.text();
    if (!responseText) {
      return {};
    }
    return JSON.parse(responseText);
  }
  resolveUrl(path22) {
    return new URL(`${this.baseUrl}/${path22}`);
  }
  async fetchWithTimeout(url, opts) {
    const controller = new AbortController;
    const timeoutId = setTimeout(() => controller.abort(), this.requestTimeoutMs);
    try {
      const response = await fetch(url, {
        ...opts,
        signal: controller.signal
      });
      return response;
    } catch (error) {
      throw new JulesNetworkError(url, {
        cause: error
      });
    } finally {
      clearTimeout(timeoutId);
    }
  }
}

class Semaphore {
  constructor(maxConcurrentRequests) {
    this.maxConcurrentRequests = maxConcurrentRequests;
  }
  currentRequests = 0;
  queue = [];
  async acquire() {
    if (this.currentRequests < this.maxConcurrentRequests) {
      this.currentRequests++;
      return Promise.resolve();
    }
    return new Promise((resolve2) => {
      this.queue.push(resolve2);
    });
  }
  release() {
    if (this.queue.length > 0) {
      const resolve2 = this.queue.shift();
      if (resolve2) {
        resolve2();
      }
    } else {
      this.currentRequests--;
    }
  }
}
function mapRawSourceToSdkSource(rawSource) {
  if (rawSource.githubRepo) {
    const { defaultBranch, branches, ...rest } = rawSource.githubRepo;
    return {
      name: rawSource.name,
      id: rawSource.id,
      type: "githubRepo",
      githubRepo: {
        ...rest,
        defaultBranch: defaultBranch?.displayName,
        branches: branches?.map((b) => b.displayName)
      }
    };
  }
  throw new Error(`Unknown source type for source: ${rawSource.name}`);
}

class SourceManagerImpl {
  apiClient;
  constructor(apiClient) {
    this.apiClient = apiClient;
  }
  async* list(options = {}) {
    let pageToken = undefined;
    while (true) {
      const params = {
        pageSize: (options.pageSize || 100).toString()
      };
      if (options.filter) {
        params.filter = options.filter;
      }
      if (pageToken) {
        params.pageToken = pageToken;
      }
      const response = await this.apiClient.request("sources", { query: params });
      if (response && response.sources) {
        for (const rawSource of response.sources) {
          yield mapRawSourceToSdkSource(rawSource);
        }
      }
      pageToken = response?.nextPageToken;
      if (!pageToken) {
        break;
      }
    }
  }
  async get(filter) {
    const { github } = filter;
    if (!github || !github.includes("/")) {
      throw new Error("Invalid GitHub filter. Expected format: 'owner/repo'.");
    }
    const resourceName = `sources/github/${github}`;
    try {
      const rawSource = await this.apiClient.request(resourceName);
      if (!rawSource) {
        return;
      }
      return mapRawSourceToSdkSource(rawSource);
    } catch (error) {
      if (error instanceof JulesApiError && error.status === 404) {
        return;
      }
      throw error;
    }
  }
}
function createSourceManager(apiClient) {
  const manager = new SourceManagerImpl(apiClient);
  const callable = manager.list.bind(manager);
  const sourceManager = callable;
  sourceManager.get = manager.get.bind(manager);
  return sourceManager;
}
function isWritable(dir) {
  try {
    accessSync(dir, constants.W_OK);
    return true;
  } catch {
    return false;
  }
}
function getRootDir() {
  const julesHome = process.env.JULES_HOME;
  if (julesHome && isWritable(julesHome)) {
    return julesHome;
  }
  const cwd = process.cwd();
  const isInProject = existsSync(path3.join(cwd, "package.json"));
  if (isInProject && cwd !== "/" && isWritable(cwd)) {
    return cwd;
  }
  const home = process.env.HOME;
  if (home && home !== "/" && isWritable(home)) {
    return home;
  }
  const osHome = homedir();
  if (osHome && osHome !== "/" && isWritable(osHome)) {
    return osHome;
  }
  const tmpDir = process.env.TMPDIR || process.env.TMP || "/tmp";
  return tmpDir;
}
function parseUnidiff(patch) {
  if (!patch)
    return [];
  const files = [];
  const diffSections = patch.split(/^diff --git /m).filter(Boolean);
  for (const section of diffSections) {
    const lines = section.split(`
`);
    let path22 = "";
    let fromPath = "";
    let toPath3 = "";
    for (const line of lines) {
      if (line.startsWith("--- ")) {
        fromPath = line.slice(4).replace(/^a\//, "").replace(/^\/dev\/null$/, "");
      } else if (line.startsWith("+++ ")) {
        toPath3 = line.slice(4).replace(/^b\//, "").replace(/^\/dev\/null$/, "");
      }
    }
    let changeType;
    if (fromPath === "" || lines.some((l) => l.startsWith("--- /dev/null"))) {
      changeType = "created";
      path22 = toPath3;
    } else if (toPath3 === "" || lines.some((l) => l.startsWith("+++ /dev/null"))) {
      changeType = "deleted";
      path22 = fromPath;
    } else {
      changeType = "modified";
      path22 = toPath3;
    }
    if (!path22)
      continue;
    let additions = 0;
    let deletions = 0;
    let inHunk = false;
    for (const line of lines) {
      if (line.startsWith("@@")) {
        inHunk = true;
        continue;
      }
      if (inHunk) {
        if (line.startsWith("+") && !line.startsWith("+++")) {
          additions++;
        } else if (line.startsWith("-") && !line.startsWith("---")) {
          deletions++;
        }
      }
    }
    files.push({ path: path22, changeType, additions, deletions });
  }
  return files;
}
function parseUnidiffWithContent(patch) {
  if (!patch)
    return [];
  const files = [];
  const diffSections = patch.split(/^diff --git /m).filter(Boolean);
  for (const section of diffSections) {
    const lines = section.split(`
`);
    let path22 = "";
    let fromPath = "";
    let toPath3 = "";
    for (const line of lines) {
      if (line.startsWith("--- ")) {
        fromPath = line.slice(4).replace(/^a\//, "").replace(/^\/dev\/null$/, "");
      } else if (line.startsWith("+++ ")) {
        toPath3 = line.slice(4).replace(/^b\//, "").replace(/^\/dev\/null$/, "");
      }
    }
    let changeType;
    if (fromPath === "" || lines.some((l) => l.startsWith("--- /dev/null"))) {
      changeType = "created";
      path22 = toPath3;
    } else if (toPath3 === "" || lines.some((l) => l.startsWith("+++ /dev/null"))) {
      changeType = "deleted";
      path22 = fromPath;
    } else {
      changeType = "modified";
      path22 = toPath3;
    }
    if (!path22)
      continue;
    let additions = 0;
    let deletions = 0;
    let inHunk = false;
    const contentLines = [];
    for (const line of lines) {
      if (line.startsWith("@@")) {
        inHunk = true;
        continue;
      }
      if (inHunk) {
        if (line.startsWith("+") && !line.startsWith("+++")) {
          additions++;
          contentLines.push(line.slice(1));
        } else if (line.startsWith("-") && !line.startsWith("---")) {
          deletions++;
        }
      }
    }
    const content = changeType === "deleted" ? "" : contentLines.join(`
`);
    files.push({ path: path22, changeType, content, additions, deletions });
  }
  return files;
}
function createGeneratedFiles(files) {
  return {
    all: () => files,
    get: (path22) => files.find((f) => f.path === path22),
    filter: (changeType) => files.filter((f) => f.changeType === changeType)
  };
}

class MediaArtifact {
  type = "media";
  data;
  format;
  platform;
  activityId;
  constructor(artifact, platform, activityId) {
    this.data = artifact.data;
    this.format = artifact.mimeType;
    this.platform = platform;
    this.activityId = activityId;
  }
  async save(filepath) {
    await this.platform.saveFile(filepath, this.data, "base64", this.activityId);
  }
  toUrl() {
    return this.platform.createDataUrl(this.data, this.format);
  }
}

class BashArtifact {
  type = "bashOutput";
  command;
  stdout;
  stderr;
  exitCode;
  constructor(artifact) {
    this.command = artifact.command;
    this.stdout = artifact.output;
    this.stderr = "";
    this.exitCode = artifact.exitCode;
  }
  toString() {
    const output = [this.stdout, this.stderr].filter(Boolean).join("");
    const commandLine = `$ ${this.command}`;
    const outputLine = output ? `${output}
` : "";
    const exitLine = `[exit code: ${this.exitCode ?? "N/A"}]`;
    return `${commandLine}
${outputLine}${exitLine}`;
  }
}

class ChangeSetArtifact {
  type = "changeSet";
  source;
  gitPatch;
  constructor(source, gitPatch) {
    this.source = source;
    this.gitPatch = gitPatch;
  }
  parsed() {
    if (!this.gitPatch?.unidiffPatch) {
      return {
        files: [],
        summary: { totalFiles: 0, created: 0, modified: 0, deleted: 0 }
      };
    }
    const files = parseUnidiff(this.gitPatch.unidiffPatch);
    const summary = {
      totalFiles: files.length,
      created: files.filter((f) => f.changeType === "created").length,
      modified: files.filter((f) => f.changeType === "modified").length,
      deleted: files.filter((f) => f.changeType === "deleted").length
    };
    return { files, summary };
  }
}
function mapRestArtifactToSdkArtifact(restArtifact, platform, activityId) {
  if ("changeSet" in restArtifact) {
    return new ChangeSetArtifact(restArtifact.changeSet.source, restArtifact.changeSet.gitPatch);
  }
  if ("media" in restArtifact) {
    return new MediaArtifact(restArtifact.media, platform, activityId);
  }
  if ("bashOutput" in restArtifact) {
    return new BashArtifact(restArtifact.bashOutput);
  }
  throw new Error(`Unknown artifact type: ${JSON.stringify(restArtifact)}`);
}
function mapRestActivityToSdkActivity(restActivity, platform) {
  const {
    name,
    createTime,
    originator,
    artifacts: rawArtifacts,
    description
  } = restActivity;
  const activityId = name.split("/").pop();
  const artifacts = (rawArtifacts || []).map((artifact) => mapRestArtifactToSdkArtifact(artifact, platform, activityId));
  const baseActivity = {
    name,
    id: activityId,
    description,
    createTime,
    originator: originator || "system",
    artifacts
  };
  if (restActivity.agentMessaged) {
    return {
      ...baseActivity,
      type: "agentMessaged",
      message: restActivity.agentMessaged.agentMessage
    };
  }
  if (restActivity.userMessaged) {
    return {
      ...baseActivity,
      type: "userMessaged",
      message: restActivity.userMessaged.userMessage
    };
  }
  if (restActivity.planGenerated) {
    return {
      ...baseActivity,
      type: "planGenerated",
      plan: restActivity.planGenerated.plan
    };
  }
  if (restActivity.planApproved) {
    return {
      ...baseActivity,
      type: "planApproved",
      planId: restActivity.planApproved.planId
    };
  }
  if (restActivity.progressUpdated) {
    return {
      ...baseActivity,
      type: "progressUpdated",
      title: restActivity.progressUpdated.title,
      description: restActivity.progressUpdated.description
    };
  }
  if (restActivity.sessionCompleted) {
    return {
      ...baseActivity,
      type: "sessionCompleted"
    };
  }
  if (restActivity.sessionFailed) {
    return {
      ...baseActivity,
      type: "sessionFailed",
      reason: restActivity.sessionFailed.reason
    };
  }
  throw new Error("Unknown activity type");
}
function mapRestStateToSdkState(state) {
  switch (state) {
    case "STATE_UNSPECIFIED":
      return "unspecified";
    case "QUEUED":
      return "queued";
    case "PLANNING":
      return "planning";
    case "AWAITING_PLAN_APPROVAL":
      return "awaitingPlanApproval";
    case "AWAITING_USER_FEEDBACK":
      return "awaitingUserFeedback";
    case "IN_PROGRESS":
      return "inProgress";
    case "PAUSED":
      return "paused";
    case "FAILED":
      return "failed";
    case "COMPLETED":
      return "completed";
    default:
      return "unspecified";
  }
}
function mapRestSourceToSdkSource(rest) {
  if (rest.githubRepo) {
    const { defaultBranch, branches, ...other } = rest.githubRepo;
    return {
      type: "githubRepo",
      name: rest.name,
      id: rest.id,
      githubRepo: {
        ...other,
        defaultBranch: defaultBranch?.displayName,
        branches: branches?.map((b) => b.displayName)
      }
    };
  }
  throw new Error(`Unknown source type: ${JSON.stringify(rest)}`);
}
function mapRestOutputToSdkOutput(rest) {
  if (rest.pullRequest) {
    return {
      type: "pullRequest",
      pullRequest: rest.pullRequest
    };
  }
  if (rest.changeSet) {
    return {
      type: "changeSet",
      changeSet: rest.changeSet
    };
  }
  throw new Error(`Unknown output type: ${JSON.stringify(rest)}`);
}
function mapRestSessionToSdkSession(rest, platform) {
  const session = {
    ...rest,
    archived: rest.archived ?? false,
    state: mapRestStateToSdkState(rest.state),
    requirePlanApproval: rest.requirePlanApproval,
    automationMode: rest.automationMode,
    outputs: (rest.outputs || []).map(mapRestOutputToSdkOutput),
    source: rest.source ? mapRestSourceToSdkSource(rest.source) : undefined,
    generatedFiles: rest.generatedFiles,
    activities: undefined,
    outcome: undefined
  };
  if (rest.activities && platform) {
    session.activities = rest.activities.map((a) => mapRestActivityToSdkActivity(a, platform));
  }
  try {
    session.outcome = mapSessionResourceToOutcome(session);
  } catch (error) {
    if (error instanceof AutomatedSessionFailedError) {
      session.outcome = {
        sessionId: session.id,
        title: session.title,
        state: "failed",
        outputs: session.outputs,
        generatedFiles: () => createGeneratedFiles([]),
        changeSet: () => {
          return;
        }
      };
    } else {
      throw error;
    }
  }
  return session;
}
function mapSessionResourceToOutcome(session) {
  if (session.state === "failed") {
    throw new AutomatedSessionFailedError(`Session ${session.id} failed.`);
  }
  const outputs = session.outputs ?? [];
  const prOutput = outputs.find((o) => ("pullRequest" in o));
  const pullRequest = prOutput ? prOutput.pullRequest : undefined;
  const changeSetOutput = outputs.find((o) => ("changeSet" in o));
  const changeSet = changeSetOutput ? changeSetOutput.changeSet : undefined;
  return {
    sessionId: session.id,
    title: session.title,
    state: "completed",
    pullRequest,
    outputs,
    generatedFiles: () => {
      if (!changeSet?.gitPatch?.unidiffPatch) {
        return createGeneratedFiles([]);
      }
      const files = parseUnidiffWithContent(changeSet.gitPatch.unidiffPatch);
      return createGeneratedFiles(files);
    },
    changeSet: () => {
      if (!changeSet?.gitPatch) {
        return;
      }
      return new ChangeSetArtifact("session", changeSet.gitPatch);
    }
  };
}
var sleep$1 = (ms) => new Promise((resolve2) => setTimeout(resolve2, ms));
var DEFAULT_INITIAL_RETRIES = 10;
var MAX_RETRY_DELAY_MS = 30000;
async function* streamActivities(sessionId, apiClient, pollingInterval, platform, options = {}) {
  let pageToken = undefined;
  let isFirstCall = true;
  let lastSeenTime = "";
  const seenIdsAtLastTime = /* @__PURE__ */ new Set;
  while (true) {
    let response;
    try {
      response = await apiClient.request(`sessions/${sessionId}/activities`, {
        query: {
          pageSize: "50",
          ...pageToken ? { pageToken } : {}
        }
      });
    } catch (error) {
      if (isFirstCall && error instanceof JulesApiError && error.status === 404) {
        let lastError = error;
        let successfulResponse;
        let delay = 1000;
        const maxRetries = options.initialRetries ?? DEFAULT_INITIAL_RETRIES;
        for (let i = 0;i < maxRetries; i++) {
          await sleep$1(delay);
          delay = Math.min(delay * 2, MAX_RETRY_DELAY_MS);
          try {
            successfulResponse = await apiClient.request(`sessions/${sessionId}/activities`, {
              query: {
                pageSize: "50",
                ...pageToken ? { pageToken } : {}
              }
            });
            break;
          } catch (retryError) {
            if (retryError instanceof JulesApiError && retryError.status === 404) {
              lastError = retryError;
            } else {
              throw retryError;
            }
          }
        }
        if (successfulResponse) {
          response = successfulResponse;
        } else {
          throw lastError;
        }
      } else {
        throw error;
      }
    }
    isFirstCall = false;
    const activities = response.activities || [];
    for (const rawActivity of activities) {
      const activity = mapRestActivityToSdkActivity(rawActivity, platform);
      if (activity.createTime < lastSeenTime) {
        continue;
      }
      if (activity.createTime === lastSeenTime) {
        if (seenIdsAtLastTime.has(activity.id)) {
          continue;
        }
        seenIdsAtLastTime.add(activity.id);
      } else {
        lastSeenTime = activity.createTime;
        seenIdsAtLastTime.clear();
        seenIdsAtLastTime.add(activity.id);
      }
      if (options.exclude?.originator && activity.originator === options.exclude.originator) {
        continue;
      }
      yield activity;
    }
    if (response.nextPageToken) {
      pageToken = response.nextPageToken;
      continue;
    } else {
      pageToken = undefined;
      await sleep$1(pollingInterval);
    }
  }
}
var sleep = (ms) => new Promise((resolve2) => setTimeout(resolve2, ms));
async function pollSession(sessionId, apiClient, predicateFn, pollingInterval, platform, timeoutMs) {
  const startTime = Date.now();
  while (true) {
    const restSession = await apiClient.request(`sessions/${sessionId}`);
    const session = mapRestSessionToSdkSession(restSession, platform);
    if (predicateFn(session)) {
      return session;
    }
    if (timeoutMs && Date.now() - startTime >= timeoutMs) {
      throw new TimeoutError(`Polling for session ${sessionId} timed out after ${timeoutMs}ms`);
    }
    await sleep(pollingInterval);
  }
}
async function pollUntilCompletion(sessionId, apiClient, pollingInterval, platform, timeoutMs) {
  return pollSession(sessionId, apiClient, (session) => {
    const state = session.state;
    return state === "completed" || state === "failed";
  }, pollingInterval, platform, timeoutMs);
}
function isSessionFrozen(lastActivityCreateTime, thresholdDays = 30) {
  const lastActivity = new Date(lastActivityCreateTime);
  const now = /* @__PURE__ */ new Date;
  const ageMs = now.getTime() - lastActivity.getTime();
  const ageDays = ageMs / (1000 * 60 * 60 * 24);
  return ageDays > thresholdDays;
}
function createTimeFilter(createTime) {
  return `create_time>"${createTime}"`;
}

class DefaultActivityClient {
  constructor(storage, network) {
    this.storage = storage;
    this.network = network;
  }
  _hydrateActivityArtifacts(activity) {
    if (!activity.artifacts || activity.artifacts.length === 0) {
      return activity;
    }
    const hydratedArtifacts = activity.artifacts.map((artifact) => {
      if (artifact instanceof MediaArtifact)
        return artifact;
      if (artifact instanceof BashArtifact)
        return artifact;
      if (artifact instanceof ChangeSetArtifact)
        return artifact;
      switch (artifact.type) {
        case "changeSet":
          const rawChangeSet = artifact.changeSet || artifact;
          return new ChangeSetArtifact(rawChangeSet.source, rawChangeSet.gitPatch);
        case "bashOutput":
          const rawBashOutput = artifact.bashOutput || artifact;
          return new BashArtifact(rawBashOutput);
        case "media":
          const rawMedia = artifact.media || artifact;
          return new MediaArtifact(rawMedia, {}, activity.id);
        default:
          return artifact;
      }
    });
    return {
      ...activity,
      artifacts: hydratedArtifacts
    };
  }
  async* history() {
    await this.hydrate();
    for await (const activity of this.storage.scan()) {
      yield this._hydrateActivityArtifacts(activity);
    }
  }
  async hydrate() {
    await this.storage.init();
    const latest = await this.storage.latest();
    if (latest?.createTime && isSessionFrozen(latest.createTime)) {
      return 0;
    }
    const filter = latest?.createTime ? createTimeFilter(latest.createTime) : undefined;
    let count = 0;
    let nextPageToken;
    do {
      const response = await this.network.listActivities({
        filter,
        pageToken: nextPageToken
      });
      const existingChecks = await Promise.all(response.activities.map((activity) => this.storage.get(activity.id)));
      for (let i = 0;i < response.activities.length; i++) {
        const activity = response.activities[i];
        const existing = existingChecks[i];
        if (existing) {
          continue;
        }
        await this.storage.append(activity);
        count++;
      }
      nextPageToken = response.nextPageToken;
    } while (nextPageToken);
    return count;
  }
  async* updates() {
    await this.storage.init();
    const latest = await this.storage.latest();
    let highWaterMark = latest?.createTime ? new Date(latest.createTime).getTime() : 0;
    let lastSeenId = latest?.id;
    for await (const activity of this.network.rawStream()) {
      const actTime = new Date(activity.createTime).getTime();
      if (actTime < highWaterMark) {
        continue;
      }
      if (actTime === highWaterMark && activity.id === lastSeenId) {
        continue;
      }
      await this.storage.append(activity);
      highWaterMark = actTime;
      lastSeenId = activity.id;
      yield activity;
    }
  }
  async* stream() {
    yield* this.history();
    yield* this.updates();
  }
  async select(options = {}) {
    await this.storage.init();
    const results = [];
    let started = !options.after;
    let count = 0;
    for await (const act of this.storage.scan()) {
      if (!started) {
        if (act.id === options.after) {
          started = true;
        }
        continue;
      }
      if (options.before && act.id === options.before) {
        break;
      }
      if (options.type && act.type !== options.type) {
        continue;
      }
      results.push(this._hydrateActivityArtifacts(act));
      count++;
      if (options.limit && count >= options.limit) {
        break;
      }
    }
    return results;
  }
  async list(options) {
    return this.network.listActivities(options);
  }
  async get(activityId) {
    await this.storage.init();
    const cached = await this.storage.get(activityId);
    if (cached) {
      return this._hydrateActivityArtifacts(cached);
    }
    const fresh = await this.network.fetchActivity(activityId);
    await this.storage.append(fresh);
    return fresh;
  }
}

class NetworkAdapter {
  constructor(apiClient, sessionId, pollingIntervalMs = 5000, platform) {
    this.apiClient = apiClient;
    this.sessionId = sessionId;
    this.pollingIntervalMs = pollingIntervalMs;
    this.platform = platform;
  }
  async fetchActivity(activityId) {
    const restActivity = await this.apiClient.request(`sessions/${this.sessionId}/activities/${activityId}`);
    return mapRestActivityToSdkActivity(restActivity, this.platform);
  }
  async listActivities(options) {
    const params = {};
    if (options?.pageSize) {
      params.pageSize = options.pageSize.toString();
    }
    if (options?.pageToken) {
      params.pageToken = options.pageToken;
    }
    if (options?.filter) {
      params.filter = options.filter;
    }
    const response = await this.apiClient.request(`sessions/${this.sessionId}/activities`, { query: params });
    return {
      activities: (response.activities || []).map((activity) => mapRestActivityToSdkActivity(activity, this.platform)),
      nextPageToken: response.nextPageToken
    };
  }
  async* rawStream() {
    while (true) {
      let pageToken = undefined;
      do {
        const response = await this.listActivities({ pageToken });
        for (const activity of response.activities) {
          yield activity;
        }
        pageToken = response.nextPageToken;
      } while (pageToken);
      await this.platform.sleep(this.pollingIntervalMs);
    }
  }
}
var ONE_MONTH_MS = 30 * 24 * 60 * 60 * 1000;
var ONE_DAY_MS = 24 * 60 * 60 * 1000;
function determineCacheTier(cached, now = Date.now()) {
  const createdAt = new Date(cached.resource.createTime).getTime();
  const age = now - createdAt;
  const isTerminal = ["failed", "completed"].includes(cached.resource.state);
  if (age > ONE_MONTH_MS) {
    return "frozen";
  }
  const timeSinceSync = now - cached._lastSyncedAt;
  if (isTerminal && timeSinceSync < ONE_DAY_MS) {
    return "warm";
  }
  return "hot";
}
function isCacheValid(cached, now = Date.now()) {
  if (!cached)
    return false;
  const tier = determineCacheTier(cached, now);
  return tier === "frozen" || tier === "warm";
}

class SessionSnapshotImpl {
  id;
  state;
  url;
  createdAt;
  updatedAt;
  durationMs;
  prompt;
  title;
  pr;
  activities;
  activityCounts;
  timeline;
  insights;
  generatedFiles;
  changeSet;
  constructor(options) {
    const { session, activities = [] } = options.data;
    this.id = session.id;
    this.state = session.state;
    this.url = session.url;
    this.createdAt = new Date(session.createTime);
    this.updatedAt = new Date(session.updateTime);
    this.durationMs = this.updatedAt.getTime() - this.createdAt.getTime();
    this.prompt = session.prompt;
    this.title = session.title;
    if (session.outcome) {
      this.pr = session.outcome.pullRequest;
      this.generatedFiles = session.outcome.generatedFiles();
      this.changeSet = typeof session.outcome.changeSet === "function" ? session.outcome.changeSet : () => {
        return;
      };
    } else {
      const prOutput = session.outputs?.find((o) => o.type === "pullRequest");
      this.pr = prOutput?.pullRequest;
      this.generatedFiles = {
        all: () => [],
        get: () => {
          return;
        },
        filter: () => []
      };
      this.changeSet = () => {
        return;
      };
    }
    this.activities = Object.freeze(activities);
    this.activityCounts = this.computeActivityCounts();
    this.timeline = this.computeTimeline();
    this.insights = this.computeInsights();
    Object.freeze(this);
  }
  computeActivityCounts() {
    const counts = {};
    for (const activity of this.activities) {
      counts[activity.type] = (counts[activity.type] || 0) + 1;
    }
    return counts;
  }
  computeTimeline() {
    return this.activities.map((activity) => ({
      time: activity.createTime,
      type: activity.type,
      summary: this.generateSummary(activity)
    }));
  }
  generateSummary(activity) {
    switch (activity.type) {
      case "planGenerated":
        return `Plan with ${activity.plan.steps.length} steps`;
      case "planApproved":
        return "Plan approved";
      case "sessionCompleted":
        return "Session completed";
      case "sessionFailed":
        return `Failed: ${activity.reason}`;
      case "userMessaged": {
        const msg = activity.message;
        return `User: ${msg.substring(0, 100)}${msg.length > 100 ? "..." : ""}`;
      }
      case "agentMessaged": {
        const msg = activity.message;
        return `Agent: ${msg.substring(0, 100)}${msg.length > 100 ? "..." : ""}`;
      }
      case "progressUpdated": {
        const progress = activity;
        return progress.title || progress.description || "Progress update";
      }
      default:
        return activity.type;
    }
  }
  computeInsights() {
    const failedCommands = this.activities.filter((activity) => activity.artifacts.some((artifact) => {
      if (artifact.type === "bashOutput") {
        return artifact.exitCode !== 0;
      }
      return false;
    }));
    return {
      completionAttempts: this.activityCounts["sessionCompleted"] || 0,
      planRegenerations: this.activityCounts["planGenerated"] || 0,
      userInterventions: this.activityCounts["userMessaged"] || 0,
      failedCommands
    };
  }
  toJSON(options = { exclude: ["activities", "generatedFiles"] }) {
    const full = {
      id: this.id,
      state: this.state,
      url: this.url,
      createdAt: this.createdAt.toISOString(),
      updatedAt: this.updatedAt.toISOString(),
      durationMs: this.durationMs,
      prompt: this.prompt,
      title: this.title,
      activities: this.activities,
      activityCounts: this.activityCounts,
      timeline: this.timeline,
      generatedFiles: this.generatedFiles.all(),
      insights: {
        completionAttempts: this.insights.completionAttempts,
        planRegenerations: this.insights.planRegenerations,
        userInterventions: this.insights.userInterventions,
        failedCommandCount: this.insights.failedCommands.length
      },
      pr: this.pr
    };
    if (options?.include) {
      return Object.fromEntries(options.include.filter((key) => (key in full)).map((key) => [key, full[key]]));
    }
    if (options?.exclude) {
      const result = { ...full };
      for (const key of options.exclude) {
        delete result[key];
      }
      return result;
    }
    return full;
  }
  toMarkdown() {
    const lines = [];
    lines.push(`# Session: ${this.title}`);
    lines.push(`**Status**: \`${this.state}\` | **ID**: \`${this.id}\``);
    lines.push("");
    lines.push("## Overview");
    lines.push(`- **Duration**: ${Math.round(this.durationMs / 1000)}s`);
    lines.push(`- **Total Activities**: ${this.activities.length}`);
    if (this.pr) {
      lines.push(`- **Pull Request**: [${this.pr.title}](${this.pr.url})`);
    }
    if (this.generatedFiles.all().length > 0) {
      lines.push(`- **Generated Files**: ${this.generatedFiles.all().length}`);
      for (const file of this.generatedFiles.all()) {
        lines.push(`  - ${file.path}`);
        lines.push(`  - Type: ${file.changeType}`);
        lines.push(`  - Additions: ${file.additions}`);
        lines.push(`  - Deletions: ${file.deletions}`);
      }
    }
    lines.push("");
    lines.push("## Insights");
    lines.push(`- **Completion Attempts**: ${this.insights.completionAttempts}`);
    lines.push(`- **Plan Regenerations**: ${this.insights.planRegenerations}`);
    lines.push(`- **User Interventions**: ${this.insights.userInterventions}`);
    lines.push(`- **Failed Commands**: ${this.insights.failedCommands.length}`);
    lines.push("");
    lines.push("## Timeline");
    if (this.timeline.length === 0) {
      lines.push("_No activities recorded._");
    } else {
      for (const entry of this.timeline) {
        lines.push(`- **[${entry.type}]** ${entry.summary} _(${entry.time})_`);
      }
    }
    lines.push("");
    if (Object.keys(this.activityCounts).length > 0) {
      lines.push("## Activity Counts");
      lines.push("```");
      for (const [type, count] of Object.entries(this.activityCounts)) {
        lines.push(`${type.padEnd(20)}: ${count}`);
      }
      lines.push("```");
    }
    return lines.join(`
`);
  }
}
async function collectAsync(iterable) {
  const items = [];
  for await (const item of iterable) {
    items.push(item);
  }
  return items;
}

class SessionClientImpl {
  id;
  apiClient;
  config;
  sessionStorage;
  _activities;
  platform;
  constructor(sessionId, apiClient, config, activityStorage, sessionStorage, platform) {
    this.id = sessionId.replace(/^sessions\//, "");
    this.apiClient = apiClient;
    this.config = config;
    this.sessionStorage = sessionStorage;
    this.platform = platform;
    const network = new NetworkAdapter(this.apiClient, this.id, this.config.pollingIntervalMs, platform);
    this._activities = new DefaultActivityClient(activityStorage, network);
  }
  async request(path22, options = {}) {
    return this.apiClient.request(path22, options);
  }
  history() {
    return this._activities.history();
  }
  hydrate() {
    return this._activities.hydrate();
  }
  updates() {
    return this._activities.updates();
  }
  select(options) {
    return this._activities.select(options);
  }
  get activities() {
    return this._activities;
  }
  async* stream(options = {}) {
    for await (const activity of this._activities.stream()) {
      if (options.exclude?.originator && activity.originator === options.exclude.originator) {
        continue;
      }
      yield activity;
    }
  }
  async approve() {
    await this.request(`sessions/${this.id}:approvePlan`, {
      method: "POST",
      body: {}
    });
  }
  async send(prompt) {
    await this.request(`sessions/${this.id}:sendMessage`, {
      method: "POST",
      body: { prompt }
    });
  }
  async ask(prompt) {
    const startTime = /* @__PURE__ */ new Date;
    await this.send(prompt);
    for await (const activity of this.stream({
      exclude: { originator: "user" }
    })) {
      const activityTime = new Date(activity.createTime).getTime();
      const askTime = startTime.getTime();
      if (activityTime <= askTime) {
        continue;
      }
      if (activity.type === "agentMessaged") {
        return activity;
      }
      if (activity.type === "sessionCompleted" || activity.type === "sessionFailed") {
        throw new JulesError("Session ended before the agent replied.");
      }
    }
    throw new JulesError("Session ended before the agent replied.");
  }
  async result(options) {
    const finalSession = await pollUntilCompletion(this.id, this.apiClient, this.config.pollingIntervalMs, this.platform, options?.timeoutMs);
    await this.sessionStorage.upsert(finalSession);
    return mapSessionResourceToOutcome(finalSession);
  }
  async waitFor(targetState, options) {
    await pollSession(this.id, this.apiClient, (session) => {
      const state = session.state;
      return state === targetState || state === "completed" || state === "failed";
    }, this.config.pollingIntervalMs, this.platform, options?.timeoutMs);
  }
  async archive() {
    await this.request(`sessions/${this.id}:archive`, {
      method: "POST",
      body: {}
    });
    const cached = await this.sessionStorage.get(this.id);
    if (cached) {
      const resource = { ...cached.resource, archived: true };
      await this.sessionStorage.upsert(resource);
    }
  }
  async unarchive() {
    await this.request(`sessions/${this.id}:unarchive`, {
      method: "POST",
      body: {}
    });
    const cached = await this.sessionStorage.get(this.id);
    if (cached) {
      const resource = { ...cached.resource, archived: false };
      await this.sessionStorage.upsert(resource);
    }
  }
  async info() {
    let resource;
    const cached = await this.sessionStorage.get(this.id);
    if (isCacheValid(cached)) {
      resource = cached.resource;
    } else {
      try {
        const restResource = await this.request(`sessions/${this.id}`);
        resource = mapRestSessionToSdkSession(restResource, this.platform);
        await this.sessionStorage.upsert(resource);
      } catch (e) {
        if (e.status === 404 && cached) {
          await this.sessionStorage.delete(this.id);
        }
        throw e;
      }
    }
    resource.outcome = mapSessionResourceToOutcome(resource);
    return resource;
  }
  async snapshot(options) {
    const includeActivities = options?.activities ?? true;
    const [info, activities] = await Promise.all([
      this.info(),
      includeActivities ? collectAsync(this.history()) : []
    ]);
    return new SessionSnapshotImpl({ data: { session: info, activities } });
  }
}
async function pMap(items, mapper, options = {}) {
  const concurrency = options.concurrency ?? 3;
  const stopOnError = options.stopOnError ?? true;
  const delayMs = options.delayMs ?? 0;
  const results = new Array(items.length);
  const errors = new Array;
  let nextIndex = 0;
  const workers = new Array(concurrency).fill(0).map(async () => {
    while (true) {
      const index = nextIndex++;
      if (index >= items.length) {
        break;
      }
      const item = items[index];
      if (delayMs > 0) {
        await new Promise((resolve2) => setTimeout(resolve2, delayMs));
      }
      try {
        results[index] = await mapper(item, index);
      } catch (err) {
        if (stopOnError) {
          throw err;
        }
        errors.push(err);
      }
    }
  });
  await Promise.all(workers);
  if (!stopOnError && errors.length > 0) {
    throw new AggregateError(errors, "Multiple errors occurred during jules.all()");
  }
  return results;
}

class SessionCursor {
  constructor(apiClient, storage, platform, options = {}) {
    this.apiClient = apiClient;
    this.storage = storage;
    this.platform = platform;
    this.options = options;
  }
  then(onfulfilled, onrejected) {
    return this.fetchPage(this.options.pageToken).then(onfulfilled, onrejected);
  }
  async* [Symbol.asyncIterator]() {
    let currentToken = this.options.pageToken;
    let itemCount = 0;
    const limit = this.options.limit ?? Infinity;
    do {
      if (itemCount >= limit)
        break;
      const response = await this.fetchPage(currentToken);
      if (!response.sessions || response.sessions.length === 0) {
        break;
      }
      for (const session of response.sessions) {
        if (itemCount >= limit)
          break;
        yield session;
        itemCount++;
      }
      currentToken = response.nextPageToken;
    } while (currentToken);
  }
  async all() {
    const results = [];
    for await (const session of this) {
      results.push(session);
    }
    return results;
  }
  async fetchPage(pageToken) {
    const params = {};
    if (this.options.pageSize)
      params.pageSize = this.options.pageSize.toString();
    if (pageToken)
      params.pageToken = pageToken;
    if (this.options.filter)
      params.filter = this.options.filter;
    const response = await this.apiClient.request("sessions", { query: params });
    const sessions = (response.sessions || []).map((s) => mapRestSessionToSdkSession(s, this.platform));
    if (sessions.length > 0 && this.options.persist !== false) {
      await this.storage.upsertMany(sessions);
    }
    return {
      sessions,
      nextPageToken: response.nextPageToken
    };
  }
}
var GLOBAL_METADATA_FILE = "global-metadata.json";
async function updateGlobalCacheMetadata(rootDirOverride) {
  const rootDir = getRootDir();
  const cacheDir = path$1.join(rootDir, ".jules/cache");
  const metadataPath = path$1.join(cacheDir, GLOBAL_METADATA_FILE);
  let metadata = { lastSyncedAt: 0, sessionCount: 0 };
  try {
    const content = await fs2.readFile(metadataPath, "utf8");
    metadata = JSON.parse(content);
  } catch {}
  metadata.lastSyncedAt = Date.now();
  try {
    const entries = await fs2.readdir(cacheDir, { withFileTypes: true });
    metadata.sessionCount = entries.filter((e) => e.isDirectory()).length;
  } catch {
    metadata.sessionCount = 0;
  }
  await fs2.mkdir(cacheDir, { recursive: true });
  await fs2.writeFile(metadataPath, JSON.stringify(metadata), "utf8");
}
function parseSelectExpression(expr) {
  if (expr === "*") {
    return { path: [], exclude: false, wildcard: true };
  }
  const exclude = expr.startsWith("-");
  const pathStr = exclude ? expr.slice(1) : expr;
  const cleanPath = pathStr.replace(/\[\]/g, "");
  const path22 = cleanPath.split(".").filter((p) => p.length > 0);
  return { path: path22, exclude, wildcard: false };
}
function getPath(obj, path22) {
  if (path22.length === 0)
    return obj;
  if (obj === null || obj === undefined)
    return;
  const [head, ...tail] = path22;
  if (Array.isArray(obj)) {
    const results = obj.map((item) => getPath(item, path22)).filter((v) => v !== undefined);
    return results.length > 0 ? results : undefined;
  }
  if (typeof obj === "object") {
    const value = obj[head];
    return getPath(value, tail);
  }
  return;
}
function setPath(obj, path22, value) {
  if (path22.length === 0 || value === undefined)
    return;
  const [head, ...tail] = path22;
  if (tail.length === 0) {
    obj[head] = value;
    return;
  }
  if (!(head in obj)) {
    obj[head] = {};
  }
  const next = obj[head];
  if (typeof next === "object" && next !== null && !Array.isArray(next)) {
    setPath(next, tail, value);
  }
}
function deletePath(obj, path22) {
  if (path22.length === 0 || obj === null || obj === undefined)
    return;
  if (Array.isArray(obj)) {
    obj.forEach((item) => deletePath(item, path22));
    return;
  }
  if (typeof obj !== "object")
    return;
  const record = obj;
  const [head, ...tail] = path22;
  if (tail.length === 0) {
    delete record[head];
    return;
  }
  if (head in record) {
    deletePath(record[head], tail);
  }
}
function deepClone(obj) {
  if (obj === null || typeof obj !== "object")
    return obj;
  if (Array.isArray(obj))
    return obj.map((item) => deepClone(item));
  const cloned = {};
  for (const key of Object.keys(obj)) {
    cloned[key] = deepClone(obj[key]);
  }
  return cloned;
}
function projectArray(arr, subPaths, excludePaths) {
  return arr.map((item) => {
    if (item === null || typeof item !== "object")
      return item;
    const projected = {};
    for (const subPath of subPaths) {
      const value = getPath(item, subPath);
      if (value !== undefined) {
        if (subPath.length === 0) {
          Object.assign(projected, deepClone(item));
        } else {
          setPath(projected, subPath, deepClone(value));
        }
      }
    }
    for (const excludePath of excludePaths) {
      deletePath(projected, excludePath);
    }
    return projected;
  });
}
function projectDocument(doc, selects) {
  if (!selects || selects.length === 0) {
    return doc;
  }
  const parsed = selects.map(parseSelectExpression);
  const hasWildcard = parsed.some((p) => p.wildcard && !p.exclude);
  const inclusions = parsed.filter((p) => !p.exclude && !p.wildcard);
  const exclusions = parsed.filter((p) => p.exclude);
  let result;
  if (hasWildcard) {
    result = deepClone(doc);
  } else {
    result = {};
    const byTopLevel = /* @__PURE__ */ new Map;
    for (const incl of inclusions) {
      if (incl.path.length === 0)
        continue;
      const top = incl.path[0];
      if (!byTopLevel.has(top)) {
        byTopLevel.set(top, []);
      }
      byTopLevel.get(top).push(incl.path.slice(1));
    }
    for (const [topField, subPaths] of byTopLevel) {
      const value = doc[topField];
      if (value === undefined)
        continue;
      if (Array.isArray(value)) {
        const exclusionSubPaths = exclusions.filter((e) => e.path[0] === topField).map((e) => e.path.slice(1));
        if (subPaths.some((p) => p.length === 0)) {
          result[topField] = projectArray(value, [[]], exclusionSubPaths);
        } else {
          result[topField] = projectArray(value, subPaths, exclusionSubPaths);
        }
      } else if (typeof value === "object" && value !== null) {
        if (subPaths.some((p) => p.length === 0)) {
          result[topField] = deepClone(value);
        } else {
          const nestedSelects = subPaths.map((p) => p.join("."));
          result[topField] = projectDocument(value, nestedSelects);
        }
      } else {
        result[topField] = value;
      }
    }
  }
  for (const excl of exclusions) {
    deletePath(result, excl.path);
  }
  return result;
}
var MAX_SUMMARY_LENGTH = 200;
function toSummary(activity) {
  const { id, type, createTime } = activity;
  let summary = type;
  switch (activity.type) {
    case "agentMessaged":
    case "userMessaged": {
      const message = activity.message;
      if (!message || message.length === 0) {
        summary = type;
      } else if (message.length > MAX_SUMMARY_LENGTH) {
        summary = message.substring(0, MAX_SUMMARY_LENGTH) + "...";
      } else {
        summary = message;
      }
      break;
    }
    case "progressUpdated": {
      const progress = activity;
      if (progress.title && progress.description) {
        summary = `${progress.title}: ${progress.description}`;
      } else if (progress.title) {
        summary = progress.title;
      } else if (progress.description) {
        summary = progress.description;
      }
      break;
    }
    case "planGenerated": {
      const plan = activity;
      const stepCount = plan.plan?.steps?.length ?? 0;
      summary = `Plan generated with ${stepCount} steps`;
      break;
    }
    case "planApproved":
      summary = "Plan approved";
      break;
    case "sessionCompleted":
      summary = "Session completed";
      break;
    case "sessionFailed": {
      const failed = activity;
      summary = failed.reason ? `Session failed: ${failed.reason}` : "Session failed";
      break;
    }
  }
  return { id, type, createTime, summary };
}
function computeArtifactCount(activity) {
  return activity.artifacts?.length ?? 0;
}
function computeSummary(activity) {
  return toSummary(activity).summary;
}
function computeDurationMs(session) {
  if (!session.createTime || !session.updateTime)
    return 0;
  const created = new Date(session.createTime).getTime();
  const updated = new Date(session.updateTime).getTime();
  if (isNaN(created) || isNaN(updated))
    return 0;
  return Math.max(0, updated - created);
}
function injectActivityComputedFields(activity, selectFields) {
  const result = { ...activity };
  const includeAll = !selectFields || selectFields.length === 0 || selectFields.includes("*");
  const needsArtifactCount = includeAll || selectFields?.includes("artifactCount");
  const needsSummary = includeAll || selectFields?.includes("summary");
  if (needsArtifactCount) {
    result.artifactCount = computeArtifactCount(activity);
  }
  if (needsSummary) {
    result.summary = computeSummary(activity);
  }
  return result;
}
function injectSessionComputedFields(session, selectFields) {
  const result = { ...session };
  const includeAll = !selectFields || selectFields.length === 0 || selectFields.includes("*");
  const needsDurationMs = includeAll || selectFields?.includes("durationMs");
  if (needsDurationMs) {
    result.durationMs = computeDurationMs(session);
  }
  return result;
}
var DEFAULT_ACTIVITY_PROJECTION = [
  "id",
  "type",
  "createTime",
  "originator",
  "artifactCount",
  "summary"
];
var DEFAULT_SESSION_PROJECTION = [
  "id",
  "state",
  "title",
  "createTime"
];
function match(actual, filter) {
  if (filter === undefined)
    return true;
  if (typeof filter !== "object" || filter === null || Array.isArray(filter)) {
    return actual === filter;
  }
  const op = filter;
  if (op.exists !== undefined) {
    const valueExists = actual !== undefined && actual !== null;
    return op.exists ? valueExists : !valueExists;
  }
  if (op.eq !== undefined && actual !== op.eq)
    return false;
  if (op.neq !== undefined && actual === op.neq)
    return false;
  if (op.contains !== undefined && typeof actual === "string" && !actual.toLowerCase().includes(op.contains.toLowerCase()))
    return false;
  if (op.gt !== undefined && op.gt !== null && actual <= op.gt)
    return false;
  if (op.gte !== undefined && op.gte !== null && actual < op.gte)
    return false;
  if (op.lt !== undefined && op.lt !== null && actual >= op.lt)
    return false;
  if (op.lte !== undefined && op.lte !== null && actual > op.lte)
    return false;
  if (op.in !== undefined && !op.in.includes(actual))
    return false;
  return true;
}
function isDotPath(key) {
  return key.includes(".");
}
function matchPath(doc, path22, filter) {
  const pathParts = path22.split(".");
  const value = getPath(doc, pathParts);
  if (Array.isArray(value)) {
    return value.some((v) => match(v, filter));
  }
  return match(value, filter);
}
function matchWhere(doc, where) {
  if (!where)
    return true;
  for (const [key, filter] of Object.entries(where)) {
    if (isDotPath(key)) {
      if (!matchPath(doc, key, filter))
        return false;
    } else {
      const value = doc[key];
      if (!match(value, filter))
        return false;
    }
  }
  return true;
}
function toActivitySelectOptions(where) {
  if (!where)
    return {};
  const options = {};
  if (where.type) {
    if (typeof where.type === "string") {
      options.type = where.type;
    } else if (typeof where.type === "object" && "eq" in where.type && where.type.eq) {
      options.type = where.type.eq;
    }
  }
  return options;
}
function applyProjection(doc, select2, domain) {
  const docRecord = doc;
  const withComputed = domain === "activities" ? injectActivityComputedFields(doc, select2) : injectSessionComputedFields(docRecord, select2);
  if (!select2) {
    const defaults = domain === "activities" ? DEFAULT_ACTIVITY_PROJECTION : DEFAULT_SESSION_PROJECTION;
    return projectDocument(withComputed, defaults);
  }
  if (select2.length === 0) {
    return withComputed;
  }
  return projectDocument(withComputed, select2);
}
async function select(client, query) {
  const storage = client.storage;
  const results = [];
  const limit = query.limit ?? Infinity;
  if (query.from === "sessions") {
    const where = query.where;
    for await (const entry of storage.scanIndex()) {
      if (results.length >= limit)
        break;
      if (where?.id && !match(entry.id, where.id))
        continue;
      if (where?.state && !match(entry.state, where.state))
        continue;
      if (where?.title && !match(entry.title, where.title))
        continue;
      if (where?.search && !entry.title.toLowerCase().includes(where.search.toLowerCase()))
        continue;
      const cached = await storage.get(entry.id);
      if (!cached)
        continue;
      const whereRecord = where;
      const dotFilters = whereRecord ? Object.entries(whereRecord).filter(([k]) => isDotPath(k)) : [];
      if (dotFilters.length > 0) {
        const dotWhere = Object.fromEntries(dotFilters);
        if (!matchWhere(cached.resource, dotWhere))
          continue;
      }
      const item = applyProjection(cached.resource, query.select, "sessions");
      const resourceRecord = cached.resource;
      item._sortKey = {
        createTime: resourceRecord.createTime,
        id: resourceRecord.id
      };
      results.push(item);
    }
    if (query.include && "activities" in query.include) {
      const actConfig = query.include.activities;
      let mappedOptions = {};
      if (typeof actConfig === "object") {
        mappedOptions = {
          ...toActivitySelectOptions(actConfig.where),
          limit: actConfig.limit
        };
      }
      await pMap(results, async (session) => {
        const sessionClient = await client.session(session.id);
        const localActivities = await sessionClient.activities.select({});
        const activities = [];
        for (const act of localActivities) {
          if (mappedOptions.limit && activities.length >= mappedOptions.limit) {
            break;
          }
          if (mappedOptions.type && act.type !== mappedOptions.type) {
            continue;
          }
          activities.push(act);
        }
        session.activities = activities;
      }, { concurrency: 5 });
    }
  } else if (query.from === "activities") {
    const where = query.where;
    let targetSessionIds = [];
    if (where?.sessionId) {
      if (typeof where.sessionId === "string") {
        targetSessionIds = [where.sessionId];
      } else if (typeof where.sessionId === "object" && "eq" in where.sessionId && where.sessionId.eq) {
        targetSessionIds = [where.sessionId.eq];
      }
    }
    const sessionCache = /* @__PURE__ */ new Map;
    const sessionScanner = async function* () {
      if (targetSessionIds.length > 0) {
        for (const id of targetSessionIds) {
          yield { id };
        }
      } else {
        yield* storage.scanIndex();
      }
    };
    for await (const sessionEntry of sessionScanner()) {
      const sessionClient = await client.session(sessionEntry.id);
      const localActivities = await sessionClient.activities.select({});
      for (const act of localActivities) {
        if (where?.id && !match(act.id, where.id))
          continue;
        if (where?.type && !match(act.type, where.type))
          continue;
        const activityWhere = where ? Object.fromEntries(Object.entries(where).filter(([k]) => k !== "sessionId")) : undefined;
        if (!matchWhere(act, activityWhere))
          continue;
        const item = applyProjection(act, query.select, "activities");
        const actRecord = act;
        item._sortKey = {
          createTime: actRecord.createTime,
          id: actRecord.id
        };
        if (query.include && "session" in query.include) {
          const sessConfig = query.include.session;
          const sessSelect = typeof sessConfig === "object" ? sessConfig.select : undefined;
          let sessionInfo = sessionCache.get(sessionEntry.id);
          if (!sessionInfo) {
            const info = await sessionClient.info();
            sessionInfo = info;
            sessionCache.set(sessionEntry.id, sessionInfo);
          }
          item.session = applyProjection(sessionInfo, sessSelect, "sessions");
        }
        results.push(item);
      }
    }
  }
  const order = query.order ?? "desc";
  results.sort((a, b) => {
    const sortKeyA = a._sortKey;
    const sortKeyB = b._sortKey;
    const timeA = new Date(sortKeyA?.createTime ?? a.createTime).getTime();
    const timeB = new Date(sortKeyB?.createTime ?? b.createTime).getTime();
    const idA = sortKeyA?.id ?? a.id;
    const idB = sortKeyB?.id ?? b.id;
    if (timeA !== timeB) {
      return order === "desc" ? timeB - timeA : timeA - timeB;
    }
    if (order === "desc") {
      return idB.localeCompare(idA);
    }
    return idA.localeCompare(idB);
  });
  let finalResults = results;
  const cursorId = query.startAfter ?? query.startAt;
  if (cursorId) {
    const cursorIndex = finalResults.findIndex((item) => {
      const sortKey = item._sortKey;
      const itemId = sortKey?.id ?? item.id;
      return itemId === cursorId;
    });
    if (cursorIndex === -1) {
      return [];
    }
    const sliceIndex = query.startAfter ? cursorIndex + 1 : cursorIndex;
    finalResults = finalResults.slice(sliceIndex);
  }
  for (const result of finalResults) {
    delete result._sortKey;
  }
  return finalResults.slice(0, limit);
}

class JulesClientImpl {
  sources;
  storage;
  apiClient;
  config;
  options;
  storageFactory;
  platform;
  syncInProgress = false;
  constructor(options = {}, defaultStorageFactory2, defaultPlatform2) {
    this.options = options;
    this.storageFactory = options.storageFactory ?? defaultStorageFactory2;
    this.platform = options.platform ?? defaultPlatform2;
    this.storage = this.storageFactory.session();
    const apiKey = options.apiKey_TEST_ONLY_DO_NOT_USE_IN_PRODUCTION ?? options.apiKey ?? this.platform.getEnv("JULES_API_KEY");
    const baseUrl = options.baseUrl ?? "https://jules.googleapis.com/v1alpha";
    this.config = {
      pollingIntervalMs: options.config?.pollingIntervalMs ?? 5000,
      requestTimeoutMs: options.config?.requestTimeoutMs ?? 30000
    };
    this.apiClient = new ApiClient({
      apiKey,
      baseUrl,
      requestTimeoutMs: this.config.requestTimeoutMs,
      rateLimitRetry: options.config?.rateLimitRetry
    });
    this.sources = createSourceManager(this.apiClient);
  }
  async select(query) {
    return select(this, query);
  }
  async sync(options = {}) {
    if (this.syncInProgress) {
      throw new SyncInProgressError;
    }
    this.syncInProgress = true;
    try {
      const startTime = Date.now();
      const {
        sessionId,
        limit = 100,
        depth = "metadata",
        incremental = true,
        concurrency = 3,
        onProgress,
        checkpoint: useCheckpoint = false,
        signal
      } = options;
      let wasAborted = false;
      const candidates = [];
      let activitiesIngested = 0;
      let sessionsIngestedThisRun = 0;
      if (sessionId) {
        const restSession = await this.apiClient.request(`sessions/${sessionId}`);
        const session = mapRestSessionToSdkSession(restSession, this.platform);
        await this.storage.upsert(session);
        candidates.push(session);
        sessionsIngestedThisRun = 1;
      } else {
        let resumeFromId = null;
        let startingCount = 0;
        if (useCheckpoint) {
          const ckpt = await this.loadCheckpoint();
          if (ckpt) {
            resumeFromId = ckpt.lastProcessedSessionId;
            startingCount = ckpt.sessionsProcessed;
          }
        }
        let skipUntilPast = !!resumeFromId;
        const highWaterMark = incremental ? await this._getHighWaterMark() : null;
        const cursor = this.sessions({
          pageSize: Math.min(limit, 100),
          persist: false
        });
        onProgress?.({ phase: "fetching_list", current: 0 });
        for await (const session of cursor) {
          if (signal?.aborted) {
            wasAborted = true;
            break;
          }
          if (skipUntilPast) {
            if (session.id === resumeFromId) {
              skipUntilPast = false;
              continue;
            }
            continue;
          }
          if (highWaterMark && new Date(session.createTime) <= highWaterMark) {
            if (depth === "activities") {
              await this.storage.upsert(session);
              candidates.push(session);
            }
            break;
          }
          await this.storage.upsert(session);
          candidates.push(session);
          sessionsIngestedThisRun++;
          if (useCheckpoint) {
            await this.saveCheckpoint({
              lastProcessedSessionId: session.id,
              sessionsProcessed: startingCount + sessionsIngestedThisRun,
              startedAt: new Date(startTime).toISOString()
            });
          }
          onProgress?.({
            phase: "fetching_list",
            current: sessionsIngestedThisRun,
            lastIngestedId: session.id
          });
          if (candidates.length >= limit)
            break;
        }
      }
      if (depth === "activities" && candidates.length > 0 && !wasAborted) {
        let hydratedCount = 0;
        onProgress?.({
          phase: "hydrating_records",
          current: 0,
          total: candidates.length
        });
        await pMap(candidates, async (session) => {
          if (signal?.aborted)
            return;
          const sessionClient = this.session(session.id);
          const count = await sessionClient.activities.hydrate();
          activitiesIngested += count;
          hydratedCount++;
          onProgress?.({
            phase: "hydrating_records",
            current: hydratedCount,
            total: candidates.length,
            lastIngestedId: session.id,
            activityCount: count
          });
        }, { concurrency });
      }
      if (useCheckpoint && !wasAborted && !sessionId) {
        await this.clearCheckpoint();
      }
      const stats = {
        sessionsIngested: sessionsIngestedThisRun,
        activitiesIngested,
        isComplete: !wasAborted,
        durationMs: Date.now() - startTime
      };
      await updateGlobalCacheMetadata();
      return stats;
    } finally {
      this.syncInProgress = false;
    }
  }
  getCheckpointPath() {
    return join2(getRootDir(), ".jules", "cache", "sync-checkpoint.json");
  }
  async loadCheckpoint() {
    if (!this.platform.readFile)
      return null;
    try {
      const path22 = this.getCheckpointPath();
      const data = await this.platform.readFile(path22);
      return JSON.parse(data);
    } catch {
      return null;
    }
  }
  async saveCheckpoint(checkpoint) {
    if (!this.platform.writeFile)
      return;
    const path22 = this.getCheckpointPath();
    await this.platform.writeFile(path22, JSON.stringify(checkpoint, null, 2));
  }
  async clearCheckpoint() {
    if (!this.platform.deleteFile)
      return;
    try {
      const path22 = this.getCheckpointPath();
      await this.platform.deleteFile(path22);
    } catch {}
  }
  async _getHighWaterMark() {
    let newest = null;
    for await (const entry of this.storage.scanIndex()) {
      const date = new Date(entry.createTime);
      if (!newest || date > newest)
        newest = date;
    }
    return newest;
  }
  getEnv(key) {
    return this.platform.getEnv(`NEXT_PUBLIC_${key}`) || this.platform.getEnv(`REACT_APP_${key}`) || this.platform.getEnv(`VITE_${key}`) || this.platform.getEnv(key);
  }
  with(options) {
    return new JulesClientImpl({
      ...this.options,
      ...options,
      config: {
        ...this.options.config,
        ...options.config
      }
    }, this.storageFactory, this.platform);
  }
  connect(options) {
    return new JulesClientImpl({
      ...this.options,
      ...options
    }, this.storageFactory, this.platform);
  }
  async getSessionResource(id) {
    const cached = await this.storage.get(id);
    if (isCacheValid(cached)) {
      return cached.resource;
    }
    try {
      const restFresh = await this.apiClient.request(`sessions/${id}`);
      const fresh = mapRestSessionToSdkSession(restFresh, this.platform);
      await this.storage.upsert(fresh);
      return fresh;
    } catch (e) {
      if (e.status === 404 && cached) {
        await this.storage.delete(id);
      }
      throw e;
    }
  }
  sessions(options) {
    return new SessionCursor(this.apiClient, this.storage, this.platform, options);
  }
  async all(items, mapper, options) {
    return pMap(items, async (item) => {
      const config = await mapper(item);
      return this.run(config);
    }, options);
  }
  async _prepareSessionCreation(config) {
    if (!config.source) {
      return {
        prompt: config.prompt,
        title: config.title
      };
    }
    const source = await this.sources.get({ github: config.source.github });
    if (!source) {
      throw new SourceNotFoundError(config.source.github);
    }
    return {
      prompt: config.prompt,
      title: config.title,
      sourceContext: {
        source: source.name,
        githubRepoContext: {
          startingBranch: config.source.baseBranch
        }
      }
    };
  }
  async run(config) {
    const body = await this._prepareSessionCreation(config);
    const restSessionResource = await this.apiClient.request("sessions", {
      method: "POST",
      body: {
        ...body,
        automationMode: config.autoPr === false ? "AUTOMATION_MODE_UNSPECIFIED" : "AUTO_CREATE_PR",
        requirePlanApproval: config.requireApproval ?? false
      }
    });
    const sessionResource = mapRestSessionToSdkSession(restSessionResource, this.platform);
    await this.storage.upsert(sessionResource);
    const sessionId = sessionResource.id;
    return {
      id: sessionId,
      stream: async function* () {
        yield* streamActivities(sessionId, this.apiClient, this.config.pollingIntervalMs, this.platform);
      }.bind(this),
      result: async () => {
        const finalSession = await pollUntilCompletion(sessionId, this.apiClient, this.config.pollingIntervalMs, this.platform);
        await this.storage.upsert(finalSession);
        return mapSessionResourceToOutcome(finalSession);
      }
    };
  }
  session(configOrId) {
    if (typeof configOrId === "string") {
      const storage = this.storageFactory.activity(configOrId);
      return new SessionClientImpl(configOrId, this.apiClient, this.config, storage, this.storage, this.platform);
    }
    const config = configOrId;
    const sessionPromise = (async () => {
      const body = await this._prepareSessionCreation(config);
      const restSession = await this.apiClient.request("sessions", {
        method: "POST",
        body: {
          ...body,
          automationMode: config.autoPr === false ? "AUTOMATION_MODE_UNSPECIFIED" : "AUTO_CREATE_PR",
          requirePlanApproval: config.requireApproval ?? true
        }
      });
      const session = mapRestSessionToSdkSession(restSession, this.platform);
      await this.storage.upsert(session);
      const activityStorage = this.storageFactory.activity(session.id);
      return new SessionClientImpl(session.name, this.apiClient, this.config, activityStorage, this.storage, this.platform);
    })();
    return sessionPromise;
  }
}

class NodeFileStorage {
  filePath;
  metadataPath;
  initialized = false;
  writeStream = null;
  index = /* @__PURE__ */ new Map;
  indexBuilt = false;
  indexBuildPromise = null;
  currentFileSize = 0;
  constructor(sessionId, rootDir) {
    const sessionCacheDir = path$1.resolve(rootDir, ".jules/cache", sessionId);
    this.filePath = path$1.join(sessionCacheDir, "activities.jsonl");
    this.metadataPath = path$1.join(sessionCacheDir, "metadata.json");
  }
  async init() {
    if (this.initialized)
      return;
    await fs2.mkdir(path$1.dirname(this.filePath), { recursive: true });
    try {
      const stats = await fs2.stat(this.filePath);
      this.currentFileSize = stats.size;
    } catch (e) {
      if (e.code === "ENOENT") {
        this.currentFileSize = 0;
      } else {
        throw e;
      }
    }
    this.writeStream = createWriteStream(this.filePath, {
      flags: "a",
      encoding: "utf8"
    });
    this.writeStream.on("error", (err) => {
      console.error(`[NodeFileStorage] WriteStream error for ${this.filePath}:`, err);
    });
    this.initialized = true;
  }
  async close() {
    if (this.writeStream) {
      await new Promise((resolve2) => this.writeStream.end(resolve2));
      this.writeStream = null;
    }
    this.initialized = false;
    this.indexBuilt = false;
    this.index.clear();
    this.indexBuildPromise = null;
  }
  async _readMetadata() {
    try {
      const content = await fs2.readFile(this.metadataPath, "utf8");
      return JSON.parse(content);
    } catch (e) {
      if (e.code === "ENOENT") {
        return { activityCount: 0 };
      }
      throw e;
    }
  }
  async _writeMetadata(metadata) {
    await fs2.writeFile(this.metadataPath, JSON.stringify(metadata, null, 2), "utf8");
  }
  async append(activity) {
    if (!this.initialized)
      await this.init();
    const metadata = await this._readMetadata();
    metadata.activityCount += 1;
    await this._writeMetadata(metadata);
    const line = JSON.stringify(activity) + `
`;
    const startOffset = this.currentFileSize;
    if (this.writeStream) {
      const canContinue = this.writeStream.write(line);
      this.currentFileSize += Buffer.byteLength(line);
      if (this.indexBuilt || this.indexBuildPromise) {
        if (!this.index.has(activity.id)) {
          this.index.set(activity.id, startOffset);
        }
      }
      if (!canContinue) {
        await new Promise((resolve2) => this.writeStream.once("drain", resolve2));
      }
    } else {
      throw new Error("NodeFileStorage: WriteStream is not initialized");
    }
  }
  async buildIndex() {
    if (this.indexBuilt)
      return;
    if (this.indexBuildPromise)
      return this.indexBuildPromise;
    this.indexBuildPromise = (async () => {
      try {
        this.index.clear();
        try {
          await fs2.access(this.filePath);
        } catch (e) {
          this.indexBuilt = true;
          return;
        }
        const fileStream = createReadStream(this.filePath, {
          encoding: "utf8"
        });
        const rl = readline.createInterface({
          input: fileStream,
          crlfDelay: Infinity
        });
        let currentOffset = 0;
        for await (const line of rl) {
          const byteLen = Buffer.byteLength(line);
          const lineTotalBytes = byteLen + 1;
          if (line.trim().length > 0) {
            try {
              const activity = JSON.parse(line);
              if (!this.index.has(activity.id)) {
                this.index.set(activity.id, currentOffset);
              }
            } catch (e) {}
          }
          currentOffset += lineTotalBytes;
        }
        this.indexBuilt = true;
      } finally {
        this.indexBuildPromise = null;
      }
    })();
    return this.indexBuildPromise;
  }
  async get(activityId) {
    if (!this.initialized)
      await this.init();
    if (!this.indexBuilt)
      await this.buildIndex();
    const offset = this.index.get(activityId);
    if (offset === undefined)
      return;
    return new Promise((resolve2, reject) => {
      const stream = createReadStream(this.filePath, {
        start: offset,
        encoding: "utf8"
      });
      const rl = readline.createInterface({
        input: stream,
        crlfDelay: Infinity
      });
      let found = false;
      rl.on("line", (line) => {
        if (found)
          return;
        found = true;
        rl.close();
        stream.destroy();
        try {
          const activity = JSON.parse(line);
          resolve2(activity);
        } catch (e) {
          resolve2(undefined);
        }
      });
      rl.on("error", (err) => {
        reject(err);
      });
      stream.on("error", (err) => {
        reject(err);
      });
      rl.on("close", () => {
        if (!found)
          resolve2(undefined);
      });
    });
  }
  async latest() {
    if (!this.initialized)
      await this.init();
    try {
      await fs2.access(this.filePath);
    } catch (e) {
      if (e.code === "ENOENT") {
        return;
      }
      throw e;
    }
    const stat2 = await fs2.stat(this.filePath);
    const fileSize = stat2.size;
    if (fileSize === 0)
      return;
    const bufferSize = 4096;
    const buffer = Buffer.alloc(bufferSize);
    let fd;
    try {
      fd = await fs2.open(this.filePath, "r");
      let currentPos = fileSize;
      let trailing = "";
      while (currentPos > 0) {
        const readSize = Math.min(bufferSize, currentPos);
        const position = currentPos - readSize;
        const result = await fd.read(buffer, 0, readSize, position);
        const chunk = result.buffer.toString("utf8", 0, readSize);
        const content = chunk + trailing;
        const lines = content.split(`
`);
        if (position > 0) {
          trailing = lines.shift() || "";
        } else {
          trailing = "";
        }
        for (let i = lines.length - 1;i >= 0; i--) {
          const line = lines[i].trim();
          if (line.length === 0)
            continue;
          try {
            return JSON.parse(line);
          } catch (e) {
            console.warn(`[NodeFileStorage] Corrupt JSON line ignored during latest() check in ${this.filePath}`);
          }
        }
        currentPos -= readSize;
      }
    } finally {
      if (fd)
        await fd.close();
    }
    return;
  }
  async* scan() {
    if (!this.initialized)
      await this.init();
    try {
      await fs2.access(this.filePath);
    } catch (e) {
      if (e.code === "ENOENT") {
        return;
      }
      throw e;
    }
    const fileStream = createReadStream(this.filePath, { encoding: "utf8" });
    const rl = readline.createInterface({
      input: fileStream,
      crlfDelay: Infinity
    });
    for await (const line of rl) {
      if (line.trim().length === 0)
        continue;
      try {
        yield JSON.parse(line);
      } catch (e) {
        console.warn(`[NodeFileStorage] Corrupt JSON line ignored in ${this.filePath}`);
      }
    }
  }
}

class NodeSessionStorage {
  cacheDir;
  indexFilePath;
  initialized = false;
  constructor(rootDir) {
    this.cacheDir = path$1.resolve(rootDir, ".jules/cache");
    this.indexFilePath = path$1.join(this.cacheDir, "sessions.jsonl");
  }
  async init() {
    if (this.initialized)
      return;
    await fs2.mkdir(this.cacheDir, { recursive: true });
    this.initialized = true;
  }
  getSessionPath(sessionId) {
    return path$1.join(this.cacheDir, sessionId, "session.json");
  }
  async upsert(session) {
    await this.init();
    const sessionDir = path$1.join(this.cacheDir, session.id);
    await fs2.mkdir(sessionDir, { recursive: true });
    const cached = {
      resource: session,
      _lastSyncedAt: Date.now()
    };
    await fs2.writeFile(path$1.join(sessionDir, "session.json"), JSON.stringify(cached, null, 2), "utf8");
    const indexEntry = {
      id: session.id,
      title: session.title,
      state: session.state,
      createTime: session.createTime,
      source: session.sourceContext?.source || "unknown",
      _updatedAt: Date.now()
    };
    await fs2.appendFile(this.indexFilePath, JSON.stringify(indexEntry) + `
`, "utf8");
  }
  async upsertMany(sessions) {
    await Promise.all(sessions.map((s) => this.upsert(s)));
  }
  async get(sessionId) {
    await this.init();
    try {
      const data = await fs2.readFile(this.getSessionPath(sessionId), "utf8");
      return JSON.parse(data);
    } catch (e) {
      if (e.code === "ENOENT")
        return;
      throw e;
    }
  }
  async delete(sessionId) {
    await this.init();
    const sessionDir = path$1.join(this.cacheDir, sessionId);
    await fs2.rm(sessionDir, { recursive: true, force: true });
  }
  async* scanIndex() {
    await this.init();
    try {
      const fileStream = createReadStream(this.indexFilePath, {
        encoding: "utf8"
      });
      const rl = readline.createInterface({
        input: fileStream,
        crlfDelay: Infinity
      });
      const entries = /* @__PURE__ */ new Map;
      for await (const line of rl) {
        if (!line.trim())
          continue;
        try {
          const entry = JSON.parse(line);
          entries.set(entry.id, entry);
        } catch (e) {}
      }
      for (const entry of entries.values()) {
        yield entry;
      }
    } catch (e) {
      if (e.code === "ENOENT")
        return;
      throw e;
    }
  }
}

class NodePlatform {
  async saveFile(filepath, data, encoding, activityId) {
    const buffer = Buffer$1.from(data, encoding);
    await writeFile2(filepath, buffer);
  }
  async sleep(ms) {
    await setTimeout$1(ms);
  }
  createDataUrl(data, mimeType) {
    return `data:${mimeType};base64,${data}`;
  }
  async fetch(input, init) {
    const res = await global.fetch(input, init);
    return {
      ok: res.ok,
      status: res.status,
      json: () => res.json(),
      text: () => res.text()
    };
  }
  crypto = {
    randomUUID: () => crypto.randomUUID(),
    async sign(text, secret) {
      const hmac = crypto.createHmac("sha256", secret);
      hmac.update(text);
      return hmac.digest("base64url");
    },
    async verify(text, signature, secret) {
      const expected = await this.sign(text, secret);
      const a = Buffer$1.from(expected);
      const b = Buffer$1.from(signature);
      return a.length === b.length && crypto.timingSafeEqual(a, b);
    }
  };
  encoding = {
    base64Encode: (text) => {
      return Buffer$1.from(text).toString("base64url");
    },
    base64Decode: (text) => {
      return Buffer$1.from(text, "base64url").toString("utf-8");
    }
  };
  getEnv(key) {
    return process.env[key];
  }
  async readFile(path22) {
    return readFile2(path22, "utf-8");
  }
  async writeFile(path22, content) {
    await writeFile2(path22, content, "utf-8");
  }
  async deleteFile(path22) {
    await rm2(path22, { force: true });
  }
}
var FILTER_OP_SCHEMA = {
  description: "Filter operators for where clause",
  operators: [
    {
      name: "eq",
      description: "Equals (also supports direct value)",
      example: '{ id: "abc" } or { id: { eq: "abc" } }'
    },
    {
      name: "neq",
      description: "Not equals",
      example: '{ state: { neq: "failed" } }'
    },
    {
      name: "contains",
      description: "Case-insensitive substring match",
      example: '{ title: { contains: "bug" } }'
    },
    {
      name: "gt",
      description: "Greater than",
      example: '{ createTime: { gt: "2024-01-01" } }'
    },
    {
      name: "lt",
      description: "Less than",
      example: '{ createTime: { lt: "2024-12-31" } }'
    },
    {
      name: "gte",
      description: "Greater than or equal",
      example: "{ artifactCount: { gte: 1 } }"
    },
    {
      name: "lte",
      description: "Less than or equal",
      example: "{ artifactCount: { lte: 10 } }"
    },
    {
      name: "in",
      description: "Value in array",
      example: '{ state: { in: ["completed", "failed"] } }'
    },
    {
      name: "exists",
      description: "Field existence check",
      example: '{ "outputs.pullRequest": { exists: true } }'
    }
  ],
  dotNotation: {
    description: "Use dot notation for nested field paths. When filtering arrays, uses existential matching (ANY element matches).",
    examples: [
      '"artifacts.type": "bashOutput"',
      '"artifacts.exitCode": { neq: 0 }',
      '"plan.steps.title": { contains: "test" }',
      '"outputs.pullRequest.url": { exists: true }'
    ]
  }
};
var VALID_OPERATORS = new Set(FILTER_OP_SCHEMA.operators.map((op) => op.name));
var defaultPlatform = new NodePlatform;
var defaultStorageFactory = {
  activity: (sessionId) => new NodeFileStorage(sessionId, getRootDir()),
  session: () => new NodeSessionStorage(getRootDir())
};
function connect(options = {}) {
  return new JulesClientImpl(options, defaultStorageFactory, defaultPlatform);
}
var jules = connect();

// fleet-merge.ts
var repoInfo = await getGitRepoInfo();
var OWNER = repoInfo.owner;
var REPO = repoInfo.repo;
var BASE_BRANCH = process.env.FLEET_BASE_BRANCH ?? "main";
var MAX_RETRIES = Number(process.env.FLEET_MAX_RETRIES ?? 2);
var PR_POLL_INTERVAL_MS = 30000;
var PR_POLL_TIMEOUT_MS = 15 * 60 * 1000;
var headers = {
  Authorization: `Bearer ${GITHUB_TOKEN}`,
  Accept: "application/vnd.github+json",
  "X-GitHub-Api-Version": "2022-11-28"
};
var API = `https://api.github.com/repos/${OWNER}/${REPO}`;
var date = new Intl.DateTimeFormat("en-CA", { year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date).replaceAll("-", "_");
var root = path4.dirname(findUpSync(".git"));
var fleetDir = path4.join(root, ".fleet", date);
var analysis = await Bun.file(path4.join(fleetDir, "issue_tasks.json")).json();
var sessions = await Bun.file(path4.join(fleetDir, "sessions.json")).json();
async function findFleetPRs() {
  const res = await fetch(`${API}/pulls?state=open&per_page=100`, { headers });
  const pulls = await res.json();
  const prMap = new Map;
  for (const session of sessions) {
    const matchingPR = pulls.find((pr) => pr.head.ref.includes(session.sessionId) || pr.body?.includes(session.sessionId));
    if (matchingPR) {
      prMap.set(session.taskId, matchingPR);
    }
  }
  return prMap;
}
async function waitForCI(prNumber, maxWaitMs = 10 * 60 * 1000) {
  const start = Date.now();
  const prRes = await fetch(`${API}/pulls/${prNumber}`, { headers });
  const prData = await prRes.json();
  const headSha = prData.head.sha;
  while (Date.now() - start < maxWaitMs) {
    const res = await fetch(`${API}/commits/${headSha}/check-runs`, { headers });
    const data = await res.json();
    if (data.check_runs.length === 0) {
      console.log(`  \u2139\uFE0F  No check runs found for PR #${prNumber}. Proceeding without CI.`);
      return true;
    }
    const allComplete = data.check_runs.every((run) => run.status === "completed");
    const allPassed = data.check_runs.every((run) => run.conclusion === "success" || run.conclusion === "skipped");
    if (allComplete && allPassed)
      return true;
    if (allComplete && !allPassed)
      return false;
    console.log(`  \u23F3 CI still running for PR #${prNumber}... waiting 30s`);
    await new Promise((r) => setTimeout(r, 30000));
  }
  console.log(`  \u23F0 CI timeout for PR #${prNumber}`);
  return false;
}
async function redispatchTask(task, oldPr) {
  console.log(`  \uD83D\uDD12 Closing conflicting PR #${oldPr.number}...`);
  await fetch(`${API}/pulls/${oldPr.number}`, {
    method: "PATCH",
    headers: { ...headers, "Content-Type": "application/json" },
    body: JSON.stringify({
      state: "closed",
      body: `${oldPr.body ?? ""}

---
\u26A0\uFE0F Closed by fleet-merge: merge conflict detected. Task re-dispatched as a new session.`
    })
  });
  console.log(`  \uD83D\uDE80 Re-dispatching task "${task.id}" against current ${BASE_BRANCH}...`);
  const run = await jules.run({
    prompt: task.prompt,
    source: {
      github: `${OWNER}/${REPO}`,
      baseBranch: BASE_BRANCH
    }
  });
  console.log(`  \uD83D\uDCDD New session: ${run.id}`);
  const sessionEntry = sessions.find((s) => s.taskId === task.id);
  if (sessionEntry) {
    sessionEntry.sessionId = run.id;
    const sessionsPath = path4.join(fleetDir, "sessions.json");
    await Bun.write(sessionsPath, JSON.stringify(sessions, null, 2));
  }
  console.log(`  \u23F3 Waiting for new PR from session ${run.id}...`);
  const start = Date.now();
  while (Date.now() - start < PR_POLL_TIMEOUT_MS) {
    await new Promise((r) => setTimeout(r, PR_POLL_INTERVAL_MS));
    const res = await fetch(`${API}/pulls?state=open&per_page=100`, { headers });
    const pulls = await res.json();
    const newPr = pulls.find((pr) => pr.head.ref.includes(run.id) || pr.body?.includes(run.id));
    if (newPr) {
      console.log(`  \u2705 New PR #${newPr.number} found (${newPr.head.ref})`);
      return newPr;
    }
    console.log(`  \u23F3 No PR yet... polling again in 30s`);
  }
  throw new Error(`Timed out waiting for new PR from re-dispatched session ${run.id}`);
}
var prMap = await findFleetPRs();
console.log(`Found ${prMap.size}/${analysis.tasks.length} fleet PRs`);
for (const [taskId, pr] of prMap) {
  console.log(`  ${taskId} \u2192 PR #${pr.number} (${pr.head.ref})`);
}
if (prMap.size !== analysis.tasks.length) {
  console.error(`\u274C Expected ${analysis.tasks.length} PRs but found ${prMap.size}. Waiting for all PRs before merging.`);
  process.exit(1);
}
for (const task of analysis.tasks) {
  let pr = prMap.get(task.id);
  if (!pr) {
    console.error(`\u274C No PR found for task "${task.id}". Aborting.`);
    process.exit(1);
  }
  let retryCount = 0;
  let merged = false;
  while (!merged) {
    console.log(`
\uD83D\uDCE6 Processing Task "${task.id}" \u2192 PR #${pr.number}${retryCount > 0 ? ` (retry ${retryCount})` : ""}`);
    if (analysis.tasks.indexOf(task) > 0 || retryCount > 0) {
      console.log(`  \uD83D\uDD04 Updating PR #${pr.number} branch from ${BASE_BRANCH}...`);
      const updateRes = await fetch(`${API}/pulls/${pr.number}/update-branch`, {
        method: "PUT",
        headers: { ...headers, "Content-Type": "application/json" }
      });
      if (!updateRes.ok) {
        const body = await updateRes.text();
        if (updateRes.status === 422) {
          if (retryCount >= MAX_RETRIES) {
            console.error(`  \u274C Conflict persists after ${MAX_RETRIES} retries. Human intervention required.`);
            console.error(`  PR: https://github.com/${OWNER}/${REPO}/pull/${pr.number}`);
            process.exit(1);
          }
          console.log(`  \u26A0\uFE0F Merge conflict detected. Re-dispatching task "${task.id}"...`);
          pr = await redispatchTask(task, pr);
          retryCount++;
          continue;
        }
        throw new Error(`Update branch failed (${updateRes.status}): ${body}`);
      }
      await new Promise((r) => setTimeout(r, 5000));
    }
    console.log(`  \uD83E\uDDEA Waiting for CI on PR #${pr.number}...`);
    const ciPassed = await waitForCI(pr.number);
    if (!ciPassed) {
      console.error(`  \u274C CI failed for PR #${pr.number}. Aborting sequential merge.`);
      process.exit(1);
    }
    console.log(`  \u2705 CI passed. Merging PR #${pr.number}...`);
    const mergeRes = await fetch(`${API}/pulls/${pr.number}/merge`, {
      method: "PUT",
      headers: { ...headers, "Content-Type": "application/json" },
      body: JSON.stringify({ merge_method: "squash" })
    });
    if (!mergeRes.ok) {
      const body = await mergeRes.text();
      console.error(`  \u274C Failed to merge PR #${pr.number}: ${body}`);
      process.exit(1);
    }
    console.log(`  \uD83C\uDF89 PR #${pr.number} merged successfully.`);
    merged = true;
  }
}
console.log(`
\u2705 All ${analysis.tasks.length} PRs merged sequentially. No conflicts.`);
