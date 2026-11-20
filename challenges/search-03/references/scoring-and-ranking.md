# 打分、facet 与排序口径

脚本实现：`scripts/analyze.py` 中的 `facet_score` / `judge` / `rank_rows`。改阈值必须同步本文档。

## 1. 相关性分数（0–1）

```
score = 0.40·topic + 0.20·object + 0.15·method + 0.10·evidence + 0.10·recency + 0.05·completeness
```

| 分量 | 计算 | 说明 |
|---|---|---|
| `topic` | 主题词命中加权覆盖：题名 ×2、关键词 ×1.5、摘要 ×1，除以 `2×词数`，上限 1.0 | 词数取前 8 个主题词 |
| `object` / `method` | 同上，作用于研究对象/方法 facet 词表 | facet 词表为空时取 `0.9×topic` 作代理，并标 `facet_unspecified` |
| `evidence` | 有摘要且含结果线索（we found/results show/显著/p 值/数值结论）=1.0；有摘要无线索=0.6；无摘要=0.1 | 摘要 <40 字符视为无摘要 |
| `recency` | 落在时间窗内=1.0；窗口 ±2 年=0.6；窗口外=0.05；无窗口时按"近 5 年 1.0 / 近 10 年 0.7 / 更早 0.45 / 缺失 0.4" | 无窗口属默认口径，写进 `assumptions` |
| `completeness` | (题名+摘要+年份+DOI+作者) 命中字段数 / 5 | 元数据缺失影响置信度，不直接判负 |

硬排除（R8）命中时 `score = min(score, 0.12)`；重复/版本条目 `score = 0`。

**结构代评分**（语言不通、或输入完全没有研究问题时启用）：不臆断相关性，改用
`score = 0.35·evidence + 0.25·recency + 0.20·completeness + 0.20·type_fit`，且所有记录至少 `maybe`
（硬排除与重复除外）。触发条件写在 `result.method_notes.lexical_bridge` 与 `degradations`。

## 2. facet 怎么来

| facet | 来源 | 抽取 |
|---|---|---|
| `topic` | `case.json` 的 `task_instruction`/研究问题（取"研究问题："之后到句号） | 拉丁词干（≥3 字符）＋中文二元组，去停用词与泛词组（研究/文献/方法/结果…），前 14 个 |
| `object` | 纳入条款中含"研究对象/人群/样本/体系/sample/cohort"的句子 | 同上，前 8 个 |
| `method` | 含"方法/技术/模型/表征/检测/method/model/assay"的句子 | 前 8 个 |
| `type_include` / `type_exclude` | 纳入/排除条款中的类型词 | 映射到 `primary`/`review`/`preprint`/`rct`/`cohort` |
| `time_window` | `YYYY-YYYY`、`since/after/from YYYY`、`近 N 年` | `[起, 止]` |
| `exclusions` | 排除条款 | 排除词表，用于 R8 的条款命中判定 |

排除条款**不参与** object/method/type 抽样（否则"排除综述"会污染对象词表）。
`k` 取值：`case.json` 的 `k/top_k/target_k/top_n` → 文本里的 `top k = N` / `前 N 篇` → 默认 10。

## 3. 排序键（固定、可复算、无随机）

```
score desc（保留 4 位小数）
  → relevance（direct 0 < indirect 1 < none 2）
  → 类型权重 desc（原始研究 1.0 / 综述 0.8 / 预印本 0.7 / 其他 0.3）
  → 年份 desc（缺失记 0）
  → record_id asc
```

- 只有 `label != exclude` 且非重复条目进入排名；其余进 `ranking.excluded[]`（保留理由）。
- `score` 相同的记录进 `ranking.tie_groups[]`，写明成员与后续键，便于复核"为什么这篇在前"。
- `k` 来自输入；`ranking.top_k` 取前 k 条，若不足 k 条必须在 `assumptions` 说明（候选不足/待定过多）。
- 复算方法：任意人拿 `screening.jsonl` 的 `score` / `relevance` / `record_type` / `year` / `record_id`
  用上面的键排序，必须得到同样的 `rank`（`selfcheck` 会重算并比对）。

## 4. 阈值与标签映射（规则通道）

| 条件 | 标签 |
|---|---|
| 硬排除 R8 | `exclude` / `none` |
| 结构代评分模式 | `maybe` / `indirect` |
| 无摘要（R11） | `maybe`；topic≥0.35 时 `indirect` 否则 `none` |
| `score ≥ 0.55` 且 `topic ≥ 0.35` | `keep` |
| `score ≥ 0.35` 或 `topic ≥ 0.20` | `maybe` |
| 其它 | `exclude` / `none` |

`relevance`：`topic≥0.5 且 object≥0.4 且 method≥0.35` → `direct`；`topic≥0.25 或 object≥0.4` → `indirect`；
否则 `none`。

## 5. 置信度与可核验

| 置信度 | 条件 |
|---|---|
| `high` | 有摘要、命中 ≥4 条规则、引证逐字命中 |
| `medium` | 有摘要、命中 2–3 条 |
| `low` | 摘要缺失 / 命中 ≤1 条 / 引证未通过校验 / 双通道分歧被降级 |

引证（`evidence_quote`）必须能在 `evidence_locator` 指向的字段里逐字找到（空白规范化后比较）。
未通过 → `confidence=low`、`label=maybe`、`score≤0.5`，并在 `conflicts.quote_unverified` 与
`pending_human` 记录；这条规则优先于任何"看起来更合理"的分数。

## 6. 效率与增益的可度量项（写进 coverage）

- `coverage_ratio = screened / total_candidates`（必须为 1.0）。
- `maybe_zone`：待定区规模，直接等于人工必看条目数。
- `merged_duplicates`：被合并的重复/版本条目数，等于人工本来要重复读的量。
- `agent_rows` vs `rule_fallback_rows`：多少条有语义复核，多少条只是规则兜底。
- `quote_verified`：多少条判定可被他人逐字复核。
- `rule_fallback_rows`、`not_processed_cap`、`missing_abstract` 三项异常必须为 0 才算"干净交付"。

两次运行同一输入，`screening.jsonl` / `ranking.json` / `coverage.json` / `conflicts.json` 必须逐字节一致
（已实测；`runtime.elapsed_sec` 与 `changes[].at` 是唯一的时间戳差异，不参与比对）。
