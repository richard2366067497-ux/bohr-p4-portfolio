# GAIN_EVIDENCE — search-06 / latest-lit-tracking

本文件记录**使用增益**的证据口径与本次实测，全部为确定性结构对照，**不是官方分数**。

## 1. 对照设置（公平对照）

- 相同输入：`examples/case.json` + `examples/materials/{crossref.md,europepmc.md}` 快照（两个订阅源）。
- 相同条件：同一解释器、同一 `--input/--output/--work`、无网络、无第三方依赖。
- 基线口径 `baseline_sim`：一个**只读题面、不读状态、不比快照**的朴素基线——不归一化、不去重、
  不增量、不给依据，`reported_new = 全部条目`、`dedup_rate = 0`、`traceable_rate = 0`、`contract_keys_filled = 0`。
  该基线由结构确定性构造，仅用于结构对照，不代表基础 Agent 的真实表现。

## 2. 实测（示例案例，`examples/`）

| 指标 | baseline_sim | 本 Skill |
|---|---:|---:|
| 原始记录数 `N_raw` | 0 | 5 |
| 去重后唯一记录数 `N_unique` | 0 | 3 |
| 去重率 `D` | 0 | 0.40 |
| 新增发现 `N_new` | 5（全量误报） | 2 |
| 窗口外正确隔离 `N_old` | 0 | 1 |
| 告警数 `alerts` | 5 | 2 |
| 来源可追溯率（带 locator+依据） | 0 | 100% |
| 幂等重跑（第二次 new=0） | 否 | 是 |
| 回填的契约键数 | 0 | 16 |
| 结构化产物数 | 0 | 6 |

命令：`python3 -B scripts/main.py --input examples --output /tmp/out --work /tmp/work`
（产出 `result.json` 与 6 个产物；`status=completed`）。

## 3. 增益来源（可复核）

1. **稳定判重键**：DOI 大小写不敏感，示例中 5 条原始记录归并为 3 条唯一记录（重复率 0.40）。
2. **增量而非全量**：与 `state.json:last_snapshot` 比对，只报 2 条 new；窗口外的 2019 年记录进 `out_of_window`。
3. **告警抑制**：new 2 条即告警 2 条（对比 baseline 全量误报 5 条），重复投递被 `delivery_log` 抑制。
4. **幂等**：同快照重跑 `new` 为空、`last_window_end` 不漂移，可安全按窗口调度。
5. **可举证**：每条决策带 `source` + `S0x#rN` locator + 判重键；缺 DOI 的记录进入 `decision_missing` 而非被猜测补全。
6. **契约诚实回填**：逐键回填真实值，`decisions / decision_missing / out_of_window` 给非空结构，不写类型占位符。

## 4. 明确不做的事

- 不虚构基线分数或平台分数；不声称相对基础 Agent 的百分比提升。
- 不联网、不查询远程数据库，不冒充全局召回、live coverage 或"最新发表"。
- 不同快照之间不比较指标（跨快照结果不可直接比较）。

## 5. 复跑

```bash
python3 -B scripts/main.py --input examples --output /tmp/out1 --work /tmp/w1
python3 -B scripts/main.py --input examples --output /tmp/out2 --work /tmp/w2
# 规范化后两次的 result.json / diff_report.json / window.json 应完全一致；第二次 new 为空
```

确定性：同输入重跑，规范 `dedup_key`、分类、契约键与计数不变，时间戳不参与判等。
