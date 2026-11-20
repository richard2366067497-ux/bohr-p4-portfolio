```
{
  "case_id": "case-000",
  "status": "success",
  "language": "en",
  "deliverable": "revised_manuscript.md",
  "preserved_facts": [{"anchor": "materials/manuscript.md#C1", "comment": "RC01", "change": "C1", "marker": "[[C1]]", "kind": "narrow"}],
  "evidence_map": [{"comment_id": "RC01", "anchor": "materials/manuscript.md [B2.S1] chars:120-210",
                    "decision": "accept", "change_ids": ["C1"], "kind": "narrow"}],
  "change_log": [{"action": "applied a narrow revision", "target": "C1", "reason": "comment RC01",
                  "locator": "revised_manuscript.md#C1"}],
  "output_contract": {
    "case_id": "case-000",
    "deliverable": "revised_manuscript.md",
    "preserved_facts": [{"anchor": "materials/manuscript.md#C1", "comment": "RC01", "change": "C1", "marker": "[[C1]]", "kind": "narrow"}],
    "evidence_map": [{"comment_id": "RC01", "anchor": "materials/manuscript.md [B2.S1] chars:120-210",
                      "decision": "accept", "change_ids": ["C1"], "kind": "narrow"}],
    "change_log": [{"action": "applied a narrow revision", "target": "C1", "reason": "comment RC01",
                    "locator": "revised_manuscript.md#C1"}]
  }
}
```

# 使用与结构说明 / Usage and structure

这是**审稿回复与论文修改**（reviewer response and manuscript revision）的离线工具包。
纯标准库，无网络；单命令跑完全流程；坏输入也恒 `exit 0`。

## 调用

```text
python3 scripts/main.py --input /input --output /app/output --work /app/work
```

可选参数：`--draft FILE`（Agent 起草的决定/改句，见下）、`--lang zh|en`（强制语言）。

## Agent-first：两条路径

1. **确定性路径（默认）**：脚本自己切分评论、匹配锚点、按类型生成真实修订句并落盘。
2. **Agent 起草路径（优先）**：若存在 `--draft FILE`，或 `$WORK/draft.json`，或 `$INPUT/draft.json`，
   其中按条给出决定与改句即被原样采用。格式：

   ```json
   {"language": "en",
    "decisions": [{"comment_id": "RC01", "decision": "accept", "kind": "narrow",
                    "revised_text": "We now state that the effect holds only in the reported setting."}]}
   ```

无论走哪条路径，脚本只声称**能在修改稿中定位到 `[[Cx]]` 锚点**的改动（`selfcheck.json` 会校验三向一致性）。

## 评论的两种常见形态

- **编号形态**：`1.`、`(1)`、`Comment 2:`、`Reviewer 1`、`审稿意见 3`。逐条切分。
- **项目符号形态**：`- `、`* `、`• `。可用于修改会议的要点记录。
- 若两种都不足两条，则按空行段落切分，避免把一整段当成一条。

## 评论类型与动作（taxonomy）

| 类型 type | 中文 | 触发信号（示例） | 动作 kind | 默认判定 |
|---|---|---|---|---|
| `clarify_scope` | 范围不清 | scope, generalise, over-claim, 范围, 外推, 过强 | `narrow` | accept |
| `add_evidence` | 证据不足 | sample, significance, statistics, 样本, 统计 | `cite` | accept/partial |
| `new_material` | 需新材料 | approval, consent, new data, 伦理, 审批, 招募 | `defer` | defer |
| `wording` | 措辞 | wording, tone, phrasing, 措辞, 表述, 语气 | `clarify` | accept |
| `format` | 格式与引用 | reference, figure, table, 引用, 图, 表 | `clarify` | accept |
| `out_of_scope` | 超范围/误读 | out of scope, irrelevant, misread, 超出范围, 无关, 误读 | `reject` | reject |

## 判定口径（四态）

| 情形 | 判定 decision |
|---|---|
| 可锚定，且不依赖新材料 | `accept`（真改正文 + `[[Cx]]` 锚点） |
| 可锚定，但依赖新材料 | `partial`（尽量改可改部分 + 记待补） |
| 无法锚定，或明确需要新样本/伦理审批 | `defer`（记待补清单，不猜改） |
| 超出研究所报告范围或基于误读 | `reject`（不采纳，回复信写明理由） |

锚点匹配阈值 `ANCHOR_THRESHOLD = 0.15`：低于阈值的评论不再被强行锚定，而是落入 `defer`/`reject`。

## 修订句是怎么生成的（真实可核验）

`revise_sentence()` 对锚定句做**可见改写**，并附加唯一锚点 `[[Cx]]`：

- `narrow`：软化过度断言（`overclaim`）并追加范围限定（"… is not generalized beyond it." / "该结论仅限本研究所报告的情形…"）。
- `cite`：在句末插入引用位标记（"[citation needed: …]" / "[待补引用：…]"）。
- `clarify`：软化过度断言；若无可软化词，则补一句"按审稿意见已明确"的声明。
- `defer` / `reject`：不改正文；分别进入待补清单或回复信的理由说明。

修改稿末尾追加一节「修改点清单 / Tracked changes」，逐条列出 `[[Cx]] 原句 -> 新句`。

## 台账字段

| 字段 | 含义 |
|---|---|
| `id` | 评论编号 `RC01` 起 |
| `text` | 评论原文 |
| `kind` | 评论类型（见 taxonomy） |
| `sub_requirements` | 由分号/顿号/and 切出的子要求 |
| `anchor` | 基线中的最佳匹配段落定位（`path [B#.S#] chars:a-b`），空串表示未锚定 |
| `anchor_similarity` | 锚点相似度 |
| `decision` | `accept` / `partial` / `reject` / `defer` |
| `needs_new_material` | 是否明确要求新样本、伦理审批等 |
| `change_ids` | 对应的修改编号 |

## 修改定位表 change_locator.json

`changes[]` 每项：`id`、`comment_id`、`kind`、`decision`、`anchor_locator`、`anchor_text`、
`revised_text`、`revised_locator`（`revised_manuscript.md#Cx`）、`marker`（`[[Cx]]`）、`applied`。

## 回复模板（templates）

`accept`：已采纳。修改稿已包含相应改动（{{change_ids}}，见 {{locator}}）。
`partial`：部分采纳。{{change_ids}} 回应了可在基线内解决的部分，其余需基线之外的材料。
`reject`：未采纳。该要求超出本研究所报告的范围（或基于对本文的误读）；理由见下。
`defer`：暂缓。需补充新材料（如伦理审批或新增数据）后方可回应；已记入待补清单。

## 自查 selfcheck.json

- 每个 `change_ids` 都在 `change_locator.json` 中存在，且其 `[[Cx]]` 出现在修改稿正文；
- `response_letter.md` 只引用已知改动；
- 所有 `partial`/`defer` 项都在 `evidence_pending.md` 中列出；
- 不存在"判定为 accept 却无对应改动"的条目。
