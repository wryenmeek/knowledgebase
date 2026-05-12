# Manual of Style

Reference standard for prose in wiki pages. Apply during `semantic-wiki-lint`
review and `enforce-npov` checks. When in doubt, ask: "Would this sentence appear
in a neutral encyclopedia entry about Medicare coverage?"

---

## Prose register

- **Voice:** Encyclopedic and neutral. Never conversational or persuasive.
- **Person:** Third-person only. No "we", "our", "you", or "I".
- **Tense:** Present tense for current policy; past tense only for documented historical changes.
- **Hedging:** Avoid weak qualifiers ("might", "could", "seems to"). Cite the source or omit the claim.

```
✗ We believe this coverage rule may apply to most beneficiaries.
✓ Medicare Part B covers medically necessary services for eligible beneficiaries.
```

---

## Heading conventions

- **Case:** Title case for top-level (`##`) headings; sentence case for sub-headings (`###`+).
- **Depth:** Maximum three heading levels (`##`, `###`, `####`). Deeper nesting signals the section should be split.
- **No questions:** Headings state topics, they do not pose questions.
- **No punctuation** at the end of headings.

```
✗ ### What Does Part B Cover?
✓ ### Part B Coverage Scope
```

---

## Pronoun and vocabulary standards

- Replace "we/our" with the entity name or "the policy/the plan/Medicare".
- Replace "beneficiary's plan" with "the beneficiary's plan" (always definite article).
- Avoid jargon without definition; define domain terms on first use with a parenthetical.

### Medicare domain vocabulary

| Preferred | Avoid |
|---|---|
| beneficiary | member, patient, enrollee (unless quoting a source) |
| covered service | benefit item, covered item |
| cost-sharing | copay/coinsurance when the specific type is unknown |
| Medicare Advantage plan | MA plan (acceptable abbreviation after first use) |
| Original Medicare | Traditional Medicare, Fee-for-Service |
| prior authorization | prior auth, PA (acceptable abbreviation after first use) |
| formulary | drug list |
| network | provider network (acceptable on first use) |

---

## Citation style within prose

- Cite inline immediately after the claim, not at the end of the paragraph.
- Use the canonical `SourceRef` format: `[Source title](repo://owner/repo/path@sha)`.
- If a claim is drawn from multiple sources, cite each source at the end of the relevant sentence.
- Do not use footnote-style citations; all citations are inline.
- Never cite secondary sources (news articles, summaries) when the authoritative CMS source exists.

```
✗ According to various sources, Part B covers durable medical equipment.
✓ Medicare Part B covers durable medical equipment that is medically necessary
  and prescribed by a physician [CMS DME Benefit Policy](repo://...).
```

---

## What to avoid

| Pattern | Why | Fix |
|---|---|---|
| Editorializing | "notably", "importantly", "unfortunately" | Delete the adverb; let facts speak |
| Hedged claims | "it appears", "it seems", "generally" | Cite the source or remove the claim |
| First-person commentary | "we added this section because" | Remove; rewrite as factual statement |
| Passive voice stacking | "it has been determined that it may be required" | Rewrite: "CMS requires..." |
| Redundant preambles | "This section explains that..." | Delete; start with the content |
| Unsourced superlatives | "the most common", "the best approach" | Cite or rewrite without superlative |
| Future speculation | "this policy will likely change" | Cite a scheduled change or omit |

---

## Page-level checklist

Before marking a page complete, verify:

- [ ] No first-person pronouns
- [ ] All claims have inline SourceRef citations
- [ ] Headings follow title case / sentence case split
- [ ] Domain vocabulary uses preferred terms from the table above
- [ ] No editorializing adverbs or hedged language
- [ ] Passive voice stacking resolved
