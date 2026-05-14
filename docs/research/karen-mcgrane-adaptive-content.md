# Karen McGrane's Adaptive Content: Ideas for the Knowledgebase Project

**Research date:** 2026-05-14  
**Primary source:** Karen McGrane, "Adapting Ourselves to Adaptive Content" (talk, 2012) + companion articles  
**Scope:** What adaptive content principles would be most valuable for `wryenmeek/knowledgebase`?

---

## Executive Summary

Karen McGrane is the most influential voice on structured, channel-agnostic content strategy for the web era. Her 2012 talk and surrounding body of work (2012–2024) converges on a single architectural thesis: **content must be separated from its presentation, stored as typed semantic components with rich metadata, and designed for reuse across unknown future platforms.** This is the "adaptive content" framework. Her canonical case study is NPR's COPE model (Create Once, Publish Everywhere), in which a single structured content API serves dozens of platforms — directly analogous to the challenge this knowledgebase faces as it expands from Markdown wiki to AI query target, Slack bot source, docs generator input, and future interfaces.

The `wryenmeek/knowledgebase` project already implements several of McGrane's core prescriptions at a sophisticated level: typed `type:` frontmatter enum, required `sources` SourceRef provenance, `confidence` evidence scoring, `open_questions` uncertainty tracking, and a schema-enforced body structure (`## Summary / ## Evidence / ## Open Questions`). What it has not yet done is *use* most of that metadata in the reader or API experience, populate the entity/analysis namespaces that would create the knowledge graph, or formalize content-length variants that enable richer downstream consumption. The highest-value opportunities, in priority order, are: (1) adding TV-Guide-style content-length variants to the page schema, (2) making `confidence` and `open_questions` visible in the reader experience, (3) populating entities and activating the relationship graph, (4) enforcing tag quality, and (5) planning for an API/query export layer.

---

## Part 1: Karen McGrane's Adaptive Content Framework

### 1.1 The Core Argument (2012 Talk)

McGrane's foundational talk — delivered at Breaking Development Conference in April 2012 and at the same-named format in September 2012 — opens with a structural critique of how organizations manage content: they build for one platform (print, desktop web), then manually "shovel" content onto other platforms when demand arises. This produces the Condé Nast outcome: enormous labor, tiny audience.[^1]

The alternative is NPR's **COPE model** — Create Once, Publish Everywhere.[^2] NPR built a content API that stores every story as a set of discrete fields (title, short title, teaser, short teaser, body text, images, audio, metadata). Each platform — the website, iPhone app, Android app, public radio player, member station sites, iTunes — queries that API and selects the fields appropriate to its context. The result: 80% page-view growth directly attributed to having the API.[^3]

**The TV Guide precedent** is McGrane's most transferable historical example.[^4] In the 1980s, TV Guide instructed writers to create *three versions* of every programme description — short, medium, long — using a green-screen mainframe. They didn't know those descriptions would later appear in cable TV guides, TiVo, iPhone apps. They just knew flexible content had more value. When the magazine brand sold, it sold for $1. All the value was in the content/data.

**The "blobs vs. chunks" war** is her sharpest formulation of the CMS problem:

> *"We are in a war of Blobs versus Chunks. We are in a war between giant, unstructured blobs of content, and clean, well-structured fields of content that have metadata attached. You all are on Team Chunk. We cannot let the blobs win."*[^5]

Blobs = WYSIWYG editors, giant unstructured text fields, content that can only live in one context. Chunks = typed fields, multiple length variants, metadata-tagged content objects.

**Metadata as art direction** is the paradigm shift she asks content practitioners to make.[^6] Traditionally, art directors decide how a piece of content looks in each context — what's prominent, what's truncated, what's omitted. With structured content, *metadata and business rules replace manual art direction*: "If the content has a label, the platform can decide how to use it." A `confidence` score on a wiki page is art direction for how cautiously it should be presented. A `sensitivity: public` flag is art direction for who sees it.

**The three-way separation** is her prescription for fixing the CMS:[^7]

> *"Content authoring is not the same thing as content management and content management is not the same thing as content publishing. Right now, most of the tools that we have force us to think about all three of these together."*

Future CMSes must allow these to be broken apart. Until then, organizations are just recycling content from one context to another, not actually designing for reuse.

### 1.2 The Five Adaptive Content Steps (ALA: "Future-Ready Content")

In her companion A List Apart article, McGrane operationalizes adaptive content into five design steps for any content type[^8]:

| Step | Instruction | What It Means |
|---|---|---|
| **Get purposeful** | Define each content type's goal | Know *why* this type exists before modeling it |
| **Get micro** | Decompose into smallest meaningful elements | Title, teaser, image, ingredients, rating — not a blob |
| **Get meaningful** | Understand what's lost when an element is removed | Which fields are semantically load-bearing? |
| **Get organized** | CMS structure must reflect the model | Authoring interface = schema enforcement |
| **Get structured** | Use semantic markup to encode meaning | `<em>` not `<i>`; meaning not appearance |

The Epicurious recipe is her canonical decomposition example: a recipe is not a page — it's a title, author, prep time, cook time, servings, ingredient list (each item typed), instructions (each step typed), images, tags (cuisine, dietary restrictions, season), and rating. Each field has a distinct purpose and can be independently displayed or omitted per platform.

### 1.3 The WYSIWYG Problem (ALA: "WYSIWTF", 2013)

McGrane identifies three specific CMS tools that undermine structured content[^9]:

1. **The Preview button** — "The preview button is a lie." A desktop preview implies one canonical rendering. In reality, content renders differently on every device. Preview should show content *across multiple contexts*, not one.
2. **The WYSIWYG editor** — Embedding visual formatting into content "can be at odds with the style sheet, and it's difficult for developers to parse what's style and what's substance. When it comes time to put that content on other platforms, we wind up with a muddled mess."
3. **Inline editing** — "Inline editing encourages content creators to focus on the visual presentation of the desktop interface. Just at the moment when we need content creators to think about the underlying structure, we're investing in tools that obscure the 'connective tissue.'"

Her recommended replacement: authoring interfaces that force semantic tagging of *what content is*, not *what it looks like*.

### 1.4 Cross-Device Content Parity (ALA: "Windows on the Web", 2013)

90% of people start a task on one device and complete it on another (Google research). Users treat devices as "windows on content" — not separate containers with different content.[^10] McGrane's five practical corollaries:

1. **Content parity** — same content available on all devices
2. **Consistent navigation labels** — same IA/taxonomy across devices
3. **Consistent search** — same search results regardless of device
4. **Persistent URLs** — bookmarkable, shareable, transferable
5. **Better analytics** — track cross-device behavior

### 1.5 The Self-Critique: Structured ≠ Targeted (2017 Talk)

In her 2017 "Adaptive Content: Context and Controversy" talk, McGrane issues an important correction to her own popularized framing[^11]:

> *"I popularised the term 'adaptive content'... and as I have seen, you put your ideas out there in the world and then you see what people do with them, and I start to have some concerns about where we are taking this."*

Her concern: people conflate *having structured content* with *targeting different content to different users/devices*. She distinguishes:

- **Structured/granular content** — breaking content into typed components with metadata → **always good, do this first**
- **Targeted/contextual content** — serving different content based on device characteristics, location, time → **complicated, use only in narrow justified cases**

Her enduring core argument (unchanged): "I will argue until the end of my days about the value of storing content in more granular ways... having that content be semantically rich, stored in more granular ways, stored in presentation-independent ways, allows us to do more with that content."

NPR's own evolution is instructive: they eventually *removed* device-specific targeting and went fully responsive, because maintaining phone/tablet/desktop versions was unsustainable. The lasting value of their COPE investment was the **structured content model**, not the device-targeting aspect.

### 1.6 The Disruption Framing (2013–2014)

McGrane applies Clayton Christensen's disruptive innovation theory to content systems.[^12] DEC (Digital Equipment Corporation) was the world's second-largest computer manufacturer in 1988; by 1998 it was gone. Its CEO famously said "There is no reason why anyone would need a computer in their home." The disruptors (PCs) were cheaper, worse at most things, but better at reach/accessibility.

Mobile, AI query interfaces, and voice systems are doing the same to desktop-first content. Organizations whose content is locked in PDFs, InDesign files, WYSIWYG blobs, or giant wiki pages will fail to adapt to chatbot interfaces, voice assistants, and API consumers — because the content cannot be extracted cleanly.

> *"Mobile is a wedge; it's a catalyst within an organization. It's going to be the thing that makes people wake up and go, 'Oh crap! There's no way we're going to be able to support getting our content out on all of these different platforms unless we start planning ahead.'"*[^13]

Substitute "AI query interfaces" for "mobile" and the argument is more urgent in 2026 than it was in 2013.

---

## Part 2: Companion Frameworks

### 2.1 Ann Rockley's Intelligent Content

Ann Rockley (founder of the Intelligent Content Conference) developed the enterprise-side equivalent of McGrane's framework, drawing on DITA (Darwin Information Typing Architecture) and XML publishing.[^14] Her five characteristics of intelligent content:

| Characteristic | What it means |
|---|---|
| **Structurally rich** | Broken into typed, granular components (not blobs) with explicit structure |
| **Semantically categorized** | Metadata labels *what* content means, not just *where* it lives |
| **Discoverable** | Machine and human retrieval enabled by the semantic layer |
| **Reusable** | Components can appear in multiple contexts without copy-pasting |
| **Reconfigurable** | Presentation assembled dynamically from components at publish time |

Rockley's DITA typed topics — `concept`, `task`, `reference` — predate McGrane's work and provide a field-validated content-type taxonomy that maps directly to knowledge base design.

### 2.2 The Diátaxis Framework

Diátaxis (diataxis.fr) is a modern, practical content type system proven at Cloudflare, Gatsby, and hundreds of documentation projects.[^15] It defines four functionally distinct content types based on user mode:

| Content Type | User Mode | Orientation | DITA Equivalent |
|---|---|---|---|
| **Tutorial** | Learning | Experience-based | `learning` topic |
| **How-to guide** | Working | Goal/problem-solving | `task` topic |
| **Reference** | Working | Information/consulting | `reference` topic |
| **Explanation** | Studying | Understanding/discussion | `concept` topic |

Diátaxis's key architectural insight: **conflating these types in a single page is the most common KB structural failure** — a tutorial mixed with reference material serves neither user mode well.

### 2.3 COPE at Scale: Contentful's Content Model

Karen McGrane now works as Senior Director of Customer Insights & Adoption at Contentful[^16] — the company that operationalized COPE into a product. Contentful's data model implements COPE directly: content types with up to 50 typed fields (Symbol/short text, Text/long text, RichText, Date, Boolean, Link/reference, Array), delivered via CDN REST/GraphQL API to any frontend.[^17] The field type taxonomy is instructive — it enforces the chunk-not-blob principle at the platform level.

---

## Part 3: Current State of the Knowledgebase

Before mapping opportunities, the key points about the current project state:

**Strengths (already aligned with adaptive content principles):**

| Principle | Current Implementation |
|---|---|
| Typed content | `type:` enum (`entity`, `concept`, `source`, `analysis`, `process`) |
| Separation of content from presentation | `raw/` pipeline → `wiki/` publish layer |
| Semantic metadata | 9 required frontmatter fields, schema-enforced |
| Evidence quality scoring | `confidence: 1..5` on every page |
| Explicit uncertainty | `open_questions` array on every page |
| Source provenance | `sources` SourceRef list (commit-pinned, checksum-verified) |
| Lifecycle management | `status: active/superseded/archived` |
| Access control | `sensitivity: public/internal/restricted` |
| Controlled vocabulary | Relationship types in `schema/ontology-entity-contract.md` |

**Current content state (as of 2026-05-14):**

| Namespace | Population |
|---|---|
| `wiki/sources/` | 8 pages |
| `wiki/concepts/` | 6 pages (all confidence 5, except wiki-quality-best-practices at 3) |
| `wiki/entities/` | **0 pages** (`.gitkeep` only) |
| `wiki/analyses/` | **0 pages** (`.gitkeep` only) |

The framework is mature; the content layer is early. This is precisely the moment to apply adaptive content principles before content scales — fixing the structural model after hundreds of pages exist is much harder.[^18]

---

## Part 4: High-Value Opportunities

### Opportunity 1: Multiple Content Lengths (TV Guide Model)

**McGrane's principle:** "Create multiple sizes of your content — write it with multiple lengths in mind."[^4]

**Current gap:** Every wiki page has a single `## Summary` section as its short-form representation. There is no `teaser` (2-3 sentence abstract) or `short_title` field. When the KB is queried by a chatbot or search index, only one length is available.

**Specific recommendation:** Add two optional advisory fields to the page schema[^19]:

```yaml
# Optional multi-length fields (TV Guide pattern)
teaser: "<2-3 sentence abstract for tooltips, search snippets, chatbot answers>"
short_title: "<abbreviated form for navigation labels, breadcrumbs>"
```

This directly maps to NPR's COPE fields (`teaser`, `short teaser`) and enables any downstream consumer to render an appropriate length. The existing `## Summary` section serves as the "medium" length; body text is "long." A `teaser` field fills the critical "short" slot.

**Why now:** `qmd` already indexes wiki pages for vector search. When a user asks a question, the query result currently surfaces a full page link. A `teaser` field would enable richer answer previews without changing the governance model — it's purely additive metadata.

**Schema evolution:** Additive, advisory, optional. No blocking validator change required. Aligns with schema evolution rule #1: "new fields start optional and advisory."[^20]

---

### Opportunity 2: Confidence Tiers in Reader UX ("Metadata as Art Direction")

**McGrane's principle:** "Metadata is the new art direction."[^6]

**Current gap:** Every page carries a `confidence: 1..5` integer. The `wiki/concepts/wiki-quality-best-practices.md` page explicitly has `confidence: 3` because its external citations are unverifiable.[^21] But this field is invisible to readers — both high-confidence and low-confidence pages render identically.

**Specific recommendation:** Surface confidence tiers visually in the rendered wiki (MkDocs):

- `confidence: 5` → no admonition (clean, authoritative)
- `confidence: 3-4` → `> **ℹ Note:** This page contains some unverified claims. See Open Questions.` (blue info admonition)
- `confidence: 1-2` → `> **⚠ Caution:** Evidence for this page is weak or unverified. Use with care.` (yellow warning admonition)

**Additional application:** Expose `confidence` in the query persistence threshold. The knowledgebase already has `auto_persist_when_high_value` requiring confidence ≥ 4/5.[^22] Making this threshold visible to human stewards (and surfacing confidence in search result rankings via `search.boost`) would close the loop.

**Why this matters:** A knowledge base that treats a confidence-3 page the same as a confidence-5 page is training users to distrust all of it. McGrane's lesson from the Amazon product case study is that "don't bury the lede" applies to metadata too — the uncertainty signal is important content.

---

### Opportunity 3: Diátaxis Content Type Expansion

**McGrane's principle:** "We are not in the web page publishing business. We are in the content publishing business."[^1]

**Current gap:** All six wiki concept pages are `type: concept`. The `wiki/entities/` and `wiki/analyses/` namespaces are empty despite having full schema contracts. There are no procedural/how-to pages, no reference pages, no tutorial pages.

**Specific recommendation:** Map the current type enum to Diátaxis roles and activate the empty namespaces:

| KB `type:` | Diátaxis role | Currently populated? |
|---|---|---|
| `concept` | Explanation — understanding-oriented | ✅ 6 pages |
| `entity` | Reference — information lookup | ❌ 0 pages |
| `analysis` | Explanation + evidence evaluation | ❌ 0 pages |
| `source` | Reference — provenance record | ✅ 8 pages |
| `process` | How-to — task/procedure-oriented | Reserved pages only |

The Diátaxis insight that tutorials conflate with references creates the same kind of reader confusion as McGrane's "we are in a war of blobs vs. chunks" — the issue is that *page type is not communicated*, so every page reads as a general-purpose blob. Adding a brief `type`-aware header to rendered pages ("This is a reference page. For conceptual background, see...") would apply Diátaxis without any schema changes.

**Higher-value action:** Create entity pages. The ontology contract is fully specified — relationship types (`related_to`, `part_of`, `governs`, `governed_by`, `replaces`, `depends_on`) are defined but unused.[^23] An entity page for "NPR's COPE Model" with relationships to three concept pages would be more retrievable than having that knowledge scattered in prose.

---

### Opportunity 4: Entity Graph for Relationship-Based Discovery

**McGrane's principle:** "The choices about how that content is going to look and work can be made to be appropriate for the individual platform, because they have invested in having a clean, well-structured base of content to work from."[^3]

**Current gap:** The `suggest-backlinks` skill is AFK-allowlisted and produces `BacklinkProposal` JSON — but there is no automated backlink index, no "related pages" rendering in the published wiki, and no graph traversal available to query consumers.[^24] The `wiki/open-questions.md` governed artifact is schema-defined but does not exist in the repo.[^25]

**Specific recommendation:** Three phased actions:

1. **Short term:** Wire the existing `suggest-backlinks` AFK output to a rendered "Related Pages" section in each wiki page (via MkDocs hooks). This is read-only, zero governance change, uses existing infrastructure.

2. **Medium term:** Create the `wiki/open-questions.md` governed artifact. The schema contract defines it; it just hasn't been materialized. Aggregating `open_questions` arrays across all pages into a browsable uncertainty ledger creates a "what we don't know" discovery surface — McGrane's equivalent of NPR's "editorial priority" metadata deciding what the homepage features.

3. **Longer term:** Populate entity pages. Each new entity page with `## Relationships` sections begins building the knowledge graph. When `wiki/entities/` has 10–20 pages, the AFK `cross-reference-symmetry-check` skill becomes actionable for detecting asymmetric links and missing backlinks.

---

### Opportunity 5: Tag Quality Enforcement

**McGrane's principle:** "Metadata is the new art direction" — but only if the metadata is meaningful.[^6]

**Current gap:** Tags are required frontmatter but quality is advisory in MVP. Most current pages share only generic tags (`knowledgebase`, `governance`) that duplicate namespace information rather than adding retrieval value.[^26] The taxonomy contract blocks tags that repeat the page title, but weaker forms of tag redundancy are undetected.

**Specific recommendation:** Promote tag quality to blocking validation for at least two rules:

1. **Block tags that repeat namespace name** — e.g., a `wiki/concepts/` page should not have `concept` as a tag (it's already encoded in the namespace)
2. **Require minimum 1 topical tag** — at least one tag that describes *what the content is about* (not just that it exists in the governance layer)

**Why this matters for adaptive content:** In a COPE-style query model, tags are the "business rules" layer that enables platform-specific filtering. If a chatbot asks "show me all pages about monitoring pipelines," tag quality determines recall. Currently the tags would surface every governance page in the repo.

**The KnowledgeOwl insight:** Tags serve as a "virtual Venn diagram" — their value is in set intersection, not enumeration.[^27] A page tagged `[google-drive, source-monitoring, adr-021, ci-6, pipeline]` is queryable on five independent axes; a page tagged `[knowledgebase, governance]` is only queryable on two axes that overlap with every other page.

---

### Opportunity 6: Authoring/Management/Publishing Separation

**McGrane's principle:** "Content authoring is not the same thing as content management and content management is not the same thing as content publishing."[^7]

**Current state (already strong):** The ingest pipeline (`raw/inbox/ → synthesis pipeline → wiki/`) is a direct implementation of this separation. Raw sources are authored/collected in `raw/`; they are managed by the agent pipeline (governance, validation, evidence verification); they are published to `wiki/` as governed artifacts. This is structurally sound.

**Remaining gap:** The **authoring interface** for knowledge consumers doesn't exist yet. Currently, the only way to add knowledge is through the intake pipeline (file into `raw/inbox/`), which is a producer-facing, pipeline-mediated process. There's no pattern for a knowledge *consumer* — someone who reads a wiki page and wants to note a correction, flag an open question, or suggest a related entity — to contribute without understanding the full pipeline.

**Specific recommendation:** Formalize a lightweight "consumer contribution" pattern:
- GitHub issue template for "I found a gap / error in wiki/concepts/X"
- Pre-defined fields: page slug, type of gap (factual error / missing relationship / low confidence claim / stale info), proposed correction
- This feeds `change-patrol` without requiring the consumer to understand the ingest pipeline

McGrane's Huffington Post example applies: "HuffPost commits 8–10–12 code changes to their CMS every single day, treating it like a product."[^7] The knowledge consumer pathway is the equivalent CMS improvement — small, frequent, governable.

---

### Opportunity 7: COPE API Layer / Headless Export

**McGrane's principle:** COPE's lasting value is the structured content model, enabling new delivery surfaces to be built "in a matter of weeks."[^3]

**Current state:** The knowledgebase uses `qmd` for local vector search. There is no external API endpoint or structured export format that would let a Slack bot, documentation generator, or support tool consume KB content without knowing Markdown file paths.

**Specific recommendation:** Design a minimal COPE-compliant export format. For each wiki page, a JSON representation of the core fields:

```json
{
  "slug": "knowledgebase-spec",
  "type": "concept",
  "title": "Knowledgebase Specification",
  "teaser": "2-3 sentence short form",
  "summary": "Full ## Summary section text",
  "confidence": 5,
  "tags": ["knowledgebase", "governance", "architecture"],
  "sources": ["..."],
  "updated_at": "2026-05-12T...",
  "related": ["context-md-domain-model", "..."]
}
```

This doesn't require building an API server — a CI-generated `wiki/export.json` artifact would serve the same COPE function for the project's current scale. When downstream consumers exist (Slack bot, custom search, chatbot RAG), they consume the export rather than scraping Markdown.

**McGrane's warning:** "You don't get to decide which device people use to access the internet: *they* do."[^28] Analogously: you don't get to decide what interface future collaborators use to query the knowledgebase. A structured export format is the insurance.

---

## Part 5: What Not to Do (McGrane's 2017 Self-Critique)

McGrane's most important caution: **do not leap from "structured content" to "targeted content"**.[^11]

The project should not:
- Create device-specific variants of wiki pages
- Build user-role-based content targeting before the content model is solid
- Add personalisation or adaptive delivery complexity *before* the chunk model is working

The wryenmeek/knowledgebase project's strong governance model is actually a protective factor here — the ADR-014 HITL/AFK classification system would naturally block premature automation of contextual targeting. The correct sequence is:
1. Get structured content right (chunked fields, meaningful metadata, typed entities) ← *current focus*
2. Activate the query/export layer ← *medium term*
3. Consider contextual delivery only when specific use cases justify it ← *future*

---

## Part 6: Alignment Summary

| McGrane Principle | KB Alignment | Gap | Priority |
|---|---|---|---|
| Multiple content lengths | `## Summary` exists; no `teaser` or `short_title` | Missing short-form field | **High** |
| Metadata as art direction | `confidence`, `sensitivity`, `tags` exist as fields | Not surfaced in reader UX | **High** |
| Chunks not blobs | YAML frontmatter + structured body sections | `## Evidence` is unstructured prose | Medium |
| Type-based content modeling | `type:` enum defined | Entity/analysis namespaces empty | **High** |
| COPE / API-first | Local `qmd` index only | No external query/export surface | Medium |
| Relationship-based discovery | Ontology vocabulary defined | No rendered backlinks or graph traversal | Medium |
| Open questions surface | `open_questions` field on every page | `wiki/open-questions.md` doesn't exist | Medium |
| Tag quality for retrieval | Tags required frontmatter | Quality is advisory; weak discrimination | Medium |
| Authoring ≠ management ≠ publishing | Pipeline separation is strong | No consumer contribution pathway | Low |
| Content parity / persistent URLs | All pages have stable slug-based paths | No cross-device analytics | Low |
| Avoid targeted-content complexity | ADR-014 HITL gates provide natural protection | N/A | N/A |

---

## Confidence Assessment

**High confidence (directly verified):**
- All claims about McGrane's 2012 talk content — retrieved from full transcript at karenmcgrane.com[^1]
- All claims about McGrane's articles — retrieved directly from her site and ALA[^8][^9][^10]
- All claims about the knowledgebase project schema, frontmatter fields, and current population — read directly from schema/*.md and wiki/ files[^19][^20][^23]
- NPR COPE field list — retrieved from ALA "Future-Ready Content" article[^3]

**Medium confidence (secondary sources):**
- Ann Rockley's five intelligent content characteristics — reconstructed from MadCap Software blog; annrockley.com was unreachable[^14]
- Diátaxis framework details — retrieved from diataxis.fr directly[^15]
- Contentful data model — retrieved from Contentful developer docs[^17]

**Inferred (not directly verified):**
- "Substitute 'AI query interfaces' for 'mobile'" framing — logical extrapolation from McGrane's disruption theory, not a claim she made
- Specific MkDocs implementation approaches for confidence admonitions — practical recommendation, not sourced from the repo's current MkDocs configuration

**Unresolved gaps:**
- Jeff Eaton's writing on COPE (eaton.fyi under construction)
- Karen McGrane's work at Autogram (autogram.is/thinking/ returned 404)
- McGrane's 2024 webinar "The Problem with Page Builders" (YouTube, not fetched)
- Ann Rockley's primary sources (*Managing Enterprise Content*, *Intelligent Content: A Primer*) — not accessed

---

## Footnotes

[^1]: Karen McGrane, "Adapting Ourselves to Adaptive Content" (talk transcript), Breaking Development Conference, September 24, 2012. Retrieved from: https://karenmcgrane.com/talks/adapting-ourselves-to-adaptive-content/

[^2]: Daniel Jacobson, "COPE: Create Once, Publish Everywhere," ProgrammableWeb, October 13, 2009. URL: http://www.programmableweb.com/news/cope-create-once-publish-everywhere/2009/10/13 (site defunct; content preserved in McGrane's transcripts).

[^3]: McGrane (2012), citing Zach Brand (NPR Head of Technology). "NPR directly attributes 80% page growth to having an API." Content model and API architecture described in: A List Apart, "Future-Ready Content" — https://alistapart.com/article/future-ready-content/

[^4]: McGrane (2012), transcript §28–39, "The TV Guide Precedent." TV Guide sold for $1; the data service (with three-length descriptions per programme) retained all value.

[^5]: McGrane (2012), transcript §55–66, "Blobs vs. Chunks" section.

[^6]: McGrane (2012), transcript §67–74, "Metadata" section. Quote: "Metadata is the new art direction."

[^7]: McGrane (2012), transcript §75–90. Quote: "Content authoring is not the same thing as content management and content management is not the same thing as content publishing." HuffPost 8–12 daily CMS commits cited.

[^8]: Karen McGrane, "Future-Ready Content," A List Apart. URL: https://alistapart.com/article/future-ready-content/ — Five steps: purposeful, micro, meaningful, organized, structured.

[^9]: Karen McGrane, "WYSIWTF," A List Apart, May 2, 2013. URL: https://karenmcgrane.com/wysiwtf/ — Three CMS anti-patterns: preview button, WYSIWYG editor, inline editing.

[^10]: Karen McGrane, "Windows on the Web," A List Apart, January 23, 2013. URL: https://karenmcgrane.com/windows-on-the-web/ — 90% multi-device task completion stat (Google research); five content parity recommendations.

[^11]: Karen McGrane, "Adaptive Content: Context and Controversy" (talk transcript), Now What? Conference, April 27, 2017. URL: https://karenmcgrane.com/talks/adaptive-content-context-and-controversy/

[^12]: Karen McGrane, "The Mobile Content Mandate" (talk transcript), Confab Higher Ed, November 12, 2013. URL: https://karenmcgrane.com/talks/the-mobile-content-mandate/ — DEC disruption case study from Clayton Christensen.

[^13]: McGrane (2012), transcript §84–85, "Mobile as Catalyst" section.

[^14]: Ann Rockley, "Intelligent Content" (five characteristics). Primary: *Managing Enterprise Content: A Unified Content Strategy* (O'Reilly, 2002); *Intelligent Content: A Primer* (XML Press, 2012). Secondary source used: MadCap Software blog — https://www.madcapsoftware.com/blog/intelligent-content/

[^15]: Diátaxis framework — https://diataxis.fr (retrieved). Tutorial/how-to/reference/explanation taxonomy with user-mode mapping.

[^16]: Karen McGrane current role confirmed at https://karenmcgrane.com/ — Senior Director, Customer Insights & Adoption, Contentful.

[^17]: Contentful data model — https://www.contentful.com/developers/docs/concepts/data-model/ (retrieved). Field types: Symbol, Text, RichText, Date, Boolean, Link, Array.

[^18]: wryenmeek/knowledgebase: wiki/index.md — current page counts: 8 sources, 6 concepts, 0 entities, 0 analyses. Confirmed via research subagent reading the file directly.

[^19]: wryenmeek/knowledgebase: schema/page-template.md — current required/optional frontmatter fields. TV Guide model `teaser` + `short_title` fields are not currently present.

[^20]: wryenmeek/knowledgebase: schema/metadata-schema-contract.md:40–55 — Schema evolution rules. Rule 1: "Additive first — new fields start optional and advisory."

[^21]: wryenmeek/knowledgebase: wiki/concepts/wiki-quality-best-practices.md — confidence: 3 with explicit open_question about unverifiable external citations [1]–[13].

[^22]: wryenmeek/knowledgebase: wiki/concepts/knowledgebase-spec.md:29–30 — `auto_persist_when_high_value` requires confidence ≥ 4/5, ≥ 2 source references.

[^23]: wryenmeek/knowledgebase: schema/ontology-entity-contract.md:44–65 — Relationship vocabulary: `related_to`, `part_of`, `has_part`, `governs`, `governed_by`, `replaces`, `replaced_by`, `depends_on`. Currently unused (0 entity pages).

[^24]: wryenmeek/knowledgebase: docs/decisions/ADR-014 — `suggest-backlinks` is AFK-allowlisted. Currently produces BacklinkProposal JSON but output is not rendered in wiki pages.

[^25]: wryenmeek/knowledgebase: schema/governed-artifact-contract.md:14–35 — `wiki/open-questions.md` defined as a mutable ledger artifact, but confirmed absent from the repo (`wiki/index.md` shows no open-questions.md).

[^26]: wryenmeek/knowledgebase: wiki/index.md + concept pages — Current tags: `knowledgebase`, `governance`, `architecture`, `spec` (knowledgebase-spec), `context-md`, `agent-context`, `domain-vocabulary` (context-md-domain-model), etc. Most tags co-occur on governance concept pages, providing low discriminative value.

[^27]: KnowledgeOwl, "Knowledge Base Metadata Best Practices" — https://www.knowledgeowl.com/blog/posts/knowledge-base-metadata (retrieved). Tags as "virtual Venn diagram" for set-intersection retrieval.

[^28]: Karen McGrane, *Content Strategy for Mobile* (A Book Apart, 2012). Also stated in "The Mobile Content Mandate" (2013): "You don't get to decide which device people use to access the internet: they do."
