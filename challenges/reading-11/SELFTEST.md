# SELFTEST — reading-11 · table-cleaning-benchmark

## 1. how to run

```bash
python3 scripts/main.py all --input <case_dir> --output <out_dir> --work <work_dir>
python3 -c "import json;print(json.load(open('<out_dir>/result.json'))['status'])"
```

`scripts/eval_sim.py` (the local evaluator) is run as `rich × single`, `rich × agent`,
`boundary × single`, `boundary × agent`; all four must end `PASS`.

## 2. abnormal-case test list

Each row is a deliberately hostile case, the expected behaviour, and the artifact that proves it.
These are the checks that a naive cleaner fails.

| # | abnormal case | expected behaviour | proof |
|---|---|---|---|
| 1 | two identical rows (`TiO2` / `titanium dioxide`, same value) | exactly one duplicate group is reported, not a silent merge | `duplicates.json` |
| 2 | an arbitrary unit (`a.u.`) | row held, unit listed, never converted | `unknown_units.json`, `pending_review.json` |
| 3 | an unreported value (`n.r.`) | row held, no number invented | `pending_review.json`, `cleaned_table.csv` status `held` |
| 4 | a typo indicator (`bank gap`) | normalised to `band gap` with rule `R_IND` | `change_log.json` |
| 5 | an alias material (`TiO2`, `SiO2`) | mapped to the canonical name with rule `R_ALIAS` | `change_log.json` |
| 6 | a trailing-zero value (`3.20`) | normalised to `3.2` with rule `R_VAL` | `change_log.json` |
| 7 | a range value (`12-15`) | kept verbatim, never parsed into a single number | `cleaned_table.csv` |
| 8 | a corrupt JSON material (`broken.json`) | classified `corrupt-json`, skipped, named | `run_log.txt` |
| 9 | an empty material file | classified `empty-file`, skipped | `run_log.txt` |
| 10 | a placeholder-only text file | classified `no-data-only`, skipped | `run_log.txt` |
| 11 | no data row at all | `status: insufficient_evidence`, artifacts still written | `result.json`, `cleaned_table.csv` |
| 12 | a missing input directory | `status: input_error`, exit 0 | `result.json` |

## 3. invariants asserted by `selfcheck`

- `materials_scanned` — at least one material file was read.
- `no_invented_value` — every held row has an empty value (nothing was guessed).
- `every_row_has_locator` — every collected row carries a `M##/rec#` or `M##/row#` locator.
- `every_material_has_sha` — every material has a content hash, so the run is reproducible.

## 4. observed results

| case | mode | status | exit | output files | contract keys |
|---|---|---|---|---|---|
| rich | single | partial | 0 | 18 | 7 |
| rich | agent | partial | 0 | 18 | 7 |
| boundary | single | insufficient_evidence | 0 | 18 | 7 |
| boundary | agent | insufficient_evidence | 0 | 18 | 7 |
