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
 * Deterministic, versioned report assembly for the Jules persona PR
 * learning loop (U2). Turns a set of classified `EvidenceEnvelope`s (see
 * `classify.ts`) into a report artifact whose digest depends only on the
 * underlying evidence — not on collection order, pagination boundaries, or
 * incidental map/array iteration order — so the same GitHub snapshot always
 * regenerates the same digest (R5).
 *
 * Separate summary views (unique-lesson-eligible, aged-open, ambiguous,
 * incomplete, terminalized) are reported side by side so a growing backlog
 * cannot be hidden by only reporting a single merge-rate number.
 */

import type { EvidenceEnvelope, Persona } from "./types.ts";

/** Report schema version; bump whenever the report shape changes. */
export const REPORT_SCHEMA_VERSION = 1;

export interface OutcomeCounts {
  merged: number;
  closed_unmerged: number;
  open: number;
  ambiguous: number;
}

export interface PersonaSummary {
  persona: Persona;
  counts: OutcomeCounts;
  /** merged / (merged + closed_unmerged); null when the denominator is zero. */
  merge_rate: number | null;
  /** Distinct closure causes observed among closed_unmerged records, each with its count. */
  closure_causes: Record<string, number>;
  /** open records older than the caller-supplied aged-open threshold. */
  aged_open_count: number;
}

export interface CollectionReport {
  schema_version: number;
  repo: string;
  as_of: string;
  generated_at: string;
  /** False if any contributing collection run was incomplete; consumers must not treat this report as authoritative for watermark advancement. */
  complete: boolean;
  collection_errors: string[];
  personas: PersonaSummary[];
  /** Canonical envelopes retained for proposal-job session-link revalidation. */
  envelopes: EvidenceEnvelope[];
  total_envelope_count: number;
  /** Deterministic content digest over the full envelope set (sha256 hex). */
  digest: string;
}

export interface BuildReportOptions {
  repo: string;
  asOf: string;
  generatedAt: string;
  complete: boolean;
  collectionErrors: readonly string[];
  agedOpenThresholdMs?: number;
  /** Reference instant for "aged open" calculation; defaults to `Date.parse(asOf)`. */
  nowMs?: number;
}

const DEFAULT_AGED_OPEN_THRESHOLD_MS = 14 * 24 * 60 * 60 * 1000; // 14 days

function sha256Hex(input: string): string {
  const hasher = new Bun.CryptoHasher("sha256");
  hasher.update(input);
  return hasher.digest("hex");
}

/**
 * Canonical JSON serialization: object keys sorted, no incidental
 * whitespace, so semantically identical data always serializes to the same
 * string regardless of construction order.
 */
function canonicalJson(value: unknown): string {
  if (Array.isArray(value)) {
    return `[${value.map((item) => canonicalJson(item)).join(",")}]`;
  }
  if (value !== null && typeof value === "object") {
    const keys = Object.keys(value as Record<string, unknown>).sort();
    const entries = keys.map(
      (key) => `${JSON.stringify(key)}:${canonicalJson((value as Record<string, unknown>)[key])}`
    );
    return `{${entries.join(",")}}`;
  }
  return JSON.stringify(value);
}

function summarizePersona(
  persona: Persona,
  envelopes: readonly EvidenceEnvelope[],
  options: BuildReportOptions
): PersonaSummary {
  const nowMs = options.nowMs ?? Date.parse(options.asOf);
  const agedThresholdMs = options.agedOpenThresholdMs ?? DEFAULT_AGED_OPEN_THRESHOLD_MS;

  const counts: OutcomeCounts = { merged: 0, closed_unmerged: 0, open: 0, ambiguous: 0 };
  const closureCauses: Record<string, number> = {};
  let agedOpenCount = 0;

  for (const envelope of envelopes) {
    counts[envelope.outcome] += 1;
    if (envelope.outcome === "closed_unmerged" && envelope.closure_cause !== null) {
      closureCauses[envelope.closure_cause] = (closureCauses[envelope.closure_cause] ?? 0) + 1;
    }
    if (envelope.outcome === "open") {
      const collectedMs = Date.parse(envelope.collected_at);
      if (Number.isFinite(collectedMs) && nowMs - collectedMs >= agedThresholdMs) {
        agedOpenCount += 1;
      }
    }
  }

  const denominator = counts.merged + counts.closed_unmerged;
  const mergeRate = denominator > 0 ? counts.merged / denominator : null;

  return {
    persona,
    counts,
    merge_rate: mergeRate,
    closure_causes: closureCauses,
    aged_open_count: agedOpenCount,
  };
}

/**
 * Builds a deterministic `CollectionReport` from a set of classified
 * envelopes. The `digest` field is computed over a canonicalized,
 * PR-number-sorted view of the input envelopes plus the report's own
 * scoping fields (`repo`, `as_of`, `schema_version`) — never over
 * `generated_at`, which is inherently non-deterministic across runs.
 */
export function buildCollectionReport(
  envelopes: readonly EvidenceEnvelope[],
  options: BuildReportOptions
): CollectionReport {
  const byPersona = new Map<Persona, EvidenceEnvelope[]>();
  for (const envelope of envelopes) {
    const bucket = byPersona.get(envelope.persona);
    if (bucket) {
      bucket.push(envelope);
    } else {
      byPersona.set(envelope.persona, [envelope]);
    }
  }

  const personas = [...byPersona.keys()]
    .sort()
    .map((persona) => summarizePersona(persona, byPersona.get(persona)!, options));

  const sortedEnvelopes = [...envelopes].sort((a, b) => {
    if (a.persona !== b.persona) {
      return a.persona < b.persona ? -1 : 1;
    }
    return a.pr_number - b.pr_number;
  });

  const digestInput = canonicalJson({
    schema_version: REPORT_SCHEMA_VERSION,
    repo: options.repo,
    as_of: options.asOf,
    envelopes: sortedEnvelopes,
  });

  return {
    schema_version: REPORT_SCHEMA_VERSION,
    repo: options.repo,
    as_of: options.asOf,
    generated_at: options.generatedAt,
    complete: options.complete,
    collection_errors: [...options.collectionErrors],
    personas,
    envelopes: sortedEnvelopes,
    total_envelope_count: envelopes.length,
    digest: sha256Hex(digestInput),
  };
}

export { DEFAULT_AGED_OPEN_THRESHOLD_MS };
