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

/**
 * Read-only, repository-scoped collection for the Jules persona PR learning
 * loop (U2). Implements the "collect" half of R1/R2/R4/R13 from
 * `schema/jules-pr-learning-contract.md`: paginate PR metadata to
 * exhaustion under a fixed `as_of`/lookback watermark, verify identity and
 * Jules session linkage, and reconcile mutable fields with a final
 * re-fetch — never checking out or executing PR code.
 *
 * This module never reads PR title/body/comment/review/log text. Only
 * structured, low-cardinality fields (state, SHAs, repo names, author
 * identity, label names, mergeable_state, check-run conclusions) are ever
 * collected, which is the primary prompt-injection defense: attacker
 * text simply never enters this pipeline. See `classify.ts` for the
 * corresponding classification boundary.
 */

import { evaluateCheckRuns, type CheckRunStatus } from "../github/ci-checks.js";
import { getSanitizedErrorMessage } from "../github/mutation-diagnostics.js";
import type { Persona } from "./types.ts";

/** Injected fetch boundary so every network call in this module is testable. */
export interface CollectorFetchResponse {
  ok: boolean;
  status: number;
  json(): Promise<unknown>;
  text(): Promise<string>;
}

export type CollectorFetchLike = (
  url: string,
  init?: { headers?: HeadersInit }
) => Promise<CollectorFetchResponse>;

/**
 * A verified linkage between a PR and a real Jules session/source record.
 * Must be produced by an independently verified source (a Jules session
 * registry, the Jules SDK, or an equivalent authoritative lookup) — never
 * derived from text found in the PR title, body, or branch name. A
 * `sessionId`-shaped token appearing in PR text is not itself evidence.
 */
export interface VerifiedSessionLink {
  sessionId: string;
}

/**
 * Injected session-verification boundary (R1). This checkout has no
 * built-in access to a real Jules session registry, so every caller must
 * supply an implementation explicitly — there is no default that accepts
 * title/body/branch markers as a substitute for verification.
 *
 * `NullSessionVerifier` below is the explicit, fail-closed stand-in for
 * "no linkage source is wired up in this environment": it always returns
 * `null`, which the identity predicate in `classify.ts` treats as
 * unverified (and therefore `ambiguous`), never as an accepted fallback.
 */
export interface JulesSessionVerifier {
  verify(candidate: {
    repoFullName: string;
    prNumber: number;
    authorId: string | null;
    headRepoFullName: string | null;
    headSha: string;
  }): Promise<VerifiedSessionLink | null> | VerifiedSessionLink | null;
}

/**
 * Explicit fail-closed verifier: always reports "no verified session
 * linkage". Use this only when the caller genuinely has no session
 * registry to consult — every PR collected under this verifier is
 * quarantined `ambiguous` rather than silently treated as identity-verified.
 */
export const NullSessionVerifier: JulesSessionVerifier = Object.freeze({
  verify: () => null,
});

/** Accepted historical Jules author identities used by both collection paths. */
export const JULES_AUTHOR_LOGINS = Object.freeze([
  "google-labs-jules",
  "google-labs-jules[bot]",
  "jules-bot",
] as const);

/** Structured, non-text fields collected for a single candidate PR. */
export interface RawPullRecord {
  number: number;
  state: "open" | "closed";
  draft: boolean;
  merged_at: string | null;
  merge_commit_sha: string | null;
  base_sha: string;
  base_repo_full_name: string | null;
  head_sha: string;
  head_repo_full_name: string | null;
  author_id: string | null;
  /** Structured label names only (never label descriptions/PR text). */
  labels: string[];
  mergeable_state: string | null;
  check_conclusion: "pass" | "fail" | "pending" | "no_checks";
  /** ISO-8601 timestamp of the most recent "reopened" timeline event, if any. */
  reopened_at: string | null;
  session_link: VerifiedSessionLink | null;
  event_ids: string[];
  /**
   * True when a reconciliation re-fetch observed a different `head_sha`
   * (or base/head repository) than the initial fetch, i.e. the PR mutated
   * mid-collection or the two endpoint reads were inconsistent. Consumed by
   * `classify.ts` to force `ambiguous` rather than trusting a moving target.
   */
  evidence_inconsistent: boolean;
}

export interface CollectorOptions {
  apiBase: string;
  headers: HeadersInit;
  /** Repository scope boundary (`owner/repo`); PRs outside this base repo are never collected. */
  repoFullName: string;
  /** The persona this collection run is scoped to. */
  persona: Persona;
  /** Historical author login forms accepted as candidates for this persona (not a text-marker check — used only to select which PRs to fetch in detail). */
  authorLogins: readonly string[];
  /** Fixed snapshot watermark; PRs created after this instant are excluded. */
  asOf: string;
  /** Lower bound on `created_at`; pagination stops once older records are reached. */
  lookbackWatermark: string;
  /** Session/source verifier (R1). No default — callers must decide explicitly. */
  sessionVerifier: JulesSessionVerifier;
  /** Milliseconds a reopened PR must remain stable before it can leave `open`. Default 24h. */
  stabilizationCutoffMs?: number;
  fetchImpl?: CollectorFetchLike;
}

export interface CollectionResult {
  records: RawPullRecord[];
  /** False whenever any pagination/API failure or cross-endpoint inconsistency was observed. */
  complete: boolean;
  errors: string[];
  as_of: string;
}

interface ListedPull {
  number: number;
  created_at: string;
  user: { login: string | null } | null;
}

interface PullDetail {
  number: number;
  state: "open" | "closed";
  draft: boolean;
  merged_at: string | null;
  merge_commit_sha: string | null;
  mergeable_state: string | null;
  base: { sha: string; repo: { full_name: string | null } | null };
  head: { sha: string; repo: { full_name: string | null } | null };
  user: { login: string | null } | null;
  labels: Array<{ name: string }>;
}

interface TimelineEvent {
  id: number | string;
  event: string;
  created_at: string;
}

const DEFAULT_STABILIZATION_CUTOFF_MS = 24 * 60 * 60 * 1000;
const LIST_PAGE_SIZE = 100;
const MAX_LIST_PAGES = 50; // hard upper bound so a misconfigured watermark cannot paginate forever

async function readJson<T>(response: CollectorFetchResponse, context: string): Promise<T> {
  if (!response.ok) {
    const body = getSanitizedErrorMessage(await response.text());
    throw new Error(`${context} failed (${response.status}): ${body}`);
  }
  try {
    return (await response.json()) as T;
  } catch (error) {
    throw new Error(`${context} returned invalid JSON: ${getSanitizedErrorMessage(error)}`);
  }
}

/**
 * Paginate `GET /pulls?state=all` to exhaustion, bounded by `asOf` (upper
 * bound) and `lookbackWatermark` (lower bound), then filter to candidate
 * author logins. This is a scope-narrowing step only — full identity/session
 * verification happens per-record afterward.
 */
async function listCandidatePulls(
  options: CollectorOptions,
  fetchImpl: CollectorFetchLike
): Promise<{ numbers: number[]; complete: boolean; errors: string[] }> {
  const errors: string[] = [];
  const numbers: number[] = [];
  const asOfMs = Date.parse(options.asOf);
  const watermarkMs = Date.parse(options.lookbackWatermark);
  const acceptedLogins = new Set(options.authorLogins);

  let complete = true;
  for (let page = 1; page <= MAX_LIST_PAGES; page++) {
    let response: CollectorFetchResponse;
    try {
      response = await fetchImpl(
        `${options.apiBase}/pulls?state=all&sort=created&direction=desc&per_page=${LIST_PAGE_SIZE}&page=${page}`,
        { headers: options.headers }
      );
    } catch (error) {
      errors.push(`pull list page ${page} request failed: ${getSanitizedErrorMessage(error)}`);
      complete = false;
      break;
    }

    let items: ListedPull[];
    try {
      items = await readJson<ListedPull[]>(response, `pull list page ${page}`);
    } catch (error) {
      errors.push(getSanitizedErrorMessage(error));
      complete = false;
      break;
    }

    if (!Array.isArray(items)) {
      errors.push(`pull list page ${page} was not an array`);
      complete = false;
      break;
    }

    let reachedWatermark = false;
    for (const item of items) {
      const createdMs = Date.parse(item.created_at);
      if (!Number.isFinite(createdMs) || createdMs > asOfMs) {
        continue; // skip anything created after the fixed snapshot instant
      }
      if (createdMs < watermarkMs) {
        reachedWatermark = true;
        break;
      }
      const login = item.user?.login ?? null;
      if (login !== null && acceptedLogins.has(login)) {
        numbers.push(item.number);
      }
    }

    if (reachedWatermark || items.length < LIST_PAGE_SIZE) {
      break;
    }
    if (page === MAX_LIST_PAGES) {
      errors.push(
        `pull list pagination reached the ${MAX_LIST_PAGES}-page safety bound before the lookback watermark`
      );
      complete = false;
    }
  }

  return { numbers, complete, errors };
}

async function fetchPullDetail(
  options: CollectorOptions,
  fetchImpl: CollectorFetchLike,
  prNumber: number
): Promise<PullDetail> {
  const response = await fetchImpl(`${options.apiBase}/pulls/${prNumber}`, {
    headers: options.headers,
  });
  return readJson<PullDetail>(response, `pull #${prNumber} detail`);
}

async function fetchAllTimelineEvents(
  options: CollectorOptions,
  fetchImpl: CollectorFetchLike,
  prNumber: number
): Promise<TimelineEvent[]> {
  const events: TimelineEvent[] = [];
  for (let page = 1; page <= MAX_LIST_PAGES; page++) {
    const response = await fetchImpl(
      `${options.apiBase}/issues/${prNumber}/events?per_page=${LIST_PAGE_SIZE}&page=${page}`,
      { headers: options.headers }
    );
    const pageEvents = await readJson<TimelineEvent[]>(response, `pull #${prNumber} events page ${page}`);
    events.push(...pageEvents);
    if (pageEvents.length < LIST_PAGE_SIZE) {
      break;
    }
  }
  return events;
}

async function fetchCheckConclusion(
  options: CollectorOptions,
  fetchImpl: CollectorFetchLike,
  headSha: string
): Promise<"pass" | "fail" | "pending" | "no_checks"> {
  const allRuns: CheckRunStatus[] = [];
  for (let page = 1; page <= MAX_LIST_PAGES; page++) {
    const response = await fetchImpl(
      `${options.apiBase}/commits/${headSha}/check-runs?per_page=${LIST_PAGE_SIZE}&page=${page}`,
      { headers: options.headers }
    );
    const data = await readJson<{ check_runs: CheckRunStatus[] }>(
      response,
      `check runs for ${headSha} page ${page}`
    );
    allRuns.push(...data.check_runs);
    if (data.check_runs.length < LIST_PAGE_SIZE) {
      break;
    }
  }
  if (allRuns.length === 0) {
    return "no_checks";
  }
  const evaluation = evaluateCheckRuns(allRuns, { allowNoChecks: false });
  return evaluation;
}

function mostRecentReopenedAt(events: TimelineEvent[]): string | null {
  const reopenedEvents = events.filter((event) => event.event === "reopened");
  if (reopenedEvents.length === 0) {
    return null;
  }
  return reopenedEvents.reduce((latest, event) =>
    Date.parse(event.created_at) > Date.parse(latest.created_at) ? event : latest
  ).created_at;
}

async function collectSingleRecord(
  options: CollectorOptions,
  fetchImpl: CollectorFetchLike,
  prNumber: number
): Promise<RawPullRecord> {
  const initialDetail = await fetchPullDetail(options, fetchImpl, prNumber);
  const events = await fetchAllTimelineEvents(options, fetchImpl, prNumber);
  const checkConclusion = await fetchCheckConclusion(options, fetchImpl, initialDetail.head.sha);

  // Reconciliation re-fetch: mutable fields (merged_at, mergeable_state,
  // head sha) may change between the list scan and now. Re-fetch once more
  // and flag any inconsistency rather than silently trusting the first read.
  const reconciledDetail = await fetchPullDetail(options, fetchImpl, prNumber);
  const evidenceInconsistent =
    initialDetail.head.sha !== reconciledDetail.head.sha ||
    (initialDetail.base.repo?.full_name ?? null) !== (reconciledDetail.base.repo?.full_name ?? null) ||
    (initialDetail.head.repo?.full_name ?? null) !== (reconciledDetail.head.repo?.full_name ?? null);

  const detail = reconciledDetail;
  const authorId = detail.user?.login ?? null;
  const headRepoFullName = detail.head.repo?.full_name ?? null;

  const sessionLink = await options.sessionVerifier.verify({
    repoFullName: options.repoFullName,
    prNumber,
    authorId,
    headRepoFullName,
    headSha: detail.head.sha,
  });

  return {
    number: prNumber,
    state: detail.state,
    draft: detail.draft,
    merged_at: detail.merged_at,
    merge_commit_sha: detail.merge_commit_sha,
    base_sha: detail.base.sha,
    base_repo_full_name: detail.base.repo?.full_name ?? null,
    head_sha: detail.head.sha,
    head_repo_full_name: headRepoFullName,
    author_id: authorId,
    labels: detail.labels.map((label) => label.name),
    mergeable_state: detail.mergeable_state,
    check_conclusion: checkConclusion,
    reopened_at: mostRecentReopenedAt(events),
    session_link: sessionLink,
    event_ids: events.map((event) => String(event.id)),
    evidence_inconsistent: evidenceInconsistent,
  };
}

/**
 * Collects a bounded, repository-scoped snapshot of candidate PRs for one
 * persona. Never checks out or executes PR code — every field collected is
 * structured GitHub API metadata (state, SHAs, repo names, author id,
 * label names, mergeable_state, check-run conclusions).
 *
 * On any pagination/API failure the result is marked `complete: false`;
 * callers must not advance any collection watermark when that is the case.
 */
export async function collectPersonaPullRequests(
  options: CollectorOptions
): Promise<CollectionResult> {
  const fetchImpl = options.fetchImpl ?? (fetch as unknown as CollectorFetchLike);
  const errors: string[] = [];
  const records: RawPullRecord[] = [];

  const { numbers, complete: listComplete, errors: listErrors } = await listCandidatePulls(
    options,
    fetchImpl
  );
  errors.push(...listErrors);

  let complete = listComplete;
  for (const prNumber of numbers) {
    try {
      records.push(await collectSingleRecord(options, fetchImpl, prNumber));
    } catch (error) {
      errors.push(`pull #${prNumber} collection failed: ${getSanitizedErrorMessage(error)}`);
      complete = false;
    }
  }

  return {
    records,
    complete,
    errors,
    as_of: options.asOf,
  };
}

export { DEFAULT_STABILIZATION_CUTOFF_MS };
