---
name: experiment-interpretation-dossier
description: Turn a batch of experimental readout material into a reviewable interpretation dossier — the five checkable conclusions (trend, anomaly point, candidate causes, recheck steps, next-round experiment) each tied to a locator and a verbatim quote, the screening rules R1-R9, the unit dictionary and the threshold constants indexed from the material, a definitional statistic ledger recomputed on a fixed fixture, and the anomalies bound to their sample, batch, channel or estimator-fold. Use when a task asks what a batch of readouts shows, which point is genuinely off and by how much, what may have caused it, what to recheck, or what to run next.
version: 2.6.0
---

# experiment-interpretation-dossier

## 0. result.json contract

`result.json` carries every key of the case's `output_contract`, both at the top level and
inside a nested `output_contract` object. When the case does not declare one, the sample
below applies:

```json
{"output_contract": {"id": "string", "case_id": "string", "time_course": "string",
 "deviation": "string", "mechanism": "string", "dataset": "string", "parameter": "string",
 "limitation": "string", "answered": "string", "partial": "string",
 "insufficient_evidence": "string", "input_error": "string"}}
```

`case_id` is passed through unchanged. `status` is one of `answered`, `partial`,
`insufficient_evidence`, `input_error`. No key is ever empty and no empty-value token is
written into any artifact.

## 1. 单命令（one-shot，评测入口）

```
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

One command runs the whole pipeline: scan every input file → index the screening rules, the
unit dictionary and the threshold constants with a locator and a verbatim quote → recompute the
screening definitions on a fixed five-value fixture → screen any numeric column with the
modified-z, IQR-fence, duplicate and saturation rules → organise the five conclusions → render
the artifacts → fill the contract → sweep empty-value tokens. It works with no draft present,
prints a one-line summary and exits 0. Empty input, malformed JSON and a missing `case.json`
still produce a legal `result.json` and exit 0.

## 2. 五命令（agent 深读，质量更高）

```
python3 scripts/main.py init        # index the material, write a partial result.json + work/draft.skeleton.json
python3 scripts/main.py show        # print material paragraphs with locators (--grep, --mat)
# the agent reads the material and writes /app/work/draft.json (trends, dossiers, causes, result_fields)
python3 scripts/main.py check       # verify each dossier's rule_id exists and every judged dossier carries a basis
python3 scripts/main.py build       # render every artifact and the final result.json
python3 scripts/main.py selfcheck   # verify the artifacts exist and the contract echo is non-empty
```

The agent reads the material with `show`, writes `/app/work/draft.json`, runs `check` to confirm
every dossier points at an indexed rule and every judged dossier carries an attribution basis,
then `build` and `selfcheck`.

## 3. draft schema (`/app/work/draft.json`)

```json
{"case_id": "same id as the case",
 "task_understanding": "the checkable question this case answers",
 "dataset_note": "which artefact is the original, which is the summary, which is the control",
 "trends": [{"trend_id": "TR-01", "scope": "metric/group/interval",
             "statement": "direction, breakpoint or plateau, departure with its unit",
             "method": "interval, control and fitting rule", "locator": "f#L12",
             "quote": "verbatim source line", "strength": "A"}],
 "dossiers": [{"id": "A-001", "anomaly_type": "outlier", "target": "which sample/batch/channel/fold",
               "locator": "f#L20", "observed": "value with unit",
               "expected_or_rule": "rule and cited threshold", "rule_id": "R1",
               "severity": "high", "judged": true, "verdict": "confirmed",
               "attribution": "data_quality", "attribution_basis": "support plus exclusion",
               "evidence_quote": "verbatim line", "excluded_alternatives": ["what was ruled out"],
               "do_not_conclude": ["what must not be read into this"],
               "recheck_actions": ["object + action + decision condition"],
               "next_experiment": "the next change", "strength": "A"}],
 "causes": [{"candidate": "candidate cause", "support": "supporting evidence",
             "exclusion": "excluding evidence", "strength": "B"}],
 "uncertainties": ["what could not be read from the material"],
 "confirmations": ["items that need an expert or equipment owner"],
 "next_steps": ["work-draft level next experiment"],
 "result_fields": {"<an output_contract key>": "the value for that key"}}
```

`check` reports, per dossier, whether the referenced `rule_id` exists in the indexed rule table
and whether a `judged` dossier carries a non-empty `attribution_basis`. A judged dossier without
a basis must be fixed before `build`.

## 4. What each artifact holds

| artifact | contents |
|-|-|
| `interpretation.md` | the eight sections: inventory, the five conclusions (trend, anomaly, causes, recheck, next), uncertainties and method |
| `dossier_index.json` | one entry per anomaly with its target, severity, verdict, attribution, strength, locator and its per-dossier `dossiers/anomaly-<id>.md` file, plus the per-entry issues |
| `inventory.json` | the per-file inventory with every table object, its columns and size, the numeric series and the unit groups |
| `recompute.json` | the fixed fixture, the recomputed definitions with their expected values, the per-series statistics, the rule candidates and the consistency checks |
| `thresholds.json` | every threshold constant with its locator, its quote and the conflicting constants kept side by side |
| `evidence.json` | every indexed item with source_id, locator, verbatim quote and a hit-rate |
| `uncertainties.json` | the uncertainty items, the confirmations that need a human and the recorded gaps |
| `method_notes.md` | parsing, statistics, criteria and the re-run command |
| `result.json` | the contract keys plus inventory, rule index, thresholds, units, the recomputed definitions, the dossiers, metrics, limits, uncertainties, sources, change records and artifacts |

## 5. The five checkable conclusions

Trend, anomaly point, candidate causes, recheck steps and next-round experiment. A trend is a
direction plus breakpoint or plateau plus a departure with a unit, never a restatement of the
readings. An anomaly is bound to the sample, batch, channel, well, time point or estimator-fold
it actually belongs to, with its severity and the rule that fired. Candidate causes are ranked
by evidence strength with the support and the exclusion written out, and the four attribution
values are `data_quality`, `method_artifact`, `source_ambiguity` and `undetermined`. A recheck
step names the object, the action and the decision condition; a step such as "check the data
quality" is not accepted. A next-round experiment follows from the cause candidates and the
evidence gaps.

## 6. Rules and statistics

The screening rules R1-R9 (modified z, IQR fence, recomputation deviation, calibration
back-calculation, unit inconsistency, duplicate rows, incomplete series, threshold conflict,
physical bounds, saturation plateau, cross-source inconsistency) are indexed from the material
with their trigger and their default severity. The statistics are the ones the material defines:
arithmetic mean, sample standard deviation with n-1, interpolated median, MAD, modified z
`0.6745*(x-median)/MAD`, the IQR fence, the least-squares fit and the relative deviation. Rules
only find a disagreement with a distribution or with another source; they never decide that it
is a fault. Conflicting units or thresholds are kept side by side and never silently reduced to
one value.

## 7. Boundaries

Standard library only, offline, no third-party dependency. No fabricated wet measurements, no
fabricated causes and no fabricated replicate counts. A structure the material does not carry is
reported as searched-but-absent with its searched locations. Nothing is fetched or installed.
