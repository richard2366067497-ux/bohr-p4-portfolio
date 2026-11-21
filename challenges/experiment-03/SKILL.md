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

## 随包方法论（执行前必读）

在执行任何命令、产出任何交付物之前，**先完整阅读 `references/expert_playbook.md`（专家参考手册）**，
并按它组织全部产出：

- **流程**：按其 **§1 七步法（S1–S7）** 推进——解析目标 → 识别变量 → 抽可行域 → 定义响应与成本口径
  → 选搜索策略 → 算成本 → 列风险；前一步未冻结不进入下一步，并遵守其门控规则。
- **可行域口径**：按其 **§2 检查表**逐变量核验（设备量程 / 材料耐温耐压 / 安全阈值 / 历史 /
  互斥约束 / 步进），全部勾选后方可冻结，写进 `parameter_table.json` 与 `feasible_grid.json`。
- **成本口径**：按其 **§3 成本折算公式**（`总成本 = Σ(机时×单价) + Σ(表征费×项数) + 耗材×点数×1.1`）
  逐行核算，比对预算，写进 `cost_ledger.json` 并做算术自检。
- **搜索策略**：按其 **§4 决策树**选策略、按其 §4.3/§4.4 给初始设计、补点规则与停止条件，
  写进 `search_plan.json`；预算不足时走其 §4.5 降级方案。
- **风险与降级**：按其 **§5 风险矩阵**给出触发阈值与处置动作（🔴终止 / 🟡降级 / 🟢继续）。
- **门控**：交付前逐项通过其 **§7 高分交付物清单（9 项自查表）**，并用其 **§8 专家注意点**逐条排雷。

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

## 1. 单命令（one-shot，评测入口，无 draft 时执行）

Run this single command; with no draft it still writes every artifact and a complete
`result.json` and exits 0. **无 draft.json 时直接运行本命令即可产出完整契约与全部交付物；评测环境按此执行。**

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

**专家检查表逐项通过**：以上每件交付物在写入前，都要通过 `references/expert_playbook.md` §7
高分交付物清单的 9 项自查表逐项核验——变量清单可溯页码/DOI、互斥约束以不等式给出且可代入验证、
响应指标表引用标准号/仪器型号、成本预算表可手工核算（单价×数量=小计，各项加总=总计）、搜索策略
引用 §4 决策树分支、搜索计划满足累计点数×单点成本 ≤ 预算、候选方案 ≥3 个且参数在可行域内、风险矩阵
每条可映射到变量/约束、复现路径列全输入/种子/版本；并用 §8 逐条排雷。任一项不通过则修正后重出。

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

## 自检（selfcheck）与专家门控

`selfcheck` 核验产物齐备与契约回显非空，并做算术自检（行和=单次成本、总成本=单点×点数、不超预算）。
在此之上，**专家检查表逐项通过**是交付前的硬门控：每件交付物必须通过 `references/expert_playbook.md`
§7 的 9 项自查表并用 §8 逐条排雷后，方可视为完成。任一项未通过，`status` 记为 `partial` 并把未决项
写入 `uncertainties`/`search_notes.md`，绝不静默提升为 `answered`。

## 随包文件（v10 新增）

```
references/expert_playbook.md  专家参考手册（七步法/可行域检查表/成本口径/搜索决策树/风险矩阵/案例/自查表）
environment/resources.yaml     运行环境、入口命令、输入/输出路径、预算与依赖声明（离线、纯标准库）
examples/                      最小可复跑样例（case.json + params.json），评审可直接复跑
GAIN_EVIDENCE.md               无 Skill 基线对照与使用增益证据（含确定性 baseline_sim 说明，非官方对照）
```
