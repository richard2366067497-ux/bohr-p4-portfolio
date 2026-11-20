# 输入发现、字段字典与工作稿 schema

## 1. 输入发现（不假设文件名与键名）

| 位置 | 处理 |
|---|---|
| `/input/case.json` | 容错解析（BOM、尾逗号、`//` 注释）；取 `case_id`、`task_instruction`、`output_contract`；坏 JSON → `errors` + `degradations`，继续 |
| `/input/task.md` | 题面，写入 `task_instruction`（前 4000 字） |
| `/input/**` | 递归扫描全部文件；排除 `case.json`/`task.md`；>12MB 记 `gaps`；隐藏文件跳过 |

`case_id` 取值顺序：`case.json.case_id` → `case.json.id` → 工作稿 `case_id` → `null`。
`output_contract` 可以是 dict（值可为 schema 或字符串说明）、list（字段名数组）或缺失；
缺失时按本文件第 3 节的默认字段输出，并记 `degradations: output_contract_missing`。

## 2. 材料角色与解析器

| `role` | 判定 | 用途 |
|---|---|---|
| `manuscript` | 体量最大的文本材料（或被名称标为 paper/main/article/正文） | 规则扫描与条目定位只在此文档 |
| `supplement` | 名称含 supp/appendix/附录/SI | 对照材料，用于核对数值一致性 |
| `response_letter` | 名称含 response/rebuttal/回复/答复 | 对照材料，用于核对「声称已改」是否落地 |
| `bibliography` | `.bib` / references.* | 引用核对 |
| `supporting` | 其余 | 备用 |

`parser` 记录实际引擎：`pdftotext` / `pypdf` / `PyPDF2` / `pdfminer` / `raw_stream` / `docx-xml` /
`text:<enc>` / `image-skip`。`quality_flags` 记录 `very_short`、`low_text_signal`、`cid_glyphs`、
`replacement_chars` —— 出现后两类说明文字不可靠，相关结论须 `pending_review`。

## 3. 工作稿 `/app/work/draft.json`（Agent 写，脚本读）

```json
{
  "case_id": "由输入材料决定",
  "summary": "3-5 句可交办摘要：最要紧的 2-3 个问题 + 整体判断（不要写‘结构完整、论证较充分’）",
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
      "severity_reason": "同一队列样本量在摘要(48)与方法(36)不一致，影响全部统计结论的分母",
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

必填：`findings`（可为空则走兜底）、`coverage`。建议全填：`summary`、`rejected_candidates`、
`unchecked_items`、`uncertainties`。工作稿也可命名为 `plan.json` / `review.json`，脚本依次查找。

### 3.1 枚举

| 字段 | 取值 |
|---|---|
| `facet` | `struct` `consistency` `citation` `method` `statistics` `logic` `compliance` |
| `issue_type` | `fact_error` `insufficient_evidence` `reporting_gap` `method_flaw` `statistical_misreport` `logic_gap` `compliance` `citation_unsupported` `improvement` |
| `severity` | `critical` `major` `minor` `suggestion` |
| `verdict_type` | `error` `insufficient_evidence` `compliance` `suggestion` `pending_review` |
| `status` | `confirmed` `pending_review`（quote 未命中会被强制改为后者） |
| `confidence` | `high` `medium` `low` |

非法枚举不会让流程失败：脚本按 `verdict_type` 推一个合法值，写进 `check` 的 warning 列表。

## 4. 输出 `/app/output/result.json` 字段字典

| 字段 | 类型 | 说明 |
|---|---|---|
| `case_id` | str/null | 原样回填输入案例标识 |
| `status` | str | `ok` 全部条目经判定且无降级；`partial` 有降级/兜底/缺条目；`input_error` 无可用材料；`failed` 仅崩溃兜底 |
| `task` | str | 固定 `manuscript_quality_audit` |
| `skill_version` / `rules_version` | str | `1.0.0` / `2026-11-18` |
| `task_instruction` | str | 题面摘要 |
| `summary` | str | 可交办摘要 |
| `findings` | array | 见 4.1 |
| `coverage` | object | 7 个 facet → `{label, checked, items_checked, findings, note}` |
| `severity_summary` | object | `{critical, major, minor, suggestion, total}` |
| `facet_summary` | object | facet → `{count, critical, major, minor, suggestion}` |
| `result` | object | 结构化主结果（报告文件名、覆盖、严重度、条目 ID 列表） |
| `sources` | array | `{doc_id, path, role, parser, pages, sha256, bytes}` |
| `uncertainties` / `limitations` | array | 不确定性与边界，缺省时给通用两条（外部文献未核实、图表未像素级读取） |
| `unchecked_items` | array | 未检查项与原因 |
| `rejected_candidates` | array | 候选排除台账 |
| `errors` / `degradations` / `changes` | array | 错误、降级、变更记录 |
| `runtime` | object | `python`、版本、阶段（不含耗时，保证逐字节可复现） |
| `<output_contract 的每个键>` | 任意 | 原样回填，键名不改 |

### 4.1 `findings[]`

| 字段 | 说明 |
|---|---|
| `finding_id` | `F-001`…；排序 facet 顺序 → 文档顺序 → 页 → 严重度，稳定可复现 |
| `facet` / `rule` / `candidate_ids` | 检查项、来源规则、来源候选 |
| `location` | `doc_id`、`section`、`locator`、`page`、`table_or_figure` |
| `quote` | 逐字原文（≤300 字符，脚本上限 600） |
| `quote_verified` / `quote_match` | 是否命中、命中段的 uid |
| `issue_type` / `severity` / `severity_reason` | 性质、严重度与理由 |
| `evidence` / `rationale` / `revision` | 判定依据、推理、落到句子的修改建议 |
| `verdict_type` / `confidence` / `status` | 判定口径、置信度、复核状态 |
| `review_note` | 脚本自动降级/兜底时的说明 |

### 4.2 契约回填映射

| 契约键特征 | 回填值 |
|---|---|
| 含 `finding/issue/problem/条目/问题` | `findings` 数组 |
| 含 `severity/严重` | `severity_summary` |
| 含 `coverage/覆盖` | `coverage` 对象 |
| 含 `facet/dimension/checklist/检查项` | `facet_summary` |
| 含 `report`+`path/file/name` | `"audit_report.md"` |
| 含 `report/markdown/报告` | `audit_report.md` 全文 |
| 含 `summary/overview/摘要/总结` | `summary` 字符串 |
| 含 `evidence/quote/citation/证据/引文` | 证据数组 |
| 含 `revision/suggest/修改/建议` | 修改建议数组 |
| 含 `status/状态` | 状态字符串 |
| 含 `count/total/数量` | 计数字典 |
| 含 `source/document/material/材料` | `sources` 数组 |
| 含 `uncertain/limitation/risk/不确定/局限` | 数组 |
| 含 `unchecked/未检查` | `unchecked_items` |
| 其它 | `null`，并记 `contract_field_unmapped` |

解析顺序：先按**字段名**匹配，未命中才用描述文字兜底（避免「…严重度…」的描述把 findings 键误判成严重度统计）。

## 5. 最小示例（**示例数据，非正式案例结果**）

`/app/output/evidence.jsonl` 一行：

```json
{"finding_id": "F-001", "facet": "consistency", "rule": "CO-01", "locator": "D1 p.1 ¶1 §2. Materials and Methods",
 "quote": "A total of 36 participants were recruited ... tested at 80 MPa.", "quote_verified": true,
 "issue_type": "fact_error", "verdict_type": "error", "severity": "critical",
 "severity_reason": "同一队列样本量在摘要(48)与方法(36)不一致", "evidence": "摘要 48 / 方法 36",
 "revision": "统一为 36 并同步摘要", "confidence": "high", "status": "confirmed"}
```

`/app/output/result.json` 片段：

```json
{"case_id": "DEMO", "status": "ok", "task": "manuscript_quality_audit",
 "summary": "示例：样本量口径冲突 + 结论外推两处实质问题。",
 "findings": [{"finding_id": "F-001", "facet": "consistency", "severity": "critical",
               "verdict_type": "error", "quote_verified": true, "status": "confirmed"}],
 "coverage": {"struct": {"checked": true, "items_checked": 6, "findings": 0, "note": "…"}},
 "severity_summary": {"critical": 1, "major": 0, "minor": 0, "suggestion": 0, "total": 1}}
```

## 6. 异常处置（摘要，完整矩阵见 SKILL.md 第 11 节）

| 输入异常 | 产出 |
|---|---|
| `case.json` 缺失/坏 JSON | `case_id=null` 或沿用可用字段，`errors` 记录，继续出条目 |
| `output_contract` 缺失 | 按第 4 节默认字段输出，记 `output_contract_missing` |
| 无材料 / 仅图片 / PDF 无文本层 | `status=input_error` 或 `partial`，`quality_flags` + `unchecked_items` 说明缺口 |
| 工作稿缺失 / 空 / quote 不命中 | 兜底候选条目或逐条降级 `pending_review`，`status=partial` |
