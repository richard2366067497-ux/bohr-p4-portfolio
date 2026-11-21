# GAIN_EVIDENCE

Every number below is produced by the package, not asserted by it. The measurement is
`python3 scripts/main.py compare --input <case> --work <work>`, which loads the same input twice in one
run: once the way the skill does it, and once as a baseline that

> reads the table at face value, prints a mean per column and runs one t test on the first two levels:
> no plan, no gate, no interval and no locator.

The comparison lands in `<work>/compare_report.json`, so the table can be re-derived instead of believed.
Measured on the packaged example (`examples/sample_data.csv`, 30 rows: two exact duplicates, three blank
`mass`, two Tukey outliers, nine columns):

| measure                | baseline | this skill | delta |
|------------------------|---------:|-----------:|------:|
| records analysed       |       30 |         30 |     0 |
| cleaning steps counted |        0 |          7 |    +7 |
| inferential rows       |        1 |         10 |    +9 |
| gate checks recorded   |        0 |         29 |   +29 |
| effect sizes reported  |        0 |         15 |   +15 |
| 95% intervals          |        1 |         14 |   +13 |
| multiplicity-corrected |        0 |         10 |   +10 |
| evidence rows          |        0 |         25 |   +25 |
| figures                |        0 |          5 |    +5 |
| artifacts written      |        1 |         11 |   +10 |
| degradation triggers   |        0 |          0 |     0 |

The four deltas that carry the task:

1. **One method per question, chosen by gates.** The baseline runs a single t test and stops. This run
   forms six questions from the columns present (descriptive, two-group, multi-group, contingency,
   association, paired), records 29 gate verdicts and selects the test that fits each design:
   `student_t`, `paired_t` and `fisher_exact` where both parametric gates pass, `mann_whitney_u`,
   `kruskal_wallis` and `spearman_rho` where normality or equal variance fails. Rejected siblings stay in
   the ledger with `selected: false` and a reason, so the choice is auditable rather than implied.
2. **Numbers with intervals, not bare p values.** 15 effect sizes, 14 intervals, 10 inferential rows
   passing through Holm inside their family (descriptive rows are their own family).
3. **Every number bound to a source.** 25 evidence rows, each with a locator, a verbatim quote and a
   `sha256_16` that `self_check.json` re-derives (`evidence_verifiable`).
4. **Cleaning that is counted.** Two exact duplicate rows dropped, three empty cells kept and counted,
   two Tukey outliers flagged and kept - 7 counted steps, 30 records read, 28 analysed, printed in
   `report.md` and in `result.json -> summary`.

On the two synthetic degradation cases (`rich`, `boundary`) the input carries no analysable table, so
baseline and skill both run zero tests: the gain there is not a test, it is that the run says so -
`status: insufficient_evidence`, all 8 contract keys returned as `computed: false` with a reason and a
requirement, and 2 respectively 4 degradation triggers declared instead of a silently empty deliverable.
