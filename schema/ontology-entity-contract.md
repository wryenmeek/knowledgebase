# Ontology and Entity Identity Contract

This document is the authoritative contract for canonical naming, aliases,
relationship vocabulary, and merge/split escalation in `wiki/**`. It
complements [`page-template.md`](page-template.md),
[`taxonomy-contract.md`](taxonomy-contract.md), and
[`metadata-schema-contract.md`](metadata-schema-contract.md).

## Identity model

- One canonical page represents one durable subject.
- Canonical identity is determined first by stable referent, then by title and
  page path.
- When present, `entity_id` is the strongest local identity key for entity
  pages; when absent, the canonical page path is the provisional identifier.
- Aliases, redirects, and superseded names must never create competing canonical
  identities for the same referent.

## Canonical naming rules

| Page type | Canonical naming rule |
|---|---|
| `entity` | Use the most stable, neutral, and source-grounded name for the referent. Prefer official names unless a more common neutral name is needed for disambiguation. |
| `concept` | Use a singular, durable concept label rather than a question, campaign phrase, or source-specific heading. |
| `source` | Prefix with `Source: ` followed by the authoritative source title or a stable repository-local label. |
| `analysis` | Use a concise reusable synthesis title describing the analytical output, not the transient request wording. |
| `process` | Reserve for operational pages such as `Knowledgebase Index` and `Knowledgebase Log`. |

Additional rules:

1. Titles are title-cased unless the source's official styling requires
   otherwise.
2. Use disambiguators only when needed to separate genuinely distinct subjects.
3. Do not encode aliases, dates, confidence, or workflow state in the canonical
   title.

## Alias contract

Aliases are alternate surface forms for the same canonical subject: abbreviations,
former names, punctuation/casing variants, or source-specific phrasings.

- Record aliases in optional frontmatter `aliases`, optional `## Aliases`
  section, or both.
- Normalize aliases as human-readable strings; do not repeat the canonical
  title.
- Only include aliases supported by evidence or strong operational need.
- Do not record parent/child concepts, broader/narrower terms, or unresolved
  ambiguous acronyms as aliases.

Escalate before accepting an alias when:

- one alias can refer to multiple active pages,
- the alias changes legal/regulatory meaning,
- or the alias is only weakly attested in authoritative sources.

## Relationship vocabulary

Until a richer relation schema is ratified, use the following controlled
vocabulary in optional `## Relationships` sections or other explicitly labeled
structured content:

| Relation | Meaning |
|---|---|
| `related_to` | Non-hierarchical association worth discovery but not stronger than the other listed relations. |
| `part_of` | The subject is a component or member of another canonical subject. |
| `has_part` | The subject contains or governs named component subjects. |
| `governs` | The subject sets rules, coverage, or obligations for another subject. |
| `governed_by` | Inverse of `governs`. |
| `replaces` | The subject succeeds and supersedes an earlier canonical subject. |
| `replaced_by` | Inverse of `replaces`. |
| `depends_on` | The subject requires another subject to be meaningful or executable. |

Prefer the narrowest valid relation. Fall back to `related_to` when stronger
semantics are not justified by evidence.

## Merge, split, and escalation rules

### Merge when

- two pages clearly refer to the same canonical subject,
- differences are only aliases, formatting, or source-local naming,
- or one page is a duplicate created before identity was resolved.

Merge behavior:

1. Keep one surviving canonical page.
2. Carry forward sources, evidence, tags, aliases, and open questions.
3. Mark the retired page as `superseded` or convert it into an alias/redirect
   pattern once that mechanism is formally implemented.

### Split when

- one page contains more than one durable referent,
- entity and concept content are mixed such that neither has a clear canonical
  home,
- or a source/analysis page is carrying evergreen entity or concept content that
  should stand alone.

Split behavior:

1. Create one canonical page per resulting subject.
2. Reassign evidence and relationships to the new pages explicitly.
3. Leave open questions when evidence cannot be partitioned cleanly.

### Escalate when

- high-confidence sources disagree on the canonical identity,
- the merge/split would materially change public meaning or legal interpretation,
- a short alias or acronym maps to multiple plausible active subjects,
- or the surviving canonical title cannot be chosen without editorial judgment.

Unresolved identity conflicts are blocking for write-capable automation.
