# SELFTEST — measured, not asserted

Every number below was produced by running this package. Engine: stdlib only
(`pymupdf` was not installed in the measuring environment). Runtime: CPython 3.12.

## 1. Two entry paths, same engine

| path | command | result |
|-|-|-|
| one-shot (evaluation entry) | `python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work` | exit 0, `build: status=ok artifacts=8` then `selfcheck: files=ok echo=ok placeholders=ok` |
| agent | `init` → `show` → `check` → `build` → `selfcheck` → `compare` | exit 0 each; `init` prints `1 file(s) indexed, 22 page object(s), 16 draft candidate(s)`; `build` output is byte-identical to `all` |

`all` = `build` + `selfcheck`. No draft is needed: with no `work/draft.json` every contract field and
every artifact is produced by the program itself.

## 2. Rich run — the shipped `examples/sample.pdf` (2 pages, two columns)

| measure | value |
|-|-|
| `status` | `ok` |
| document | `sample.pdf`, 2 pages, engine `stdlib`, 1777 chars |
| title | `Reading order in two-column PDFs` |
| page objects | 22 — heading 6, paragraph 9, caption 2, table_row 4, formula 1 |
| sections | 5 — Abstract / 1. Introduction / 2. Method / 3. Discussion / References |
| tables | 1 grid, 4 rows × 3 cols, header `["engine", "pages", "seconds"]` |
| formulas | 1 — `E = m c^2 (1)`, number `(1)` |
| reading-order notes | 4 — two per page: `gutter(s) at x=304-328` (p1) / `x=297-328` (p2), plus 2 excluded running-matter bands per page (`Journal of Reading Studies 12 (2026) 1-9`, `Preprint, open review copy`) |
| evidence rows | 39, none with an empty quote; kinds: block_heading / block_paragraph / block_table_row / block_caption / block_formula, section, table, formula, caption, reference, reading_order |
| layout rows (`layout_objects.jsonl`) | 26 (includes the 4 excluded running-matter rows) |
| coverage checks | 10, `missing = []` |
| page sizes | 612×792 pt on both pages |
| uncertainty | 1 line (top-to-bottom fallback when no whitespace gutter exists) |
| change_records | 2 (`reading_order_reconstructed`, `running_matter_marked`, both `reversible: true`) |

## 3. Draft path — accept / reject is really decided by the locator

`init` produced 16 candidates, each carrying a locator of the form `<file> pN <oid> <type>`.
A draft of three items was checked:

```
check: draft=3 accepted=1 rejected=2 objects=22
```

- accepted — `title` at `sample.pdf p1 p1-b01 heading` (a real object);
- rejected — `authors` at `sample.pdf p9 p9-b99 heading` → *locator does not name a page object of this file*;
- rejected — `abstract` with an empty value → *empty field or value*.

`build` with that draft adds `CH-03 draft_override_applied` (locator `sample.pdf p1 p1-b01 heading`,
`reversible: true`) and leaves the 10 contract keys complete. With no draft, the output is unchanged.

## 4. Boundary degradation — 4-combination matrix (`work/p4/synth_cases/reading-01`)

| case | mode | status | failures | warnings | contract source | artifacts |
|-|-|-|-|-|-|-|
| rich | single | PASS | 0 | 0 | `case.json:output_contract` | 9 |
| rich | agent | PASS | 0 | 0 | `case.json:output_contract` | 9 |
| boundary | single | PASS | 0 | 0 | `SKILL.md` json sample (10 keys) | 9 |
| boundary | agent | PASS | 0 | 0 | `SKILL.md` json sample (10 keys) | 9 |

Checks that ran and passed in all four: `exit_code`, `result_json`, `contract_echo`, `deliverables`,
`case_id`, `placeholder_sweep`, `field:{status,sources,uncertainty,change_records,limits}`.

The synthetic **rich** case ships an empty `materials/` directory, so it exercises the honest-empty path:
`status=insufficient_evidence`, `sources` empty, `unreadable` = 0 readable materials with the reason,
all 9 artifacts written and ≥ 40 B, exit 0.

The synthetic **boundary** case ships `broken.json` (invalid JSON), `empty.md` (0 B) and `notes.txt`
(10 B) with `output_contract: null`. Result: `status=insufficient_evidence`, each file listed in
`sources` with its own status (`invalid-json` / `empty-file` / `note-only`), nothing guessed, exit 0.
The `SKILL.md` sample supplies the 10 keys, so the contract is still complete.

## 5. Test matrix

| input kind | what is checked | observed |
|-|-|-|
| PDF with a text layer, two columns | object rebuild, column cut, gutter, running matter, table, formula, evidence, locator | `status=ok`, 22 objects, 1 table, 1 formula, 39 evidence rows |
| PDF whose page has no text layer | not readable → `unreadable`, no guessing | `status=insufficient_evidence`, reason recorded |
| `.md` / `.txt` body | single-page text; note that columns/tables are unrecoverable | `status=ok` with the "no layout geometry" note |
| empty file | `empty-file`, no body invented | counted in `sources`, excluded from body |
| note-only file | `note-only` | counted in `sources`, reason "the file holds only a note asking for a later draft" |
| corrupt JSON | `invalid-json` | counted in `sources`, reason recorded |
| PNG / DOCX / binary with NUL | `unparsed-binary` | counted in `sources`, not parsed |
| missing / empty input dir | complete 10-key contract, all artifacts, exit 0 | `status=insufficient_evidence` |
| file > 500000 chars | truncated, fact recorded | recorded in `uncertainty` and `sources.reason` |
| > 60 files in the dir | first 60 read, rest recorded | recorded in `result.errors` |
| any unexpected exception | `result.json` still written | `status=input_error`, exit 0 |

## 6. Invariants

- every structure item and every evidence row carries a locator of the form `<file> pN <oid> <type>` and
  a verbatim quote; `sha256_16` in `evidence.json` is the first 16 hex digits of the quote's UTF-8 SHA-256;
- the contract is filled at the top level **and** under `output_contract`, with the same values;
- engine order is `pymupdf` (only if already importable) → stdlib; both report their name in `document.engine`;
- runs are deterministic: the same input yields the same reading (see `compare` → `reproducibility`);
- nothing outside `/input`, `/app/output`, `/app/work` is touched; no network, no model call.
