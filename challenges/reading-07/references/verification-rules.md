# Verification rules, field dictionary and draft schema

Everything below is implemented in `scripts/engine.py`; change a rule, change this file too.

---

## 1. Verdict vocabulary (closed set)

| verdict | meaning | minimum requirement |
|---|---|---|
| `supported` | the passage states the claim's entity, direction and values | at least one verbatim quote, no counter-evidence |
| `partially_supported` | the core assertion holds but a comparator, value, significance or scope element is missing or unmatched | one verbatim quote plus an explicit limitation tag |
| `contradicted` | a passage states the opposite direction, the opposite value ordering, or a null result where the claim asserts an effect | a counter quote with `supports: false` |
| `insufficient_evidence` | no passage in the supplied corpus carries the assertion | a `search_scope` record; **never** a fabricated quote |

Two hard separations this skill exists to enforce:

1. **Topic relevance is not support.** Shared keywords without the same comparator, sample or
   endpoint cap out at `partially_supported`, and usually at `insufficient_evidence`.
2. **Not supported is not disproved.** Only an explicit opposite statement yields
   `contradicted`; a missing experiment stays `insufficient_evidence`.

## 2. Retrieval score

For a sub-claim with key-term set `K` (stop-words removed, CJK bigrams kept) and numeric
anchors `N` (`62%`, `450 °C`, `p = 0.42`, …):

```
coverage = |K ∩ unit_tokens| / |K|
numcov   = |{n in N : n occurs in unit, token-bounded}| / |N|
score    = 0.72 * coverage + 0.28 * numcov        (if N is non-empty)
score    = coverage                               (if N is empty)
score   += 0.15                                   (source_hint matches file name or source id)
```

Candidates sort by `score desc`, then input order (file, block), then `unit_id`. The top three
become the candidate set. Numeric anchors are matched on token boundaries, so `1` does not
match `120` and `62` does not match `620`.

The quote attached to a candidate is the highest-scoring **complete sentence** of that unit
(12–300 characters); if no sentence qualifies, a contiguous window of the unit is used. The
quote is always a substring of the unit, never a paraphrase.

## 3. Decision table (evaluated top-down, first match wins)

| rule | condition | verdict | confidence |
|---|---|---|---|
| R0 | no candidate, or best `coverage < 0.14` and `numcov = 0` | `insufficient_evidence` | low |
| R1a | best candidate's direction cue is the opposite of the claim's, `coverage ≥ 0.30` | `contradicted` | high if `coverage ≥ 0.55` |
| R1b | two anchors, claim says "A higher than B", quote attaches values to A and B in the opposite order | `contradicted` | high |
| R4b | same value-ordering test, order agrees with the claim | `supported` | high |
| R1c | another candidate (not the best) has the opposite direction cue, `coverage ≥ 0.30` | `contradicted` (both quotes kept) | high if `coverage ≥ 0.55` |
| R2 | claim asserts an effect (no negation, no null phrasing), quote reports no significant difference / no effect, `coverage ≥ 0.40` | `contradicted` | medium |
| R3 | claim and quote both negate the same predication | `supported` | medium |
| R4 | `coverage ≥ 0.34` and (no anchors, or every anchor matched) | `supported` | high when anchors matched and `coverage ≥ 0.50` |
| R5 | `coverage ≥ 0.20` or at least one anchor matched | `partially_supported` | medium / low |
| R6 | anything else | `insufficient_evidence` | low |

Direction cues: `higher, increase, above, improve, 高于, 提高, 增加, 升高, 上升, 增强 …` (+1) versus
`lower, decrease, below, reduce, 低于, 降低, 下降, 抑制 …` (−1). A quote containing both polarities
carries no direction.

**R1b in detail.** For a claim with two numeric anchors and a direction, the engine locates each
anchor in the quote and reads the first number that follows it within 60 characters. If that
number is another anchor, or no number follows, the test abstains. Otherwise the ordering of the
two values decides: for "A higher than B", `value(A) > value(B)` supports and `value(A) < value(B)`
contradicts. This is what catches "450 °C reached 62% … 350 °C reached 78%" against the claim
"450 °C reached a higher conversion than 350 °C".

## 4. Aggregation and status

| sub-claim verdicts | claim verdict |
|---|---|
| all `supported` | `supported` |
| all `contradicted` | `contradicted` |
| all `insufficient_evidence` | `insufficient_evidence` |
| any `contradicted` plus any `supported`/`partially_supported` | `partially_supported` |
| `supported` plus `insufficient_evidence` | `partially_supported` |
| otherwise | `partially_supported` |

Claim confidence is the minimum sub-claim confidence. Two sources giving opposite directions
(both `score ≥ 0.30`, different `source_id`) set `conflict.present = true`,
`conflict.unresolved = true`, keep both quotes, and force `partially_supported` at `low`
confidence.

Run status:

| status | when |
|---|---|
| `answered` | claims were read, material was readable, no degradation, and no claim ended all-insufficient |
| `partial` | the ledger is complete but at least one claim is insufficient, a quote failed re-check, or a material/degradation record exists |
| `input_error` | no claim list found, or no readable text unit at all |

`partial` is a legitimate terminal state: what could be checked is here, with the gaps named.

## 5. Locators

`<file>#p<n>` — `n` is the PDF page when the extractor reports pages (`pypdf`, `pdftotext`), and
otherwise the block ordinal inside that file (markdown heading blocks, JSON paragraphs, CSV rows,
text paragraphs). `unit_id` (`U7`) is the internal key; `locator` is the human key; both are
written next to every quote. `sources[]` maps `source_id` → path, format, extractor and unit count.

## 6. Output fields

`result.json` echoes every `output_contract` key at top level, then adds:

| field | content |
|---|---|
| `case_id`, `status` | input identity and one of the three statuses above |
| `claims[]` | one object per input claim: `claim_id`, `text`, `kind`, `verdict`, `confidence`, `sub_claims[]`, `conflict`, `limitations`, `rationale` |
| `claims[].sub_claims[]` | `sub_id`, `text`, `type`, `required_evidence_type`, `verdict`, `verdict_confidence`, `rule_id`, `verdict_basis`, `evidence[]`, `rationale`, `limitations[]`, `search_scope`, `counter_evidence_searched` |
| `evidence[]` | one record per sub-claim (the same rows as `evidence_cards.jsonl`) |
| `counts` | claims, sub-claims, per-verdict totals, `evidence_items`, `verified_quotes`, `claims_with_conflict`, `corpus_units`, `sources` |
| `sources[]` | `source_id`, `path`, `file`, `format`, `units`, `extraction`, `chars`, `readable` |
| `uncertainties[]` | insufficient or partial items with `next_step` and the search scope |
| `assumptions[]`, `method_notes[]` | reading conventions and the rule summary |
| `errors[]`, `degradations[]`, `pending_human[]` | failures, fallbacks and what a human must finish |
| `query_log[]` | per sub-claim: query terms, units scanned, top candidate scores |
| `self_check` | `passed`, `issues[]`, `checked{}` |
| `runtime`, `changes` | paths, version, command list, budget |

Evidence record: `source_id`, `unit_id`, `locator`, `quote`, `score`, `numbers_matched`,
`direction`, `supports`, `role` (`minimal_sufficient` | `counter`), `verified`.

`evidence_cards.jsonl` has one JSON object per **sub-claim** — claim id, sub id, text, type,
verdict, confidence, rule, basis, evidence list, rationale, limitations.

## 7. Optional agent draft (`/app/work/draft.json`)

Not required. When present it replaces the rule verdict **only** where it survives validation.

```json
{
  "schema": "claim-evidence-draft/2",
  "case_id": "case-001",
  "claims": [{
    "claim_id": "C1",
    "sub_claims": [{
      "sub_id": "C1.1",
      "text": "450 °C gave a higher CO conversion than 350 °C",
      "type": "comparison",
      "verdict": "contradicted",
      "verdict_confidence": "high",
      "rationale": "62% at 450 °C vs 78% at 350 °C",
      "evidence": [{"unit_id": "U3", "quote": "The 450 °C sample reached a CO conversion of 62%, whereas the 350 °C sample reached 78%."}],
      "limitations": ["direction_opposite"],
      "search_scope": {"units_scanned": 12}
    }],
    "aggregation_note": "single sub-claim"
  }]
}
```

Validation applied to every draft sub-claim:

1. `verdict` must be in the four-value set, otherwise the entry is dropped;
2. `unit_id` must exist in the run index;
3. `quote` must be verbatim inside that unit (whitespace/NFKC-normalised), otherwise the evidence
   item is dropped and counted in `degradations[draft_merged]`;
4. `supported` / `partially_supported` with no surviving evidence is dropped, so a draft cannot
   assert support without a checkable quote;
5. dropped entries fall back to the deterministic verdict for that claim — never to an empty card.

`/app/work/draft.template.json` is rewritten on every run with the current claims and candidate
units, so an agent can fill it in without guessing ids.

## 8. Limitation tags

`no_lexical_candidate`, `overlap_below_threshold`, `topic_overlap_only`, `direction_opposite`,
`material_reports_null_result`, `negation_aligned`, `value_not_matched`, `direction_not_stated`,
`partial_key_term_coverage`, `partial_alignment`, `verification_error`, `quote_unverified`,
`material_unreadable`.

## 9. Known limits

- Lexical overlap plus anchor matching is a retrieval heuristic, not entailment; paraphrase,
  synonymy and clause-scoped negation can defeat it.
- The unit is a paragraph or sentence, so a conclusion split across Results and Discussion is
  judged from the best single unit.
- Scattered scope qualifiers ("at any loading") are not always checked against the limiting
  experiment; such claims can pass as `supported` when the scope word is not the matched term.
- Figure/table readings need caption text; images are registered as `gaps` only.
- PDFs without a text layer and without `pypdf`/`pdftotext` produce `no_text_layer`; the affected
  claims are `insufficient_evidence` and `pending_human` names the file.
