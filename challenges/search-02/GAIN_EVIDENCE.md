# GAIN_EVIDENCE — search-02 / rq-driven-retrieval

本文件记录**使用增益**的证据口径与本次实测，全部为确定性结构对照，**不是官方分数**。

## 1. 对照设置（公平对照）

- 相同输入：`examples/case.json` + `examples/materials/sample-records.md` 快照。
- 相同条件：同一解释器、同一 `--input/--output`、无网络、无第三方依赖。
- 基线口径 `baseline_sim`：一个**只读题面、不解析材料**的朴素基线——不产生可定位候选，
  `locatable_candidates = 0`、`distinct_after_dedup = 0`、`contract_keys_filled = 0`。
  该基线由结构确定性构造，仅用于结构对照，不代表基础 Agent 的真实表现。

## 2. 实测（示例案例，`examples/`）

| 指标 | baseline_sim | 本 Skill |
|---|---:|---:|
| 可定位候选数（带 `source_id#n`） | 0 | 4 |
| 入选候选数（附筛选依据） | 0 | 4 |
| 回填的契约键数 | 0 | 25 |
| 结构化产物数 | 0 | 8 |

命令：`python3 -B scripts/main.py --input examples --output /tmp/out --work /tmp/work`
（产出 `result.json` 与 8 个产物；`status=answered`，覆盖 1/1 子问题）。

## 3. 增益来源（可复核）

1. **拆解**：研究问题拆为带 `queries / depends_on / priority / required` 的结构化子问题，基线不拆。
2. **定位**：每条候选带 `M01#rN` locator 与逐字 quote，基线无定位 → 溯源率 0 → 100%。
3. **依据**：入选 / 排除各带 `basis` 与相关性评分，基线只输出一段文字。
4. **停止**：给出 `saturated / low_marginal_gain / needs_human` 判据与理由，基线不判停止。
5. **契约诚实回填**：逐键回填真实值，空内容给带说明的非空结构，不写类型占位符。

## 4. 明确不做的事

- 不虚构基线分数或平台分数；不声称相对基础 Agent 的百分比提升。
- 不同快照之间不比较指标（跨快照结果不可直接比较）。
- 相关性为确定性关键词重叠排序，属内部顺序，不冒充 Precision@k / nDCG@k 等官方指标。

## 5. 复跑

```bash
python3 -B scripts/main.py --input examples --output /tmp/out1 --work /tmp/w1
python3 -B scripts/main.py --input examples --output /tmp/out2 --work /tmp/w2
# 规范化后两次的 result.json / coverage.json / candidates.jsonl 应完全一致
```

确定性：同输入重跑，规范 rid、排名、契约键与覆盖计数不变，时间戳不参与判等。
