---
name: stats-decision-ledger
description: Turn one messy research table into a reproducible statistics package. It reads the real file, cleans it while counting every step, runs the fixed gate order (sample size, normality, equal variance, independence, multiplicity family), picks exactly one method per question, publishes the rejected alternatives beside the finding, binds every number to a locator plus a verbatim quote, and writes a ledger, a report, a PDF preview and figures. Reports honest degradation when the input carries no analysable data.
license: MIT
---

# Statistical analysis and result interpretation

Use this skill when a research dataset has to become an auditable answer: descriptive statistics with
units, an inferential test that matches the design, an effect size with a 95% interval, and an
interpretation a researcher can use. The data are observational, so a difference or an association is
reported as such and never as a cause.

## Output contract

Every key of `case.json -> output_contract` is echoed inside `result.output_contract`, carrying the
block this run produced or the reason that key could not run - never a substitute number:

```json
{
  "output_contract": {
    "student_t": "the student_t block from this run, or the reason it did not run",
    "mann_whitney_u": "the mann_whitney_u block from this run, or the reason it did not run",
    "kruskal_wallis": "the kruskal_wallis block from this run, or the reason it did not run",
    "wilcoxon_signed_rank": "the wilcoxon_signed_rank block from this run, or the reason it did not run",
    "spearman_rho": "the spearman_rho block from this run, or the reason it did not run",
    "ols_slope": "the ols_slope block from this run, or the reason it did not run",
    "fisher_exact": "the fisher_exact block from this run, or the reason it did not run",
    "descriptive": "the descriptive block from this run, or the reason it did not run"
  }
}
```

A filled block holds `method`, `result_id`, `decision_id`, `selected_by_gates`, `design`,
`estimate_type`, `groups`, `n`, `df`, `statistic_name`, `statistic`, `p`, `p_adj`, `estimate_point`,
`ci_95`, `ci_method`, `effect_size{type,value,ci_95,ci_method,direction}`, `unit`, `status`,
`gate_results`, `candidates[]`, `note`. A key that could not run holds `computed: false`, `reason`,
`requirement`, `input`, `degradations`.

## Draft shape (the only file an agent writes)

An agent may write `work/draft.json` before running the engine, never as an answer: every decision is
recomputed, and a draft value that disagrees with the recomputed one is kept as a change record.

```json
{
  "case_id": "example-analysis-02",
  "data_plan": {
    "missing": {"policy": "mark_only", "columns": ["mass_g"]},
    "duplicates": {"policy": "drop_exact", "keys": []},
    "outliers": {"policy": "flag", "rule": "tukey_1.5iqr", "columns": ["mass_g"]},
    "units": {"mass_g": "g"}
  },
  "items": [
    {
      "decision_id": "D-02",
      "question_id": "Q2",
      "design": "two_independent_groups",
      "variables": {"outcome": "mass_g", "group": "group"},
      "candidates": [{"method": "mann_whitney_u"}],
      "chosen_method": "mann_whitney_u",
      "multiple_comparison_family": "primary",
      "correction": "holm"
    }
  ]
}
```

`items` is the decision list; `decisions` is accepted too. Policies: `missing: listwise|pairwise|
mark_only`, `duplicates: drop_exact|keep|flag_only`, `outliers: keep|flag|winsorize|exclude`. An unknown
policy, or a column absent from the loaded table, is rejected into the change records rather than
silently applied; an unknown question id, or an unresolvable design or method, is skipped and counted.
Without a draft: keep the empty cell and count it, drop exact repeats, flag outliers with Tukey fences
and keep them.

## Single command entry (one shot, no draft needed)

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

That one command reads the case, cleans the table, runs the gates, fills every contract key, writes all
deliverables under the output directory and exits 0. Every path is a flag or an environment variable;
input, output and work default to `/input`, `/app/output`, `/app/work`.

## Agent path (same engine, plus a draft)

```bash
python3 /skills/weekly-skill/scripts/main.py init --input /input --work /app/work
python3 /skills/weekly-skill/scripts/main.py build --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py selfcheck --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py compare --input /input --work /app/work
```

`init` lists the questions this input can support - a suggestion, never read back as a plan. `build` is
the whole pipeline of `all`. `selfcheck` re-reads the artifacts it just wrote and fails loudly if a
number drifted. `compare` measures the baseline (load at face value, one t test, no gates) against this
run, so the gain is a measurement and not a claim.

## Input

- `case.json` (or `challenge.json`) with `case_id`, `language`, `materials_root` and the
  `output_contract` object; those keys are authoritative and this skill never invents keys.
- the materials it points at: CSV, TSV, JSON, JSONL, SQLite, Markdown or text. Anything else is
  snapshotted byte for byte and named in the manifest instead of guessed at.
- optionally the draft above.

## Files under the output directory

Eleven files come from one pass: `result.json` (machine answer), `results_ledger.json` (every result)
and its flat projection `statistics_table.csv`; `cleaned_data.csv` (analysis table, one quality flag per
row); `evidence.json` (one row per number: locator, verbatim quote, sha256_16); `decision_log.json`
(per-decision trace); `input_manifest.json` and `reproducibility.json` (input hashes, seed, one hash per
artifact); `report.md` and `report.pdf` (readable report); `self_check.json` (audits the other ten).

## Method and gate rules

The question list follows the columns present: a descriptive question always, a two-group question when
a two-level column exists, a multi-group question for three or more levels, a contingency question for
two two-level columns, an association question for two numeric columns, and a paired question only when
the names declare a pairing such as `pre`/`post`. Pairing is never invented and a group is never
manufactured by splitting a numeric column.

The gate order is fixed and printed with every verdict: sample size, normality (Jarque-Bera, needs at
least eight observations), equal variance (Brown-Forsythe on medians), independence, multiplicity.
One method is selected per question: `student_t` needs both parametric gates, otherwise the rank sibling
`mann_whitney_u` carries the finding; `one_way_anova` gives way to `kruskal_wallis`, `paired_t` to
`wilcoxon_signed_rank`, `pearson_r` to `spearman_rho` when normality fails or values carry ties.
`fisher_exact` is the 2x2 test reported here, with its smallest expected count stated. Alternatives are
computed anyway and kept in the ledger marked as not selected, so a reader sees what lost and why.
Inferential rows pass through Holm inside their family; descriptive rows are never corrected. Every p
value is two-sided and every interval is 95%.

## Honest degradation

Triggers are recorded, never hidden: a missing or invalid draft (defaults are used), no decisions, an
unresolved variable (that decision is skipped, the rest continue), empty groups, a gate value that
disagrees with the draft (the recomputed value wins, the draft value is kept for audit), a test that
fails internally, an effect size that cannot be computed, a missing interpretation (one is generated and
marked as auto generated), an automatically formed correction family, an unreadable material
(snapshotted and named), no analysable data (the ledger stays empty) and a failed artifact write (a
partial `result.json` is still written). Status is `ok`, `partial` or `insufficient_evidence`.

## What this skill will not do

- It will not claim a cause: the banned expressions (proves, proven, proved, confirmed causal, no
  difference exists) block the interpretation if they appear and are listed in the lint record.
- It will not report a p value without its effect size and, where one exists, its interval.
- It will not remove a row or a value without recording how many and why.
- It will not present a method the gates did not select as the finding.
- It will not split a numeric column into groups to manufacture a design, nor pair columns that do not
  declare a pairing.

## Limits

Standard library only, no network, no clock, fixed seed 20240517, deterministic byte for byte; below
eight observations per group only rank and descriptive methods run. Bootstrap intervals (1000 draws) may
move in the last digit with the seed. The PDF preview is plain ASCII text and the figures are SVG with
labels. A file larger than the size cap is read up to the cap and the truncation is reported.
