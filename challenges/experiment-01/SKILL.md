---
name: plan-forge-experiment
description: Turn a batch of experiment material into a reviewable, versioned experiment plan — six required elements (hypothesis and variables, controls, equipment and materials, time and cost, parameter ranges, risks and exceptions) extracted with locator and verbatim quote, three versioned candidate plans, six validation rules, an arithmetic ledger with self-checks, a rule-based revision pass, and a reproducible recommended setting with a tolerance band. Use when a task asks for an experiment plan, a protocol design, a candidate comparison, a cost or booking check, or a plan that must be derived item by item from the supplied material.
version: 2.6.0
---

# plan-forge-experiment

## 0. result.json contract

`result.json` carries every key of the case's `output_contract`, both at the top level and
inside a nested `output_contract` object. When the case does not declare one, this package
default applies:

```json
{"output_contract": {"case_id": "string", "status": "string", "plan_report": "string",
 "plan_revised": "string", "validation_report": "string", "arithmetic_ledger": "string",
 "evidence": "string", "uncertainties": "string"}}
```

`case_id` is passed through unchanged. `status` is one of `answered`, `partial`,
`insufficient_evidence`, `input_error`. No key is ever empty and no empty-value token is
written into any artifact.

## 1. 单命令（one-shot，评测入口）

```
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

One command runs the whole pipeline: scan the input → extract the six elements with locator
and quote → pull domains, constraints, resources, plans, controls, risks and confirmations →
generate three versioned candidates when none were supplied → validate each against the six
rules → revise the failures → tot up the arithmetic ledger with self-checks → render the
artifacts → fill the contract → sweep empty-value tokens. It works with no draft present,
prints a one-line summary and exits 0. Empty input, malformed JSON and a missing `case.json`
still produce a legal `result.json` and exit 0.

## 2. 五命令（agent 深读，质量更高）

```
python3 scripts/main.py init        # index the material, write a partial result.json + work/draft.skeleton.json
python3 scripts/main.py show        # print material paragraphs with locators (--grep, --mat)
python3 scripts/main.py check       # map the draft's recommended settings onto the finite domains and flag anything out of range
python3 scripts/main.py build       # render every artifact and the final result.json
python3 scripts/main.py selfcheck   # verify the artifacts exist and the contract echo is non-empty
```

The agent reads the material with `show`, writes `/app/work/draft.json`, runs `check` to
confirm every proposed setting sits inside its declared domain, then `build` and `selfcheck`.

## 3. draft schema (`/app/work/draft.json`)

```json
{"case_id": "same id as the case", "objective_weights": {"metric name": 0.5},
 "recommended": {"parameter name": 120},
 "constraints_added": ["free text rule the agent read from the prose"],
 "resource_notes": ["free text note about equipment or booking"],
 "uncertainties": ["what could not be read from the material"],
 "change_log": ["what the agent changed and why"],
 "hypothesis": "the testable statement the run is meant to settle",
 "control_design": "the control or baseline arm"}
```

`check` maps each `recommended` key onto a declared parameter domain (exact key first, then a
unique substring match) and reports `inside_domain` per entry plus any key that maps to
nothing. Out-of-range or unmapped settings must be fixed before `build`.

## 4. What each artifact holds

| artifact | contents |
|-|-|
| `plan_report.md` | status and reason, the six elements each with locator and quote, the recommendation with its tolerance band, every arithmetic check, limits and sources |
| `plan_revised.json` | candidate versions with their revisions (`from → to` plus the reason), the winner, the revision rules |
| `validation_report.json` | the six rules, per-plan violations/warnings/notes, before-revision state, totals |
| `arithmetic_ledger.json` | per version: formula, cost lines, duration lines, the input rows, and each self-check |
| `evidence.json` | every extracted item with source_id, locator, verbatim quote and a hit-rate |
| `version_diff.md` | one row per version (settings, cost, duration, violations, feasible, revised) and the locators |
| `reproduce.md` | the entry point, materials read, the recommended settings, ordered steps and the decision rules |
| `result.json` | the contract keys plus domains, constraints, resources, candidate versions, arithmetic, validation totals, evidence stats, limits, uncertainties, sources, change records and artifacts |

## 5. Six required elements

Every plan must carry all six, each traceable to the material: hypothesis and variables,
controls, equipment and materials, time and cost, parameter ranges, risks and exceptions. An
element that the material does not carry is reported as absent or proposed with the reason —
it is never replaced by an invented list.

## 6. Six validation rules

`param_domain` (inside the finite domain and on the step grid), `constraint_*` (stated le/ge/
lt/gt/eq/ne bounds and mutex pairs), `booking` (facilities reserved inside a declared window),
`budget` (total cost within the ceiling), `quantity` (consumption within stock), `control` (a
control arm exists), `unit` (each parameter and priced item has a unit).

## 7. Arithmetic and revision

Cost is `amount × unit price` per item, summed to a per-run cost, then `× replicates` for the
total; duration is the sum of serial step minutes plus one maximum per parallel group. Both
are written out line by line and re-checked (line totals vs per-run cost, per-run × replicates
vs total, budget ceiling, calendar fit). A failing plan is repaired by rule: clamp to the
nearest legal grid point, satisfy the stated bound, trim usage to stock, cut replicates to
`floor(budget / per_run_cost)`, or add a flagged reference control. Every action is recorded.

## 8. Boundaries

Standard library only, offline, no third-party dependency. No significance testing; with few
history rows the model is reported as a hint alongside its sample count. Missing budget or
domain is preserved as an open rule with a reason, never guessed. Nothing is fetched or
installed.
