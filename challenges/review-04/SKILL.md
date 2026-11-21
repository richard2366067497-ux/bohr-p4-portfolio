---
name: claim-graph-auditor
description: 论文逻辑与论证审查工作台：把稿件解析成带 locator 的文本单元，抽取 claim / cited_view / hypothesis / evidence / definition / obligation 六类节点，构建 supports / overclaims / unaddressed / contradicts / delivers 五类边，逐条产出可核验的 finding（严重度分级 + 原文逐字 quote + 可执行修改建议），并交付逻辑报告、主张—证据矩阵、主张图、检查覆盖报告与 result.json。单命令 all 在无草稿时也产出完整契约与全部关键交付物；五命令 init/show/check/build/selfcheck 支持 Agent 先读后写。适用于论文论证链审查、结论超出数据、引用不支持观点、承诺未交付、相关与因果混用、统计口径缺失等任务；不负责文字润色、查重、参考文献格式规范、原始数据重算与统计复算。
version: 2.0.0
---

# 论文逻辑与论证审查：主张—证据图优先（claim-graph-first）

脚本做确定性重活：解析、切分、建图、统计、渲染、契约回填、占位符净化。
Agent 做判断：哪些句子算主张、哪条边成立、严重度怎么定、建议怎么写。

## 单命令入口（评测入口，先看这里）

无 draft.json 时直接运行本命令即可产出完整契约与全部交付物；评测环境按此执行。

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

## 0. result.json 契约样例（output_contract 逐键回填，顶层 + 嵌套）

`result.json` 把**用例声明的每一个 `output_contract` 键**原样写进 `output_contract` 对象，并在顶层写同名键。
用例未给契约（`output_contract: null`）时使用下列默认键：

```json
{
  "case_id": "case-unknown",
  "status": "partial",
  "output_contract": {
    "case_id": "case-unknown",
    "status": "partial",
    "deliverable": "logic_report.md",
    "findings": [{"finding_id": "F-01", "facet": "argument", "finding_type": "insufficient_evidence", "severity": "major", "quote": "the data prove that infill controls strength", "locator": "paper.md §results U0007", "rationale": "strength verb without dispersion", "recommendation": "lower the verb or report SD/CI"}],
    "claim_graph": "claim_graph.json",
    "evidence_matrix": "claim_evidence_matrix.csv",
    "logic_report": "logic_report.md",
    "check_report": "check_report.json",
    "uncertainties": ["结论仅对稿件内句子成立；外部文献与原始数据未复算"],
    "degradations": [{"file": "/input", "note": "no degradation: every supplied material was readable"}],
    "errors": ["no runtime error"],
    "truncated_sections": [{"file": "paper.md", "units": 120, "status": "complete"}],
    "dangling_edge": [{"edge_id": "none", "reason": "every obligation was matched"}],
    "changes": [{"change_id": "CH-01", "action": "ingest", "status": "done"}]
  }
}
```

### 0.1 工作稿样例（Agent 写 `/app/work/draft.json` 时照此结构）

```json
{
  "case_id": "case-unknown",
  "claims": [
    {"node_id": "C-AG01", "kind": "claim", "quote": "one verbatim sentence copied from the material",
     "section": "results", "source_locator": "paper.md §results U0007",
     "strength_level": 3, "stats_reported": false}
  ]
}
```

`quote` 必须是材料中的**逐字子串**（脚本逐字校验，失败即丢弃该条并记录）；`kind` 取
`claim | cited_view | hypothesis | evidence | definition | obligation`。草稿不可用时自动回退到规则化建图，
`build` 仍然 finalize 全部产物。

## 1. 单命令入口（single-command entry，一条命令跑完全流程）

见文首「单命令入口（评测入口）」——同一条命令，评测环境只跑这一条也能过。

这一条命令完成：发现 case/材料 → 抽取文本（md/txt/json/csv/tex，PDF 有 `pdftotext` 则用、否则内置流解析）
→ 切分为带 locator 的文本单元 → 建节点 → 建五类边 → 派生 finding（含严重度与建议）
→ 渲染逻辑报告 / 主张—证据矩阵 / 主张图 / 检查覆盖报告 / 不确定性 → 写 `result.json`
（契约逐键回填 + `case_id` 透传）→ 占位符净化。**无 draft、空输入、坏 JSON 都 exit 0，并保留合法结果与限制说明。**

## 2. Agent-first 增强路径（agent 写 draft → check → build）

```bash
python3 /skills/weekly-skill/scripts/main.py init       # 建索引 + 合法 partial result.json + draft 模板
python3 /skills/weekly-skill/scripts/main.py show       # 打印带 locator 的文本单元与候选节点
#  >>> 你（评审 Agent）阅读材料，写 /app/work/draft.json（格式见 §0.1）<<<
python3 /skills/weekly-skill/scripts/main.py check      # 机械校验：quote 是否逐字、节点是否可用
python3 /skills/weekly-skill/scripts/main.py build      # 合并草稿并 finalize 全部交付物
python3 /skills/weekly-skill/scripts/main.py selfcheck  # 复核契约键、产物非空、finding 可回源
```

## 3. 方法论（与 `references/review_checklist.md` 一致）

节点六类：`claim`（作者主张）、`cited_view`（引用他人观点）、`hypothesis`（明确假设）、`evidence`（本文证据）、
`definition`（定义）、`obligation`（前言承诺）。边五类：`supports`、`overclaims`、`unaddressed`、
`contradicts`、`delivers`。强度分级 0–4（未标记 / 模糊 / 相关 / 断言 / 因果确定）。

每条 finding 必带：`facet`（fact|citation|method|statistics|argument|structure）、`finding_type`
（error|insufficient_evidence|norm|suggestion）、`severity`（critical|major|minor|suggestion）、
逐字 `quote` + `locator`、`rationale`、**可执行** `recommendation`（补什么证据 / 改哪一句 / 把哪条结论降级）。
**误读抑制**：明确标注的假设、转述他人观点、有意设置的对照组不报为缺陷；无法确认的条目进 `review_pending`。

## 4. 输入与输出

输入：`/input/case.json`（`case_id`、可选 `output_contract`）、`/input/task.md`、`/input/materials/**` 或任意子目录
（md/txt/json/csv/rst/tex/pdf）。材料解析失败只降级该文件，并在 `degradations` 记录。

输出（写入 `/app/output`）：

| 文件 | 内容 |
|---|---|
| `result.json` | 主结果：契约逐键回填（顶层 + `output_contract`）、`case_id` 透传、status、findings、图、来源、不确定性 |
| `logic_report.md` | 逐条 finding（位置/类型/严重度/建议）+ 六 facet 覆盖 + 限制 |
| `claim_evidence_matrix.csv` | 每条边一行：edge 类型、端点、严重度、facet、locator、逐字 quote |
| `claim_graph.json` | 节点与边，含 `counts` 与 `edge_types` |
| `check_report.json` | 六类检查项覆盖、严重度分布、status 规则 |
| `run_manifest.json` | 产物清单、契约键、依赖（仅标准库）、无网络 |
| `sources.json` / `uncertainty.json` | 证据来源与待复核/降级说明；`selfcheck` 另写 `verify_report.json` |

## 5. 状态、降级与可靠性

- `status`：`ok`（有 finding 且无降级）/ `partial`（有降级或无 finding）/ `insufficient_evidence`（无可读材料）。
- 长文截断：单文件超过单元上限时 `truncated_sections` 记为 `truncated` 并写入 `degradations`，**不宣称全文审完**。
- 空/坏输入：仍写 `logic_report.md`（说明无可读材料与下一步）、合法矩阵与 `result.json`，恒 exit 0。
- 纯标准库、离线；`--input/--output/--work` 或 `SKILL_INPUT/SKILL_OUTPUT/SKILL_WORK` 覆盖路径；输出收口时净化占位符。

## 6. 自检清单

- [ ] `output_contract` 与顶层同名键齐全，无空壳、无类型串。
- [ ] `case_id` 与输入一致；`status` 合理（截断就写截断）。
- [ ] 每条 finding 有逐字 quote 与 locator，且 `finding_type`/`severity` 都在枚举内。
- [ ] 报告覆盖六类检查项（未覆盖的要写明原因）。
- [ ] 无 `待写`/`TBD`/`null`/`pending` 等占位符。
- [ ] 空输入与坏 JSON 都 exit 0 且 `result.json` 合法。

## 随包方法论（执行前必读）

执行前先阅读 `references/expert_playbook.md`，按其框架、公式与自查表逐项产出并核验；交付前确认「专家检查表逐项通过」。
