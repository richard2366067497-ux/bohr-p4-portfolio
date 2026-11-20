# longdoc-consistency-ledger (writing-15, v9)

A stdlib-only skill that turns thesis / long-document chapters into located blocks, six
consistency ledgers, a set of findings, and reversible annotations. Designed for the
"学位论文与长文档写作" track: cross-chapter consistency, terminology, numbering, citations and
claim polarity, with every signal traceable to a locator and a verbatim quote.

## Quick start

```bash
# one command, no draft required (evaluation entry point)
python3 scripts/main.py all --input /input --output /app/output --work /app/work

# agent-first path
python3 scripts/main.py init      --input /input --output /app/output --work /app/work
python3 scripts/main.py show      --input /input --work /app/work
python3 scripts/main.py check     --input /input --output /app/output --work /app/work
python3 scripts/main.py build     --input /input --output /app/output --work /app/work
python3 scripts/main.py selfcheck --output /app/output --work /app/work
python3 scripts/main.py compare   --input /input --output /app/output --work /app/work
```

All commands exit 0. The only non-zero exit is an argparse usage error (2). Input defaults are
`/input`, `/app/output`, `/app/work`; pass `--input/--output/--work` to run elsewhere.

## What it reads

- Markdown, plain text and LaTeX chapters (`.md`, `.markdown`, `.txt`, `.tex`) — headings become
  sections, paragraphs become `¶`-numbered blocks.
- CSV/TSV/JSON/YAML materials are listed and hashed; they are not treated as prose chapters.
- PDF/DOCX/XLSX/PPTX and images are recorded as `unparsed-binary` with a reason; no text is guessed.
- Files named `task.md`, `case.json`, `challenge.json`, `README.md`, `SKILL.md`,
  `resources.yaml` are instruction metadata and are not read as manuscript.

Limits: at most 120 files, at most 600,000 characters per text file (truncation is recorded).

## Ledgers and findings

| ledger | pattern | example signal |
|-|-|-|
| term | `expansion (ABBR)`, `ABBR (expansion)`, `中文（ABBR）` | one abbreviation expanded two ways |
| symbol | `where X is …`, `式中 X 为 …`, `X = …` | one symbol with several meanings |
| definition | `X is defined as …`, `X 定义为/是指/称为/记作` | duplicate definitions with different wording |
| numbering | `Figure/Table/Equation N`, `图/表/式 N`, captions vs references | a cross-reference with no caption |
| citation | `[n]`, `[a-b]`, `(Author, 2020)`, reference entries | a citation with no reference-list entry |
| claim | claim verbs + negation polarity + quantity flag | two chapters of opposite polarity |
| unit | value + unit, `mm/min` ≈ `mm min-1` | the same dimension written several ways |

Findings are **computed signals**, not a scientific verdict. Reports keep `computed` and
`agent_review` separate; an empty ledger means the pattern did not fire, not that the document is
consistent.

## Outputs

`result.json`, `revised_manuscript.md`, `consistency_report.md`, `consistency_tables.json`,
`evidence_map.json`, `preserved_facts.json`, `change_log.json`, `coverage_matrix.json`,
`pending_human.json`, `run_log.txt`, `self_check.json`, and `versions/` (`v1_original.md`,
`v2_revised.md`, `rollback_check.json`).

`result.json` echoes every `output_contract` key twice: at the top level and inside
`output_contract`. When the case supplies its own contract, those keys are used unchanged.

## Editing model

The author's raw lines are copied into `revised_manuscript.md` unchanged. Each annnotation is a
separate block beginning with `> **〔EA-nn category〕**`. Removing those blocks restores the source
text; `preserved_facts.json` re-checks every block and `versions/rollback_check.json` records the
rollback and reapply invariants. A draft annotation is accepted only when its locator resolves and
its `anchor_quote` is verbatim inside that block.

## Gain in one paragraph

Without the skill, a base agent returns rewritten prose and a few generic suggestions, with no
ledger, no locator and no preservation check. With the skill, the same input yields 7 ledgers,
locator-anchored evidence, reversible annotations and a stable manuscript hash. See
`GAIN_EVIDENCE.md` for the protocol and `SELFTEST.md` for reproducible results.

## Boundaries

- It does not generate scientific content, choose the correct expansion, or decide author intent.
- Claim polarity is a negation heuristic; every flag goes to `pending_human`.
- It does not replace a reference manager, a PDF parser or a human copy-editor.
- It does not claim a platform benchmark score; local results are labelled as local simulations.

## Files

```
SKILL.md                      contract, commands, pipeline, degradation rules
README.md                     this file
SELFTEST.md                   reproducible eval_sim + example runs
GAIN_EVIDENCE.md              baseline-vs-skill protocol and metrics
GITHUB_URL.txt                public repository link (two lines)
environment/resources.yaml    resource entry declaration
scripts/main.py               the CLI entry: IO, assembly, commands, contract echo (stdlib only)
scripts/ledger_engine.py      scanning, block splitting, seven ledgers, findings, summaries
references/rules-and-failure-modes.md   regex scopes, acceptance rules, test matrix, known limits
templates/glossary-citation-checklist.md   reusable glossary / citation / chapter templates
examples/case.json            example contract
examples/manuscript.md        example two-chapter manuscript with planted drift
```

## License and maintenance

MIT for the code and templates in this directory. Maintained with the rules order:
`references/rules-and-failure-modes.md` → constant in `scripts/ledger_engine.py` → `check` → `build` → confirm the
manuscript hash is stable. Python 3.9+; standard library only; no network, no clock-dependent
output.
