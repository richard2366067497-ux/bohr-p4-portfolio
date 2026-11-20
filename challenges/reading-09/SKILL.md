---
name: reading-09
description: Read a supplied research paper and produce section-aligned, evidence-anchored structured notes — section notes, a seven-field paper card, retrievable knowledge points, cited answers, reproduction checks and a self-verdict — from one deterministic command.
---

# Reading-09 — section-aligned paper notes with anchors

Turn one real paper (PDF, DOCX, Markdown, TeX or plain text) into notes that
follow the paper's own headings instead of a generic summary template, where
every claim points back to a verbatim quote on the page it came from.

## 1. Run it

The one required command produces the complete `output_contract` and every
artifact:

```sh
python3 scripts/paper_notes.py all --input /input --out /app/output
```

`--work` defaults to `<out>/work`; pass `--work /app/work` to keep scratch files
apart. Pure standard library, no network. It always exits 0 and always leaves a
valid `result.json` — including for empty, unreadable or corrupt input.

Optional helpers (not needed for the contract):

```sh
python3 scripts/paper_notes.py doctor --input /input --out /app/output
python3 scripts/paper_notes.py check --result /app/output/result.json --work /app/work
```

## 2. What it writes

`/app/output/`

| file | content |
|---|---|
| `result.json` | the full contract: case_id, status, documents, answers, section_notes, paper_card, knowledge_points, evidence, uncertainties, not_reported, sources, change_log, reproduction, claims, result, self_check, output_contract |
| `notes.md` | human-readable notes in the paper's section order |
| `anchors.csv` | `anchor_id,doc_id,kind,page,para,section,verified,verdict,quote_or_label` — one row per anchor with its verification verdict |
| `work/text/<doc>.json` | decoded per-page text (audit trail) |
| `work/section_map.json` | detected headings, roles and page spans |
| `work/digest.md` | one screen of per-section key sentences |
| `work/notes_draft.json` | notes before final packaging |
| `work/selfcheck.json` | the same C1–C24 verdict as in `result.json` |

Every top-level key is present even when empty. Each key of the supplied
`output_contract` is echoed at the top level; a contract `case_id` never
overwrites the real one.

## 3. Input discovery

Found automatically anywhere under `--input`: `case.json` (case_id,
`output_contract`, optional `language`, `materials_root`, `questions`), then the
paper itself and any supplementary files. `task.md` is read for context only.
PDFs are decoded with a built-in Flate/object scan; DOCX via its
`word/document.xml`; text formats as-is. `case.materials_root` narrows the
search when present. Files that cannot be decoded produce a warning and a
`partial`/`unable_to_determine` status — never invented content.

## 4. Note model

- `section_notes[]` — one entry per detected heading: `section_id`, `title`,
  `role`, `page_start/page_end`, `purpose`, `methods`, `results`,
  `conclusions`, `link_from_previous`, `anchors`.
- `paper_card` — exactly seven fields: `research_question`, `data`, `methods`,
  `key_findings`, `conditions`, `limitations`, `conclusion`; each is
  `{text, anchors}` and may say what the material does not report.
- `knowledge_points[]` — term, definition, synonyms (searchable variants).
- `answers[]` — an answer per case question, each carrying anchor ids.
- `evidence[]` — anchors with `doc_id`, `page`, verbatim `quote`.
- `not_reported[]` and `uncertainties[]` — gaps and conflicts, stated rather
  than filled.

## 5. Evidence rules

An anchor is valid only if its `quote` (20–240 characters) occurs verbatim in
the cited page of the cited document. Numbers quoted in a claim must also appear
inside that claim's quote. A field with no support is recorded in
`not_reported` or `uncertainties`; it is never guessed. Section prose is
rewritten in the reader's voice; quotes stay verbatim.

## 6. Status

`success | partial | unable_to_determine | refused`.

| Condition | Status |
|---|---|---|
| Full notes, card, answers, KPs, anchors, no blocking check fails | `success` |
| No readable document | `unable_to_determine` |
| Document has no text layer | `partial` (OCR unavailable is stated) |
| Some anchors/fields cannot be bound | `partial` |
| Fewer than three knowledge points | `partial` |
| Blocking self-check failure after a would-be `success` | downgraded to `partial` |
| Internal error | caught, `unable_to_determine`, valid `result.json`, exit 0 |

The 24 checks and their thresholds are documented in `references/selfcheck.md`;
record shapes and the contract are in `references/result_contract.md`.

## 7. Files

```
SKILL.md
scripts/paper_notes.py    entry: discover → decode → split → anchor → card/KP/answers → check
scripts/pn_sections.py    document decoding, heading detection, KP extraction, C1–C24 checks
scripts/pn_notes.py       note/card/answer assembly, metrics, markdown + CSV rendering
references/result_contract.md  field shapes, contract echo and status logic
references/selfcheck.md        the 24 checks, thresholds and reading of failures
```
