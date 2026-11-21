# GAIN_EVIDENCE — experiment-01 / plan-forge-experiment（使用增益证据）

本文件给出「不加载本 Skill 的基线 Agent」与「加载本 Skill」在同一最小样例上的对照证据，
并映射到官方 rubric 五维。所有「加载本 Skill」数字来自本包 `examples/` 的**真实运行**，可逐字复现。

> **诚实声明**：本文「基线 Agent（无 Skill）」一栏为**基线模拟，非官方对照**，由随包文档描述的
> 确定性朴素策略（§1.2）在同一输入上生成，仅用于说明**缺口类别**，不代表官方评测中的真实对手；
> 本包**未伪造任何官方 A/B 数据**。

---

## 1 基线 Agent（无 Skill）

### 1.1 典型输出与缺口

输入 `examples/`（`case.json` + `params.json`：3 个有限参数域、1 条上界约束、4 项带单价的资源、
3 个版本候选方案、2 个对照、若干风险与确认项，budget 15000、deadline 5 天）下，未加载本 Skill
的基线 Agent 典型缺口：

1. **无逐字证据 / 无定位符** —— 不给 `locator`（如 `M02/..parameters[0]`）与原文逐字 `quote`。
2. **无契约回填** —— 不产出 `result.json`，8 个契约键覆盖 0/8。
3. **无校验** —— 不许算六条规则（域/constraint/booking/budget/quantity/control）、无算术台账自检。
4. **易幻觉** —— 可能给出不在参数域内、或违反上界（temperature ≤ 160 °C）的「推荐点」，或编造采购价。
5. **无差异比较** —— 只给单一方案，不给三版本成本/时长/可行性横比与修订记录。
6. **无确定性** —— 每次「建议方案」不同，无稳定成本与关键路径。

### 1.2 基线模拟（确定性，非官方对照）

```python
# baseline_sim（示意）：只给「取中间值」的定性建议，不判约束、不算成本、不做版本对比
import json, pathlib
p = json.loads(pathlib.Path("examples/params.json").read_text(encoding="utf-8"))
mid = {d["name"]: (d["min"] + d["max"]) / 2 for d in p["parameters"]}
pathlib.Path("baseline_out").mkdir(exist_ok=True)
(pathlib.Path("baseline_out") / "advice.md").write_text(
    "建议取值：" + ", ".join(f"{k}={v}" for k, v in mid.items()) +
    "。可按此设置一次实验。\n", encoding="utf-8")
# 无 result.json、无 plan_revised.json、无 validation_report.json、无 arithmetic_ledger.json、无 evidence.json
```

模拟结果：产物 **1** 件、版本对比 **0**、校验规则 **0**、成本/时长 **0**、逐字证据 **0**、契约键 **0/8**。

---

## 2 加载本 Skill（真实运行）

命令（§4）在 `examples/` 上的实测（`status=answered`，exit 0）：

| 可核验指标 | 实测值 |
|---|---|
| 产物文件数 | **8** |
| 逐字证据 `evidence_stats` | total **19** / verbatim_hits **19** / hit_rate **1.0** |
| 识别参数域 `parameter_domains` | **3**（temperature [60,180] step20 C；time [6,24] step2 h；naoh [5,15] step2 M） |
| 约束 `constraints` | **1** 条（C01 temperature le 160 C，`source=M02`，带 locator+quote） |
| 资源 `resources` | **4**（水热釜 300、钛前驱体 180、NaOH 70、FE-SEM 200 /h） |
| 候选版本 `candidate_versions` | **3**（v1 保守 / v2 平衡 / v3 激进） |
| 校验汇总 `validation_totals` | plans **3**、feasible **3**、hard_violations **0**、warnings **0** |
| 推荐版本 | **v1**（naoh=7, temperature=100, time=10），带 ±1 step 容差带 |
| 算术台账 | per_run **2080**、total **10400**（×5 重复）、duration **1035** min |
| 算术自检 | **4/4 通过**（cost_reconciliation / budget_ceiling / duration_reconciliation / calendar_fit） |
| 预算与工期 | budget **15000**（总额 10400 ≤ 15000 ✓）、deadline **5** 天（1035 min ≈ 2.16 天 ✓） |
| 契约键覆盖 | **8/8**（`case_id, status, plan_report, plan_revised, validation_report, arithmetic_ledger, evidence, uncertainties`） |
| 占位符扫描 | **0** |
| `result.json` 规范化哈希 | `sha256=e0b5c4f9a2ece55e`（无 `runtime` 字段） |

关键产物：`plan_report.md` / `plan_revised.json`（含 `from → to` 修订）/ `validation_report.json` /
`arithmetic_ledger.json`（逐行成本行 + 4 项自检）/ `evidence.json`（19 条逐字命中的证据）/ `version_diff.md` /
`reproduce.md` / `result.json`。本样例三个候选均无硬违规，故无需修订，`revision_count=0`。

---

## 3 差异对照表 → rubric 五维

| 对照项 | 无 Skill（基线模拟，非官方对照） | 加载本 Skill（实测） | 主要增益维度 |
|---|---|---|---|
| 交付完整度 | 1 件定性建议，无 `result.json` | 8 件成套产物（报告/修订/校验/台账/证据/对比/复现） | **完成度 / 完整性** |
| 方案正确性 | 「取中值」，可能越界或违反上界 | 三版本均在有限域内、在 step 网格上、满足上界 | **正确性** |
| 证据可核验 | 无 locator / 无 quote | 19 条证据全部逐字命中（rate 1.0） | **可核验性** |
| 契约回填 | 键覆盖 0/8 | 键覆盖 8/8（顶层 + `result.output_contract`） | **完成度** |
| 抗幻觉 | 可能编造采购价/工期 | 成本=用量×单价 逐行可复算，缺失项如实记 `limits` | **正确性 / 可靠性** |
| 确定性与自检 | 每次建议漂移 | 规范化哈希稳定、4 项算术自检全通过 | **可靠性** |

**为什么对应 rubric**：完成度＝成套产物 + 契约回填；正确性＝有限域枚举 + 约束判定 + 逐行成本复算；
完整性＝报告/校验/台账/证据/版本对比；可核验性＝locator + 逐字引文 + 命中率；使用增益＝同输入下多维同时提升。

---

## 4 复现命令

```bash
python3 scripts/main.py all --input examples --output /tmp/out --work /tmp/work
# exit 0；8 件产物；status=answered；domains=3, constraints=1, resources=4, candidates=3；
# per_run=2080, total=10400, duration=1035, replicates=5, checks 4/4 ok；
# evidence_stats = {total:19, verbatim_hits:19, hit_rate:1.0}
```

哈希复算：读 `/tmp/out/result.json`，`json.dumps(sort_keys=True, ensure_ascii=False,
separators=(",",":"))` 取 `sha256` 前 16 位应为 `e0b5c4f9a2ece55e`。
