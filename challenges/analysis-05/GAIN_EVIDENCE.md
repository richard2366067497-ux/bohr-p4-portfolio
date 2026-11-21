# GAIN_EVIDENCE — analysis-05 (sci-analysis-dag, v10)

Reproduce everything below from the packaged example:

```bash
python3 scripts/main.py all --input /input --output /app/output --work /app/work
```

with `/input` containing `examples/sample_data.csv` (30 rows × 5 columns: one categorical `group`,
three measurements, one index column; one exact duplicate row; two blank `mass_g`; two IQR outliers in
`mass_g`). The right-hand column is written by that run into `checkpoint_ledger.jsonl`, `stats.json`,
`data_quality.json` and `result.json`, so it can be re-read instead of believed.

| measure                                            | naive one-shot read | this skill |
|----------------------------------------------------|--------------------:|-----------:|
| pipeline checkpoints (import → clean → stats → fig)|                   0 |          4 |
| row-conservation checked (30 → 29, 1 dropped)      |                   0 |       pass |
| cleaning records (dedupe / impute / flag)           |                   0 |  1 / 2 / 2 |
| descriptive statistic columns                       |                   0 |          5 |
| inferential tests reported                          |                   0 |          3 |
| effect sizes reported (η²)                          |                   0 |          1 |
| p-values bounded to [0,1] and checked               |                   0 |          3 |
| figure elements traced to source columns            |                   0 |          2 |
| artifacts written                                    |                   1 |         12 |

The `naive one-shot read` column is the **definitional floor** for a script that loads the table and
runs one t test: it plans no checkpoints, keeps no ledger and reports no effect size, so each count is
0 by construction, not a measured run. The `this skill` column is measured on the shipped example.

What carries the task: each stage freezes a checkpoint with `rows_in`/`rows_out` and its own checks
(`checkpoint_ledger.jsonl`), so the conservation identity `rows_out + removed == rows_in` (29 + 1 = 30)
is machine-checked at the clean step; the analysis step emits an ANOVA, a Pearson `r` and an OLS fit,
each with an effect size and a p-value verified to lie in `[0,1]`; every figure element maps back to a
source column (`field_mapping.json`). Missing values are imputed by a stated rule (median = 18.6 for
two `mass_g` cells) and outliers are **flagged, not deleted** (IQR 1.5, count 2) — both recorded in
`data_quality.json` rather than applied silently.

Deterministic, offline, no clock reads: rerunning the same input yields byte-identical artifacts.
**Deterministic illustration, not an official score.**
