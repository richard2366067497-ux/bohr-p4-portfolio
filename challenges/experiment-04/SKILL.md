---
name: plan-choice-sensitivity
description: Turn a batch of experiment material into a reviewable, source-grounded plan comparison and choice — the criteria dictionary with direction and weight, the state and evidence-grade dictionaries, the candidate matrix under min-max normalisation and weighted scoring, the hard-constraint gate, the dominance relation, the line-level cost and duration ledger recomputed from expressions, and the flip-threshold scan that says how far each assumption can move before the choice changes. Use when a task asks which of several plans to pick, how the options compare, what the choice is sensitive to, or whether a stated flip point is right.
version: 2.6.0
---

# plan-choice-sensitivity

## 0. result.json contract

`result.json` carries every key of the case's `output_contract`, both at the top level and
inside a nested `output_contract` object. When the case does not declare one, the sample below
applies:

```json
{"output_contract": {"case_id": "string", "status": "string", "decision_memo": "string",
 "criteria_matrix": "string", "flip_report": "string", "cost_ledger": "string",
 "evidence": "string", "uncertainties": "string", "selected": "string"}}
```

`case_id` is passed through unchanged. `status` is one of `answered`, `partial`,
`insufficient_evidence`, `input_error`. No key is ever empty and no empty-value token is written
into any artifact. A contract field that is not recognised by name is still filled — with the
recomputed comparison summary, never left blank.

## 1. 单命令（one-shot，评测入口）

```
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

One command runs the whole pipeline: scan the input → index the material with locators → pull the
criteria dictionary (id, unit, direction, weight), the state map, the evidence grades and the cost
and duration formulas → read any candidate workbook → map values to numbers → min-max normalise
inside the candidate set → weight to a 0-100 score → gate on the hard constraints → compute the
dominance relation → recompute every ledger expression → scan each assumption range for the flip
threshold → rank → render the artifacts → fill the contract → sweep empty-value tokens. It works
with no draft present, prints a one-line summary and exits 0. Empty input, malformed JSON and a
missing `case.json` still produce a legal `result.json` and exit 0.

## 2. 五命令（agent 深读，质量更高）

```
python3 scripts/main.py init        # index the material, write a partial result.json + work/draft_template.json
python3 scripts/main.py show        # print material paragraphs with locators (--grep, --mat)
# the agent reads the material and writes /app/work/draft.json (candidates, ledger, assumptions)
python3 scripts/main.py check       # criteria weights, schema, ledger expressions, matrix computability
python3 scripts/main.py build       # render every artifact and the final result.json
python3 scripts/main.py selfcheck   # verify the artifacts exist and the contract echo is non-empty
```

The agent reads the material with `show`, writes `/app/work/draft.json`, runs `check` to confirm the
weight sum, the coverage and the ledger expressions, then `build` and `selfcheck`.

## 3. draft schema (`/app/work/draft.json`)

```json
{"case_id": "same id as the case",
 "task_understanding": {"objective": "one testable question", "decision_question": "which options",
                        "hard_constraints": ["budget cap", "deadline"]},
 "criteria": [{"id": "objective_fit", "weight": 0.15, "why": "read from the dictionary"}],
 "candidates": [{"candidate_id": "plan_v1", "name": "solution route",
                 "params": {"anneal_temp_c": 420},
                 "values": {"objective_fit": {"display": 4, "unit": "score_1_5",
                            "evidence": {"locator": "plans/plan_v1.md#p2", "quote": "verbatim"}}}}],
 "constraints": [{"id": "K1", "criterion": "total_cost", "op": "<=", "value": 48000, "severity": "hard"}],
 "cost_time": {"runs": 12, "currency": "CNY",
               "cost_rows": [{"candidate": "plan_v1", "item": "kit", "class": "per_run", "expr": "2*480"}],
               "duration_rows": [{"candidate": "plan_v1", "item": "setup", "hours": 8}]},
 "assumptions": [{"id": "A1", "name": "price index", "range": [1.0, 1.8], "base": 1.0,
                  "effect": {"type": "scale", "criterion": "total_cost", "candidate": "plan_v1"}}],
 "selected": "plan_v1", "risks": [], "confirmations": []}
```

`check` reports `criteria_weights` (the sum must sit in 1.00±0.02), `schema` (candidates and a
selection), `ledger_expr` (every expression must evaluate) and `matrix_computable`. A `display`
that is a state word is mapped to 0-4 by the state map; `未声明` never receives a middle score.

## 4. What each artifact holds

| artifact | contents |
|-|-|
| `decision_memo.md` | status and reason, the decision question, the hard gate, the criteria dictionary with a weight checksum, the per-criterion quotes, the matrix, the normalisation intervals, the dominance relation, the ranking, the ledger lines, the flip scan, the risks, the confirmations and the degradations |
| `criteria_matrix.json` | the criteria dictionary with evidence, the weight sum and its verdict, the normalisation per criterion, the per-candidate scores and coverage, the dominance relation, the ranking, the state map, the grades, the feasibility states, the constraints and the metrics |
| `flip_report.json` | the per-assumption 17-point chooser trace, the bisected threshold, the stable assumptions and any declared claim for recomputation |
| `cost_ledger.json` | the currency, the run count, every cost item with its expression and recomputed value, every duration item, the per-candidate totals and the arithmetic self-checks |
| `evidence.json` | every extracted item with source_id, locator, verbatim quote and a hit-rate |
| `version_diff.md` | one row per candidate (score, coverage, state, hit and missing criteria, source) and the winner |
| `result.json` | the contract keys plus criteria, candidates, ranking, ledger, sensitivity, metrics, limits, uncertainties, sources, change records and artifacts |

## 5. Scoring rules

Hard constraints filter first — a violated `severity=hard` entry makes a candidate `infeasible` and
keeps it out of the ranking. Each criterion is min-max normalised inside the current candidate set
(higher-is-better and lower-is-better both handled; `hi == lo` maps to 1.0). The score is
`100 × Σ(w_i × n_i)`. A missing value is *not* exempt: it scores zero and is counted in the
coverage. Dominance is only judged when both candidates are fully valued. Ties break by
feasibility state, then by score.

## 6. Sensitivity

Each assumption with a `range` and an `effect` (`scale`, `delta` or `cap`) is scanned at 17 equally
spaced levels; when the chosen candidate changes between two levels, the threshold is bisected for
22 rounds. A range that never changes the choice is reported as `stable`. A declared flip point is
recomputed, never trusted.

## 7. Boundaries

Standard library only, offline, no third-party dependency. Expressions are evaluated by a
restricted AST walker — no `eval` of arbitrary code. No significance testing. Missing budget,
candidate, ledger or assumption is preserved as an open item with a reason — never guessed.
Nothing is fetched or installed.
