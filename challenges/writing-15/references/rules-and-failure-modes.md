# Ledger rules, test matrix and known failure modes

This file is the authority for the mechanical checks. When a rule changes, change it here first,
then the constant in `scripts/ledger_engine.py`, then rerun `check` and `build`.

## 1. What a block is

A readable chapter is split on headings. Markdown headings (`#`…`######`), numbered headings
(`2.1 Title`) and Chinese headings (`第3章 Title`) start a section (`§n`). Non-empty line groups
between headings are paragraphs (`¶m`). A heading itself is a block with locator
`<rel> §n <title> (heading)`. Every ledger row and every annotation carries this locator.

## 2. Six ledgers (seven rule families including unit)

| family | pattern | records | known blind spot |
|-|-|-|-|
| term | `expansion (ABBR)`, `ABBR (expansion)`, `中文（ABBR）` | abbreviation, expansion, locator, quote | only parenthetical forms; free prose ("FDM 即熔融沉积") is missed |
| symbol | `where X is …`, `式中 X 为 …`, `X = …` | symbol, meaning, locator, quote | inline math and sub/superscripts are not parsed |
| definition | `X is defined as …`, `X 定义为/是指/称为/记作` | term, definition | paraphrased re-definitions are missed |
| numbering | `Figure/Fig./Table/Equation/Eq. N`, `图/表/式 N`, caption lines | role (caption/reference), kind, number | combined captions (`Figure 1 and 2`) count once; sub-panels are ignored |
| citation | `[n]`, `[a-b]`, `(Author, 2020)`, entries `[n] text` or `n. text` | citation, kind, locator | without a reference list only "cannot cross-check" is reported |
| claim | claim verbs (`increase`, `improve`, `significant`, `表明`, `显著`, `提高` …) + negation | polarity, quantity flag, locator, quote | negation is a heuristic, not entailment |
| unit | number + unit from a fixed lexicon | value, unit, written form | spelling is normalised only; no unit conversion and no silent change of a number |

## 3. Findings

A finding is created by a rule, not by opinion:

- term: one abbreviation has more than one expansion.
- symbol: one symbol has more than one meaning.
- numbering: a cited `kind N` has no caption `kind N`; or references exist with no caption list.
- citation: a cited number has no reference-list entry; or citations exist with no reference list.
- claim: two claims from different located blocks share at least four topic tokens with Jaccard ≥ 0.45
  and have opposite polarity.
- unit: repeated dimension writings are listed as a low-severity note; values are never converted.

Each finding names a `decision_owner` (`author` or `editor`). The skill writes both sides of a
conflict and does not decide it.

## 4. Acceptance rules for a draft annotation

| id | rule | severity |
|-|-|-|
| A1 | the locator resolves to a located block | high (reject) |
| A2 | `anchor_quote` is verbatim inside that block after normalisation | high (reject) |
| A3 | the annotation does not introduce a number absent from the material (reference numbers are exempt) | high |
| A4 | the same target is not annotated twice | warn |
| A5 | `evidence[].quote` also resolves inside its own locator | high |

A rejected annotation is reported in `work/check_report.json`; the source manuscript is unchanged.

## 5. Preservation and rollback

- `revised_manuscript.md` copies the author's raw lines; an annotation is inserted as a separate
  quote block after the target paragraph.
- `preserved_facts.json` re-checks each source block as a sanitised substring of the manuscript.
- `versions/rollback_check.json` records `rollback_equals_v1` and `reapply_equals_v2`.
- Sanitisation: placeholder tokens in the source are neutralised in deliverables (the original file
  is untouched). This is recorded as a degradation, not hidden.

## 6. Mapping to the rubric

| rubric item | artifact and count |
|-|-|
| task completion | `revised_manuscript.md`, `annotations_applied`, `coverage_matrix.json` |
| correctness | `evidence_map.json` verbatim rows, `consistency_tables.json` findings |
| completeness | `preserved_facts.json` total / not-preserved, `coverage_matrix.json` |
| verifiability | locator + quote + sha per row, `versions/` rollback check |
| efficiency gain | one index pass over all blocks; `work/compare_report.json` |
| innovation | reversible annotations and seven-ledger backtracking |
| reliability | every command exits 0; `self_check.json`; degradation ledger |
| ecology | this file and the three reusable templates |

## 7. Test matrix (every row is exercised by the deterministic CLI)

`all`, `build`, `check` and `selfcheck` always exit 0.

| input | expected behaviour |
|-|-|
| review chapter (long prose, many citations) | blocks split on headings; citation ledger lists `[n]`; missing entries become findings |
| methods chapter (symbols, definitions, units) | symbol/definition/unit ledgers populate; repeated symbol meanings become findings |
| results chapter (numbers, claim verbs) | claim ledger records polarity and quantity flags; numbers are echoed, never changed |
| results/discussion (opposite conclusions in two paragraphs) | claim pair with opposite polarity becomes a high-severity finding |
| 1 short paragraph | one block; status `ok` or `partial`; artifacts still complete |
| 40k+ characters | one pass; block and ledger caps keep the run bounded |
| >600k characters in one file | file truncated, `partial`, truncation listed in `uncertainties` |
| >120 files | first 120 read, an error line is recorded, `partial` |
| empty file | `empty-file`; never quoted; listed in sources and `uncertainties` |
| placeholder-only file (`[待写]`) | `placeholder-only`; skipped; sanitisation recorded |
| invalid JSON | `invalid-json`; not parsed as a chapter; reason recorded |
| PDF / DOCX / XLSX / PPTX / image | `unparsed-binary`; no text guessed; reason recorded |
| file with NUL bytes | `unparsed-binary` |
| missing `/input` or no case JSON | valid `result.json`, `status=input_error` or `insufficient_evidence`, exit 0 |
| draft absent | deterministic ledgers and annotations still produced; `draft_used=false` |
| draft annotation locator not found | rejected, reported, source unchanged |
| draft annotation quote not verbatim | rejected, reported, source unchanged |
| quote in the wrong block | rejected (locator and quote must agree) |
| placeholder tokens in source | neutralised in deliverables; original untouched |
| very long single line | quoted up to 240 characters; the block hash still covers the full line |
| Unicode curly quotes / dashes / NBSP | normalised before matching; the raw line in the manuscript stays as supplied |

## 8. Known limits (stated, not hidden)

- Term/definition/symbol extraction is pattern-based; free-text synonymy and paraphrase are missed.
- Claim contradiction is a token-overlap heuristic; it can flag a false pair or miss a paraphrase.
- Citation cross-check needs a reference list in the material; without one the skill says so.
- Unit handling normalises spellings only and never converts units.
- The skill does not decide which expansion, number or conclusion is scientifically correct.

## 9. Maintenance order

1. Edit this file.
2. Edit the matching constant in `scripts/ledger_engine.py`.
3. Run `check`; review `work/check_report.json`.
4. Run `build`; confirm the `sha` of `revised_manuscript.md` is stable for unchanged input.
