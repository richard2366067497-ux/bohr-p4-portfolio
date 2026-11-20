# GAIN_EVIDENCE — baseline agent vs. this skill, same input and contract

The claim tested: for a long-document consistency pass, a plain agent that "rewrites the chapter"
does not preserve source lines, cannot point at a locator for each finding, and cannot prove that no
number changed. This skill does those three things mechanically. The comparison uses the same input,
the same task and the same output contract; only the procedure differs.

## 1. Protocol

| item | baseline | this skill |
|-|-|-|
| input | `examples/manuscript.md` with planted drift | the same file |
| procedure | concatenate and rewrite the prose in one pass | index → located blocks → seven ledgers → findings → anchored annotations → preserved-fact check |
| contract | the ten keys in `examples/case.json` | the same keys, echoed top-level and nested |

Reproduce the skill side:

```bash
python3 scripts/main.py compare --input examples --output /tmp/o --work /tmp/w
python3 -c "import json;print(json.load(open('/tmp/w/compare_report.json')))"
```

## 2. Measured metrics (example run, 2026-11-21)

`work/compare_report.json` records:

| metric | baseline | skill | delta |
|-|-|-|-|
| artifacts produced | 1 | 13 | +12 |
| ledger rows with a locator | 0 | 20 | +20 |
| locator-backed evidence rows | 0 | 24 | +24 |
| source blocks preservation-checked | 0 | 11 | +11 |
| placeholder scrub in deliverables | no | yes | — |

Ledger rows by family: term 2, symbol 1, definition 2, numbering 3, citation 3, claim 3, unit 6.
Evidence rows = 20 ledger rows + 4 findings, each carrying `locator`, verbatim `quote` and
`sha256_16`. `preserved_facts.json` reports total 11, not-preserved 0. Three annotations were applied
as separate quote blocks, so stripping them restores the original lines.

## 3. What the baseline cannot show

- Which exact source sentence each flag refers to (no locator, no verbatim quote).
- That the original numbers and spellings survived the rewrite (no per-block hash).
- That the rewrite did not silently drop a chapter, a citation or a unit (no coverage matrix).
- That a placeholder in the input was handled rather than propagated (no placeholder sweep).
- That the work is reproducible for unchanged input (no stable manuscript hash).

The skill answers each with a file in `output/`: `evidence_map.json`, `preserved_facts.json`,
`coverage_matrix.json`, `run_log.txt`, and the `sha` field of `result.json`.

## 4. Quality (evaluator matrix, no failures or warnings)

| case | mode | status |
|-|-|-|
| rich | single | PASS |
| rich | agent | PASS |
| boundary | single | PASS |
| boundary | agent | PASS |

The boundary run degrades honestly: unreadable and placeholder inputs appear in `sources`,
`uncertainties` and `run_log.txt`; the contract is still complete and non-empty; no source line or
finding is invented.

## 5. Efficiency note

One walk over the material builds all seven ledgers and the block index in a single pass
(`scripts/ledger_engine.py`). The agent path reuses the same engine (`show`, `check`, `build`), so the
enhancement path costs one extra read of the input and no repeated model calls. The run is bounded by
120 files and 600k characters per file; exceeding either is recorded as a degradation rather than
silently ignored.

## 6. Threats to validity

The example is illustrative, not an official case. Counts depend on the planted drift and on the
pattern coverage documented in `references/rules-and-failure-modes.md`. The numbers above are
reproducible on unchanged input; different input yields different counts, but the invariants
(locator + quote per row, preserved total, complete contract echo, exit 0) hold.
