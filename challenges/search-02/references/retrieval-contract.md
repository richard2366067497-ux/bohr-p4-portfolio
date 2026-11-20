# 检索契约与判据（search-02）

本文件固定检索过程的字段与判据，供 Agent 与复核者使用。所有结论都必须能回到某个 `locator`
与逐字 `quote`。

## 1. 子问题（subquestions）

| 字段 | 含义 |
|-|-|
| `id` | 子问题编号，`SQ1`、`SQ2`…… |
| `type` | `object / mechanism / method / comparison / time` 之一 |
| `text` | 子问题文本 |
| `queries` | 该子问题的检索式（同义/缩写/上下位扩展） |
| `depends_on` | 前置子问题 id 列表（无则空） |
| `priority` | 检索顺序，数字越小越先 |
| `required` | 是否为必须覆盖（决定停止判据） |

## 2. 候选记录（candidates）

| 字段 | 含义 |
|-|-|
| `rid` | 记录编号，来自材料快照 |
| `locator` | 定位串，形如 `M01#p3` 或 `M01#r2` |
| `relevance` | 0–1 相关性，规则化计算，可复算 |
| `decision` | `include / exclude / uncertain` |
| `subquestion_ids` | 该记录服务的子问题 |
| `basis` | 判定依据（如 token overlap） |
| `quote` | 逐字支撑片段 |

## 3. 停止判据（stop_decision）

- `saturated`：某子问题已有 ≥2 条可核验 include 记录，边际收益低。
- `low_marginal_gain`：仅有 1 条 include，继续检索无新增。
- `needs_human`：无 include 证据，需人工或补充数据源。

## 4. 覆盖度（coverage）

`covered / required_total` 只统计带 locator 的 include 决策；不给“全球召回率”，只给快照内覆盖率。

## 5. 诚实边界

- 相关性是规则打分，不是人工金标准；每条都保留 `basis` 与 `quote`。
- 不做全文精读、偏倚评估、翻译；元数据缺失如实记录，不补造。
- 空/坏输入时输出 `insufficient_evidence` 或 `input_error`，并写清 `limits`。
