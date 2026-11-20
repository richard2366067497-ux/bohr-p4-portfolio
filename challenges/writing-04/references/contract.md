# contract.md — 数据契约、去重判据与 Agent 交接格式

本文件说明：`output_contract` 如何逐键回填、各交付物的字段结构、去重/核验判据，以及 Agent 撰写的
`work/draft.json` 该长什么样。脚本按此契约渲染，评测与人工都按此复核。

---

## 1. output_contract 逐键回填

`result.json` 中：

- `output_contract` 是对象，**必须包含用例声明的每一个键**（key-by-key 回填，不重命名、不丢弃、不合并）。
- 同时把每个键的同一个值放到 `result.json` **顶层同名键**，方便只读顶层的消费方。
- `case_id` 原样透传（来自 `/input/case.json`）；无法取得时回退为输入目录名。
- `status` ∈ `success | partial | failed`，由产物推导。

键名 → 语义的回填规则（按优先级）：

| 键名线索 | 回填值 |
|---|---|
| `numbering_policy` / 含 `policy` | 编号策略字符串，默认 `first-citation` |
| `key_to_number` / 含 `number`+`map` | `{规范键: 编号}` 数组/对象 |
| 含 `duplicate` / `dedup` / `merge` | 合并决策数组 `[{a,b,verdict,confidence,reasons,conflicts}]` |
| `reference_list` / 含 `bibliograph` | 文献表文件路径 `references.gbt.md` |
| 恰为 `references` / `refs` | 参考文献条目数组 `[{number,key,entry_type,plain,gbt,apa,doi}]` |
| 含 `citation_map` / `mapping` | `citation_map.csv` 路径 |
| 含 `verif` | `verification.csv` 路径 |
| 含 `claim` / `support` | `claim_support.csv` 路径 |
| 含 `audit` | `audit.json` 路径 |
| 含 `change` / `diff` / `edit` | 变更记录数组 `[{type,target,before,after,reason,locator,quote}]` |
| 含 `uncertain` / `manual` / `review` | 不确定项数组 |
| 含 `source` | `[{source_id,path,locator,quote}]` |
| 含 `manuscript` / `revised` | `manuscript.revised.md` 路径 |
| 含 `unknown` / `unresolved` | 正文出现但文献表缺失的键数组 |
| 无法匹配 | `{"kind","items":[],"count":0,"note"}` 诚实信封 |

**没有数据时不写空壳**：用结构信封 `{"kind": <键名>, "items": [], "count": 0, "note": "<原因>"}`，
并记入 `result.json.uncertainty`，供人工补判。绝不出现 `[待写]` / `pending` / `null` 这类占位符。

## 2. 交付物字段

- **citation_map.csv**：`old_key, canonical_key, new_number, title, doi, cited_in_text, source`
- **dedup_decisions.csv**：`a, b, a_title, b_title, verdict, confidence, reasons, conflicts`
- **verification.csv**：`key, doi, status, detail, issues`（`issues` 为 `code:detail` 分号拼接）
- **claim_support.csv**：`sentence, marker, ref, score, shared_terms, status, locator, quote`
  （`status` ∈ `matched | weak | mismatch_suspect`）
- **changes.csv**：`type, target, old_key, before, after, reason, locator, quote`
  （`type` ∈ `insert | merge | renumber | format | no_op`，`locator` 形如 `L12:C34` 或 `C120`，
  `quote` 是可逐字回溯的原文摘录）
- **audit.json**：`input_records / canonical_records / numbering_unique / changes / claims_* / improvement`
- **sources.json**：`{"sources": [{source_id, path, locator, quote}]}`
- **uncertainty.json**：`{"items": [...], "limits": [...], "notes": [...]}`

## 3. 去重判据（并查集 + 阈值制，逐对可核验）

- DOI 相同（均非空）`0.99`；eprint/arXiv 相同 `0.97`；
- 规范化题名相同且同首作者 `0.98`（同年）/`0.95`（不同年）；
- 题名 token 相似 ≥`0.85` 且同作者同年 `0.92`；
- 相似 ≥`0.65` → 只记 `manual_review`，**不自动合并**；
- 同 DOI 不同题名、同题名不同首作者 → 记 `conflicts` 并降为 `review`。

合并时保留字段最全的一条为 `canonical`，其余记入 `merged[]`。

## 4. 离线核验（无网络、无时钟）

`verification.csv.status`：`clean | warn | error`。**不谎称已联网核验**。本地规则：

- error 级：DOI 语形非 `10.xxxx/...`；DOI 用示例保留前缀（`10.1234/` 等）；题名/刊名含示例文本；
  年份越界（早于 1500 / 晚于 2100）；题名与刊名相同。
- warn 级：无 DOI、无作者、期刊论文缺卷期页。

## 5. Agent 交接：work/draft.json

Agent 读完 `work/evidence.json` 与 `work/candidates.json` 后撰写 `work/draft.json`：

```json
{
  "claims": [
    {"sentence": "The fill compositing technique improved the tensile strength",
     "action": "insert", "refs": ["smith2020fill"],
     "reason": "功能性主张，需要来源支撑，插到该句句末"},
    {"sentence": "A sentence the agent decided not to cite",
     "action": "skip", "refs": [], "reason": "常识性陈述，不引"}
  ],
  "dedupe_overrides": [
    {"a": "wang2019a", "b": "wang2019b", "verdict": "no_merge",
     "reason": "两文同年不同卷，非重复"}
  ],
  "contract_overrides": {}
}
```

- `claims[].sentence` 用**正文句子的前缀**（≥6 字）匹配；`action` 取 `insert | skip`。
- `insert` 时 `refs` 指定要挂的规范键（最多 2 个）；匹配不上的条目记入 `result.notes`
  （`draft_unmatched`），不影响交付。
- `dedupe_overrides` 的 `no_merge` 会记录人工意见；`contract_overrides` 可覆盖任一契约键的最终值。
- 没有 `draft.json` 时，`build` 与 `all` 等价 —— 单命令路径始终可用。

## 6. 边界与降级

- 空/坏输入：`exit 0`，写合法 `result.json`（`partial` 或 `failed`）、全部交付物（少量为诚实说明行），
  `limits` / `uncertainty` 记录原因，**不编造任何文献条目或引用位置**。
- 稿件无文献表、无独立文献库：仍产出修订稿与完整 `result.json`，契约键以结构信封回填。
