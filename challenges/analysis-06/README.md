# analysis-06 — db-query-workbook (v10)

把科研数据库查询做成一份**可复核的查询工作簿**：发现库表 → 字段字典（编码型字段按标签解释）
→ 派生查询 → **在真实 SQLite 快照上执行** → 每个结果集导出 CSV → 行数与连接膨胀对账 → 报告。
每条被引用的 SQL 都真实执行过，每个数字都能回算到某个结果集。

**执行前必读**：`references/expert_playbook.md`（专家参考手册）。先按其 §2 的 S0–S6 六步流水线与门控
推进（快照确认 → 字典/Schema 交叉比对 → 质量探查 → 清洗规则 → 编 SQL 执行 → 组装交付），按其 §3
复算缺失率 / 重复行 / IQR 与 3σ 异常 / JOIN 膨胀比（>5 须人工审查）/ 聚合交叉验证，按其 §4 排雷
（K1 行数≠完整、K2 龄期必须分组、K3 编码当连续、K4 cement≠concrete、K5 单位、K6 NULL），
交付前逐项通过其 §5 的 DC-01…DC-17 自查表并用 §7 决策树、§8 专家注意点排雷。

## 包内文件

| 文件 | 作用 |
|---|---|
| `SKILL.md` | 契约样例、单命令入口、产物清单、降级矩阵、交付前自检清单 |
| `scripts/main.py` | CLI 与编排：跑查询 DAG、回填契约、写 `result.json` |
| `scripts/engine.py` | 引擎库：发现 / 快照 / schema / 字段字典 / 执行 / 对账 / 报告 |
| `references/expert_playbook.md` | 专家参考手册（S0–S6 / 量化口径 / 领域陷阱 / DC-01…DC-17 / 完整案例） |
| `references/query-method.md` | 查询派生与对账口径说明 |
| `environment/resources.yaml` | 运行环境、入口命令、输入/输出路径、预算与依赖声明（离线、纯标准库） |
| `examples/` | 最小可复跑样例（case.json + samples.csv + batches.csv + dictionary.md） |
| `GAIN_EVIDENCE.md` | 无 Skill 基线对照与使用增益证据（含确定性 `baseline_sim` 说明，非官方对照） |
| `README.md` / `SELFTEST.md` / `GITHUB_URL.txt` | 说明与自检 |

纯标准库（sqlite3, csv, json, re, hashlib, pathlib）；无网络、无时钟，重复运行字节稳定。

## 单命令入口

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

退出码恒为 0。若无授权库，则把输入里的表材料装进 `work/snapshot.db` 后执行同一批 SQL。

## 关键推导示例（真实可复算）

用一张测试快照（`samples` 6 行、`measurements` 7 行，共享键 `sample_id`）跑同一条命令：

- `Q_rows_samples` → `SELECT COUNT(*) FROM "samples"` → 6；独立重算 6，对账通过。
- `Q_code_samples_material` → 取值分布：concrete 2 / iris 2 / wine 2（编码字段按标签，不求和）。
- `Q_num_samples_mass_mg` → n=6，min=95.0，mean=105.1667，max=120.5。
- `Q_join_measurements_samples` → `JOIN ON sample_id` 得 7 行；两侧行数 7/6，未超出驱动表 →
  连接检查通过；`join_ledger.json` 记录 expansion_factor=1.1667 供人工复核一对多关系。
- `Q_missing_samples_material` → missing=0，duplicate_extra=3（6 行只有 3 个不同取值）。
- 共 15 条语句，全部写进 `queries.sql`；对账 7/7 通过（`reconciliation.json`）。

上述数字来自 `results/*.csv` 与 `reconciliation.json`；用同一快照复跑得到相同结果。

## 契约回填

`result.json` 的 `output_contract` 逐键回填，并在顶层同名键回显；`case_id` 原样透传。
用例声明的键优先（含以子命令名命名的键），未声明的用 SKILL 默认键；无法直接映射的键写成结构信封。

## 降级

空输入 / 坏 JSON / 无库无表 → 仍然退出 0、写出合法 `result.json`（`status=partial|input_error`）
与全部交付物；空态工作簿显式说明 `no_queryable_snapshot`，绝不编造结果数值。

## 随包最小样例（examples/，可直接复跑）

```bash
python3 scripts/main.py all --input examples --output /tmp/out --work /tmp/work
# exit 0；status=ok；26 件产物；tables=2( batches, samples ), fields=9, queries=16(失败 0)
# 结果集 CSV 16 份；对账 7/7；连接 Q_join_batches_samples 膨胀比 2.5（no_inflation=true）
# 契约 10/10；哈希 6ddb955ed0cfd49e
```

样例输入：`examples/case.json`（10 键契约）+ `examples/samples.csv`（12 行试块明细）+ 
`examples/batches.csv`（4 行批次，共享键 `batch_id`）+ `examples/dictionary.md`（数据字典）。
无授权 SQLite 库时引擎把表材料装进 `work/snapshot.db` 再执行同一批 SQL。

## 随包文件（v10 新增）

```
references/expert_playbook.md  专家参考手册（S0–S6 六步流水线/量化口径 §3/领域陷阱与单位 §4/自查表 DC-01…DC-17/完整案例）
environment/resources.yaml     运行环境、入口命令、输入/输出路径、预算与依赖声明（离线、纯标准库）
examples/                      最小可复跑样例（case.json + samples.csv + batches.csv + dictionary.md）
GAIN_EVIDENCE.md               无 Skill 基线对照与使用增益证据（含确定性 baseline_sim 说明，非官方对照）
```
