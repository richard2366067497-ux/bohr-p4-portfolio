---
name: source-bound-manuscript-audit
description: Audit a full scientific manuscript or research material against six review facets (structure, internal consistency, citation support, method design, statistical reporting, argument chain) plus academic-compliance reporting, and deliver per-item findings that each carry a verbatim quote plus a paragraph-level locator, a typed verdict (error / insufficient evidence / compliance / suggestion / pending review), a severity with reason and a sentence-level revision. Deterministic lead scanning (section presence, cross-section numeric conflicts, citation-vs-reference mismatch, missing reporting items, overgeneralisation and causal-language cues) produces a candidate pool that the reviewing agent must triage, confirm or reject with reasons. Use when the user asks 论文质量审查 / 审稿 / 投稿前自查 / 发现论文问题并给出证据 / review this manuscript / audit a paper for structural, statistical, citation or reporting problems.
version: 1.0.0
---

# 论文质量审查：条目化问题清单 + 逐字证据（source-bound-manuscript-audit）

本 Skill 把「这篇稿子哪里有问题」变成一组**可定位、可核对、可交办**的条目：每条都带原文逐字引用、段落级 locator、
问题性质（事实错误 / 证据不足 / 规范问题 / 建议）、严重度与理由、判定依据和落到句子上的修改建议，
并对没有查的部分显式登记。它不写评语、不改稿、不做查重或排版。

## 随包方法论（执行前必读）

在执行任何命令、产出任何交付物之前，**先完整阅读 `references/expert_playbook.md`（专家参考手册）**，并按其组织全部产出：

- **六面检查**：按其 **§1 任务本质与判分要点** 逐面核实结构 / 一致性 / 引用支持 / 方法 / 统计 / 论证链 + 规范，
  每条条目不写评语、只写可定位可核对的问题。
- **流程**：按其 **§2 求解框架（含门控）** 推进——读材料建索引 → 出候选 → 逐条回原文判定 → 机械校核 → 落盘 finalize；
  未过门控不进入下一步。
- **口径**：按其 **§3 证据与定位口径** 校验 quote 逐字、locator 段落级、严重度锚点与问题性质分类。
- **陷阱**：按其 **§4 误报抑制与领域陷阱** 逐条排雷（错误做法 → 正确做法），"没报告" ≠ "做错了"。
- **门控**：交付前逐项通过其 **§7 防扣分自查表**；任一项未过则 `status=partial` 并把未决项写入
  `uncertainties` / `unchecked_items`，绝不静默提升为完整成功。

## 结果契约（默认 7 键）

`case.json` / `task.md` 提供 `output_contract` 时，以其键名为准原样回填；未提供时按下列默认 7 键产出：

```json
{
  "output_contract": {
    "case_id": "value",
    "status": "value",
    "summary": "value",
    "severity_summary": "value",
    "coverage": "value",
    "uncertainties": "value",
    "report_path": "value"
  }
}
```

每个键都必须回填为**诚实的非空值**（`report_path`→真实报告路径，`coverage`→覆盖表，`summary`/`severity_summary`→
真实统计文本，`uncertainties`→不确定性说明），不留 `null`、不写类型串；详见 §2 输入契约与 §3 输出契约回填。

## 0. 五命令主路径（先看这里）

```bash
python3 scripts/main.py init        # 解析 case.json/task.md、材料索引与对象表，先写合法 partial result.json
python3 scripts/main.py show        # 打印带 locator 的原文/对象清单，供逐字引用
#  评审 Agent 亲自读材料，写工作稿 /app/work/draft.json
python3 scripts/main.py check       # 机械校验：quote 逐字命中、枚举合法、覆盖计数、候选台账、契约键登记
python3 scripts/main.py build       # 由工作稿生成主产物 + 最终 result.json（无条件 finalize）
python3 scripts/main.py selfcheck   # 复检（可选）
```

**脚本不代替阅读理解；必须先读材料、写工作稿，再 `build`；禁止只跑 `build` 就结束。**
只跑 `init` 或 `build` 缺工作稿时，输出为 `status=partial` 的规则兜底稿（全部 `pending_review`），仍产出全部产物、exit 0。

若不在 Skill 根目录（如装在 `/skills/weekly-skill`），把前缀换成绝对路径
`python3 /skills/weekly-skill/scripts/main.py ...`。脚本按自身文件定位资源，不依赖 CWD；目录按
`--input/--work/--output` → `AUDIT_INPUT/AUDIT_WORK/AUDIT_OUTPUT` → `/input`、`/app/work`、`/app/output` → 包内相对目录解析。

| 命令 | 脚本做什么（确定性） | Agent 做什么（判断） |
|---|---|---|
| `init` | 解析输入、抽文本、切段定位、跑规则得候选、写合法 partial `result.json` | 无（可先跑再读） |
| `show` | 按 locator 打印原文、章节表、数值/引文对象表、候选线索 | 读；决定哪些线索是真的 |
| 写 draft | 不做 | **逐条回原文核实**，写 findings / rejected_candidates / coverage |
| `check` | quote 命中、枚举合法、重复合并、覆盖计数、候选处置台账、契约键登记 | 按报告修正工作稿 |
| `build` | 回填契约、渲染报告/证据卡/清单、finalize | 无（缺工作稿也必出降级交付） |
| `selfcheck` | 复检最终产物 | 按需补跑 |

`show` 常用形态：`show`（概览）· `show --doc D1 --limit 40`（逐段读）· `show --section results`·
`show --seg D1-p3-s12`· `show --leads --facet citation`· `show --numbers`· `show --citations`· `show --contract`。

## 1. 用途与适用条件

适用：完整论文/预印本/学位论文章节/结题报告的**整体质量审查**；投稿前自查，需可直接交办作者的条目清单；
按固定六类检查项逐面排查且每条能回原文；同一稿件多版本/正文+补充+回复信的**一致性核对**。

触发（任一命中）：给了稿件并要求「审查/审稿/找问题/投稿前检查/核对引用是否支持论断/统计报告是否完整/结论是否超出数据」；
或给出 `case.json` + `task.md` 形式的审查任务。

不适用（直接说明，不硬套）：润色/改写/翻译/排版/查重；代写「总体评价」；需外部数据库的核验（文献真实性、影响因子、
图片篡改）；需重跑实验或复算统计的复现工作（只审报告是否完整，不复算）。稿件尚未成形（只有提纲）不触发。

## 2. 输入契约与解析链

- `/input/case.json`：可取 `case_id`、`task_instruction`、`output_contract`（键名未知，本 Skill 不假设键名）。
  损坏时容错解析（去 BOM、尾逗号、`//` 注释）继续，失败记 `errors` 并继续用目录材料。
- `/input/task.md`：题面，摘要写入 `result.json.task_instruction`。
- `/input/**` 其它：正文、补充材料、回复信、参考文献、图片、数据表。递归扫描，跳过隐藏文件与 >12MB 文件。

解析链（逐级降级，`documents[].parser` 记实际引擎）：PDF `pdftotext -layout`→`pypdf`→`PyPDF2`→`pdfminer`→原始流
（质量差打 `raw_stream`）；DOCX 读 `word/document.xml`；文本按 UTF-8(BOM)→UTF-16→GB18030→Big5 容错；图片只登记为材料缺口。

段落定位：文本按页（`\f`）→ 标题 → 段落切分；标题兼顾 Markdown（`## 3. Results`）、LaTeX（`\section{}`）、编号与纯词标题。
每段得 `uid = <doc>-p<page>-s<para>` 与 `locator = "<doc> p.<page> ¶<para> §<section>"`。
材料角色判定见 `references/io-and-draft-schema.md` §2；**规则扫描只对 `manuscript` 生效**，回复信与补充材料作对照登记。

## 3. 输出契约

`/app/output/` 下产出：`result.json`（信封 + 契约回填）、`audit_report.md`（人读主产物）、`evidence.jsonl`（一问题一证据卡）、
`candidates.json`（候选池与处置留痕）、`run_manifest.json`（输入 SHA256、解析器、计数、`result_sha256`、耗时）。

`result.json` 固定字段：`case_id`、`status`、`findings[]`、`coverage`、`severity_summary`、`facet_summary`、`sources[]`、
`uncertainties[]`、`limitations[]`、`unchecked_items[]`、`rejected_candidates[]`、`errors[]`、`degradations[]`、`changes[]`、`runtime`。

**契约回填**：`output_contract` 的**每个键原样回填到顶层**，同时在 `output_contract` 对象内写一份同值副本；键名不改、数量不减。
能映射到语义的键按语义填（`findings`→条目数组、`coverage`→覆盖表、`summary/report`→摘要或报告文本、
`report_path`→`audit_report.md`、`severity`→严重度统计、`evidence`→证据数组、`status`→状态）。映射不到的键填
**诚实的非空值**（带说明的字符串或真实结构），并在 `degradations` 记 `contract_field_unmapped`；**不留 `null`、不写类型串**。
用例未提供契约时使用文首「结果契约」所列默认 7 键。

`findings[]` 字段：`finding_id`（`F-001` 稳定排序）、`facet`、`rule`、`candidate_ids`、
`location{doc_id,section,locator,page,table_or_figure}`、`quote`、`quote_verified`、`quote_match`、`issue_type`、`severity`、
`severity_reason`、`evidence`、`rationale`、`revision`、`verdict_type`、`confidence`、`status`、`review_note`。

## 4. 方法与流程（候选池 → 判定 → 校核）

两段式：**确定性规则只负责「找到可能有问题的那一段」**，是否成立由评审 Agent 判断。

1. **建索引**（`init`）：抽文本、切段、定 locator、抽章节表、数值对象表、引文对象表。
2. **出候选**（`init` 自动跑，`show --leads` 查看）：每条含规则号、facet、locator、逐字 quote、「为什么被标出」与「需回答的问题」。
   规则见 `references/checklist-and-severity.md`：结构 `ST-01..03`、一致性 `CO-01..02`、引用 `CI-01..05`、方法 `ME-01..04`、
   统计 `ST-11..16`、论证 `LO-01..03`、规范 `CP-01..04` + `AX-01..02`。
3. **判定**（Agent）：逐条回原文读，写进 `/app/work/draft.json`：成立 → 一条 finding，`quote` 从材料复制（不改写、不跨段拼接），
   给 `issue_type`、`severity` 及 `severity_reason`、`evidence`、`revision`；不成立 → 写 `rejected_candidates` 并给理由；
   说不清 → finding 但 `verdict_type=pending_review`、`status=pending_review`，说明缺什么。
4. **校核**（`check`）：quote 逐字命中（NFKC + 空白归一后子串匹配）、枚举合法、重复合并、候选处置台账（未处置的会被点名）、
   覆盖表齐全；登记 `output_contract` 键名供 `build` 回填。
5. **落盘**（`build`）：未命中 quote 降级 `pending_review` 而非删除；缺条目的检查项补定位候选；渲染报告与证据卡；无条件 finalize。

Agent 判断与脚本结论冲突时以 Agent 为准，但冲突必须留在 `review_note` 或 `rejected_candidates.reason`。

## 5. 证据与定位规范

- 一条 finding 一条主 quote，≤300 字符，**必须是材料中的连续原文**；需第二处证据时另立条目或写进 `evidence`。
- quote 不得掐掉比较对象、否定词、数值、单位与显著性表述 —— 掐掉就改变了论断含义。
- `locator` 优先用 `show --seg` 的原值（`D1 p.3 ¶12 §Results`）；Agent 给的与 quote 实际位置不一致时，脚本以 quote 命中段为准并在 `quote_match` 记真实 uid。
- quote 找不到 → 不得作为 confirmed：降级 `pending_review`、`confidence=low`、写入 `degradations`。**绝不修改原文或改写 quote 去凑命中。**
- 缺图/表/参考文献、扫描页不可靠时：写明「缺什么 + 人工下一步」，不用推测填空。

## 6. 严重度锚点与问题性质

| 严重度 | 判据 |
|---|---|
| `critical` | 影响主结论或可复现性：样本量/关键数值自相矛盾、结论无数据支撑、方法缺关键对照、引用与论断反向 |
| `major` | 解释或发表前必改：统计缺检验名/离散度、结论外推到数据范围外、方法关键信息缺失、引用不支持论断 |
| `minor` | 报告与表述缺陷：图号/表号错配、参考文献冗余或残缺、术语与单位不统一 |
| `suggestion` | 可读性、结构、补充说明等改进，不影响结论成立 |

问题性质（`issue_type`/`verdict_type`）须分清，**「没报告」不等于「做错了」**：`fact_error`（能指到两处原文）、
`insufficient_evidence`（论断无支撑或引文不支持）、`reporting_gap`（方法可接受但报告不全）、`method_flaw`（设计不支持结论）、
`statistical_misreport`/`logic_gap`（统计或推理断点）、`compliance`（数据可用性/利益冲突/伦理/资助/术语格式）、
`citation_unsupported`（引用错配/编号越界/条目残缺）、`improvement`（建议）、`pending_review`（材料不足或需外部核实，不填结论）。

## 7. 误报抑制规则

逐条见 `references/checklist-and-severity.md` §5。核心：**写作惯例/期刊格式差异/作者已声明假设不算缺陷**；
**材料缺口 ≠ 稿件缺陷**（记 `unchecked_items`/`pending_review`）；同一句同一缺陷只立一条；**数值差异先换算再判断**。

## 8. 覆盖表与未检查项

`coverage` 必含 7 个 facet（`struct/consistency/citation/method/statistics/logic/compliance`），每项写 `checked`、`items_checked`、`note`。
与本文无关的检查项写 `checked: true` 并在 note 写「不适用 + 理由」；**不允许沉默跳过**：真没查的写 `checked: false` 进 `unchecked_items`，
说明是材料缺失、解析失败还是超预算。

## 9. 边界与限制

- 只审材料内可核对内容；外部文献主张、期刊最新投稿要求无法离线核实，此类条目只能 `pending_review`。
- 图表只读题注与正文引用，不做像素级读数；图注缺失处不下结论。
- PDF 无文本层（扫描件）时 `pdftotext` 返回空/乱码，脚本降级原始流并打质量标记；仍不可读时全篇按「材料不可读」处理，`status=partial`。
- 单文件 >12MB、总段落 >6000 时截断并记 `degradations`；超长稿按章 `show` + 分批写 draft，多次 `build`。
- 不复算统计量、不重跑实验、不判断图片是否被篡改、不做查重。

## 10. 失败处理与降级分支

| 情况 | 处置 | status |
|---|---|---|
| `case.json` 缺失/坏 JSON | 记 `errors`/`degradations`，继续用目录材料与 `task.md` | partial |
| 无任何可解析材料 | 仍产出合法 `result.json` + 报告（说明「未解析出文本」）、`coverage` 全填 | input_error |
| PDF 无文本层 / 乱码 | 降级引擎；打 `quality_flags`；相关条目 `pending_review` | partial |
| 图片/表格内容缺 | 登记 `unchecked_items`，不猜内容 | partial |
| 工作稿缺失/空/坏 JSON | **兜底**：按候选生成完整最小交付（全部 `pending_review`）+ 报告 + 清单 | partial |
| 工作稿 quote 不命中 | 该条降级 `pending_review`，写 `degradations`，其余照常 | partial |
| 契约键无法映射 | 填**诚实非空值**，记 `contract_field_unmapped`（不留 `null`/类型串） | 不变 |
| 超时/预算不足 | 先保证 `result.json` 合法；剩余检查项进 `unchecked_items` | partial |
| 任何未捕获异常 | 顶层捕获，写最小合法 `result.json`，**退出码恒 0** | failed/partial |

## 11. 最小调用示例（**示例数据，非正式案例结果**）

输入：`case.json` 含 `case_id="DEMO"` 与 `output_contract={"findings": {...}, "status": "..."}`；`paper.md` 摘要写 48 例、方法写 36 例。

```bash
python3 scripts/main.py init && python3 scripts/main.py show --leads --facet consistency
# C-002 [consistency/CO-01] D1 p.1 ¶1 §2  sev_hint=critical ; 多个样本量口径：36×2, 48×2
python3 scripts/main.py show --seg D1-p1-s3      # 读原段，复制作 quote
# 写 /app/work/draft.json（schema 见 references/io-and-draft-schema.md §3）
python3 scripts/main.py check && python3 scripts/main.py build && python3 scripts/main.py selfcheck
```

示意条目：`F-001 / consistency / fact_error / critical`，`locator="D1 p.1 ¶1 §2. Materials and Methods"`，
`revision="统一为实际受试数量（36），并同步修正摘要句"`，`verdict_type="error"`，`quote_verified=true`。

## 12. 自查清单（交付前）

- [ ] `python3 scripts/main.py selfcheck` 全 PASS（契约键齐全、findings 非空、quote 全命中、7 个 facet 有覆盖）。
- [ ] 每条 finding 的 `locator` 能在 `show` 输出里找到对应段，`quote` 是该段的连续原文。
- [ ] 六类检查项都有记录；不适用的写了理由；真没查的进了 `unchecked_items`。
- [ ] 严重度不是清一色：至少区分 critical / major / minor，且每条有 `severity_reason`。
- [ ] 每条 `revision` 能直接落到句子（改哪句、改成什么），不是「建议加强论证」。
- [ ] 候选台账完整：每条候选被确认或被显式排除并写理由（`check` 的 untriaged 为 0）。
- [ ] 没有外部文献编造、没有「已核对/已运行」的虚假记录；不确定项在 `uncertainties`。
- [ ] `result.json` 契约值非空非占位符（无 `null`/类型串），产物无 `[待写]`/`pending` 等占位符。
- [ ] 同一输入重复运行 `result.json` 逐字节一致（`run_manifest.json` 仅耗时不同）。
- [ ] **专家检查表逐项通过**：`references/expert_playbook.md` §7 的防扣分自查表逐项勾选通过；任一项未过则 `status=partial`
  并把未决项写入 `uncertainties`/`unchecked_items`，绝不静默提升为完整成功。

## 13. 文件清单、版本与维护

```
SKILL.md                                本文档：用途、五命令主路径、契约、方法、降级、自查
scripts/main.py                         五命令入口：init / show / check / build / selfcheck
scripts/audit_core.py                   阅读与定位：编码/PDF/DOCX 解析、切段、locator、quote 校验、草稿规范化
scripts/audit_leads.py                  规则扫描：结构/一致性/引用/方法统计/论证/规范候选
scripts/render.py                       契约回填、兜底条目、报告与证据卡渲染、run_manifest
references/checklist-and-severity.md    检查项与规则号、严重度锚点、误报抑制表、判定流程
references/io-and-draft-schema.md       输入发现、字段字典、工作稿 schema、最小示例、异常处置
references/expert_playbook.md           专家方法论：六面判分、求解框架、证据口径、误报抑制、自查表、虚构案例
GAIN_EVIDENCE.md / environment/resources.yaml / examples/case.json   增益对照、资源入口声明、最小示例
README.md / SELFTEST.md                 使用说明、实测与边界测试
```

版本 `1.0.0`，规则版本 `2026-11-18`。依赖 Python ≥3.8 标准库；`pdftotext` 可选（缺失自动换引擎）。不联网、不写包外路径、不依赖 CWD。
维护：改阈值/规则号/字段须同步 `references/` 与本文档；新增材料格式只改 `audit_core.read_document`；新增规则放
`audit_leads.scan_*` 且必须同时给出「需 Agent 回答的问题」，不得直接产出 confirmed 结论；复跑一致性是硬约束（不引入随机/时间戳/遍历顺序依赖）。
