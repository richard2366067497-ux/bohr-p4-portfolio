---
name: writing-10-reviewer-response
description: Reviewer-response and manuscript-revision assistant. Parses reviewer comments (or revision meeting notes), builds a per-comment ledger, decides accept / partial / reject / defer, writes a real, locatable revision into the manuscript for every adopted comment (each edit carries a unique [[Cx]] anchor), and produces a revised manuscript, a point-by-point response letter, a change locator table and an evidence to-do list. Use when a manuscript must be revised in response to review comments or a revision meeting.
version: 1.1.0
---

# 审稿回复与论文修改 / Reviewer response and manuscript revision

审稿意见要逐条回应，修改要能**定位核对**，回答不了的要如实标注为待补，超出范围的要不采纳并说明理由。本 Skill 把"评论清单 → 逐条判定 → 真实改动 → 回复信 → 待补清单"串成一条可复核的流水线，并自校验"回复信 / 修改定位表 / 修改稿锚点"三向一致。运行完全离线，只用 Python 标准库。

## 单命令入口（single command，一次跑完）

这一条命令就是完整流程：读取基线稿件与审稿意见 → 解析评论 → 建立逐条台账 → **逐条判定并生成真实修订句** → 写回修改稿（带 `[[Cx]]` 锚点）→ 输出回复信、修改定位表、待补清单与自查结果。**无需草稿或前置步骤**；缺材料时仍退出码 0 并写出合法结果。

```bash
python3 scripts/main.py --input /input --output /app/output --work /app/work
```

可选参数：`--draft FILE`（Agent 起草的决定/改句，优先采用）、`--case /input/case.json`、`--lang zh|en`（默认按材料自动判断）、`--version`。

### Agent-first 双路径

- **确定性路径（默认）**：脚本切分评论、匹配锚点、按类型生成真实修订句并落盘，全程可复现。
- **Agent 起草路径（优先）**：若存在 `--draft FILE`、`$WORK/draft.json` 或 `$INPUT/draft.json`，其中按条给出的
  `decision` / `kind` / `revised_text` 被原样采用（见 `references/usage.md` 的 draft 示例）。

两条路径都只声称**能在修改稿中按 `[[Cx]]` 定位到**的改动；`selfcheck.json` 会做三向一致性校验。

### 最小调用示例（示意，非正式案例结果）

输入目录示意：

```text
/input/case.json               # { "case_id": "...", "language": "en", "output_contract": {...} }
/input/materials/manuscript.md # 待修改的基线稿件
/input/materials/comments.md   # 审稿意见（编号或项目符号均可）
```

调用：`python3 scripts/main.py --input /input --output /app/output --work /app/work`

示意输出：`revised_manuscript.md`、`response_letter.md`、`comment_ledger.json`、`change_locator.json`、`evidence_pending.md`、`version_notes.md`、`selfcheck.json`、`result.json`。以上为接口示意，正式结果由平台用固定案例生成。

## 产物清单

| 文件 | 内容 |
|---|---|
| `revised_manuscript.md` | 修改稿：锚定句被**真实改写**，句尾带唯一 `[[Cx]]` 锚点；末尾附「修改点清单」 |
| `response_letter.md` | 逐条回复：评论、判定、改动编号与 `revised_manuscript.md#Cx` 定位 |
| `comment_ledger.json` | 评论台账：子要求、类型、锚点、判定、修改编号，含四态计数 |
| `change_locator.json` | 修改定位表：编号 → 原句 / 改后句 / 锚点 / 是否原地应用 |
| `evidence_pending.md` | 待补清单：`partial` / `defer` 项及原因 |
| `version_notes.md` | 版本记录：基线、评论数、四态计数、修改数、自查结论 |
| `selfcheck.json` | 一致性自查：回复信 ↔ change_ids ↔ 修改稿锚点 |
| `result.json` | 结构化结果，含逐键回填的 `output_contract`（顶层 + 嵌套） |

## result.json 字段

顶层固定字段：`case_id`、`status`、`language`、`deliverable`、`deliverable_summary`、`preserved_facts`、`evidence_map`、`change_log`、`outputs`、`metrics`、`selfcheck`、`sources`、`uncertainties`、`change_records`、`limits`、`human_review`、`degradations`、`errors`、`runtime`，以及**逐键回填**的 `output_contract` 对象。

- `status` ∈ `success` / `partial` / `failed`。
- 契约给的键全部出现在 `output_contract`（嵌套），且同样的键也出现在顶层；给文件名的键指向真实文件，描述性键回填为真实值或列表；`case_id` 透传输入值。
- `preserved_facts`、`evidence_map`、`change_log`、`uncertainties`、`limits` 恒非空；结果中无占位符。

## 处理规则

1. **解析评论**：支持编号（`1.`、`(1)`、`Comment 2:`）与项目符号两种形态，也支持无编号的段落切分。
2. **锚点匹配**：把每条评论与基线段落做相似度匹配，阈值 `ANCHOR_THRESHOLD = 0.15`；低于阈值即视为未锚定，落入 `defer`/`reject`，不再强行采纳。
3. **分类与判定（四态）**：`clarify_scope`→`narrow`、`add_evidence`→`cite`、`new_material`/伦理审批→`defer`、`out_of_scope`/误读→`reject`；可锚定且不依赖新材料→`accept`；可锚定但依赖新材料→`partial`。
4. **真实修改**：对 `accept`/`partial` 的锚定句做可见改写（软化过度断言 + 范围限定 / 插入引用位），写回正文并附唯一 `[[Cx]]` 锚点；`revised_locator = revised_manuscript.md#Cx` 可据此核对。
5. **不采纳与待补**：`reject` 在回复信写明理由、不进入待补；`partial`/`defer` 写入 `evidence_pending.md`；不在回复信里编造已完成的数据或分析。
6. **自查**：运行自带 `selfcheck`，校验回复信只引用已知改动、每条改动都有锚点、无"判定 accept 却无改动"。

## 异常处理

- 无材料：退出码 0，`status=failed`，仍写出带 `limits` 的合法结果。
- 找不到基线或评论：`status=partial`，`human_review` 指出缺失项。
- 坏文件（坏 JSON / 空文件 / 二进制）：记入 `degradations`，不阻断。
- 输出目录不可写：回退到当前目录下的 `output/`。
- 脚本内部异常：`_fail` 写出最小合法 `result.json` 后仍 `exit 0`。

## 适用条件与限制

- 适用：审稿意见、修改意见或修改会议的逐条回复与稿件修改。
- 限制：离线，不联网验证；修改为正文中可定位的措辞/范围改写（或标注引用位），不做新实验或新分析；无锚点的意见一律暂缓或不采纳，而非猜测。

调用与 draft 示例、评论类型表（taxonomy）、回复模板见 `references/usage.md`。
