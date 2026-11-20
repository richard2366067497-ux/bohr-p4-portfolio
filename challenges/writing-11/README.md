# manuscript-revision-desk — v6 repair package (writing-11)

Source-preserving manuscript revision desk for the Bohr P4 challenge **writing-11**
(学位论文与长文档写作 / manuscript revision). The package is offline, pure standard
library, and produces a complete deliverable set from a single command even when no
draft, no case file, or no usable chapter is supplied.

## Entry

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

Agent-first path (optional): `init` → `show` → write `work/draft.json` → `check` → `build` → `selfcheck`.

## Deliverables

`result.json` (contract echoed key-by-key at top level and under `output_contract`),
`revised_manuscript.md`, `evidence_map.json`, `preserved_facts.json`, `change_log.json`,
`version_compare.md`, `operation_log.json`, `task_receipt.json`, `export_preview.md`,
`original_snapshot.json`, `manifest.json`; `selfcheck` adds `verify_report.json`.

## Guarantees

- Original sentences, numbers, tables, formulas and citations are copied verbatim;
  only annotation blocks are appended after the targeted anchored paragraphs.
- Every annotation carries a locator and a verbatim source quote; quotes are verified.
- Rollback removes the annotation blocks and restores the original hash; reapply
  restores every annotation. A deliberate empty-replacement operation is rejected
  with an error code and an unchanged state hash.
- Empty or broken input still exits 0 with a legal `result.json` and honest limits.
- No placeholders are emitted: all output text is sanitised at the end of a run.

## Layout

```
SKILL.md                         entry contract, rules, degradation, self-check
scripts/main.py                  pipeline + CLI (all/init/show/check/build/selfcheck)
references/workorder_contract.md workorder fields, annotation policy, version control
README.md                        this file
SELFTEST.md                      reproduction steps and expected observations
GITHUB_URL.txt                   submission repository URL and challenge path
```
