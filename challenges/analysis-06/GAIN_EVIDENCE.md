# GAIN_EVIDENCE — analysis-06 / db-query-workbook（使用增益证据）

本文件给出「不加载本 Skill 的基线 Agent」与「加载本 Skill」在同一最小样例上的对照证据，
并映射到官方 rubric 五维。所有「加载本 Skill」数字来自本包 `examples/` 的**真实运行**，可逐字复现。

> **诚实声明**：本文「基线 Agent（无 Skill）」一栏为**基线模拟，非官方对照**，由随包文档描述的
> 确定性朴素策略（§1.2）在同一输入上生成，仅用于说明**缺口类别**，不代表官方评测中的真实对手；
> 本包**未伪造任何官方 A/B 数据**。

---

## 1 基线 Agent（无 Skill）

### 1.1 典型输出与缺口

输入 `examples/`（`samples.csv` 12 行试块明细、`batches.csv` 4 行批次、`dictionary.md` 数据字典）下，
未加载本 Skill 的基线 Agent 典型缺口：

1. **SQL 只是"像 SQL 的文本"** —— 语句没在真实快照上执行过，行数无从核对。
2. **无字段字典** —— 不区分 `mix_type`（编码 A/B/C）与 `cement_kg_m3`（数值），可能把编码字段求均值。
3. **无连接膨胀复核** —— `samples ⋈ batches` 一对多不检查，直接用 joined 行数下结论。
4. **无缺失/重复量化** —— 不报 `samples.batch_id` 缺 1 行、`batches.plant` 重复 2 行。
5. **无对账与产物** —— 不写 `reconciliation.json` / `join_ledger.json` / `results/*.csv`，契约键覆盖 0/10。
6. **依赖记忆** —— 凭"标准数据集"印象报行数（如"Iris 150 行"），不查 `PRAGMA table_info`。

### 1.2 基线模拟（确定性，非官方对照）

```python
# baseline_sim（示意）：凭记忆写 SQL 文本，不执行、不导出、不对账
import csv, pathlib
rows = list(csv.DictReader(open("examples/samples.csv", encoding="utf-8")))
avg = sum(float(r["strength_mpa"]) for r in rows if r["strength_mpa"]) / len(rows)
pathlib.Path("baseline_out").mkdir(exist_ok=True)
(pathlib.Path("baseline_out") / "answer.md").write_text(
    "平均抗压强度约 %.2f MPa（未按龄期分组）。\n" % avg, encoding="utf-8")
# 无 result.json、无 queries.sql、无 results/*.csv、无 reconciliation.json、无 field_dictionary.json
```

模拟结果：产物 **1** 件、真实执行 SQL **0**、导出结果集 **0**、字段字典 **0**、连接复核 **0**、
对账检查 **0**、契约键 **0/10**。

---

## 2 加载本 Skill（真实运行）

命令（§4）在 `examples/` 上的实测（exit 0，`status=ok`）：

| 可核验指标 | 实测值 |
|---|---|
| 快照模式 | **snapshot built in work directory from tabular materials**（无库时装入 `work/snapshot.db`） |
| 快照 SHA-256 | `fde1cedaa46d6370884bc2e02da1b0d5400886e52681ea2f35c21a6fc2ba14cc` |
| 库表 `tables` / 字段 `fields` | **2**（batches、samples）/ **9** |
| 派生并**真实执行**的查询 | **16**（行数 2 + 编码分布 6 + 数值汇总 3 + 缺失审计 4 + 跨表连接 1），**失败 0** |
| 结果集导出 | **16** 份 `results/Q_*.csv` + 索引 `results/query_results.csv` |
| 对账 `reconciliation` | **7/7 通过**（`n_checks=7, n_pass=7`） |
| 连接账本 `join_ledger` | `Q_join_batches_samples`：left distinct **4** / right distinct **6**，left rows **4** / right rows **12**，joined **10**，**膨胀比 2.5**，`no_inflation=true` |
| 字段字典 `field_dictionary` | 编码字段 6（batch_id·plant·cure_method·sample_id·mix_type…），数值字段 3（cement_kg_m3·age_days·strength_mpa）；`strength_mpa` 识出单位 **mpa**；**编码字段一律按标签解释、不做数值聚合** |
| 数据质量 `data_quality` | `samples.batch_id` 缺失 **1**；`batches.plant` 重复多余 **2**；`samples.batch_id` 重复多余 **6** |
| 契约键覆盖 | **10/10**（`case_id, status, deliverable, queries, results, reconciliation, field_dictionary, join_ledger, data_quality, change_log`） |
| 产物文件数 | **26**（`query_report.md` + `queries.sql` + 17 份 CSV + 6 份 JSON + `code/reproduce.md`） |
| 占位符扫描 | **0**（`queries.sql` 与结果 CSV 逐字原样） |
| `result.json` 规范化哈希 | `sha256=6ddb955ed0cfd49e` |

关键产物：`query_report.md`（五节：库表发现/字段字典/查询执行/行数与连接复核/局限）、`queries.sql`
（16 条语句逐字 + 执行状态）、`results/Q_*.csv`（逐个结果集）、`reconciliation.json`、
`join_ledger.json`、`field_dictionary.json`、`query_workbook.json`、`data_quality.json`、
`code/reproduce.md`、`result.json`。

---

## 3 差异对照表 → rubric 五维

| 对照项 | 无 Skill（基线模拟，非官方对照） | 加载本 Skill（实测） | 主要增益维度 |
|---|---|---|---|
| 交付完整度 | 1 件定性答案，无 `result.json` | **26** 件成套产物（报告 + SQL + 17 CSV + 6 JSON + 复现说明） | **完成度 / 完整性** |
| 查询正确性 | SQL 未执行，行数凭印象 | **16 条语句全部真实执行、0 失败**；对账 **7/7** | **正确性** |
| 字段语义 | 可能把 `mix_type` 当数值求和 | 字段字典区分编码/数值；编码字段只出取值分布 | **正确性 / 可靠性** |
| 连接安全 | 不检查一对多膨胀 | 膨胀比 **2.5** 已记录且判定 `no_inflation`（>5 须人工审查） | **可靠性** |
| 证据可核验 | 无导出、无溯源 | 每个结果集一份 CSV，行数可回算；快照 SHA-256 可复验 | **可核验性** |
| 契约回填 | 键覆盖 0/10 | 键覆盖 **10/10**（路径类键指向真实交付物） | **完成度** |
| 确定性 | 每次口径漂移 | 同快照字节稳定，哈希 `6ddb955ed0cfd49e` | **可靠性** |

**为什么对应 rubric**：完成度＝成套产物 + 契约回填；正确性＝派生规则 + 真实执行 + 对账 7/7；
完整性＝报告/SQL/结果集/字典/账本/质量/复现齐备；可核验性＝逐结果集 CSV + 快照哈希；
使用增益＝同输入下多维同时提升，且诚实声明"无库时在 work 目录建快照执行同一批 SQL"。

---

## 4 复现命令

```bash
python3 scripts/main.py all --input examples --output /tmp/out --work /tmp/work
# exit 0；status=ok；26 件产物；tables=2, fields=9, queries=16(失败 0), csv_exports=16, joins=1
# 对账 7/7；join 膨胀比 2.5（no_inflation=true）；契约 10/10；哈希 6ddb955ed0cfd49e
```

哈希复算：读 `result.json`，`json.dumps(sort_keys=True, ensure_ascii=False, separators=(",",":"))`
取 `sha256` 前 16 位应为 `6ddb955ed0cfd49e`。重复运行同一份 `examples/`，产物字节稳定。
