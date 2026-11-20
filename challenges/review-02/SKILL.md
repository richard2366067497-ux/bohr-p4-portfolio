---
name: citation-fact-audit
description: Source-bound citation and fact audit for a scientific manuscript. Indexes the real input files, pairs in-text citation markers with reference-list entries, lists every checkable claim sentence with a page/paragraph locator, then records the auditor's judgement on direction, number and scope (full_support | partial_support | no_support | undetermined) with verbatim quotes on both the manuscript side and the source side, a severity-graded finding list with executable revisions, and explicit pending_review items for anything that cannot be verified offline. Use when the user asks 论文质量审查 / 引用是否支持结论 / 引文核验 / 事实来源是否可靠 / 逐条给出证据和严重度 / 审查这篇稿件 / citation check / fact-check this manuscript's citations / audit whether references support the claims.
version: 1.0.0
---

# 引用与事实核验审查台（citation-fact-audit）

对一份完整科研稿件做「引用与事实核验」专项审查：把正文论断落到可回查的原文位置，判定**引用/事实来源是否支持该论断**，给出严重度、依据与可执行修改建议；离线无法核实的外部信息一律 `pending_review`，绝不编造文献元数据或核对结论。

## 1. 主路径：五个命令（先看这一节）

```bash
# ① 建索引：解析 case.json / output_contract / task.md，递归扫材料，建段落单元表、
#    参考文献表、引文标记配对、可核验论断候选、数值一致性候选；并立刻写出合法的
#    partial /app/output/result.json（契约字段全在，值为空壳）
python3 scripts/main.py init

# ② 打印带 locator 的原文与对象清单（分页）：论断候选、参考文献表、配对状态、
#    段落单元。你在这里拿到 逐字原文 + 定位串
python3 scripts/main.py show

# ③ 评审 Agent 亲自阅读材料，写工作稿 /app/work/draft.json（schema 见 §5 与
#    references/contract-and-playbook.md）。先写 3 条，再增量补
#    （draft.template.json 已在 init 时生成，可直接在其上填）

# ④ 机械校验：枚举合法、quote 逐字命中、三要素齐全、覆盖计数、
#    判定与三要素自相矛盾之处。逐条列 PASS/FAIL，不替你判定
python3 scripts/main.py check

# ⑤ 由工作稿生成主产物 + 最终 result.json（无条件 finalize；兜底见 §9）
python3 scripts/main.py build

# 可选：复检已落盘结果（quote 重核、计数自洽、契约齐全、确定性）
python3 scripts/main.py selfcheck
```

> **脚本不会代替你阅读理解；必须先阅读材料、写工作稿，再运行 build；禁止只跑 build 就结束。**

只跑 `build` 会产出 `status=partial` 的降级结果：核验矩阵全部是 `undetermined` 的机械候选，问题清单里只有脚本能机械证明的条目（引文标记无对应文献表条目、摘要/正文数字冲突），`coverage` 全部 `checked=false`。这类结果能拿到「完整但降级」的基础分，拿不到判定正确性的分。

工作预算很紧（64 次模型请求 / 900 秒 / 单次响应 16384 token）。推荐的读法：

1. `init`（约 1 秒，零模型请求）。
2. `show` 看论断候选与配对状态 → 挑出真正需要判定的行。
3. `show --part units --offset 0 --limit 25` 读原文，边读边写 draft。
4. 每写完 3–5 条就 `check` 一次，把 quote 未命中的当场修掉。
5. 最后 `build` + `selfcheck`。

## 2. 用途与适用条件

**适用**（满足任一条即可触发）：

- 给定一篇稿件/报告/预印本，要求审查「引用是否支持结论」。
- 要求逐条给出「位置 + 原文 + 判定 + 严重度 + 修改建议」的问题清单。
- 要求核对来源可靠性（预印本 vs 正式版、撤稿/更正、编号错位、版本差异）。
- 要求检查摘要/正文/表格/图注之间数值、样本量、显著性表述是否自相矛盾。
- 要求检查方法设计、统计报告、论证链、学术规范（署名、数据与代码可用性、伦理与利益冲突）。

**不适用**（直接说明不适用，不要硬套）：

- 论文润色、改写、翻译、综述写作、数据分析建模、代作者判断研究结论是否成立。
- 需要联网检索数据库才能完成的文献计量、影响因子、撤稿库查询。本 Skill 离线运行，只处理 `/input` 内实际存在的材料，外部信息一律 `pending_review` 并写清待人工核对什么。
- 没有材料、只有一句「帮我看看这篇论文」且 `/input` 为空：走 §9 的 `input_error` 分支，不生成审查意见。

## 3. 运行契约

| 项 | 值 |
|---|---|
| 安装位置 | `/skills/weekly-skill`（脚本用 `Path(__file__).resolve().parent` 定位自身，不依赖 CWD） |
| 输入 | `/input/case.json`、`/input/task.md`、`/input/**` 下的案例材料 |
| 工作目录 | `/app/work`（索引、工作稿、校验报告） |
| 产物目录 | `/app/output`（`result.json` + 主产物） |
| 依赖 | Python ≥ 3.8 标准库；无网络；不写系统目录 |
| 退出码 | **恒为 0**。异常写进 `result.json.errors` / `degradations`，不崩 |
| 预算 | 900 秒软预算；`init`/`show`/`check`/`build` 都是秒级 |

路径可用 CLI 或环境变量覆盖，便于本地复跑与自测：

```bash
python3 scripts/main.py init --input ./mycase --work ./work --output ./out
AUDIT_INPUT=./mycase AUDIT_WORK=./work AUDIT_OUTPUT=./out python3 scripts/main.py build
```

解析顺序：`--input/--work/--output` → `AUDIT_INPUT/AUDIT_WORK/AUDIT_OUTPUT` → `/input`、`/app/work`、`/app/output` → 当前目录下的 `input/ work/ out/`。目录不可写时退回当前目录同名子目录，并把退避写进 `degradations`。

## 4. 输入发现（语义识别，不假设固定键名）

1. `case.json`：`case_id|id|caseId|task_id` 取案例标识；`output_contract|outputContract|contract|output_schema` 取输出契约（支持三种形态：`{字段: 规格}`、`{字段: "类型说明"}`、`["字段", ...]`、`[{"name": ...}]`）。坏 JSON → 记 `errors`，继续扫材料。
2. `task.md`：作为任务约束读入 `task_excerpt`；其中出现的检查项名称用于 `coverage` 对齐。
3. 材料：递归扫 `/input/**`，跳过隐藏目录与 `__pycache__`；按扩展名与实际内容识别 PDF / TXT / MD / JSON / JSONL / CSV / DOCX / HTML / BIB / LaTeX。
4. 文件角色（写入 `sources[].kind`）：`manuscript`（paper*/manuscript*/main*/article*，或唯一的大文本）、`reference`（references*/refs*/bibliography*/cit*）、`figure`（figures/、图注）、`table`（tables/）、`data`（csv/xlsx/json 数据）、`instruction`（case.json/task.md/brief.md/environment/*）。`instruction` 不进语料，避免污染 quote 命中。
5. **不按文件名猜内容**：正文是否存在、引文标记是否存在、文献表是否存在，全部由实际解析结果决定；解析不出来就记 `gaps`。

## 5. 工作稿 `draft.json` 契约

写在 `/app/work/draft.json`。字段字典见 `references/contract-and-playbook.md`，最简形态：

```json
{
  "case_id": "<与 case.json 一致>",
  "summary": "3–6 句：审了什么、报了几类问题、最严重的是什么、哪些没能核实",
  "citation_checks": [
    {
      "claim_id": "CC-01",
      "claim_text": "被核验论断（原文句子）",
      "claim_quote": "本文侧逐字原文（必须与 show 输出一字不差）",
      "claim_locator": "manuscript.pdf §Results P4 ¶2",
      "claim_strength": "strong|moderate|hedged",
      "cited_source": {"label": "[12] / Smith et al., 2021", "source_locator_if_available": "参考文献[12] / 附件摘要 P2 §3"},
      "source_claim_if_available": "来源侧逐字原文；材料里没有就给 null",
      "verdict": "full_support|partial_support|no_support|undetermined",
      "semantics": {"direction_match": true, "numeric_match": true, "scope_match": false,
                    "comparator": "高于 / higher than", "negation": "无 / none", "significance": "p<0.05"},
      "source_quote": "来源侧逐字原文或 null",
      "rationale": "为什么是这个判定：三要素哪个不满足，原文怎么写的",
      "unresolved_reason": "verdict=undetermined 时必填",
      "human_check_needed": "verdict=undetermined 时必填：人工下一步要查什么"
    }
  ],
  "findings": [
    {
      "facet": "citation|fact|statistics|logic|method|compliance",
      "location": {"section": "Discussion", "locator": "manuscript.pdf §Discussion P7 ¶3", "page": 7},
      "quote": "本文侧逐字原文（≤300 字，必须命中）",
      "issue_type": "citation_unsupported|citation_partially_supported|overclaim|fact_mismatch|source_unreliable|numeric_inconsistency|logic_gap|compliance|improvement",
      "severity": "critical|major|minor|suggestion",
      "severity_reason": "为什么是这个严重度",
      "verdict_type": "fact_error|insufficient_evidence|compliance_issue|suggestion",
      "evidence": "判定依据：来源侧引文/另一处原文/机械核对结果",
      "rationale": "推理链，一句话能复述",
      "revision": "可执行的改法：改成什么句子 / 补什么对照 / 删哪句",
      "claim_ref": "关联的 CC-xx（可选）"
    }
  ],
  "coverage": {"<六类 facet + 五个专项>": {"checked": true, "items": 12, "findings": 3, "note": "..."}},
  "unchecked_items": [{"item": "...", "reason": "..."}],
  "uncertainties": [{"topic": "...", "detail": "...", "human_check_needed": "..."}]
}
```

硬规则（`check` 会拦）：

- `claim_quote` / `quote` / `source_quote` 必须在 `sources[].path` 的原文里**逐字命中**（去空白/全半角归一后子串匹配）。quote 必须落在**单个段落单元内**，跨段请拆成两条。
- `verdict` 只能取四级；`severity` 只能取四档；`facet` 只能取六类；`issue_type` 只能取九种。
- `full_support` 要求 `direction_match`、`numeric_match`、`scope_match` **全部为 true**；任一为 false 而写 `full_support`，`build` 会按 §7 的规则重算并记进 `changes`，不静默保留。
- `undetermined` 必须同时给 `unresolved_reason` 与 `human_check_needed`。
- 主题相关不等于支持。只找到「讲同一主题的段落」→ `undetermined` 或 `partial_support`，不是 `full_support`。

## 6. 方法：八步审查流程

1. **建索引（脚本）**：`init` 解析全部材料，产出 `index.json`：`sources[]`（路径/格式/解析器/字节/单元数/文本量/质量）、`units[]`（带 `locator` 的段落单元）、`references[]`、`citations[]`、`claim_candidates[]`、`numeric_candidates[]`、`gaps[]`。
2. **抽论断（脚本粗筛 + Agent 定稿）**：脚本按「含引文标记 / 含数值断言 / 含因果或范围词」筛出候选句并预抽特征（数字、方向词、否定、显著性、范围量词、比较词、因果词）。Agent 决定哪些真正进入 `citation_checks`，以及是否需要补充脚本漏掉的句子（方法、规范类）。
3. **配引文（脚本）**：数字式 `[12]`、`[3,5-7]`、作者-年份式 `(Smith et al., 2021)`、中文 `（张三等，2021）` 全部提取，映射到参考文献表条目，输出配对状态 `paired | missing_entry | ambiguous | numbering_gap`。配不上的进 `pending_review`，**既不判支持也不判不支持**。
4. **三要素判定（Agent）**：对每条被引论断，逐条比对 `direction_match`（方向：支持/反对）、`numeric_match`（数值/样本量/效应量）、`scope_match`（范围：原文是相关还是因果，是单组还是普遍，是某条件还是无条件）。三项全满足 → `full_support`；缺一项 → `partial_support`；方向相反或数字矛盾 → `no_support`；材料不足以判 → `undetermined`。判据细节见 `references/verdict-rubric.md`。
5. **事实与来源可靠性（Agent）**：核对出版状态（预印本/正式版/撤稿/更正/勘误）、版本差异、编号错位、同一文献多版本并存；离线不能确认的外部状态写 `pending_review`。
6. **数值与统计一致性（脚本找候选 + Agent 确认）**：脚本按桶（样本量 `n=`、百分比、p 值、单位量）跨摘要/正文/表/图注比对，冲突候选带两侧 locator+quote 交给 Agent；Agent 区分真冲突与分组差异/假设情形/单位换算。
7. **论证链与规范（Agent）**：结论跳跃、循环论证、以偏概全、缺对照；署名、重复发表、数据与代码可用性、伦理审批、利益冲突、基金声明。每条都要落到原文 locator。
8. **落盘（脚本）**：`build` 校验 quote、按规则重算矛盾判定、回填 `output_contract` 全部字段、生成 `result.json` + `citation_report.md` + `evidence.jsonl` + `run_manifest.json`，按文中出现顺序稳定排序。

## 7. 判定口径（摘要，全文见 `references/verdict-rubric.md`）

**四级支持度**

| verdict | 含义 | 触发条件 |
|---|---|---|
| `full_support` | 来源明确支持该论断的**全部要素** | 三要素全 true，且来源句与论断主语/对象一致 |
| `partial_support` | 支持一部分 | 三要素缺一项；或来源只支持子集人群/条件/强度 |
| `no_support` | 不支持或相反 | 方向相反、否定极性相反、数字矛盾、对象不同却当成同一对象 |
| `undetermined` | 材料不足以判 | 缺文献表、缺来源原文、编号错位、仅有摘要、quote 无法定位 |

**三要素**

- `direction_match`：来源结论的方向（升高/降低、有效/无效、正相关/负相关）与论断一致。
- `numeric_match`：论断里的数值、样本量、效应量、显著性表述在来源里能找到同一值（允许单位换算差异，须在 `rationale` 写明换算）。
- `scope_match`：论断的强度与范围没超出来源。来源是「相关」而论断写「导致」、来源是单一材料/单一队列而论断写「普遍」、来源是体外而论断写「临床」→ 全部 `scope_match=false`。

**严重度锚点**

| severity | 锚点 |
|---|---|
| `critical` | 结论不成立：核心结论无支持/来源相反/关键数字矛盾且影响主结论 |
| `major` | 影响可解释性或可复现性：过度推断、样本量或显著性表述冲突、关键方法缺失、来源不可靠 |
| `minor` | 局部准确性问题：单处数字/单位/编号错位、引用范围过宽但不改结论 |
| `suggestion` | 建议性改进，不影响正确性：补一句限定、补数据可用性声明、统一术语 |

**`verdict_type`**：`fact_error`（事实错误）、`insufficient_evidence`（证据不足）、`compliance_issue`（规范问题）、`suggestion`（建议）。四类必须在输出里可区分——这是题面的硬要求。

## 8. 输出契约

`result.json` 顶层 = **`output_contract` 的每个键原样出现（键名不改、一个不漏，缺值 `null/[]/{}`）** + 信封字段：

| 字段 | 内容 |
|---|---|
| `case_id` | 与 `case.json` 一致；取不到则 `null` 并记 `errors` |
| `status` | `completed` / `partial` / `input_error` |
| `findings[]` | 问题清单：`finding_id`、`facet`、`location{section, locator, page, table_or_figure}`、`quote`、`quote_verified`、`issue_type`、`severity`、`severity_reason`、`verdict_type`、`evidence`、`rationale`、`revision`、`status`（`confirmed`/`pending_review`） |
| `citation_checks[]` | 核验矩阵：每条被引论断一行，含四级 `verdict`、`semantics` 三要素、双侧 `locators{claim_loc, source_loc}`、`quote_verified`、`checked_evidence` |
| `coverage` | 六类 facet + 五个专项（支持判定/来源可靠性/定位/数值一致性/论证链）逐项 `checked/items/findings/note` |
| `unchecked_items[]` | 未检查项与理由（缺材料/无权限/超预算） |
| `uncertainties[]` | 不确定性，含 `human_check_needed` |
| `sources[]` | 实际读到的材料：`source_id`、`path`、`kind`、`format`、`parser`、`bytes`、`units`、`sha256_12` |
| `errors[]` / `degradations[]` / `changes[]` | 异常、降级缺口、`build` 对判定的自动修正记录 |
| `runtime` | 版本、计数、预算；默认不含墙钟时间（保证两次运行 `result.json` 字节一致），时间与耗时写 `run_manifest.json` |

附加主产物（都在 `/app/output/`）：

- `citation_report.md`：人读报告——核验矩阵表、按严重度排序的问题清单（每条带 locator + 逐字 quote + 依据 + 改法）、覆盖与未检查项、待复核清单、复核步骤。
- `evidence.jsonl`：一行一论断/一问题，供 grep 与标注底稿。
- `run_manifest.json`：输入文件哈希、解析器、规则版本、技能版本、耗时、命令、计数。

`output_contract` 里出现、但本 Skill 无法自然映射的键，`build` 会先做字段名同义映射（见 `references/contract-and-playbook.md` 的同义表），仍映射不上就填 `null`/`[]` 并在 `degradations` 记 `contract_field_filled_empty`。**不删键、不改名。**

## 9. 失败处理与降级链

| 情况 | 处置 | status |
|---|---|---|
| `case.json` 坏 JSON / 不存在 | 记 `errors`，继续扫材料，`case_id` 为 `null` | `partial` |
| 无 `output_contract` | 用默认信封 + 内置标准字段集，记 `degradations: contract_missing` | `partial` |
| 材料为空（`/input` 下无稿件） | 不生成审查意见；`result` 说明缺什么、需要补什么文件 | `input_error` |
| PDF 无文本层 / 解析为空 | 换解析器（`pdftotext` → 内置流解析）；仍空则登记 `gap: pdf_no_text`，相关条目全部 `undetermined` + `pending_review` | `partial` |
| 参考文献表缺失 | 全部引文 `undetermined`，`unresolved_reason: no_reference_list`，`human_check_needed` 写清需人工提供文献表 | `partial` |
| 引文编号与文献表条目错位 | 配对状态 `numbering_gap`/`missing_entry`，该行 `undetermined`，另出一条 `facet=citation` 的 `compliance` finding | `partial` |
| 工作稿缺失/坏 JSON/字段不全 | **兜底成必成**：核验矩阵用机械候选填 `undetermined`，问题清单只留脚本能证明的条目（`status=pending_review`），`coverage` 全 `checked=false`，契约字段全回填，`degradations` 写清缺口，退出码 0 | `partial` |
| 单条 draft 行异常 | 该行降级 `pending_review`，其余照常产出 | `partial` |
| 输出目录不可写 | 退回 CWD 同名目录，`degradations` 写明实际路径 | `partial` |

**兜底语义（硬承诺）**：`build` 在没有工作稿、工作稿损坏、字段缺一半的情况下，仍会产出**完整最小交付**：合法的 `result.json`（契约字段全回填）、非空的主产物 `citation_report.md`、`status=partial`、`degradations` 逐条说明缺什么。它不会因为「Agent 没写工作稿」而留下空目录。

## 10. 边界与限制

- 只处理 `/input` 里实际存在的材料。**不联网**，不做数据库检索；外部文献的真实主张、DOI 有效性、撤稿状态一律 `pending_review`，不虚构。
- 定位粒度到「文件 + 章节 + 页 + 段落」。图内像素数值、图像证据不做推断；只有图注文本可引用，图注缺失时相关结论只能 `undetermined`。
- 不做统计重算（不重跑检验、不重算 p 值），只核对稿件内部数字是否自洽。
- 引文标记与文献表条目配对依赖编号/作者-年份的表面匹配；存在同名作者同年的多篇文献时判 `ambiguous`，交人工。
- 非英文/中英混排可解析，但方向词、否定词词典覆盖有限；罕见表述可能漏检，漏检会在 `unchecked_items` 说明而不是假装查过。
- 不评价研究本身的科学价值，不替代作者对结论的判断；只计问题发现、证据定位、严重度与修改建议。

## 11. 自查清单（`selfcheck` 自动跑，也可人工对照）

- [ ] `result.json` 合法，`case_id` 与输入一致，`output_contract` 的每个键都在顶层出现。
- [ ] `citation_checks` 非空（除非无引文，且 `unchecked_items` 说明原因），每行 `verdict` 在四级集合内。
- [ ] 每行都有 `semantics.direction_match/numeric_match/scope_match` 三个键（无法判定用 `null` + 理由）。
- [ ] `undetermined` 行都有 `unresolved_reason` 与 `human_check_needed`。
- [ ] 每条 `confirmed` finding 的 `quote` 能在 `sources[]` 的原文里逐字命中；未命中的已降级为 `pending_review`。
- [ ] 每条 finding 有 `location.locator`、`severity` + `severity_reason`、`evidence`、非空可执行的 `revision`。
- [ ] 六类 facet 在 `coverage` 里都有条目；未检查的写进 `unchecked_items` 并给理由。
- [ ] 严重度不是全同一档；`verdict_type` 四类能区分。
- [ ] `coverage` 的计数与 `findings` 实际条数一致。
- [ ] 空输入 / 坏 JSON / 缺工作稿三种情况都产出合法 partial，退出码 0。
- [ ] 同输入跑两次，`result.json` 字节一致（`runtime` 不含墙钟时间）。

## 12. 评分维度 → 实现落点

| 评分点 | 本 Skill 的落点 |
|---|---|
| 实际效果·任务完成度 15 | 五命令主路径强制「先读材料写工作稿」；每条被引论断都有矩阵行，每条问题都有定位+原文+判定+严重度+改法；`build` 兜底保证任何情况都有可交付结果 |
| 实际效果·结果正确性 15 | 三要素硬规则 + 「主题相关 ≠ 支持」硬拦 + `full_support` 与三要素矛盾时按规则重算并记录 + quote 逐字命中才可 `confirmed` |
| 实际效果·结果完整性 5 | 六类 facet + 五个专项覆盖表；方法/结果/讨论章节靠 `units` 的 section 归属显式覆盖；未检查项显式登记 |
| 实际效果·可核验性 5 | 双侧定位（本文 locator + 来源 locator/标识）+ 逐字 quote + `quote_verified` + 判定依据 + 版本记录（`run_manifest.json`）+ 输入哈希 |
| 使用增益·质量 15 | 脚本完成引文抽取/配对/数值比对/quote 校验这些确定性重活，模型只做判断；召回靠候选全集（不被模型遗漏），误报靠 `no_support` 的高门槛（方向/数字/对象三证）抑制 |
| 使用增益·效率 5 | 一次 `init` + 一次 `show` 替代全文重读；`draft.template.json` 预填 locator 与 quote，模型只补判定 |
| 使用增益·可验证 5 | 判定规则外置（`references/verdict-rubric.md`），脚本无随机、无网络，同输入两次运行结果字节一致 |
| 创新增益 15 | 论断-来源双侧定位串、四级支持度 + 三要素向量、overclaim 专项检测、引文标记↔文献表配对状态机（`missing_entry`/`ambiguous`/`numbering_gap`）、数值一致性跨章节桶比对、`pending_review` 一等工作流 |
| 可靠体验 10 | 触发条件与越界拒绝（§2）、五命令序列（§1）、异常降级表（§9）、退出码恒 0、单条失败不影响全局、路径三重回退 |
| 生态贡献 10 | 本文档 + 四级判定规范 + 字段字典与同义表 + 审查手册（含最小示例）+ 可复现脚本 + `run_manifest.json` 版本记录 |

## 13. 最小调用示例（**示例数据，非正式案例结果**）

```bash
export AUDIT_INPUT=./examples/mini  AUDIT_WORK=./work  AUDIT_OUTPUT=./out
python3 scripts/main.py init
python3 scripts/main.py show --part claims
#  Agent 读材料后写 ./work/draft.json
python3 scripts/main.py check
python3 scripts/main.py build
python3 scripts/main.py selfcheck
```

示例输入（人造，仅示意接口）：`case.json` 含 `case_id: "demo-01"` 与 `output_contract: {"findings": "...", "citation_checks": "...", "coverage": "..."}`；材料 `manuscript.md` 含一段 Results：

> 处理组的存活率显著高于对照组（82% 对 61%，p=0.03）[2]，说明该处理对所有患者人群普遍有效。

而文献表 `[2]` 对应条目为一份**单中心、慢性肾病亚组**的研究。

示意输出（示例）：该行为 `citation_checks` 一行，`verdict: partial_support`，`semantics` 中 `direction_match: true`、`numeric_match: false`（来源未报告 82%/61%）、`scope_match: false`（单中心亚组 → "所有患者人群普遍有效" 属过度推断）；对应 `findings` 一条，`facet: citation`、`issue_type: overclaim`、`severity: major`、`revision: "把「对所有患者人群普遍有效」改为「在该单中心慢性肾病亚组中有效（[2]）」，并删除普遍性表述"`。完整字段解释见 `references/contract-and-playbook.md`。

## 14. 文件清单、版本与维护

```
SKILL.md                              本文档：用途、五命令主路径、契约、方法、边界、降级、自查
scripts/main.py                       五命令驱动 + 结果装配 + 兜底 finalize（不判定语义）
scripts/audit_core.py                 输入发现、PDF/文本解析、段落 locator、引文配对、quote 校验
scripts/audit_build.py                候选扫描、工作稿单遍校验与规范化、覆盖表、自检
scripts/audit_render.py               兜底内容、契约回填、result 信封、人读报告与证据流
references/verdict-rubric.md          四级判定、三要素、严重度锚点、覆盖矩阵、误报抑制
references/contract-and-playbook.md   工作稿 schema、result 字段字典、契约同义表、八步手册、异常处置
```

- 版本 `1.0.0`；规则版本 `rules/1`；索引 schema `audit-index/1`。
- 依赖：Python ≥ 3.9 标准库。可选外部工具 `pdftotext`（poppler-utils）提升 PDF 抽取质量；缺失时自动回退内置流解析，并在 `sources[].parser` 与 `degradations` 如实记录。
- 维护：改判定阈值或三要素规则必须同步 `references/verdict-rubric.md` 并在 `run_manifest.json` 的 `rules_version` 递增；新增材料格式只改 `audit_core.read_any`，`result.json` schema 不变。
- 复跑一致性：无随机、无时间戳进入 `result.json`、无网络；同输入两次 `build` 结果字节一致，用于证明「增益可验证」。
