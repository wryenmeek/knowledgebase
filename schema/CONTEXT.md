---
scope: directory
last_updated: 2026-04-29
---

# CONTEXT — schema/

Vocabulary for the schema and contract layer. `AGENTS.md` takes precedence on any conflict.

## Terms

| Term | Definition |
|------|------------|
| page-template | `schema/page-template.md` — the canonical contract for wiki page structure: required frontmatter fields, section headings, and YAML types. All wiki pages must conform. |
| metadata-schema-contract | `schema/metadata-schema-contract.md` — governs optional and required metadata fields beyond the page template, including quality assessment fields. |
| governed-artifact-contract | `schema/governed-artifact-contract.md` — defines the contract schema for governed state artifacts (log, index, status, backlog, open-questions). |
| drift-report-contract | `schema/drift-report-contract.md` — defines the JSON schema for drift reports produced by `check_drift.py` and consumed by `classify_drift.py`. |
| ingest-checklist | `schema/ingest-checklist.md` — the ordered checklist of prerequisites that must be satisfied before any source intake proceeds. Includes rejection-registry check as Step 0. |
| taxonomy-contract | `schema/taxonomy-contract.md` — defines allowed namespaces (`sources`, `entities`, `concepts`, `analyses`), browse paths, and tag normalization rules. |
| ontology-entity-contract | `schema/ontology-entity-contract.md` — governs entity identity, alias rules, canonical naming, and merge/split decisions. |
| SourceRef | Canonical citation format used throughout schema documentation: `repo://<owner>/<repo>/<path>@<git_sha>#<anchor>?sha256=<64-hex>`. |
| report-artifact-contract | `schema/report-artifact-contract.md` — defines the JSON schema for wiki report artifacts (quality scores, content quality reports). |
| github-source-registry-contract | `schema/github-source-registry-contract.md` — defines the JSON schema for `*.source-registry.json` files in `raw/github-sources/`. |
| drive-source-registry-contract | `schema/drive-source-registry-contract.md` — defines the JSON schema for `*.source-registry.json` files in `raw/drive-sources/`. |
| rejection-registry-contract | `schema/rejection-registry-contract.md` — defines the contract for write-once rejection records in `raw/rejected/`. Governs `log-intake-rejection` skill. |

## Invariants

| Invariant | Description |
|-----------|-------------|
| Schema read-only for automation | No automation surface may write to `schema/`. Schema changes go through the ADR process and human review. |
| Schema changes require ADR | Any change to a schema contract that affects existing automation behavior (new required field, changed enum) must be accompanied by an ADR. |
| Contracts reference each other by filename | When one schema document references another, it uses the relative filename path (not a full repo:// SourceRef) since schema files are part of the repo's read-only documentation. |

## File Roles

| File | Role |
|------|------|
| `page-template.md` | Wiki page frontmatter and section contract. Primary reference for all wiki writes. |
| `metadata-schema-contract.md` | Optional and extended metadata fields for wiki pages. |
| `governed-artifact-contract.md` | Contract schema for governed state artifacts (log, index, etc.). |
| `taxonomy-contract.md` | Namespace, browse path, and tag rules. |
| `ontology-entity-contract.md` | Entity identity, alias, and canonicalization rules. |
| `ingest-checklist.md` | Ordered intake prerequisites checklist. |
| `drift-report-contract.md` | JSON schema for drift reports. |
| `report-artifact-contract.md` | JSON schema for quality report artifacts. |
| `github-source-registry-contract.md` | JSON schema for GitHub source registry files. |
| `drive-source-registry-contract.md` | JSON schema for Drive source registry files. |
| `rejection-registry-contract.md` | Contract for write-once rejection records (ADR-013). |
