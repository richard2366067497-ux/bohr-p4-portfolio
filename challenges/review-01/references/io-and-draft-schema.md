# 输入发现、工作稿 schema 与输出字段

## 1. 输入发现（不假设文件名与键名）

| 位置 | 处理 |
|---|---|
| `/input/case.json` | 容错解析（BOM、尾逗号、`//` 注释）；取 `case_id`、`task_instruction`、`output_contract`；坏 JSON → `errors` + `degradations`，继续 |
| `/input/task.md` | 题面，写入 `task_instruction`（前 4000 字） |
| `/input/**` | 递归扫描；排除 `case.json`/`task.md`；>12MB 记 `gaps`；隐藏文件跳过 |

`case_id` 取值：`case.json.case_id` → `case.json.id` → 工作稿 `case_id` → 空。`output_contract` 可为 dict、list 或缺失；
缺失时按文首默认 7 键输出并记 `degradations: output_contract_missing`。

## 2. 材料角色与解析器

| `role` | 判定 | 用途 |
|---|---|---|
| `manuscript` | 体量最大的文本材料（或名称含 paper/main/article/正文） | 规则扫描与条目定位只在此文档 |
| `supplement` | 名称含 supp/appendix/附录/SI | 对照，核对数值一致性 |
| `response_letter` | 名称含 response/rebuttal/回复/答复 | 对照，核对「声称已改」是否落地 |
| `bibliography` | `.bib` / references.* | 引用核对 |
| `supporting` | 其余 | 备用 |

`parser` 记实际引擎：`pdftotext`/`pypdf`/`PyPDF2`/`pdfminer`/`raw_stream`/`docx-xml`/`text:<enc>`/`image-skip`。
`quality_flags` 含 `very_short`、`low_text_signal`、`cid_glyphs`、`replacement_chars`；后两类表示文字不可靠，相关结论须 `pending_review`。

## 3. 工作稿 `/app/work/draft.json`（Agent 写，脚本读）

```json
{
  "case_id": "由输入决定",
  "summary": "3-5 句可交办摘要：最要紧的 2-3 个问题 + 整体判断",
  "findings": [
    {
      "facet": "consistency",
      "rule": "CO-01",
      "candidate_ids": ["C-002"],
      "location": {"doc_id": "D1", "section": "2. Materials and Methods",
                   "locator": "D1 p.1 ¶1 §2. Materials and Methods", "page": 1,
                   "table_or_figure": null},
      "quote": "A total of 36 participants were recruited ... tested at 80 MPa.",
      "issue_type": "fact_error",
      "severity": "critical",
      "severity_reason": "同一队列样本量摘要(48)与方法(36)不一致，影响全部统计结论的分母",
      "evidence": "摘要写作 48，方法写作 36；同一批试验不可能是两个队列",
      "rationale": "样本量是全部百分比与检验的前提，属事实错误而非表述瑕疵",
      "revision": "统一为实际数量 36，并同步修正摘要句",
      "verdict_type": "error",
      "confidence": "high"
    }
  ],
  "rejected_candidates": [{"candidate_id": "C-005", "reason": "单批机械试验，随机化/盲法不适用，属学科惯例"}],
  "coverage": {"struct": {"checked": true, "items_checked": 6, "note": "..."}, "...": {}},
  "unchecked_items": [{"item": "图 3 曲线", "reason": "材料未含图片，无法核对"}],
  "uncertainties": ["外部文献主张未离线核实"],
  "limitations": ["未做跨版本比对"]
}
```

必填：`findings`（可为空则走兜底）、`coverage`。建议全填：`summary`、`rejected_candidates`、`unchecked_items`、`uncertainties`。
工作稿也可命名 `plan.json` / `review.json`，脚本依次查找。

### 3.1 枚举

| 字段 | 取值 |
|---|---|
| `facet` | `struct` `consistency` `citation` `method` `statistics` `logic` `compliance` |
| `issue_type` | `fact_error` `insufficient_evidence` `reporting_gap` `method_flaw` `statistical_misreport` `logic_gap` `compliance` `citation_unsupported` `improvement` |
| `severity` | `critical` `major` `minor` `suggestion` |
| `verdict_type` | `error` `insufficient_evidence` `compliance` `suggestion` `pending_review` |
| `status` | `confirmed` `pending_review`（quote 未命中被强制改为后者） |
| `confidence` | `high` `medium` `low` |

非法枚举不会中断流程：脚本按 `verdict_type` 推合法值，写进 `check` 的 warning。

## 4. 输出 `/app/output/result.json` 与契约回填

顶层固定字段见 `SKILL.md` §3（`case_id`、`status`、`findings[]`、`coverage`、`severity_summary`、`facet_summary`、
`sources[]`、`uncertainties[]`、`limitations[]`、`unchecked_items[]`、`rejected_candidates[]`、`errors[]`、`degradations[]`、`changes[]`、`runtime`）。
`findings[]` 字段：`finding_id`（`F-001` 稳定排序）、`facet`、`rule`、`candidate_ids`、`location`、`quote`、`quote_verified`、
`quote_match`、`issue_type`、`severity`、`severity_reason`、`evidence`、`rationale`、`revision`、`verdict_type`、`confidence`、`status`、`review_note`。

**契约回填**：`output_contract` 每键原样回填到顶层 + `output_contract` 内同值副本，键名不改、数量不减。按语义映射：

| 契约键特征 | 回填值 | 契约键特征 | 回填值 |
|---|---|---|---|
| `finding/issue/problem/条目/问题` | `findings` | `report`+`path/file/name` | `"audit_report.md"` |
| `severity/严重` | `severity_summary` | `report/markdown/报告` | 报告全文 |
| `coverage/覆盖` | `coverage` | `summary/overview/摘要` | `summary` |
| `facet/dimension/checklist` | `facet_summary` | `evidence/quote/证据/引文` | 证据数组 |
| `status/状态` | 状态字符串 | `revision/suggest/建议` | 修改建议数组 |
| `count/total/数量` | 计数字典 | `source/document/材料` | `sources` |
| `uncertain/limitation/局限` | 数组 | `unchecked/未检查` | `unchecked_items` |

先按字段名匹配，未命中才用描述文字兜底；都映射不到则填**诚实非空值**并记 `contract_field_unmapped`（不留 `null`、不写类型串）。

## 5. 异常处置（摘要，完整矩阵见 `SKILL.md` §10）

| 输入异常 | 产出 |
|---|---|
| `case.json` 缺失/坏 JSON | 沿用可用字段，`errors` 记录，继续出条目 |
| `output_contract` 缺失 | 默认 7 键输出，记 `output_contract_missing` |
| 无材料 / 仅图片 / PDF 无文本层 | `status=input_error` 或 `partial`，`quality_flags` + `unchecked_items` 说明缺口 |
| 工作稿缺失 / 空 / quote 不命中 | 兜底候选条目或逐条降级 `pending_review`，`status=partial` |
