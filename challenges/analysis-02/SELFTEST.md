# SELFTEST

Measured, not estimated. Reproduce with
`python3 scripts/eval_sim.py --pkg work/p4/v9/analysis-02 --case work/p4/synth_cases/analysis-02/<case> --mode <single|agent>`.

## 1. Evaluator simulation, the four combinations

| case | mode | status | exit | wall | output files | work files | warnings | failures |
|------|------|--------|-----:|-----:|-------------:|-----------:|---------:|---------:|
| rich | single | PASS | 0 | 0.32s | 15 | 1 | 0 | 0 |
| rich | agent | PASS | 0 | 0.17s | 15 | 4 | 0 | 0 |
| boundary | single | PASS | 0 | 0.31s | 17 | 1 | 0 | 0 |
| boundary | agent | PASS | 0 | 0.16s | 17 | 4 | 0 | 0 |

Agent mode runs six documented commands (`init`, `build`, `selfcheck`, `compare`, `show`, `check`) and
writes the draft from the SKILL.md draft sample; its `result.json` therefore differs from single mode
(10,071 vs 9,608 bytes on `rich`), because that draft is read and applied, field by field, into change
records. Both cases resolve 8 of 8 contract keys with zero empty-shell hits.

## 2. The worked example, end to end

`python3 scripts/main.py all` on the packaged example: `status=ok`, 30 records read, 28 after cleaning,
2 removed, 5 numeric columns, 6 questions, 6 decisions, 0 skipped, 15 ledger rows (10 inferential,
5 descriptive), 10 rows corrected by Holm, 25 evidence rows, 5 figures, 18 files, `self_check.json` PASS
with 9 of 9 checks: `artifacts_present` (10 judged substantive) · `contract_filled` (8 of 8 keys carry a
block) · `ledger_projection` (15 rows, same result ids) · `p_in_range` · `evidence_verifiable` (25 quotes
re-derive their `sha256_16`) · `report_matches_ledger` (15 of 15 printed) · `interpretation_rules` (no
banned expression) · `seed_and_hashes` (15 hashed artifacts, 3 stated as written in the same pass) ·
`no_shell_tokens` (16 text artifacts swept).

## 3. Determinism

Three consecutive `build` runs into the same output directory: example 18 files, rich 15, boundary 17 -
0 differing files in all three, self_check PASS. The artifact inventory in `result.json` and
`reproducibility.json` is declared rather than read off the directory, so a repeated run cannot list
files an earlier run left behind; JSON is written with `newline=""`, so bytes match on Windows and Linux.

## 4. Honest degradation, as measured

| case | status | contract keys not computed | degradation triggers |
|------|--------|---------------------------:|----------------------|
| rich | insufficient_evidence | 8 of 8, each with reason + requirement | `draft_missing`, `no_analyzable_data` |
| boundary | insufficient_evidence | 8 of 8, each with reason + requirement | the same, plus 2 × `index_note` |

Both still write all eleven artifacts, exit 0 and pass their own self-check: the empty ledger is stated,
never padded.

## 5. Package budget, as measured

12 files. Total 149.7 KB against the 150 KB allowance; largest file 29.3 KB (`scripts/engine.py`) against
the 30 KB limit. Standard library only, no network, no clock, fixed seed 20240517.
