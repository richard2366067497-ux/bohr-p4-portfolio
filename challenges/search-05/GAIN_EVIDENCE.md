# GAIN_EVIDENCE — search-05 / multi-db-joint-retrieval

本文件记录**使用增益**的证据口径与本次实测，全部为确定性结构对照，**不是官方分数**。

## 1. 对照设置（公平对照）

- 相同输入：`examples/case.json` + `examples/materials/{crossref.md,europepmc.md}` 快照（两个“库”）。
- 相同条件：同一解释器、同一 `--input/--output`、无网络、无第三方依赖。
- 基线口径 `baseline_sim`：一个**只读题面、不解析材料**的朴素基线——不合并、不去重、不给定位，
  `n_raw = n_unique = 0`、`dedup_rate = 0`、`traceable_rate = 0`、`contract_keys_filled = 0`。
  该基线由结构确定性构造，仅用于结构对照，不代表基础 Agent 的真实表现。

## 2. 实测（示例案例，`examples/`）

| 指标 | baseline_sim | 本 Skill |
|---|---:|---:|
| 原始记录数 `N_raw` | 0 | 4 |
| 去重后唯一记录数 `N_unique` | 0 | 3 |
| 去重率 `D` | 0 | 0.25 |
| 来源可追溯率（带 locator） | 0 | 100% |
| 回填的契约键数 | 0 | 13 |
| 结构化产物数 | 0 | 6 |

命令：`python3 -B scripts/main.py --input examples --output /tmp/out --work /tmp/work`
（产出 `result.json` 与 6 个产物；`status=answered`）。

## 3. 增益来源（可复核）

1. **跨库归并**：DOI 精确（大小写不敏感）+ 模糊键判重，示例中 4 条原始记录归并为 3 条唯一记录。
2. **定位**：每条候选带 `D01#rN` locator 与逐字 quote，基线无定位 → 可追溯率 0 → 100%。
3. **字段规范化**：缺失（null）与未知（"unknown"）区分，字段覆盖率按去重后记录数报告。
4. **去重留痕**：`dedup_report.json` 保留组与合并依据，基线只输出一段文字。
5. **契约诚实回填**：逐键回填真实值，`evidence_map / change_log / coverage` 给非空结构，不写类型占位符。

## 4. 明确不做的事

- 不虚构基线分数或平台分数；不声称相对基础 Agent 的百分比提升。
- 不同快照之间不比较指标（跨快照结果不可直接比较）。
- 不联网、不查询远程数据库，不冒充全局召回或 live coverage。

## 5. 复跑

```bash
python3 -B scripts/main.py --input examples --output /tmp/out1 --work /tmp/w1
python3 -B scripts/main.py --input examples --output /tmp/out2 --work /tmp/w2
# 规范化后两次的 result.json / coverage.json / dedup_report.json 应完全一致
```

确定性：同输入重跑，规范 rid、组、契约键与覆盖计数不变，时间戳不参与判等。
