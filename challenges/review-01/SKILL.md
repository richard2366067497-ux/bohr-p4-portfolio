---
name: source-bound-manuscript-audit
description: Audit a full scientific manuscript or research material against six review facets (structure, internal consistency, citation support, method design, statistical reporting, argument chain) plus academic-compliance reporting, and deliver per-item findings that each carry a verbatim quote plus a paragraph-level locator, a typed verdict (error / insufficient evidence / compliance / suggestion / pending review), a severity with reason and a sentence-level revision. Deterministic lead scanning (section presence, cross-section numeric conflicts, citation-vs-reference mismatch, missing reporting items, overgeneralisation and causal-language cues) produces a candidate pool that the reviewing agent must triage, confirm or reject with reasons. Use when the user asks 论文质量审查 / 审稿 / 投稿前自查 / 发现论文问题并给出证据 / review this manuscript / audit a paper for structural, statistical, citation or reporting problems.
version: 1.0.0
---

# 论文质量审查：条目化问题清单 + 逐字证据（source-bound-manuscript-audit）

本 Skill 把「这篇稿子哪里有问题」变成一组**可定位、可核对、可交办**的条目：每条都带原文逐字引用、段落级 locator、
问题性质（事实错误 / 证据不足 / 规范问题 / 建议）、严重度与理由、判定依据和落到句子上的修改建议，
并对没有查的部分显式登记。它不写评语、不改稿、不做查重或排版。

## 0. 主路径：五条命令（先看这里）

```bash
python3 scripts/main.py init        # 解析 case.json/task.md、材料索引与对象表，先写合法 partial result.json
python3 scripts/main.py show        # 打印带 locator 的原文/对象清单，供逐字引用
#  评审 Agent 亲自读材料，写工作稿 /app/work/draft.json
python3 scripts/main.py check       # 机械校验：quote 逐字命中、枚举合法、覆盖计数、候选台账齐全（并登记契约键）
python3 scripts/main.py build       # 由工作稿生成主产物 + 最终 result.json（无条件 finalize）
python3 scripts/main.py selfcheck   # 复检（可选）
```

**脚本不会代替你阅读理解；必须先阅读材料、写工作稿，再运行 build；禁止只跑 build 就结束。**

若当前目录不是 Skill 根目录（例如 Skill 装在 `/skills/weekly-skill`），把命令前缀换成绝对路径：
`python3 /skills/weekly-skill/scripts/main.py init`。脚本按自身文件位置定位资源，不依赖 CWD；
输入/输出/工作目录按 `--input/--work/--output` → `AUDIT_INPUT/AUDIT_WORK/AUDIT_OUTPUT` →
`/input`、`/app/work`、`/app/output` → 包内相对目录的顺序解析。

各命令的责任边界：

| 命令 | 脚本做什么（确定性） | Agent 做什么（判断） |
|---|---|---|
| `init` | 解析输入、抽文本、切段定位、跑规则得候选、写合法 partial `result.json` | 无（可先跑，再开始读） |
| `show` | 按 locator 打印原文、章节表、数值/引文对象表、候选线索 | 读；决定哪些线索是真的 |
| 写 draft | 不做 | **逐条回原文核实**，写 findings / rejected_candidates / coverage |
| `check` | 校验 quote 逐字命中、枚举合法、重复合并、覆盖计数、候选处置台账；登记 `output_contract` 键名供回填 | 按报告修正工作稿 |
| `build` | 回填契约、渲染报告/证据卡/清单、finalize | 无（缺工作稿也必出降级交付） |
| `selfcheck` | 复检最终产物 | 按需补跑 |

`show` 的常用形态：

```bash
python3 scripts/main.py show                      # 概览 + 读法提示
python3 scripts/main.py show --doc D1 --limit 40  # 逐段读正文（每段带 locator）
python3 scripts/main.py show --section results     # 只读某章
python3 scripts/main.py show --seg D1-p3-s12       # 读单段
python3 scripts/main.py show --leads --facet citation
python3 scripts/main.py show --numbers            # 跨章节数值对象表
python3 scripts/main.py show --citations          # 正文引文 vs 参考文献表
python3 scripts/main.py show --contract           # 契约原文（键名逐字）
```

## 1. 用途与适用条件

适用：

- 完整论文、预印本、学位论文章节、结题报告、审稿回复稿的**整体质量审查**；
- 投稿前自查，需要一份能直接交办给作者修改的条目清单；
- 需要按固定六类检查项（结构 / 一致性 / 引用支持 / 方法 / 统计 / 论证链 + 规范）逐面排查，并要求每条都能回到原文；
- 同一稿件多版本、或多份材料（正文 + 补充材料 + 回复信）并存时的**一致性核对**。

不适用的请求（直接说明不适用，不要硬套）：

- 论文润色、改写、翻译、投稿排版、查重比对 —— 题面已排除；
- 代写审稿意见的「总体评价」；本 Skill 产出条目，不产出恭维性评语；
- 需要外部数据库才能完成的核验（文献是否真实存在、影响因子、图片篡改检测）—— 离线环境不可做，只能记待复核；
- 需要重跑实验或重算统计的复现工作 —— 只审报告是否完整，不复算数据。

## 2. 触发条件与不适用情形

触发（任一命中即可用）：给了稿件/材料并要求「审查、审稿、找问题、投稿前检查、核对引用是否支持论断、
统计报告是否完整、结论是否超出数据」；或用户给出 `case.json` + `task.md` 形式的审查任务。

不要触发：只要摘要/翻译/降重；只要格式模板；只问某个概念；稿件尚未成形（只有提纲）。

## 3. 输入契约

- `/input/case.json`：可取 `case_id`、`task_instruction`、`output_contract`（键名未知，本 Skill 不假设键名）。
  损坏时按容错解析（去 BOM、去尾逗号、去 `//` 注释）继续，失败则记 `errors` 并继续使用目录内材料。
- `/input/task.md`：题面，写入 `result.json.task_instruction` 摘要。
- `/input/**` 其它文件：正文、补充材料、回复信、参考文献、图片、数据表。递归扫描，跳过隐藏文件与超大文件（>12MB）。

解析链（逐级降级，`documents[].parser` 记录实际用到的引擎）：

| 类型 | 顺序 |
|---|---|
| PDF | `pdftotext -layout`（CLI）→ `pypdf` → `PyPDF2` → `pdfminer` → 原始流 `FlateDecode` + `Tj/TJ` 提取（质量差时打 `raw_stream` 标记） |
| DOCX | ZIP 内 `word/document.xml`，段落→换行、制表/换行标签展开、去标签、反转义 |
| 文本 | UTF-8（含 BOM）→ UTF-16（BOM）→ GB18030 → Big5 → utf-8 容错 |
| 图片 | 只登记为材料缺口，不猜像素内容 |

段落定位：文本按页（`\f`）→ 标题 → 段落切分；标题识别兼顾 Markdown（`## 3. Results`）、LaTeX（`\section{}`）、
编号标题与纯词标题；无空行的 PDF 也在标题处断开。每段得到
`uid = <doc>-p<page>-s<para>` 与 `locator = "<doc> p.<page> ¶<para> §<section>"`。

材料角色：文件名含 response/rebuttal/回复 → `response_letter`；`.bib`/references → `bibliography`；
正文与补充材料按名称与体量判定 `manuscript` / `supplement`。**规则扫描只对 `manuscript` 生效**，
回复信与补充材料作为对照材料登记。

## 4. 输出契约

`/app/output/` 下：

| 文件 | 内容 |
|---|---|
| `result.json` | 主产物信封：`case_id`、`status`、`findings[]`、`coverage`、`severity_summary`、`sources[]`、`uncertainties[]`、`limitations[]`、`unchecked_items[]`、`rejected_candidates[]`、`errors[]`、`degradations[]`、`changes[]`、`runtime`，并把 `output_contract` 的**每个键原样回填到顶层** |
| `audit_report.md` | 人读主产物：摘要 → 严重度×检查项分布 → 逐条问题卡 → 候选处置台账 → 覆盖表 → 未检查项与不确定性 → 复现步骤 |
| `evidence.jsonl` | 一问题一证据卡（`finding_id/facet/locator/quote/quote_verified/issue_type/severity/revision`） |
| `candidates.json` | 候选池（规则号、locator、quote、需回答的问题），审计留痕 |
| `run_manifest.json` | 输入文件 SHA256/字节/解析器/角色、规则版本、计数、`result_sha256`、耗时 |

`output_contract` 回填规则：键名不改、数量不减；能映射到本 Skill 语义的键按语义填（`findings`→条目数组、
`coverage`→覆盖表、`summary/report`→摘要或报告文本、`report_path`→`audit_report.md`、`severity`→严重度统计、
`evidence`→证据数组、`status`→状态）；映射不到的键填 `null`/`[]`/`{}` 并在 `degradations` 记
`contract_field_unmapped`。嵌套 schema 递归回填。**不因为契约陌生就漏键**。

`findings[]` 字段：`finding_id`（`F-001` 稳定排序）、`facet`、`rule`、`candidate_ids`、
`location{doc_id,section,locator,page,table_or_figure}`、`quote`、`quote_verified`、`quote_match`、
`issue_type`、`severity`、`severity_reason`、`evidence`、`rationale`、`revision`、`verdict_type`、
`confidence`、`status`、`review_note`。完整字段字典与工作稿 schema 见 `references/io-and-draft-schema.md`。

## 5. 方法与流程（候选池 → 判定 → 校核）

两段式：**确定性规则只负责「找到可能有问题的那一段」**，是否成立由评审 Agent 判断。

1. **建索引**（`init`）：抽文本、切段、定 locator、抽章节表、数值对象表、引文对象表。
2. **出候选**（`init` 内自动跑，`show --leads` 查看）：每条候选含规则号、facet、locator、逐字 quote、
   「为什么被标出」和「需要你回答的问题」。规则见 `references/checklist-and-severity.md`：
   结构 `ST-01..03`、一致性 `CO-01..02`、引用 `CI-01..05`、方法 `ME-01..04`、
   统计 `ST-11..16`、论证 `LO-01..03`、规范 `CP-01..04` + `AX-01..02`。
3. **判定**（Agent）：逐条回原文读，写进 `/app/work/draft.json`：
   - 成立 → 写一条 finding，`quote` 从材料复制（不要改写、不要跨段拼接），给 `issue_type`、`severity`
     及 `severity_reason`、`evidence`、`revision`；
   - 不成立 → 写进 `rejected_candidates` 并给理由（学科惯例、材料缺口、作者有意取舍、已并入其它条目）；
   - 说不清 → 写 finding 但 `verdict_type=pending_review`、`status=pending_review`，说明缺什么。
4. **校核**（`check`）：quote 逐字命中（NFKC + 空白归一后子串匹配）、枚举合法、重复合并、
   候选处置台账（未处置的候选会被点名）、覆盖表齐全；同时登记 `output_contract` 键名，供 `build` 回填核对。
5. **落盘**（`build`）：未命中的 quote 降级 `pending_review` 而不是删除；缺条目的检查项补定位候选；
   渲染报告与证据卡；无条件 finalize。

Agent 判断与脚本结论冲突时以 Agent 为准，但冲突必须留在 `review_note` 或 `rejected_candidates.reason` 里。

## 6. 证据与定位规范

- 一条 finding 一条主 quote，长度 ≤300 字符，**必须是材料中的连续原文**；需要第二处证据时另立条目或写进 `evidence`。
- quote 不得掐掉比较对象、否定词、数值、单位与显著性表述 —— 掐掉就改变了论断的含义。
- `locator` 优先用 `show --seg` 给出的原值（`D1 p.3 ¶12 §Results`）；Agent 给的 locator 与 quote 实际位置不一致时，
  脚本以 quote 实际命中段为准并在 `quote_match` 记录真实 uid。
- quote 找不到 → 该条不得作为 confirmed 问题：降级 `pending_review`、`confidence=low`、写入 `degradations`。
  **绝不修改原文或改写 quote 去凑命中。**
- 缺图、缺表、缺参考文献、扫描页文字不可靠时：写明「缺什么 + 人工下一步」，不要用推测填空。

## 7. 严重度锚点与问题性质

| 严重度 | 判据 |
|---|---|
| `critical` | 影响主结论或可复现性：样本量/关键数值自相矛盾、结论无数据支撑、方法缺关键对照导致结论不成立、引用与论断反向 |
| `major` | 影响解释或发表前必改：统计报告缺检验名/离散度、结论外推到数据范围之外、方法关键信息缺失、引用不支持论断 |
| `minor` | 报告与表述缺陷：图号/表号错配、参考文献冗余或残缺、术语与单位不统一 |
| `suggestion` | 改进建议：可读性、结构优化、补充说明，不影响结论成立 |

问题性质（`issue_type` / `verdict_type`）必须分清，**「没报告」不等于「做错了」**：

- `fact_error`（`error`）：稿件内部或与材料事实直接矛盾，能指到两处原文；
- `insufficient_evidence`：论断存在但材料里没有支撑，或引文不支持该论断；
- `reporting_gap`：方法可接受但报告不全（缺 n、缺检验、缺声明）；
- `method_flaw`：设计本身不支持所得结论（缺对照、混淆变量）；
- `statistical_misreport` / `logic_gap`：统计或推理链条上的具体断点；
- `compliance`：数据可用性、利益冲突、伦理、资助、术语格式等规范项；
- `citation_unsupported`：引文与论断错配、编号越界、条目残缺；
- `improvement`（`suggestion`）：可执行的改进建议；
- `pending_review`：材料不足或需外部核实，**不填结论**。

## 8. 误报抑制规则

写 finding 之前逐条自问（这些规则也写在 `references/checklist-and-severity.md` 的抑制表里）：

1. **写作惯例不算缺陷**：单批机械试验无随机化/盲法、理论文章无伦理声明、短文体裁无独立讨论节 —— 不报或只报 suggestion。
2. **期刊格式差异不算缺陷**：引文风格、章节编号、单位写法差异，除非题面给了目标期刊要求，否则最高 `suggestion`。
3. **作者明确声明的假设、转述他人观点、明示局限**，不得当作自相矛盾或夸大报。
4. **材料缺口 ≠ 稿件缺陷**：图片未随文本提供、参考文献在另一文件、扫描页模糊 → 记 `unchecked_items` 或 `pending_review`。
5. **同一问题只立一条**：多个候选指向同一句同一缺陷时合并，`candidate_ids` 保留全部来源。
6. **纯语言偏好不报**：「建议更学术的表达」这类不入清单。
7. **数值差异先换算再判断**：百分比 vs 绝对值、单位换算、四舍五入都可能解释差异，解释得通就不报。

## 9. 覆盖表与未检查项

`coverage` 必须含 7 个 facet（`struct/consistency/citation/method/statistics/logic/compliance`），每项写
`checked`、`items_checked`、`note`。与本文无关的检查项写 `checked: true` 并在 note 里写「不适用 + 理由」，
例如「材料为纯理论推导，样本量与随机化不适用」。**不允许沉默跳过**：真没查的写 `checked: false` 进
`unchecked_items`，说明是材料缺失、解析失败还是超预算。

## 10. 边界与限制

- 只审材料内可核对的内容；外部文献的主张、期刊最新投稿要求无法离线核实，此类条目只能 `pending_review`。
- 图表只读题注与正文引用，不做像素级读数；图注缺失处不下结论。
- PDF 无文本层（扫描件）时，`pdftotext` 会返回空或乱码，脚本降级到原始流提取并打质量标记；
  仍不可读时全篇按「材料不可读」处理，`status=partial` 并写明需 OCR/人工读页。
- 单文件 >12MB、总段落 >6000 时截断并在 `degradations` 记录；超长稿按章节分批 `show` + 分批写 draft，再多次 `build`。
- 不复算统计量、不重跑实验、不判断图片是否被篡改、不做查重。

## 11. 失败处理与降级分支

| 情况 | 处置 | status |
|---|---|---|
| `case.json` 缺失/坏 JSON | 记 `errors`/`degradations`，继续用目录材料与 `task.md` | partial |
| 无任何可解析材料 | 仍产出合法 `result.json` + 报告（说明「未解析出文本」）、`coverage` 全填 | input_error |
| PDF 无文本层 / 乱码 | 降级引擎；打 `quality_flags`；相关条目 `pending_review` | partial |
| 图片/表格内容缺 | 登记 `unchecked_items`，不猜内容 | partial |
| 工作稿缺失 / 空 / 坏 JSON | **兜底**：按候选生成完整最小交付（全部 `pending_review`）+ 报告 + 清单 | partial |
| 工作稿 quote 不命中 | 该条降级 `pending_review`，写 `degradations`，其余照常 | partial |
| 契约键无法映射 | 填 `null`，记 `contract_field_unmapped` | 不变 |
| 超时 / 预算不足 | 先保证 `result.json` 合法；剩余检查项进 `unchecked_items` | partial |
| 任何未捕获异常 | 顶层捕获，写最小合法 `result.json`，**退出码恒 0** | failed/partial |

## 12. 最小调用示例（**示例数据，非正式案例结果**）

输入（示例）：`/input/case.json` 含 `case_id="DEMO"` 与 `output_contract={"findings": {...}, "status": "..."}`；
`/input/paper.md` 为 2 页示例稿，摘要写 `A total of 48 participants`，方法写 `36`。

```bash
python3 scripts/main.py init
# documents: 1  segments: 7  leads: 15
#   D1  paper.md  role=manuscript  fmt=text:utf-8 p=1 seg=7
python3 scripts/main.py show --leads --facet consistency
# C-002 [consistency/CO-01] D1 p.1 ¶1 §2. Materials and Methods  sev_hint=critical
#   quote: A total of 36 participants were recruited ... tested at 80 MPa.
#   why  : 文中出现多个样本量口径：36×2, 48×2
python3 scripts/main.py show --seg D1-p1-s3      # 读原段，复制作 quote
# 写 /app/work/draft.json（schema 见 references/io-and-draft-schema.md）
python3 scripts/main.py check                    # [PASS] F-001 ... quote verified
python3 scripts/main.py build                    # result.json + audit_report.md + evidence.jsonl
python3 scripts/main.py selfcheck                # [PASS] overall
```

示意输出（示例，非任何正式案例的答案）：`F-001 / consistency / fact_error / critical`，
`locator="D1 p.1 ¶1 §2. Materials and Methods"`，`quote="A total of 36 participants were recruited ..."`，
`revision="统一为实际受试数量（36），并同步修正摘要句"`，`verdict_type="error"`，`quote_verified=true`。
完整字段示例见 `references/io-and-draft-schema.md` 第 4 节。

## 13. 自查清单

- [ ] `python3 scripts/main.py selfcheck` 全 PASS（契约键齐全、findings 非空、quote 全命中、7 个 facet 有覆盖）。
- [ ] 每条 finding 的 `locator` 能在 `show` 输出里找到对应段，`quote` 是该段的连续原文。
- [ ] 六类检查项都有记录；不适用的写了理由；真没查的进了 `unchecked_items`。
- [ ] 严重度不是清一色：至少区分出 critical / major / minor，且每条有 `severity_reason`。
- [ ] 每条 `revision` 能直接落到句子（改哪句、改成什么），不是「建议加强论证」。
- [ ] 候选台账完整：每条候选被确认或被显式排除并写理由（`check` 的 untriaged 为 0）。
- [ ] 没有外部文献编造、没有「已核对/已运行」的虚假记录；不确定项在 `uncertainties`。
- [ ] 同一输入重复运行 `result.json` 逐字节一致（`run_manifest.json` 仅耗时不同）。

## 14. 文件清单、版本与维护

```
SKILL.md                                本文档：用途、五命令主路径、契约、方法、降级、自查
scripts/main.py                         五命令入口：init / show / check / build / selfcheck
scripts/audit_core.py                   阅读与定位：编码/PDF/DOCX 解析、切段、locator、quote 校验、草稿规范化
scripts/audit_leads.py                  规则扫描：结构/一致性/引用/方法统计/论证/规范候选
scripts/render.py                       契约回填、兜底条目、报告与证据卡渲染、run_manifest
references/checklist-and-severity.md    检查项与规则号、严重度锚点、误报抑制表、判定流程
references/io-and-draft-schema.md       输入发现、字段字典、工作稿 schema、最小示例、异常处置
```

版本 `1.0.0`，规则版本 `2026-11-18`。依赖：Python ≥3.8 标准库；`pdftotext` 可选（缺失时自动换引擎）。
不联网、不写包外路径、不依赖 CWD（脚本用 `Path(__file__).resolve()` 定位自身）。
路径顺序：`--input/--output/--work` 参数 → 环境变量 `AUDIT_INPUT/AUDIT_OUTPUT/AUDIT_WORK` →
`/input`、`/app/output`、`/app/work` → 包内 `input/`、`output/`、`work/`（相对回退）。

维护约定：

- 改阈值、改规则号、改字段必须同步 `references/` 与本文档；规则号不复用，废弃的标记 `deprecated`。
- 新增材料格式只改 `audit_core.read_document`，产物 schema 不变。
- 新增规则放在 `audit_leads.scan_*`，必须同时给出「需要 Agent 回答的问题」，不得直接产出 confirmed 结论。
- 复跑一致性是硬约束：不得引入随机、时间戳或依赖遍历顺序的排序。
- 若发布到公开仓库，可在提交根目录放 `GITHUB_URL.txt`（第一行仓库/目录链接）。本包不预置该文件，
  以免写入未经核实的链接。
