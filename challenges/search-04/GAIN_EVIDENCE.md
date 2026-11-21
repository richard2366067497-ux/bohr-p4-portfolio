# GAIN_EVIDENCE — search-04 / citation-trace

本文件记录**使用增益**的证据口径与本次实测，全部为确定性结构对照，**不是官方分数**。

## 1. 对照设置（公平对照）

- 相同输入：`examples/case.json` + `examples/materials/sample-records.md` 快照。
- 相同条件：同一解释器、同一 `--input/--output`、无网络、无第三方依赖。
- 基线口径 `baseline_sim`：一个**只读题面、不解析材料**的朴素基线——不产生可定位节点/边，
  `locatable_records = 0`、`edges = 0`、`traced_paths = 0`、`contract_keys_filled = 0`。
  该基线由结构确定性构造，仅用于结构对照，不代表基础 Agent 的真实表现。

## 2. 实测（示例案例，`examples/`）

| 指标 | baseline_sim | 本 Skill |
|---|---:|---:|
| 可定位文献节点数（带 `M01#rN`） | 0 | 3 |
| 引用边数（带 locator 与方向） | 0 | 6 |
| 从种子追踪的路径数 | 0 | 1 |
| 回填的契约键数 | 0 | 12 |
| 结构化产物数 | 0 | 6 |

命令：`python3 -B scripts/main.py --input examples --output /tmp/out --work /tmp/work`
（产出 `result.json` 与 6 个产物；`status=traced`）。

## 3. 增益来源（可复核）

1. **起点**：从种子文献出发构建网络，而非关键词检索；基线不建网。
2. **方向与定位**：每条边带 `source/target/kind/locator`，基线无定位 → 溯源率 0 → 100%。
3. **路径解释**：给出从种子出发的深度受限路径，逐跳可回查。
4. **缺口诚实**：缺字段与越界引用进 `gaps.json`，不猜补；基线只输出一段文字。
5. **契约诚实回填**：逐键回填真实值，空集合给带说明的非空结构，不写类型占位符。

## 4. 明确不做的事

- 不虚构基线分数或平台分数；不声称相对基础 Agent 的百分比提升。
- 不同快照之间不比较指标（跨快照结果不可直接比较）。
- 不联网、不查询外部引文库，不冒充全局召回率 / 精确率等官方指标。

## 5. 复跑

```bash
python3 -B scripts/main.py --input examples --output /tmp/out1 --work /tmp/w1
python3 -B scripts/main.py --input examples --output /tmp/out2 --work /tmp/w2
# 规范化后两次的 result.json / citation_network.json / edges.jsonl 应完全一致
```

确定性：同输入重跑，规范 rid、边、路径与契约键不变，时间戳不参与判等。
