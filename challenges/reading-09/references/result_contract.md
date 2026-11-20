# Result contract — `paper-notes/1`

`result.json` is written by `paper_notes.py all`. All keys below are always
present; lists are empty rather than absent when nothing could be produced.

## Top level

| key | type | meaning |
|---|---|---|
| `schema_version` | str | `"paper-notes/1"` |
| `case_id` | str \| null | taken from `case.json` (`case_id`, `caseId`, `id`, `task_id`) |
| `status` | str | `success \| partial \| unable_to_determine \| refused` |
| `status_reason` | str | why the status was chosen; empty only for `success` |
| `language` | str | case language, default `en` |
| `documents` | list | every decoded input: `doc_id, file, path, sha256, bytes, pages, backend, extraction_status, warnings` |
| `answers` | list | one entry per case question |
| `section_notes` | list | one entry per detected heading |
| `paper_card` | object | the seven fixed card fields |
| `knowledge_points` | list | retrievable terms |
| `evidence` | list | every anchor, quote-verified at write time |
| `uncertainties` | list | `item, why, what_would_resolve` |
| `not_reported` | list | `item, why_expected` |
| `sources` | list | `doc_id, file, pages, sha256` per input |
| `change_log` | list | `step, action, detail` for each pipeline stage |
| `reproduction` | object | `paper_metrics`, `candidates[]` with `file, metrics, deltas` |
| `result` | object | summary: `document_title, sections, anchors, knowledge_points, answers` |
| `claims` | list | `claim_id, section_id, field, text, anchors` for each written note field |
| `self_check` | object | `ready_to_submit, weighted_score, blocking_failures, checks` |
| `output_contract` | object | the case contract, echoed verbatim |

### Contract echo

After the real `case_id` is set, every key of the supplied `output_contract` is
copied with `setdefault`, so a contract value never overwrites a produced value.
If a contract key has no deterministic source it stays `null` (or empty) and is
also listed in `not_reported`; it is not filled with invented prose. C4 treats a
still-empty contract key as a blocking failure unless the key is `not_reported`
or `uncertainties`.

## `section_notes[]`

```json
{
  "section_id": "S02",
  "title": "4.1 Main results",
  "role": "results",
  "page_start": 1,
  "page_end": 1,
  "purpose": "该节的目的：报告主结果，并给出可以复核的数值。",
  "methods": "",
  "results": "作者报告：Top-1 accuracy 76.5% ...",
  "conclusions": "",
  "link_from_previous": "本节承接上一节的方法设定，转入结果陈述。",
  "anchors": ["A02"]
}
```

`role` is one of `abstract, introduction, related_work, methods, results,
discussion, conclusion, limitations, other, appendix`; `references` and
`acknowledgements` headings are skipped. Note prose is rewritten in the reader's
voice with a short prefix; only `quote` is verbatim.

## `paper_card`

Fixed seven keys — `research_question, data, methods, key_findings, conditions,
limitations, conclusion` — each `{ "text": str, "anchors": [anchor_id, ...] }`.
A field the material does not state reads as a "not reported" sentence, is
listed in `not_reported`, and keeps an empty anchor list.

## `knowledge_points[]`

`{"kp_id": "KP01", "term": "momentum", "definition": "...", "synonyms": ["momentum",
"momenta", ...], "anchors": ["A01"], "section_id": "S01"}`. Synonyms include
search variants (case, singular/plural, snake_case, code-metric aliases).

## `answers[]`

`{"question_id": "Q1", "question": "...", "answer": "...", "anchors": [...]}`.
An answer states content (not "see section X"); it must be at least 60 Latin
characters or 20 CJK characters.

## `evidence[]`

`{"anchor_id": "A01", "doc_id": "D01", "page": 1, "quote": "...", "claim": "方法",
"section_id": "S01"}`. `page` is a physical page (virtual page 1 for text-only
inputs); `quote` is 20–240 characters and a verbatim substring of that page.
`claim` names the reader's role label and carries no digits, so number checks
cannot be satisfied by a heading.

## Status logic

1. No decoded document → `unable_to_determine`, reason recorded, nothing invented.
2. Primary document has no text layer → `partial`.
3. An empty contract key remains → `partial` with the key names.
4. No evidence anchor bound → `partial`.
5. Any "too little text" input warning → `partial`.
6. Fewer than three knowledge points → `partial`.
7. Otherwise `success`. A blocking self-check failure downgrades a would-be
   `success` to `partial` with the failing check ids in `status_reason`.

On an unexpected exception the entry writes a minimal valid `result.json`
(`unable_to_determine`, reason in `status_reason`) and exits 0.
