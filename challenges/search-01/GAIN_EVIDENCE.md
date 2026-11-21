# GAIN_EVIDENCE — search-01 / traceable-literature-retrieval

本文件记录**使用增益**的证据口径与本次实测，全部为确定性结构对照，**不是官方分数**。

## 1. 对照设置（公平对照）

- 相同输入：同一 `case.json` + `task.md` + 同一 `materials/` 快照。
- 相同条件：同一解释器、同一 `--input/--output`、无网络、无第三方依赖。
- 基线口径 `baseline_sim`：一个**只读题面标签、不解析材料**的朴素基线——
  它不产生可定位候选，`locatable_candidates = 0`、`distinct_after_dedup = 0`、`contract_keys_filled = 0`。
  该基线由脚本确定性构造，仅用于结构对照，不代表基础 Agent 的真实表现。

## 2. 实测（示例案例，`examples/`）

| 指标 | baseline_sim | 本 Skill |
|---|---:|---:|
| 可定位候选数 | 0 | 2 |
| 去重后唯一记录数 | 0 | 3 |
| 回填的契约键数 | 0 | 9 |

命令：`python3 -B scripts/main.py compare --input examples --output /tmp/out --work /tmp/work`
（同时写 `gain_report.json` / `gain_report.md`）。

## 3. 增益来源（可复核）

1. **定位**：每条候选带 `source_id#n` locator，基线无定位 → 溯源完整率 0 → 100%。
2. **去重**：DOI/标题分层判重，重复条目合并并保留 `duplicate_of`，基线不做去重。
3. **分开记录**：入选与被排除各自带依据（`screening.json`），基线只输出一段文字。
4. **契约诚实回填**：逐键回填真实值，空列表用 `{count,items,note}` 包裹而非类型占位符。

## 4. 明确不做的事

- 不虚构基线分数、白板或平台分数；不声称相对基础 Agent 的百分比提升。
- 不同快照之间不比较指标（跨快照结果不可直接比较）。
- 相关性为关键词重叠排序，属内部顺序，不冒充 Precision@k / nDCG@k 等官方指标。

## 5. 复跑

```bash
python3 -B scripts/main.py --input examples --output /tmp/out1 --work /tmp/w1
python3 -B scripts/main.py --input examples --output /tmp/out2 --work /tmp/w2
# 规范化后两次的 result.json / coverage.json / candidates.jsonl 应完全一致
```

确定性：同输入重跑，规范 ID、排名、契约键与覆盖计数不变，时间戳不参与判等。
