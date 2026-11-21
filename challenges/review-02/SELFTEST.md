# SELFTEST — citation-fact-audit (review-02, v10)

Measured, not estimated. Reproduce with
`python3 scripts/eval_sim.py --pkg work/p4/v10/review-02 --case work/p4/synth_cases/review-02/<case> --mode <single|agent>`.

## 1. Evaluator simulation, the four combinations

| case | mode | status | failures | warnings |
|------|------|--------|---------:|---------:|
| rich | single | PASS | 0 | 0 |
| rich | agent | PASS | 0 | 0 |
| boundary | single | PASS | 0 | 0 |
| boundary | agent | PASS | 0 | 0 |

Both cases resolve all contract keys with a non-empty value and zero placeholder hits. Single mode runs the
documented one-shot entry; agent mode runs `init`, writes the draft from the SKILL.md sample, then `check`,
`build`, `selfcheck`.

## 2. The run itself

`python3 scripts/main.py all --input <case> --output <out> --work <work>` exits 0 and writes `result.json`,
`citation_report.md`, `manuscript.md`, `evidence.jsonl`, `index.json`, `run_manifest.json`.

## 3. Contract and degradation

With a case contract the keys are echoed verbatim; without one the package declares its six standard keys, so a
null-contract case still gets a filled `output_contract`, a `deliverable` that resolves to the written report,
and non-empty `evidence_map` / `change_log` / `coverage`. No analysable material yields `status: input_error` or
`partial` with declared degradations and exit 0. All JSON is written through a null-free sanitiser, so no
delivered artifact carries `null` tokens.

## 4. Expert gate and budget

- Execution starts by reading `references/expert_playbook.md`; delivery passes its §8 18-item checklist. Any
  unmet item is reported as `status=partial` with the open items in the uncertainty list.
- Budget, as measured: **14 files**, total under the 150 KB allowance, largest file `scripts/audit_core.py`
  ~29.7 KB against the 30 KB limit. Standard library only, no network, deterministic.
