# GAIN_EVIDENCE — analysis-03 (figure-spec-publisher, v10)

Reproduce everything below from the packaged example:

```bash
python3 scripts/engine.py all --input /input --output /app/output --work /app/work
```

with `/input` containing `examples/sample_data.csv` (30 rows × 5 columns: one categorical `group`,
four numeric columns, one exact duplicate row, two blank `mass_g`). Every number in the right-hand
column is written by that run into `result.json` / `figure_specs.json` / `audit.json` /
`cleaning_log.json` and can be re-read there.

| measure                                            | naive one-shot read | this skill |
|----------------------------------------------------|--------------------:|-----------:|
| figure specs (with rationale)                      |                   0 |          4 |
| rejected chart types, each with a reason           |                   0 |          8 |
| figure-element → source-column mappings            |                   0 |          4 |
| field roles classified (continuous/categorical)    |                   0 |          5 |
| cleaning records                                   |                   0 |          1 |
| audit checks passed                                |                   0 |        5/5 |
| captions readable without the body text            |                   0 |          1 |
| drawing-code skeleton                              |                   0 |          1 |
| artifacts written                                  |                   1 |         11 |

The `naive one-shot read` column is the **definitional floor** for a script that loads the table and
plots the first numeric column: it performs none of these steps, so each count is 0 by construction,
not a measured run. The `this skill` column is measured on the shipped example.

What carries the task: four specs each name the chart type **and** at least two rejected siblings with
a reason (`audit.json → specs_have_rejected_types`); every planned visual element maps back to a source
column (`data_to_figure.json → mapping`); the four numeric fields are classified with n / missing /
mean / SD so a reader can see `mass_g` has 2 missing values before trusting any figure.

Bounds are reported, not hidden: the sample ships with no data dictionary, so axes carry **no unit** —
the run does not invent "g" or "cm"; with a dictionary present the unit is passed through verbatim.
The one duplicate row and the two blanks are recorded in `cleaning_log.json`, never silently dropped.

Deterministic, offline, no clock reads: rerunning the same input yields byte-identical artifacts.
**Deterministic illustration, not an official score.**
