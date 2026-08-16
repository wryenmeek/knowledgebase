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
  computeCandidateFingerprint,
  computeCandidateFingerprintAtCurrentVersion,
  computeEvidenceDigest,
  isValidSha256Hex,
  normalizeScopeList,
  normalizeText,
} from "./fingerprints.ts";
import { CANONICALIZATION_VERSION, TAXONOMY_VERSION, type CandidateFingerprintComponents } from "./types.ts";

function baseComponents(
  overrides: Partial<CandidateFingerprintComponents> = {}
): CandidateFingerprintComponents {
  return {
    persona: "bolt",
    mechanism: "eager Path.resolve() in hot loop",
    affectedScope: ["scripts/kb/lint_wiki.py", "scripts/kb/update_index.py"],
    normalizedRule: "avoid eager resolve() calls in hot loops",
    taxonomyVersion: TAXONOMY_VERSION,
    canonicalizationVersion: CANONICALIZATION_VERSION,
    targetMemoryPath: ".jules/bolt.md",
    ...overrides,
  };
}

describe("normalizeText", () => {
  test("trims, collapses interior whitespace, and lowercases", () => {
    expect(normalizeText("  Avoid   eager\n\tresolve() calls  ")).toBe(
      "avoid eager resolve() calls"
    );
  });

  test("NFC-normalizes unicode before comparison", () => {
    const decomposed = "cafe\u0301"; // "café" using combining acute accent
    const precomposed = "café";
    expect(normalizeText(decomposed)).toBe(normalizeText(precomposed));
  });

  test("does not mutate case of the caller's original string reference", () => {
    const original = "Avoid Eager Resolve";
    normalizeText(original);
    expect(original).toBe("Avoid Eager Resolve");
  });
});

describe("normalizeScopeList", () => {
  test("sorts lexicographically regardless of input order", () => {
    expect(normalizeScopeList(["b/path.py", "a/path.py"])).toBe(
      normalizeScopeList(["a/path.py", "b/path.py"])
    );
  });

  test("drops empty entries after normalization", () => {
    expect(normalizeScopeList(["a.py", "   ", ""])).toBe("a.py");
  });

  test("joins with a comma separator", () => {
    expect(normalizeScopeList(["a.py", "b.py"])).toBe("a.py,b.py");
  });
});

describe("computeCandidateFingerprint", () => {
  test("is deterministic for identical input", () => {
    const a = computeCandidateFingerprint(baseComponents());
    const b = computeCandidateFingerprint(baseComponents());
    expect(a).toBe(b);
    expect(isValidSha256Hex(a)).toBe(true);
  });

  test("equivalent whitespace/order normalization yields one fingerprint", () => {
    const a = computeCandidateFingerprint(baseComponents());
    const b = computeCandidateFingerprint(
      baseComponents({
        mechanism: "  eager   Path.resolve()\nin hot loop  ",
        affectedScope: ["scripts/kb/update_index.py", "scripts/kb/lint_wiki.py"],
        normalizedRule: "Avoid Eager Resolve() Calls In Hot Loops",
      })
    );
    expect(a).toBe(b);
  });

  test("changed taxonomy version yields a distinct fingerprint", () => {
    const a = computeCandidateFingerprint(baseComponents({ taxonomyVersion: 1 }));
    const b = computeCandidateFingerprint(baseComponents({ taxonomyVersion: 2 }));
    expect(a).not.toBe(b);
  });

  test("changed canonicalization version yields a distinct fingerprint", () => {
    const a = computeCandidateFingerprint(baseComponents({ canonicalizationVersion: 1 }));
    const b = computeCandidateFingerprint(baseComponents({ canonicalizationVersion: 2 }));
    expect(a).not.toBe(b);
  });

  test("different persona yields a distinct fingerprint", () => {
    const bolt = computeCandidateFingerprint(baseComponents({ persona: "bolt" }));
    const sentinel = computeCandidateFingerprint(
      baseComponents({ persona: "sentinel", targetMemoryPath: ".jules/sentinel.md" })
    );
    expect(bolt).not.toBe(sentinel);
  });

  test("different target memory path yields a distinct fingerprint even for identical rule text", () => {
    const bolt = computeCandidateFingerprint(baseComponents({ targetMemoryPath: ".jules/bolt.md" }));
    const sentinel = computeCandidateFingerprint(
      baseComponents({ targetMemoryPath: ".jules/sentinel.md" })
    );
    expect(bolt).not.toBe(sentinel);
  });

  test("computeCandidateFingerprintAtCurrentVersion fills in the current canonicalization version", () => {
    const { canonicalizationVersion: _drop, ...withoutVersion } = baseComponents();
    const viaHelper = computeCandidateFingerprintAtCurrentVersion(withoutVersion);
    const viaDirect = computeCandidateFingerprint(baseComponents());
    expect(viaHelper).toBe(viaDirect);
  });
});

describe("computeEvidenceDigest", () => {
  test("is deterministic and order-independent", () => {
    const a = computeEvidenceDigest(["repo:owner/repo", "pr:123", "sha:abc123"]);
    const b = computeEvidenceDigest(["sha:abc123", "repo:owner/repo", "pr:123"]);
    expect(a).toBe(b);
    expect(isValidSha256Hex(a)).toBe(true);
  });

  test("differs when underlying evidence differs", () => {
    const a = computeEvidenceDigest(["pr:123"]);
    const b = computeEvidenceDigest(["pr:456"]);
    expect(a).not.toBe(b);
  });
});

describe("isValidSha256Hex", () => {
  test("accepts a 64-char lowercase hex string", () => {
    expect(isValidSha256Hex("a".repeat(64))).toBe(true);
  });

  test("rejects wrong length, uppercase, or non-hex input", () => {
    expect(isValidSha256Hex("a".repeat(63))).toBe(false);
    expect(isValidSha256Hex("A".repeat(64))).toBe(false);
    expect(isValidSha256Hex("z".repeat(64))).toBe(false);
    expect(isValidSha256Hex("")).toBe(false);
  });
});
