# stats-decision-ledger

One messy research table in, one auditable statistics package out: descriptive statistics with units, the
inferential test the design and the gates allow, an effect size with a 95% interval, an interpretation a
researcher can use, and a ledger in which every number carries a locator and a verbatim quote.

## Run it

```bash
# the whole pipeline in one shot: no draft needed, exit 0
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

The agent path runs the same engine step by step: `init` (candidate questions), `build` (the whole
pipeline), `selfcheck` (re-reads the artifacts it just wrote), `compare` (measures a baseline against this
run), plus `show` and `check`. Paths default to `/input`, `/app/output` and `/app/work`, and each is also a
flag. The contract echo, the draft sample and the gate rules are documented in `SKILL.md`.

## Input

`case.json` (`challenge.json` works too) carries `case_id`, `language`, `materials_root` and the
`output_contract` object, whose keys are authoritative: `{"student_t": "two-group comparison",
"kruskal_wallis": "multi-group comparison", "fisher_exact": "2x2 table", "descriptive": "per-column
summary"}` is a complete, valid contract. Materials may be CSV, TSV, JSON, JSONL, SQLite, Markdown or
text; anything else is snapshotted byte for byte and named in the manifest. A draft is optional and never
wins over the gates. Put such a case beside `examples/sample_data.csv` and run `all` on the directory:
6 questions, 15 ledger rows, 25 evidence rows, 5 figures, `status: ok`.

## What lands in the output directory

Eleven files, plus `charts/*.svg`, `logs/run.log` and `raw_snapshot/*.bin`: `result.json`,
`cleaned_data.csv`, `statistics_table.csv`, `results_ledger.json`, `evidence.json`, `decision_log.json`,
`input_manifest.json`, `reproducibility.json`, `report.md`, `report.pdf`, `self_check.json`.

## How a method is chosen

The gate order is printed with every verdict: sample size, normality (Jarque-Bera, from eight
observations), equal variance (Brown-Forsythe on medians), independence, multiplicity family. One method
is selected per question; the parametric one needs both parametric gates, otherwise its rank sibling takes
over (`mann_whitney_u`, `kruskal_wallis`, `wilcoxon_signed_rank`, `spearman_rho`). Losing candidates are
computed anyway and kept in the ledger marked as not selected, with the reason. Inferential rows pass
through Holm inside their family; descriptive rows are never corrected.

## What this package will not do

It will not claim a cause from observational data, report a p value without an effect size, remove a row
without counting it, present a method the gates did not select as the finding, split a numeric column to
manufacture a group, or pair columns that do not declare a pairing. When the input carries no analysable
data it says so: `status: insufficient_evidence`, every contract key returned as `computed: false` with a
reason, the ledger empty rather than padded.

## Package contents

`SKILL.md`, this file, `SELFTEST.md`, `GAIN_EVIDENCE.md`, `GITHUB_URL.txt`, `environment/`, `examples/`,
and `scripts/` (`main.py`, `engine.py`, `stats.py`, `dataio.py`, `report.py`; standard library only, fixed
seed 20240517, deterministic byte for byte).
