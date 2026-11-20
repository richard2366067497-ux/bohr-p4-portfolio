# 工作稿 schema、0/1/2 评分口径与失败归因

本文件是 `/app/work/draft.json` 的字段字典 + `check` 的判定规则 + 评分档位与探针构造方式。
实现分别在 `scripts/core.py`（`norm_item` / `validate` / `score_answer` / `probe_answers`）与
`scripts/ledger.py`（`build_set`）。

## 1. 工作稿顶层

| 字段 | 必需 | 类型 | 说明 |
|---|---|---|---|
| `set_meta` | 是 | obj | `set_id`（自拟）、`version`（如 `v1`）、`license`（读不到写 `unknown`）、`scope`（一句话）、`uncovered`（workorder 中不做的题号数组，附原因可写进 `uncertainties`） |
| `items` | 是 | array | 题卡，至少 1 张；建议 3–8 张（预算内能读完并写扎实的数量） |
| `conflicts` | 否 | array | `{a, b, statement}`：两处 locator + 冲突陈述，脚本只核验两处引文都存在 |
| `uncertainties` | 否 | array | 材料未报告、口径歧义、来源不全等，进入 `result.uncertainties` |
| `history` | 否 | array | 上一版摘要（可留空，脚本自己从旧 `cards.json` 取） |

## 2. 题卡字段

| 字段 | 必需 | 规则 |
|---|---|---|
| `item_id` | 是 | 唯一；workorder 有编号时沿用（`W01`…），否则自拟 `Q01`… |
| `task_type` | 是 | `extraction` / `numeric` / `method` / `definition` / `table` / `conflict` / `coverage` / `other`，越界降为 `other` |
| `question` | 是 | ≥10 字符，必须能判对错；禁止“谈谈”“简述”这类无锚点题面 |
| `source_refs[]` | 是 | 至少 1 条 `{material, locator, quote, native_id?}` |
| `reference_answer[]` | 视情况 | `{text, locator}`；`reference_missing=true` 时必须为空 |
| `reference_missing` | 否 | 材料没给答案时置 `true`；**不得自造 gold** |
| `scoring_rule` | 是 | `{mode, scale{2,1,0}, key_terms[], must_have}` |
| `difficulty` | 否 | `easy` / `medium` / `hard` / `unknown` |
| `license` | 否 | 读不到写 `unknown` |
| `notes` | 否 | 出题理由、边界说明 |

### 引文（quote）四条硬规则

1. **逐字**：从 `show` 输出整段复制，不改词、不翻译、不加省略号、不跨段拼接；
2. **长度 ≥12 字符**（脚本低于此长度直接判未命中）；
3. **locator 与引文一致**：脚本会把命中位置反推成真实段号，不一致时按真实段号更正并在
   `check` 里报 `locator_mismatch`，同时写进 `anchors[].locator_declared` 留痕；
4. 匹配顺序 `exact → casefold → 去空白`，所以大小写与换行差异可以容忍，**同义改写不行**。

### 关键项（key_terms）三条硬规则

1. 1–5 条短串，取原文用词（数字、单位、专有名词优先）；
2. **必须能在自己的 `reference_answer` 文本里找到**——否则 gold 探针拿不到 2 分，
   `check` 会报 `key_terms absent from reference_answer`，`build` 会把校准不一致写进失败库；
3. 关键项决定 `coverage`，也就决定分数档位；写成“回答准确”这类抽象描述等于无法判分。

## 3. 0/1/2 评分口径（机械可复算）

```
coverage = |{t ∈ key_terms : t 出现在答案文本}| / |key_terms|      # 大小写折叠 + 空白归一后子串包含
2  ⇐ coverage ≥ 0.75 且有 ≥1 条 verified 锚点
1  ⇐ 0.25 ≤ coverage < 0.75
0  ⇐ coverage < 0.25、空答、答非所问
```

非正常态**不进 0/1/2**，单列状态：

| 状态 | 触发条件 | 处理 |
|---|---|---|
| `missing_reference` | 题卡无参考答案 | 不评分；失败库登记；题可改为“材料是否报告 X” |
| `no_anchor` | 无逐字命中锚点 | 不可判，卡被拒收（`cards.rejected`） |
| `manual_review` | `mode=manual_only` | 交人工，不给自动分 |
| `format_error` | 候选输出不可解析/空文件 | 记 0 且带 `format_error` 标记（不混进正常 0 分） |

## 4. 探针校准（本包增量之一）

对每张**可评分**卡（有参考答案 + 有 verified 锚点 + 非 manual_only），`build` 自动构造三条探针，
用同一套规则打分，比对期望：

| 探针 | 构造 | 期望 |
|---|---|---|
| `gold` | 参考答案全文拼接 | 2 |
| `partial` | `key_terms` 前 `k = ⌈n/4⌉` 条（`k<n` 时才构造；n=1 时跳过，不伪造） | 1 |
| `empty` | 空串 | 0 |

`calibration.agreement = 一致条数 / 有期望的条数`。不一致说明**评分规则或关键项写法有问题**
（而不是模型答错），必须回改 `scoring_rule` 再 `build`，否则 `selfcheck` 报 ATTENTION。

> 探针是自校准证据，不是被评测 Agent 的分数，也不是 DSH 分数。

## 5. 失败归因 → 下一版专项题

| type | 含义 | 建议专项题 |
|---|---|---|
| `missing_reference` | 卡无参考答案 | 把题改成“材料是否报告”二元题 |
| `no_anchor` | 引文未命中 | 引文定位专项题（给段落，要求指出段号） |
| `locator_mismatch` | locator 与引文不符 | locator 反查专项题 |
| `calibration_disagreement` | 探针档位不对 | 评分档位边界题（0/1/2 各一条） |
| `unattributed_raw_output` | 候选输出无法归属到题 | 输出格式约束题 |
| `low_coverage` | 候选答案命中 <0.25 | 同题型高难度变体 |

`build` 会按 type 聚合，在 `failures.md` 末尾生成 `S01…` 编号的下一版题号建议——这就是
“一次失败归到题型 → 变成下一版专项题”的可执行落点。

## 6. `check` 的判定表

| 判据 | 级别 | 动作 |
|---|---|---|
| `question` <10 字符 / 无 `source_refs` / 引文全部未命中 | error | 卡被拒收，进 `rejected` |
| `item_id` 重复 | error | 该卡拒收 |
| `reference_missing=true` 但 `reference_answer` 非空 | error | 自相矛盾，拒收 |
| `mode=key_terms` 但 `key_terms` 为空 | error | 无法判分，拒收 |
| workorder 题号没有对应卡、也没写进 `uncovered` | error | 记 `workorder_uncovered` |
| `key_terms` 不在 `reference_answer` 里 | warning | 校准会失败，必须改 |
| `locator` 与命中段不一致 | warning | 按真实段号更正并留痕 |
| `scale` 缺 0/1/2 文案 | warning | 建议补齐（人判也要用） |

`RESULT: PASS` 只要求**零 error**；warning 需要人判断是否接受，接受就写进 `uncertainties`。

## 7. 最小合法工作稿（示例，非正式案例答案）

```json
{
  "set_meta": {"set_id": "demo", "version": "v1", "license": "unknown", "scope": "示例"},
  "items": [{
    "item_id": "Q01", "task_type": "extraction",
    "question": "示例：材料中该实验使用的培养基是什么？",
    "source_refs": [{"material": "M01", "locator": "M01#p2", "quote": "grown in modified f/2 medium"}],
    "reference_answer": [{"text": "modified f/2 medium", "locator": "M01#p2"}],
    "scoring_rule": {"mode": "key_terms",
                     "scale": {"2": "答出培养基名", "1": "只答出类别", "0": "未命中"},
                     "key_terms": ["modified f/2"], "must_have": 1},
    "difficulty": "easy", "license": "unknown"
  }]
}
```
