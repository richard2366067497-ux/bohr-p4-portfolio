# GAIN_EVIDENCE

Every number below is produced by the package. The measurement is
`python3 scripts/main.py compare --input <case> --work <work>`: it loads the input twice, once as the skill
does it and once as a baseline that reads the table at face value, prints a mean per column and runs one
t test on the first two levels (no plan, no gate, no interval, no locator). It lands in
`<work>/compare_report.json`, so the table can be re-derived instead of believed.

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

The deltas that carry the task: one method per question chosen by 29 recorded gate verdicts, rejected
siblings kept as `selected: false`; 15 effect sizes and 14 intervals instead of bare p values; every
number bound to 25 evidence rows with a locator, a verbatim quote and a re-derived `sha256_16`; counted
cleaning (7 steps, 30 read, 28 analysed).

On the two synthetic degradation cases both sides run zero tests: the gain is that the run says so -
`status: insufficient_evidence`, all 8 keys `computed: false` with a reason, declared triggers instead of
a silently empty deliverable. Deterministic simulated comparison, **not an official score**.
