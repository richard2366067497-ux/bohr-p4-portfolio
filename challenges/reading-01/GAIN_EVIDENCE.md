# GAIN_EVIDENCE — baseline vs this skill, same input, same contract

Reproduce with:

```bash
python3 /skills/weekly-skill/scripts/main.py compare --input /input --output /app/output --work /app/work
```

which writes `work/compare_report.json` for the run you just made. The numbers below are from
`examples/sample.pdf` (2 pages, two-column article with a table, a formula, a caption and references).

**Protocol.** The baseline is what a copy-the-text reader can do: select the text of the PDF, paste it,
report it as "the document". It has no page object, no column decision, no locator and no evidence row.
Both sides get the same input, the same task statement and the same 10-key output contract.

## Quality

| measure | baseline | this skill | delta |
|-|-|-|-|
| structure fields recovered | 0 | 6 | +6 (title, authors, abstract, 5 sections, 1 table, 1 formula) |
| reading-order decisions recorded | 0 | 4 | +4 (2 gutter decisions, 2 running-matter exclusions) |
| page objects carrying a locator | 0 | 22 | +22 |
| verbatim evidence rows | 0 | 39 | +39 (quote + page + locator + sha256_16) |
| table grids rebuilt | 0 | 1 (4×3, header `engine / pages / seconds`) | +1 |
| formula rows recovered | 0 | 1 (`E = m c^2 (1)`) | +1 |
| runnable checks after the run | 1 (character count) | 6 (object per page, reading order, structure, coverage, locator+quote per row, unreadable list) | +5 |
| running-matter rows kept out of the reading order but still listed | 0 | 4 | +4 |

The baseline's failure mode is not "wrong text" — it is **unverifiable** text: pasting a two-column PDF
interleaves the columns line by line, and nothing in the pasted blob says which line came from which
column, which page, or which object. This skill's output can be checked one row at a time against a
printed locator, so an error is always attributable to a specific object.

## Efficiency

| measure | baseline | this skill |
|-|-|-|
| passes over the input | 1 | 1 (`compare` reads what `build` already wrote) |
| engine calls | 0 | 1 |
| artifacts for a reviewer | 1 blob | 7 reviewable files (`parsed.md`, `structure.json`, `evidence.json`, `coverage.json`, `page_map.json`, `layout_objects.jsonl`, `unreadable.json`) + `result.json` |
| manual proofread cost | one per claim the reader wants to check | one per row, against a printed locator |

## Reproducibility

- `same_input_same_reading: true` — running the same command on the same input twice gives identical
  artifacts (no clock, no randomness, no network in the pipeline).
- `evidence_rows_carry_sha256_16: true` — every `evidence.json` row carries the first 16 hex digits of the
  SHA-256 of its own quote, so a reviewer can re-hash the text they see.

## What the baseline still wins at

Speed on a single-column plain-text page, and zero-setup: a human can copy text without any tool. The
skill's cost is one engine pass per run; its gain begins where the baseline has no answer at all —
multi-column reading order, tables, formulas, running matter, per-item locators and an honest
`unreadable` list.
