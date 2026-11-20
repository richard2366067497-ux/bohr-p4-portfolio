# SELFTEST — search-09 · literature-appraisal-benchmark

## 1. how to run

```bash
python3 scripts/main.py all --input <case_dir> --output <out_dir> --work <work_dir>
python3 -c "import json;print(json.load(open('<out_dir>/result.json'))['status'])"
```

`scripts/eval_sim.py` (the local evaluator) is run as `rich × single`, `rich × agent`,
`boundary × single`, `boundary × agent`; all four must end `PASS`.

## 2. abnormal-case test list

Each row is a deliberately hostile case, the expected behaviour, and the artifact that proves it.
These are the checks a naive "summarise the corpus" pass fails.

| # | abnormal case | expected behaviour | proof |
|---|---|---|---|
| 1 | a corrupt JSON material (`broken.json`) | classified `corrupt-json`, skipped, named | `run_log.txt` |
| 2 | an empty material file (`empty.md`) | classified `empty-file`, skipped | `run_log.txt` |
| 3 | a placeholder-only text file (`notes.txt`) | classified `no-data-only`, skipped | `run_log.txt` |
| 4 | no parseable material at all | `status: insufficient_evidence`, all artifacts still written | `result.json` |
| 5 | a parsed material with **no** rules block | a minimal built-in checklist runs; `degradations: rules_fallback` | `result.json.degradations` |
| 6 | a check point whose keyword family has no hit | `not_assessable`, listed in `check_report.json.not_assessable` | `check_report.json` |
| 7 | a negative family outranking the positives | `not_met` at a `major` risk (`R_J2_NEG`) | `grading.json` trace |
| 8 | exactly one anchor for a check point | `partial` at `some` risk (`R_J4_WEAK`) | `grading.json` trace |
| 9 | an abstain ratio ≥ 30% | overall verdict `insufficient_evidence`, not `low_risk` | `result.json.low_risk` |
| 10 | a missing input directory | `status: insufficient_evidence`, exit 0, the searched root named | `result.json.uncertainties` |
| 11 | a material file with a placeholder token in it | the token is normalised on write, never echoed raw | `run_log.txt`, artifacts |

Cases 1–4 and 10 were exercised by the shipped boundary case; cases 5, 6 and 9 by a purpose-built
self-run (a corpus with a rules block but one check point whose family never matches, and a corpus
with no rules block at all). Case 7 and 8 are the `R_J2_NEG` / `R_J4_WEAK` branches of the trace.

## 3. invariants asserted by `selfcheck`

- `materials_scanned` — at least one material file was read.
- `checklist_parsed_or_degraded` — the checklist parsed, or the run degraded explicitly to the
  built-in minimal checklist (`degradations: rules_fallback`).
- `every_cp_has_locator` — every check point carries a source locator (or the list is empty).
- `every_anchor_has_quote` — every anchor carries a verbatim quote, so no judgment is uncited.
- `every_material_has_sha` — every material has a content hash, so the run is reproducible.

## 4. observed results

| case | mode | status | exit | output files | contract keys (source) |
|---|---|---|---|---|---|
| rich | single | partial | 0 | 11 | 4 (`case.json:output_contract`) |
| rich | agent | partial | 0 | 11 | 4 (`case.json:output_contract`) |
| boundary | single | insufficient_evidence | 0 | 13 | 4 (`SKILL.md` json sample) |
| boundary | agent | insufficient_evidence | 0 | 13 | 4 (`SKILL.md` json sample) |

Rich-case counts: 46 check points, 45 keyword families, 11 study types, 2 generators, 4 judgment
rules, 3 thresholds, 111 anchors, 126 corpus lines; dimension risk `DESIGN some`, `SAMPLE low`,
`MEASURE low`, `STATSREP some`, `BIAS major`; overall `high_risk`. The trace re-derives 46/46 from
the anchor counts alone (see `GAIN_EVIDENCE.md` §3).

Extra self-runs (not part of `eval_sim`): a corpus with one never-matching family → `not_assessable`
for that check point; a corpus with no rules block → 10 built-in check points and
`degradations: rules_fallback`; a missing input directory → `insufficient_evidence`, exit 0, searched
root named. All three exit 0 and write every artifact.
