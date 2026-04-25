"""Advisory freshness classification for wiki pages.

Reads the JSON freshness report produced by ``check_doc_freshness.py`` and
classifies each stale page as either **afk-candidate** (age < threshold) or
**hitl** (age ≥ threshold or missing data).

"afk-candidate" (not "afk") because age alone is insufficient to confirm AFK
eligibility per ADR-014 §4; a downstream step must verify no open questions,
patrol findings, or source staleness before the classification becomes
operative.

This module is a lightweight advisory surface under ``scripts/validation/``
(read-only only in the AGENTS.md write-surface matrix).  The ``--output``
artifact is a transient CI artifact, not a governed repository write.
"""
from __future__ import annotations

import argparse
import json
import sys

SURFACE = "validation.classify_stale"

DEFAULT_AFK_THRESHOLD_DAYS = 180
DEFAULT_MISSING_DATA_DAYS = 999  # missing data → HITL (deny-by-default)


def classify_stale_pages(
    freshness_report_path: str,
    output_path: str,
    afk_threshold_days: int = DEFAULT_AFK_THRESHOLD_DAYS,
) -> dict:
    """Classify stale pages and write routing JSON.

    Returns a summary dict with ``total``, ``afk_candidate``, and ``hitl``
    counts.
    """
    with open(freshness_report_path) as f:
        report = json.load(f)

    files = report.get("files", [])
    classified: list[dict] = []

    for entry in files:
        path = entry.get("path", "")
        days = entry.get("days_stale", DEFAULT_MISSING_DATA_DAYS)
        classification = "afk-candidate" if days < afk_threshold_days else "hitl"
        action = (
            "verify AFK eligibility then update freshness_date metadata"
            if classification == "afk-candidate"
            else "review content for accuracy and re-source if needed"
        )
        classified.append(
            {
                "path": path,
                "last_updated": entry.get("last_updated", ""),
                "days_stale": days,
                "classification": classification,
                "recommended_action": action,
            }
        )

    afk_count = sum(1 for p in classified if p["classification"] == "afk-candidate")
    hitl_count = len(classified) - afk_count

    with open(output_path, "w") as f:
        json.dump({"stale_pages": classified}, f, indent=2)

    summary = {"total": len(classified), "afk_candidate": afk_count, "hitl": hitl_count}
    print(
        f"Classified {summary['total']} stale pages: "
        f"{afk_count} AFK-candidate, {hitl_count} HITL"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Classify stale wiki pages for freshness routing.",
    )
    parser.add_argument(
        "--freshness-report",
        required=True,
        help="Path to the wiki-freshness JSON report.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path to write the freshness-routing JSON.",
    )
    parser.add_argument(
        "--afk-threshold-days",
        type=int,
        default=DEFAULT_AFK_THRESHOLD_DAYS,
        help=f"Days-stale threshold below which a page is classified as afk-candidate (default: {DEFAULT_AFK_THRESHOLD_DAYS}).",
    )
    args = parser.parse_args()
    classify_stale_pages(args.freshness_report, args.output, args.afk_threshold_days)


if __name__ == "__main__":
    main()
