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

import { describe, expect, test } from "bun:test";
import {
  deduplicateCandidate,
  parseMemoryEntryMarkers,
  type DeduplicationInputs,
  type ProposalMarkerLike,
} from "./deduplicate.ts";

const FINGERPRINT = "a".repeat(64);
const OTHER_FINGERPRINT = "b".repeat(64);
const ENTRY_ID = FINGERPRINT.slice(0, 12);

function marker(entryId: string, fingerprint: string): string {
  return `<!-- entry_id: ${entryId} | fingerprint: ${fingerprint} -->`;
}

function baseInputs(overrides: Partial<DeduplicationInputs> = {}): DeduplicationInputs {
  return {
    candidateFingerprint: FINGERPRINT,
    entryId: ENTRY_ID,
    targetMemoryPath: ".jules/bolt.md",
    memoryContent: "",
    memoryHistory: [],
    openProposalMarkers: [],
    closedProposalMarkers: [],
    ...overrides,
  };
}

describe("parseMemoryEntryMarkers", () => {
  test("extracts entry_id/fingerprint pairs from rendered memory content", () => {
    const content = `## Some heading\n\nBody text.\n${marker("abc123", FINGERPRINT)}\n`;
    const markers = parseMemoryEntryMarkers(content);
    expect(markers).toEqual([{ entry_id: "abc123", candidate_fingerprint: FINGERPRINT }]);
  });

  test("extracts multiple markers in document order", () => {
    const content = `${marker("id-1", FINGERPRINT)}\n\n${marker("id-2", OTHER_FINGERPRINT)}`;
    const markers = parseMemoryEntryMarkers(content);
    expect(markers.map((m) => m.entry_id)).toEqual(["id-1", "id-2"]);
  });

  test("lowercases the fingerprint for comparison stability", () => {
    const content = marker("id-1", FINGERPRINT.toUpperCase());
    const markers = parseMemoryEntryMarkers(content);
    expect(markers[0]!.candidate_fingerprint).toBe(FINGERPRINT);
  });

  test("ignores content with no markers", () => {
    expect(parseMemoryEntryMarkers("no markers here at all")).toEqual([]);
  });

  test("ignores malformed comments that do not match the fixed marker shape", () => {
    const content = "<!-- entry_id: only-entry-id -->";
    expect(parseMemoryEntryMarkers(content)).toEqual([]);
  });
});

describe("deduplicateCandidate", () => {
  test("a candidate with no matching content anywhere is novel", () => {
    const result = deduplicateCandidate(baseInputs());
    expect(result.status).toBe("novel");
    expect(result.novel).toBe(true);
  });

  test("an exact fingerprint match in current memory content is a duplicate, not novel", () => {
    const inputs = baseInputs({ memoryContent: marker(ENTRY_ID, FINGERPRINT) });
    const result = deduplicateCandidate(inputs);
    expect(result.status).toBe("duplicate_current_memory");
    expect(result.novel).toBe(false);
  });

  test("same entry_id but a different fingerprint in current memory is quarantined as a contradiction", () => {
    const inputs = baseInputs({ memoryContent: marker(ENTRY_ID, OTHER_FINGERPRINT) });
    const result = deduplicateCandidate(inputs);
    expect(result.status).toBe("contradiction_quarantined");
    expect(result.novel).toBe(false);
  });

  test("an exact fingerprint match in memory history (but not current content) is a duplicate", () => {
    const inputs = baseInputs({ memoryHistory: [marker(ENTRY_ID, FINGERPRINT)] });
    const result = deduplicateCandidate(inputs);
    expect(result.status).toBe("duplicate_memory_history");
    expect(result.novel).toBe(false);
  });

  test("same entry_id with a different fingerprint in memory history is quarantined, not auto-retracted", () => {
    const inputs = baseInputs({ memoryHistory: [marker(ENTRY_ID, OTHER_FINGERPRINT)] });
    const result = deduplicateCandidate(inputs);
    expect(result.status).toBe("contradiction_quarantined");
  });

  test("an open proposal marker for the same fingerprint and target file is a duplicate", () => {
    const openMarkers: ProposalMarkerLike[] = [
      { candidate_fingerprint: FINGERPRINT, target_memory_path: ".jules/bolt.md" },
    ];
    const result = deduplicateCandidate(baseInputs({ openProposalMarkers: openMarkers }));
    expect(result.status).toBe("duplicate_open_proposal");
    expect(result.novel).toBe(false);
  });

  test("an open proposal marker for a different target file does not suppress a novel candidate", () => {
    const openMarkers: ProposalMarkerLike[] = [
      { candidate_fingerprint: FINGERPRINT, target_memory_path: ".jules/sentinel.md" },
    ];
    const result = deduplicateCandidate(baseInputs({ openProposalMarkers: openMarkers }));
    expect(result.status).toBe("novel");
  });

  test("a previously closed (rejected) proposal marker for the same fingerprint suppresses a new proposal", () => {
    const closedMarkers: ProposalMarkerLike[] = [
      { candidate_fingerprint: FINGERPRINT, target_memory_path: ".jules/bolt.md" },
    ];
    const result = deduplicateCandidate(baseInputs({ closedProposalMarkers: closedMarkers }));
    expect(result.status).toBe("duplicate_closed_proposal");
    expect(result.novel).toBe(false);
  });

  test("an unrelated fingerprint in every source does not suppress a genuinely novel candidate", () => {
    const inputs = baseInputs({
      memoryContent: marker("other-entry", OTHER_FINGERPRINT),
      memoryHistory: [marker("other-entry-2", OTHER_FINGERPRINT)],
      openProposalMarkers: [{ candidate_fingerprint: OTHER_FINGERPRINT, target_memory_path: ".jules/bolt.md" }],
      closedProposalMarkers: [{ candidate_fingerprint: OTHER_FINGERPRINT, target_memory_path: ".jules/bolt.md" }],
    });
    const result = deduplicateCandidate(inputs);
    expect(result.status).toBe("novel");
  });

  test("current memory content is checked before memory history (current-memory duplicate wins)", () => {
    const inputs = baseInputs({
      memoryContent: marker(ENTRY_ID, FINGERPRINT),
      memoryHistory: [marker("unrelated", OTHER_FINGERPRINT)],
    });
    const result = deduplicateCandidate(inputs);
    expect(result.status).toBe("duplicate_current_memory");
  });

  test("candidate fingerprint comparison is case-insensitive", () => {
    const inputs = baseInputs({
      candidateFingerprint: FINGERPRINT.toUpperCase(),
      memoryContent: marker(ENTRY_ID, FINGERPRINT),
    });
    const result = deduplicateCandidate(inputs);
    expect(result.status).toBe("duplicate_current_memory");
  });

  test("reason is always populated and never empty", () => {
    const result = deduplicateCandidate(baseInputs());
    expect(result.reason.length).toBeGreaterThan(0);
  });
});
