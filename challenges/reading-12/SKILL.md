---
name: extraction-table-cleaner
version: 1.0.0
description: >-
  Turn a literature extraction table into a cleaned, unit-normalised table that stays auditable:
  resolve each column to a role from the field dictionary, parse number / range / ±error / missing
  cells, normalise units to one label per (field, dimension) with a logged before * factor + offset,
  normalise names only on an exact synonym hit, and decide duplicates, replicates and conflicts by a
  judgment key rather than by row order. Every changed value and every row held back carries a
  row_id + rule_id + source_locator back to the input, and anything the source does not state stays
  empty instead of being guessed. Use when a task asks for 文献数据清洗 / 提取表标准化 / 单位换算 /
  同名同义合并 / 数据可追溯 with a reproducible cleaning path. Pure standard library, offline,
  deterministic.
---

# extraction-table-cleaner

An extraction table is a claim about the literature, so cleaning it must be replayable. This skill
maps columns to roles, parses each value cell, converts units only inside one dimension, merges
duplicates, keeps conflicting values side by side, and gives every change a rule id and a locator.
Nothing is invented: a missing cell stays empty, an unresolvable unit is queued, never guessed.

## 0. result.json contract

Every key below is echoed both at the top level of `result.json` and inside its `output_contract`
object; `case_id` is passed through unchanged. When the case supplies its own `output_contract`,
those keys are used instead and each is filled the same way (an artifact-like key resolves to the
written file, any other key gets a real derived value).

```json
{
  "output_contract": {
    "case_id": "the input case id, passed through",
    "status": "answered | partial | insufficient_evidence | input_error",
    "deliverable": "cleaned.csv",
    "evidence_map": "the locator-anchored change and review records",
    "change_log": "the per-change audit rows",
    "coverage": "coverage.json"
  }
}
```

## 1. Draft schema (JSON, optional)

An agent may fill `/app/work/draft.json` with its own reading of the table; `build` merges it for
provenance, and the deterministic cleaner still runs regardless, so a thin draft cannot turn an
unreadable table into an invented number. Print the skeleton with
`show --part draft`.

```json
{
  "case_id": "",
  "case_summary": "",
  "field_map": {},
  "records": [],
  "groups": [],
  "claims": [],
  "pending": [],
  "unmapped_columns": [],
  "uncertainties": []
}
```

## 2. 单命令（等价入口，one-shot，评测入口）

Run this single command; with no draft it still writes every artifact and a complete
`result.json`, and exits 0:

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

## 3. agent-first 增强路径（可选，质量更高）

List the material with locators, fill the draft above, then check it before `build` merges it:

```bash
python3 /skills/weekly-skill/scripts/main.py init      --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py show      --input /input --work /app/work
python3 /skills/weekly-skill/scripts/main.py check     --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py build     --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py selfcheck --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py compare   --input /input --output /app/output --work /app/work
```

`show` prints each source line with a `M02/p9` locator; `check` reports whether grounded rows and
changes exist; `compare` writes a base-vs-skill contrast to `/app/work/compare_report.json`.

## 4. Pipeline

1. Index every file under `/input` with its kind, size and parse status (`parsed` / `empty-file` /
   `placeholder-only` / `unparsed-binary`).
2. Classify the materials: the field dictionary (roles / synonyms / target_fields), the rule catalog
   (`rules`), the unit table (`units`) and the extraction records (`records` / `rows` / a JSON array
   or JSONL).
3. Resolve each column to a role — exact synonym, word-boundary synonym, or a `indicator (unit)`
   header whose unit is lifted out — and declare the rest as unmapped rather than dropping them.
4. Parse each value cell: number, scientific notation, thousands separators, `±`/`+/-` error,
   `a to b` range, or a missing marker.
5. Resolve the unit (exact, alias, prefix composition, NFKC folding) and convert inside one
   dimension with `after = before * factor + offset`, scaling the error and never offsetting it.
6. Group rows by judgment key (source, conditions, indicator, material) into duplicates, replicates
   and conflicts using the catalog tolerance.
7. Emit the audit trail: one change row per conversion with its rule id and locator, one review row
   per held value, and a coverage/uncertainty summary.

## 5. Artifacts written to `--output`

| file | content |
|-|-|
| `result.json` | every contract key (top level + `output_contract`), case_id, status, digest, claims, sources, uncertainties, change_records, artifacts |
| `cleaned.csv` | the deliverable: one row per record with value, unit, judgment key, status and the rule ids applied |
| `change_log.csv` | one row per change: before, factor, offset, after, precision, rule_id, formula, locator |
| `pending_review.csv` | values held back with a reason code and a suggested action |
| `anomaly_report.md` | bucket counts, method, the queued detail and the rows |
| `rules.json` | the rule base in force, its tolerance and any suppressed rule |
| `field_mapping.json` | the role/synonym map actually used and the declared unmapped columns |
| `unit_table.json` | the units, prefixes and canonical targets used, with the unit tokens actually seen |
| `evidence_map.json` | every change and every queued row with row_id, rule_id and source_locator |
| `coverage.json` | records in, rows out, converted, missing, review, duplicates, replicates, conflicts |
| `run_log.txt` | per-material parse status and the stage counts |

## 6. Degradation rules

- No extraction records, or no field dictionary and no unit table → `status=insufficient_evidence`;
  every artifact still carries a structured no-data record naming the searched locations; exit 0.
- Some values unresolvable (unknown or ambiguous unit, unparsed cell, dimension mismatch) →
  `status=partial` and the affected rows are queued instead of being guessed.
- A conflicting group keeps both values and is queued; a conversion never resolves a scientific
  disagreement.
- A name is normalised only on an exact synonym hit; a near match is left alone.
- Empty / binary / placeholder-only file → recorded with its parse status, never quoted.
- No network, no third-party package, no invented numbers.

## 7. Package map

| path | role |
|-|-|
| `SKILL.md` | name, contract, single command, agent path, draft schema, pipeline, degradation rules |
| `scripts/main.py` | the CLI: all / init / show / check / build / selfcheck / compare |
| `scripts/engine.py` | the cleaner: scan, classify, parse, convert, group (imported by the CLI) |
| `environment/resources.yaml` | entry declaration: commands, paths, inputs, contract, runtime |
| `examples/` | a dirty mini batch and the geometry of a clean run |
| `templates/result_contract.json` | a reusable contract skeleton |
| `README.md`, `SELFTEST.md`, `GAIN_EVIDENCE.md`, `GITHUB_URL.txt` | usage, stability evidence, gain evidence, portfolio link |
