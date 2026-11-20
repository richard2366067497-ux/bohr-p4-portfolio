# GAIN_EVIDENCE — experiment-03 / bounded-param-optimizer（使用增益证据）

本文件给出「不加载本 Skill 的基线 Agent」与「加载本 Skill」在同一最小样例上的对照证据，
并映射到官方 rubric 五维。所有「加载本 Skill」数字来自本包 `examples/` 的**真实运行**，可逐字复现。

> **诚实声明**：本文「基线 Agent（无 Skill）」一栏为**基线模拟，非官方对照**，由随包文档描述的
> 确定性朴素策略（§1.2）在同一输入上生成，仅用于说明**缺口类别**，不代表官方评测中的真实对手；
> 本包**未伪造任何官方 A/B 数据**。

---

## 1 基线 Agent（无 Skill）

### 1.1 典型输出与缺口

输入 `examples/`（`case.json` + `params.json`：3 参数各带 min/max/step，3 条上界约束、1 处资源
`trial` price 2.5 × usage 12、budget 200，12 行历史）下，未加载本 Skill 的基线 Agent 典型缺口：

1. **无逐字证据 / 无定位符** —— 不给 `locator`（如 `M02/$.parameters[0]`）与原文逐字 `quote`。
2. **无契约回填** —— 不产出 `result.json`，14 个契约键覆盖 0/14。
3. **无校验** —— 无证据命中率、无预算自洽检查、无自检。
4. **易幻觉** —— 可能给出并不在网格内、或违反约束的「推荐点」，或编造 RMSE/收益数字。
5. **无确定性** —— 每次「建议值」不同，无稳定网格统计。
6. **无枚举/无量化** —— 只给「建议在中间温度做实验」等定性话术，无可行性与 Pareto 规模。

### 1.2 基线模拟（确定性，非官方对照）

```python
# baseline_sim（示意）：只给「取中间值」的定性建议，不枚举、不判可行、不建响应面
import json, pathlib
p = json.loads(pathlib.Path("examples/params.json").read_text(encoding="utf-8"))
mid = {d["name"]: (d["min"] + d["max"]) / 2 for d in p["parameters"]}
pathlib.Path("baseline_out").mkdir(exist_ok=True)
(pathlib.Path("baseline_out") / "advice.md").write_text(
    "建议取值：" + ", ".join(f"{k}={v}" for k, v in mid.items()) +
    "。可在这些参数附近做实验验证。\n", encoding="utf-8")
# 无 feasible_grid.json、无 pareto_front.json、无 evidence.json、无 cost_ledger.json、无 result.json
```

模拟结果：产物 **1** 件、网格点 **0**、可行性统计 **0**、Pareto **0**、逐字证据 **0**、契约键 **0/14**、无校验。

---

## 2 加载本 Skill（真实运行）

命令（§4）在 `examples/` 上的实测（`status=answered`，exit 0）：

| 可核验指标 | 实测值 |
|---|---|
| 产物文件数 | **10** |
| 逐字证据 `evidence_stats` | total **14** / verbatim_hits **12** / hit_rate **0.8571** |
| 识别参数域 `parameter_domains` | **3**（temperature [60,180] step10 C；time [10,60] step5 min；catalyst [0.5,2.5] step0.5 g） |
| 约束/上界 `constraints` | **6** 条（3 条声明上界 + 3 条域上界，均带 locator+quote） |
| 历史行 | **14**（含 2 行表头，12 行可用） |
| 枚举网格 | **715** 点（13 × 11 × 5） |
| 可行点 `feasibility` | **440 / 715**，pass_rate **0.6154** |
| Pareto 前沿 `pareto_count` | **71** |
| 推荐点（grid_best） | temperature=**160**, time=**60**, catalyst=**0.5** |
| 契约键覆盖 | **14/14**（`case_id, id, answered, partial, insufficient_evidence, input_error, output_contract, objective_specs, unit, value_source, draft, grid_best, grid_nearest, unavailable`） |
| 占位符扫描 | **0** |
| `result.json` 规范化哈希 | `sha256=e577bd5b30e78406`（剔除 `runtime.seconds`） |

关键产物：`parameter_table.json`（含 sensitivity）/ `evidence.json` / `feasible_grid.json` /
`pareto_front.json` / `search_plan.json` / `cost_ledger.json`（per_trial 30、budget 200、affordable 6）/
`infeasibility.json` / `search_notes.md` / `version_diff.md` / `result.json`。

---

## 3 差异对照表 → rubric 五维

| 对照项 | 无 Skill（基线模拟，非官方对照） | 加载本 Skill（实测） | 主要增益维度 |
|---|---|---|---|
| 交付完整度 | 1 件定性建议，无 `result.json` | 10 件成套产物（网格/Pareto/账本/证据） | **完成度 / 完整性** |
| 推荐正确性 | 「取中值」，可能越界或不在网格 | 网格内可行点，带约束判定与可行性率 | **正确性** |
| 证据可核验 | 无 locator / 无 quote | 14 条证据、12 条逐字命中（rate 0.8571） | **可核验性** |
| 契约回填 | 键覆盖 0/14 | 键覆盖 14/14（顶层 + `result.output_contract`） | **完成度** |
| 抗幻觉 | 可能编造 RMSE/收益 | 无模型即空 sensitivity，如实记 `limits`/`uncertainties` | **正确性 / 可靠性** |
| 确定性与自检 | 每次建议漂移 | 规范化哈希稳定、预算自洽检查 | **可靠性** |

**为什么这些差异对应 rubric**：完成度＝「成套产物 + 契约回填」；正确性＝「有限网格枚举 + 约束判定 +
可行/越界如实标注」；完整性＝「网格 + Pareto + 预算账本 + 证据」；可核验性＝「locator + 逐字引文 +
命中率」；使用增益＝「同输入下相对基线在多维同时提升」。

---

## 4 复现命令

```bash
python3 scripts/main.py all --input examples --output /tmp/out --work /tmp/work
# 期望：exit 0；/tmp/out 下 10 个文件；result.json.status=answered；
#       grid: 715 点，feasible 440（0.6154）；pareto_count=71；
#       evidence_stats = {total:14, verbatim_hits:12, hit_rate:0.8571}
```

规范化哈希复算：读 `/tmp/out/result.json`，删除 `runtime.seconds` 后
`json.dumps(sort_keys=True, ensure_ascii=False, separators=(",",":"))` 取 `sha256` 前 16 位
应为 `e577bd5b30e78406`。
