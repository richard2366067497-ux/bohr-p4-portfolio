# SELFTEST — bounded-param-optimizer（experiment-03 v6）

本文件记录 **2026-11-20** 在仓库根目录用 `scripts/eval_sim.py` 对 rich / boundary 两个合成用例
× single / agent 两种模式做的本地评测结果，以及一个自带数值域的本地功能用例。所有评测均为
**PASS，0 WARN，0 FAIL**。

## 复现命令

```bash
python scripts/eval_sim.py --pkg work/p4/v6/experiment-03 \
  --case work/p4/synth_cases/experiment-03/rich     --mode single
python scripts/eval_sim.py --pkg work/p4/v6/experiment-03 \
  --case work/p4/synth_cases/experiment-03/rich     --mode agent
python scripts/eval_sim.py --pkg work/p4/v6/experiment-03 \
  --case work/p4/synth_cases/experiment-03/boundary --mode single
python scripts/eval_sim.py --pkg work/p4/v6/experiment-03 \
  --case work/p4/synth_cases/experiment-03/boundary --mode agent
```

## 实测结果

| 用例 | 模式 | 状态 | 契约来源 | 契约键 | 产物数 | 说明 |
|-|-|-|-|-|-|-|
| rich | single | PASS | case.json:output_contract | 14 键（case_id, id, answered, partial, insufficient_evidence, input_error, output_contract, objective_specs, unit, value_source, draft, grid_best, grid_nearest, unavailable） | 10 | 材料无参数域，诚实降级 `insufficient_evidence` |
| rich | agent | PASS | case.json:output_contract | 同上 14 键 | 10 | init → draft → check → build → selfcheck 全部 exit 0 |
| boundary | single | PASS | SKILL.md (json sample) | case_id, status, plan_report, parameter_table, search_plan, cost_ledger, evidence, uncertainties | 10 | 空文件 + 坏 JSON + 10 字节文本，exit 0 |
| boundary | agent | PASS | SKILL.md (json sample) | 同上 8 键 | 10 | 同上，draft 为 `{}` 仍全流程通过 |

逐项检查（每组均 PASS）：`exit_code`、`result_json`、`contract_echo`、`contract_values`、
`deliverables`、`case_id`、`placeholder_sweep`、`field:{status,sources,uncertainties,change_records,limits}`。

## 数值功能用例（本地，验证"真实推导"而非模板）

用 `scripts/main.py all` 跑一个自带 3 参数域 × 12 行历史 × 3 版本候选方案的用例：

- 参数域：temperature 60–180 step 10 °C、time 10–60 step 5 min、catalyst 0.5–2.5 step 0.5 g。
- 约束：temperature ≤ 160 °C、time ≥ 15 min、catalyst ≤ 2.0 g（其中后两条同时出现在 case.json
  与 notes.md 的散文中，去重后各只保留一条，证据各带 locator+quote）。
- 网格：715 点，可行 176 点（24.62%）。
- 响应面：yield n=12 RMSE 1.274，留一 RMSE 1.865；impurity n=12 RMSE 0.000（该指标对参数严格线性）。
- Pareto：10 个非支配点。
- 成本台账：单次成本 29.5（12 次记录 `cost` 列的均值，公式与输入行写入 cost_ledger.json），
  计划 16 点 → 总成本 472，预算 200 → 可负担 6 次；三条算术自检全部 ok。
- 版本对比：v1（120/30/1.5）胜出（可行且预测均值最高），v3 因 catalyst 2.5 越界被标为不可行。
- 推荐：temperature=160、time=55、catalyst=0.5，来源 `grid_search`，带 ±1 step 容差带。

该用例 `eval_sim` single / agent 亦均为 PASS。

## 边界行为核对

- `boundary`（空文件 + 坏 JSON + 10 字节文本）：`status=insufficient_evidence`，不编造参数域；
  `feasible_grid/pareto_front/infeasibility/cost_ledger` 用带原因的诚实 no-data 结构，
  `limits` 说明检索范围与降级原因。
- 无 `draft.json`：`build`/`all` 使用规则化推荐，仍产出全部 10 个产物；`degradations` 与
  `uncertainties` 提示需人工复核。
- 空 `/input`、坏 JSON、缺 `case.json`：均 exit 0 并写合法 `result.json`。

## 产物清单（每次运行写入 --output）

result.json、search_notes.md、parameter_table.json、feasible_grid.json、pareto_front.json、
search_plan.json、cost_ledger.json、version_diff.md、evidence.json、infeasibility.json（共 10 个）。

> 以上为本地模拟评测（`scripts/eval_sim.py`）结果，不代表平台正式分数；正式案例以平台 `/input` 为准。
