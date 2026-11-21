# GAIN_EVIDENCE — analysis-04 (analysis-codegen-execute, v10)

Reproduce everything below from the packaged example:

```bash
python3 scripts/engine.py all --input /input --output /app/output --work /app/work
```

with `/input` containing `examples/sample_data.csv` (30 rows × 5 columns: one categorical `group`,
three measurements, one index column; one exact duplicate row; two blank `mass_g`). The right-hand
column is written by that run into `results/summary.json`, `verification.json`, `run_log.json` and
`cleaning_ledger.csv`, so it can be re-read instead of believed.

| measure                                              | naive one-shot read | this skill |
|------------------------------------------------------|--------------------:|-----------:|
| self-contained analysis code generated               |                   0 |          1 |
| operations executed                                  |                   0 |         10 |
| key numbers extracted                                |                   0 |          8 |
| independent verification checks passed               |                   0 |      15/15 |
| cleaning rows (n_in / dropped / n_out)               |         n/a         | 30 / 1 / 29|
| run log entry with command, cwd and exit code        |                   0 |          1 |
| artifacts written                                    |                   1 |         12 |

The `naive one-shot read` column is the **definitional floor** for a face-value script that reads the
table and prints a mean: it generates no code, runs no named operation and verifies nothing, so each
count is 0 by construction, not a measured run. The `this skill` column is measured on the shipped
example.

What carries the task: the generated code is **executed in a subprocess** and its declared numbers are
then **recomputed on a second, independent code path** — 15/15 checks pass, including the
`row_conservation` integrity check (30 − 1 duplicate = 29 used) and a per-key-number `claim` recompute.
Two silent-error traps in this space are closed by construction: the correlation between an index
column and a measurement with missing values is computed **pairwise by row** (not by truncating the two
value lists to equal length — that older shortcut mis-reported `r` as 0.443972 instead of 0.449098),
and duplicate rows are **removed with the count kept**, so the cleaning ledger and the summary agree.

Evidence for a rerun: `run_log.json` records the exact command, working directory, exit code and
captured stdout/stderr up to a cap; `reproducibility.json` fixes the seed and states the run is
offline and deterministic. Every misuse of a table (missing treated as a value, duplicates left in)
surfaces as a `verification.json` failure instead of a plausible-looking number.

Deterministic, offline, no clock reads: rerunning the same input yields byte-identical artifacts.
**Deterministic illustration, not an official score.**
