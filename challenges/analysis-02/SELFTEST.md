# SELFTEST — stats-decision-ledger (analysis-02, v10)

Measured, not estimated. Reproduce with
`python3 scripts/eval_sim.py --pkg work/p4/v10/analysis-02 --case work/p4/synth_cases/analysis-02/<case> --mode <single|agent>`.

## 1. Evaluator simulation, the four combinations

| case | mode | status | exit | warnings | failures |
|------|------|--------|-----:|---------:|---------:|
| rich | single | PASS | 0 | 0 | 0 |
| rich | agent | PASS | 0 | 0 | 0 |
| boundary | single | PASS | 0 | 0 | 0 |
| boundary | agent | PASS | 0 | 0 | 0 |

Agent mode runs the documented commands (`init`, `build`, `selfcheck`, `compare`) and writes the draft from
the SKILL.md sample; its `result.json` differs because that draft is applied into change records. Both
cases resolve 8 of 8 contract keys with zero empty-shell hits.

## 2. The worked example

`python3 scripts/main.py all` on the packaged example: `status=ok`, 30 records read, 28 analysed, 6
questions, 15 ledger rows (10 inferential), 10 corrected by Holm, 25 evidence rows, 5 figures, 18 files,
`self_check.json` PASS 9/9 (`contract_filled` 8/8 · `p_in_range` · `evidence_verifiable` ·
`report_matches_ledger` · `interpretation_rules` · `seed_and_hashes` · `no_shell_tokens`).

## 3. Determinism and honest degradation

Three consecutive `build` runs give 0 differing files (example 18, rich 15, boundary 17) and self_check
PASS; JSON uses `newline=""`, so bytes match across platforms. The two synthetic cases carry no analysable
table: `status=insufficient_evidence`, all 8 keys `computed: false` with a reason, all eleven artifacts
still written, exit 0.

## 4. Expert gate and budget

- Execution starts by reading `references/expert_playbook.md`; delivery passes its §6 19-item checklist.
  Any unmet item is reported as `status=partial` with the open items in the uncertainty list.
- Budget, as measured: **13 files**, total under the 150 KB allowance, largest file `scripts/engine.py`
  ~29.3 KB against the 30 KB limit. Standard library only, fixed seed 20240517.
