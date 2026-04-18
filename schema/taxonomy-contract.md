# Knowledge Taxonomy Contract

This document is the authoritative taxonomy contract for `wiki/**`. It defines
namespace placement, browse-path semantics, category discipline, and tag rules
for knowledge artifacts. It complements [`page-template.md`](page-template.md),
[`ontology-entity-contract.md`](ontology-entity-contract.md), and
[`metadata-schema-contract.md`](metadata-schema-contract.md).

## Scope and authority

- Applies to all curated wiki pages and reserved process pages.
- Fails closed when a write-capable workflow cannot determine the correct
  namespace or category placement.
- Keeps structural classification deterministic: namespace comes from page role,
  not from ad hoc author preference.

## Namespace contract

| Namespace | Primary page type | Include when | Exclude when |
|---|---|---|---|
| `wiki/sources/` | `source` | The page is a durable summary or registration record for a specific authoritative source artifact under `raw/processed/**` or checksummed `raw/assets/**`. | The page is mainly a synthesis, reusable analysis, entity profile, or concept explainer. |
| `wiki/entities/` | `entity` | The subject has a stable identity across sources (person, organization, program, benefit, statute, product, named document, or other durable referent). | The subject is only an alias, a transient event, a one-off query result, or an abstract topic without a single durable referent. |
| `wiki/concepts/` | `concept` | The page explains an abstract topic, rule, workflow, policy theme, or recurring idea that can apply to multiple entities or sources. | The content is primarily about one named referent, one source artifact, or one persisted query result. |
| `wiki/analyses/` | `analysis` | The page is a policy-gated synthesis answering a scoped question or preserving a reusable comparison derived from multiple sources/pages. | The content should instead be normalized into evergreen entity/concept pages or is only a raw-source registration record. |
| `wiki/index.md`, `wiki/log.md`, `wiki/open-questions.md`, `wiki/backlog.md`, `wiki/status.md` | `process` | The page is a reserved operational artifact for deterministic discovery, append-only audit state, or governed maintenance ledgers/snapshots. | The page carries topical knowledge that belongs in `sources/`, `entities/`, `concepts/`, or `analyses/`. |

### Namespace rules

1. Namespace and frontmatter `type` must agree.
2. Topical namespaces are flat in MVP: use `wiki/<namespace>/<slug>.md`, not
   nested subdirectories, until a later ADR explicitly permits deeper trees.
3. A page belongs to exactly one topical namespace at a time.
4. Process pages are excluded from topical browse trees.

## Slug, browse-path, and category rules

### Slugs

- Use lowercase kebab-case file names.
- Make the slug stable and descriptive, not time-boxed or workflow-specific.
- Do not create a second slug for the same canonical subject; aliases belong in
  alias handling, not as parallel canonical pages.

### Browse path

`browse_path` is the ordered human navigation breadcrumb for a page. In MVP it
is optional; if omitted, the namespace alone is the minimum browse path.

- When present, encode `browse_path` as an ordered list of normalized segments.
- Exclude the namespace and final page title from `browse_path`; those are
  implied by file placement and the page itself.
- Use 1-3 segments and choose the most specific durable path that helps a human
  browse related pages together.
- Do not use aliases, timestamps, confidence labels, editorial status, or
  source-format details as browse-path segments.

### Category inclusion and exclusion

The first `browse_path` segment is the page's primary category.

Include a category when it is:

- durable across multiple updates,
- specific enough to improve retrieval,
- and likely to group at least two sibling pages now or in near-term growth.

Exclude a category when it is:

- just a restatement of namespace or title,
- only an alias or shorthand,
- ephemeral workflow state,
- or so broad that it hides more specific structure.

## Tag rules

Tags remain required frontmatter and act as secondary retrieval cues, not as a
replacement for namespace or canonical identity.

- Use normalized lowercase kebab-case tags.
- Prefer 2-6 tags for topical pages and 1-3 for operational/source pages.
- Include stable descriptors that improve discovery but are not already obvious
  from namespace, browse path, or canonical title.
- Avoid exact duplicates, aliases, timestamps, confidence labels, sensitivity
  levels, and freeform workflow chatter.
- A structural tag such as `source` or `catalog` is allowed when it improves
  retrieval, but tags should otherwise add information instead of repeating
  existing structure.

## Validation policy

### Deterministic MVP blocking

- Nested topical paths under `wiki/sources/`, `wiki/entities/`,
  `wiki/concepts/`, or `wiki/analyses/` are rejected. MVP topology stays flat
  until a later ADR explicitly permits deeper trees.

### Advisory in MVP

The following taxonomy checks still matter, but they are not enforced by the
deterministic lint/index gates in MVP. They remain review-time or
policy-time guidance until a later contract explicitly promotes them:

- Namespace cannot be determined unambiguously.
- Frontmatter `type` conflicts with namespace role.
- The slug is malformed or duplicates an existing canonical page for the same
  subject.
- A `browse_path` segment is transient, alias-only, or contradictory to page
  placement.
- Tags are empty, duplicate, or clearly unsafe to index.

- A page could be moved to a more specific category.
- `browse_path` is omitted where discoverability would materially benefit.
- Tags are technically valid but too broad, redundant, or sparse.
- A proposed new category looks plausible but should be ratified after more
  pages land.
