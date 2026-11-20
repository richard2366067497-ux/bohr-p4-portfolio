---
name: bounded-param-optimizer
description: >-
  Turn lab materials into a source-grounded bounded parameter optimisation:
  finite parameter domains (min/max/step), stated bounds with verbatim quotes,
  an enumerated feasible grid, a fitted response surface with RMSE/LOO, a Pareto
  front, a sequential search plan, a per-trial cost ledger, a minimal conflict
  set when the grid is infeasible, a three-version comparison and a recommendation
  with a tolerance band. Use when a task asks for 实验参数优化建议 / bounded
  parameter optimisation / 参数范围与优化 / search plan / 实验方案对比.
version: 2.6.0
---

# bounded-param-optimizer

Every number that leaves this skill is either copied from an input material with a
`source_id` + `locator` + verbatim quote, or recomputed from such numbers by a formula
that is written next to the result. When an input is missing the corresponding field is
reported as a structured "absent" record; nothing is invented. The contract keys are
echoed both at the top level of `result.json` and inside its `output_contract` object, and
`case_id` is passed through unchanged.

## 0. result.json contract

The engine fills every key below (top level and inside `output_contract`):

```json
{
  "output_contract": {
    "case_id": "string",
    "status": "string",
    "plan_report": "string",
    "parameter_table": "string",
    "search_plan": "string",
    "cost_ledger": "string",
    "evidence": "string",
    "uncertainties": "string"
  }
}
```

When `/input/case.json` supplies its own `output_contract`, those keys are used instead and
each is filled the same way (path-like keys resolve to the artifact written into the output
directory, text-like keys get a real derived sentence). `status` is one of `answered`,
`partial`, `insufficient_evidence`, `input_error`.

## 1. 单命令（one-shot，评测入口）

Run this single command; with no draft it still writes every artifact and a complete
`result.json` and exits 0:

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

## 2. agent-first 增强路径（质量更高，可选）

An agent may fill `/app/work/draft.json` (copy the skeleton printed by `init`) and get the
recommendation checked against every stated bound before it is adopted:

```bash
python3 /skills/weekly-skill/scripts/main.py init --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py show --input /input --work /app/work
python3 /skills/weekly-skill/scripts/main.py check --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py build --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py selfcheck --output /app/output --work /app/work
```

`show` prints material paragraphs with their locators (`M02/p3`) so the agent can quote
them; `check` reports whether the drafted values map onto the declared domains and stay
inside every bound; `build` prints the full pipeline with the draft merged in.

## 3. Draft schema (JSON, optional)

```json
{
  "case_id": "",
  "objective_weights": {},
  "recommended": {},
  "constraints_added": [],
  "resource_notes": [],
  "uncertainties": [],
  "change_log": []
}
```

`recommended` maps parameter names onto values; names are matched to the declared domains
case-insensitively, and any value that breaks a stated bound is reported and repaired to
the nearest feasible grid point (the repair is recorded in `recommendation.violations`).

## 4. Pipeline

1. Scan every file under `/input` and index it as a material (`M01`, `M02`, ...).
2. Extract finite parameter domains (min / max / step), stated bounds (`le`/`ge`/`lt`/`gt`/
   `eq`/`ne`/`mutex`), price rows, usage rows, budget, versioned candidate plans and
   response indicators — each with a locator and a verbatim quote.
3. Enumerate the Cartesian grid of the domains and evaluate every stated bound point by
   point.
4. Fit a ridge-linear response surface per indicator from the run history; report training
   RMSE and leave-one-out RMSE.
5. Rank feasible points, compute the Pareto front, run a maximin + greedy sequential search
   plan, quote a per-trial cost from price x usage, and derive the recommendation band.

## 5. Artifacts written to `--output`

| file | content |
|-|-|
| result.json | contract keys (top level + `output_contract`), case_id, status, domains, bounds, models, recommendation, search, cost, feasibility, version winner, limits, uncertainties, sources, change_records, artifacts |
| search_notes.md | method, material inventory, what was found vs absent, searched locations, next actions |
| parameter_table.json | per-domain min/max/step/unit/axis size, fitted sensitivity, evidence |
| feasible_grid.json | axes, grid size, feasible count and rate, per-constraint pass/fail, sample rows |
| pareto_front.json | non-dominated points with their indicator values, or a stated reason none is claimed |
| search_plan.json | strategy, per-round plan with predicted improvement, stop rules, budget link |
| cost_ledger.json | per-trial cost, total, budget, formula, inputs, arithmetic checks |
| version_diff.md | three-version comparison table with feasibility and predicted score |
| evidence.json | every extracted item with source_id, locator, quote, verbatim hit rate |
| infeasibility.json | minimal conflict set, relaxation options, least-violating point |

## 6. Degradation rules

- No finite parameter domain in the material → grid, model and cost are reported absent
  with the searched locations; `status=insufficient_evidence`.
- No run history → ranking falls back to a labelled constraint-margin design rule (never
  presented as a measured response); `status=partial`.
- Grid non-empty but infeasible → minimal conflict set + relaxation options;
  `status=partial`; the recommendation is the least-violating point.
- Empty `/input`, unparseable JSON, missing `case.json` → still writes a legal `result.json`
  and exits 0.
- No significance testing is performed; with few rows the model is reported as indicative
  only, with its RMSE and n printed.
