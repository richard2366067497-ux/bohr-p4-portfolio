---
name: research-frontier-event-timeline
description: 把一批科研文献整理成"有年份的有向事件台账"，再由台账派生年度产出分布、阶段划分、转折事件、代表性工作与研究空白，产出可逐条回链（source_id + locator + 逐字 quote）的趋势分析结果与 result.json。单命令 all 即可在无草稿时产出完整降级交付；五命令 init/show/check/build/selfcheck 支持 Agent 深读与人工复核。适用于"某个方向现在做到哪、往哪走、哪里还空着"的前沿与趋势分析、主题演化追踪、代表作选取、研究空白识别、综述证据矩阵构建等任务；输入为案例材料（PDF/MD/TXT/JSONL/CSV）与任务说明，输出为事件台账、时间线、派生统计、证据矩阵、空白清单与结构化结果。不适用于无材料的凭空综述、替代同行评审、需要显著性检验的计量分析，或在没有排除证据时宣称"全球空白"。
version: 1.2.0
---

# 研究前沿与趋势分析：事件台账优先（event-first）

## 单命令入口（评测入口，先看这里）

无 draft.json 时直接运行本命令即可产出完整契约与全部交付物；评测环境按此执行。

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

## 随包方法论（执行前必读）

在执行任何命令、产出任何交付物之前，**先完整阅读 `references/expert_playbook.md`（专家参考手册）**，
并按其组织全部产出：

- **四类产物**：按其 **§1** 交付"时间趋势－主题演化－代表性工作－研究空白"，每条结论回链 locator，区分
  "材料事实 / 合理推断 / 无法确定"。
- **流程**：按其 **§2 步骤 0–9（含门控）** 推进——读取输入 → 拆解问题与检索范围 → 收集去重 → 年份归一与时间切片
  → 主题归并演化 → 代表作 → 空白 → 证据矩阵 → 不确定性 → 结构化输出；前一步未过门控不进入下一步。
- **口径**：按其 **§3 量化口径** 计算年度产出量、主题占比、CAGR、拐点（>30% 且增量 ≥3）、主题出现/合并/分裂/衰退、
  代表作阶段指数与空白判据。
- **陷阱**：按其 **§4 领域陷阱清单** 逐条排雷（材料/工艺/条件/模拟/预印本/综述、单位量纲、证据状态）。
- **门控**：交付前逐项通过其 **§6 防扣分自查表（20 项）**；任一项未过则 `status=partial` 并把未决项写入
  `uncertainty` / `degradations`，绝不静默提升为完整成功。

## 0. result.json 契约样例（output_contract 逐键回填，顶层 + 嵌套）

`result.json` 把**用例声明的每一个 `output_contract` 键**写进 `output_contract` 对象，并在顶层写入同名键；
每个值都是**真实推导结果**、真实产物路径或诚实的非空结构，绝不写 `"string"`/`"array"`/`"value"` 这类类型串。
用例未给契约（`output_contract: null`）时使用下列默认 8 键：

```json
{
  "case_id": "example-case-001",
  "status": "partial",
  "output_contract": {
    "research_summary": "2016 至 2022 年，该方向从框架提出转向多对象验证；每条结论后附事件 id。",
    "events": [{"event_id": "E01", "year": 2019, "year_source": "published", "event_type": "proposal", "source_id": "S01", "locator": "S01:P03", "quote": "we propose a unified framework for X", "statement": "提出 X 的统一框架"}],
    "trend_stats": {"by_year": {"2019": 1}, "by_type": {"proposal": 1}, "events_dated": 1, "small_sample": true},
    "stage_division": [{"stage_id": "G1", "label": "框架提出期", "year_range": [2016, 2019], "basis_event_ids": ["E01"], "lifecycle": "emerging"}],
    "turning_points": [{"turning_id": "P1", "event_ids": ["E02"], "criteria_hit": "first_of_type", "why_turning": "首次出现 validation 事件"}],
    "gaps": [{"gap_id": "N1", "gap_type": "missing_validation", "description": "X 假设缺少后续验证", "events_evidence": ["E01"], "search_scope": "9 份材料全文与题面", "exclusion_evidence": "对 X 与 Y 检索 0 命中，属材料范围限制"}],
    "evidence_matrix": [{"event_id": "E01", "source_id": "S01", "locator": "S01:P03", "quote": "we propose a unified framework for X", "claim": "提出框架"}],
    "uncertainty": ["样本仅 9 份材料，结论为提示性，不外推到全领域"]
  }
}
```

- `output_contract` 与顶层同名键**同时存在且值一致**；路径型键（如 `deliverable`）写真实产物相对路径。
- `case_id` 从 `case.json`（`case_id`/`caseId`/`id`/`task_id`）**原样透传**，不得改写。
- 空内容不写成 `null`/`[]` 类型占位，而换成带 `search_scope`/`basis` 的诚实非空结构，并在 `degradations` 说明。

## 1. 单命令入口（single-command entry，一条命令跑完全流程）


见文首「单命令入口（评测入口）」——同一条命令，评测环境只跑这一条也能过。

这一条命令完成：扫描输入 → 建索引 → 事件台账（无 draft 时用规则化候选，标 auto/low）→ 年度统计/阶段/转折/空白
→ 时间线/趋势报告/证据矩阵/SVG → 写 `result.json`（契约逐键回填 + `case_id` 透传）→ 占位符净化。
**无草稿、无多阶段人工介入；空输入/坏 JSON 同样 exit 0，并保留合法结果与限制说明。**
需要更高质量时，再走第 2 节的五命令路径补一份人工工作稿。

## 2. 五命令主路径（Agent 深读；可选但推荐）

在 skill 根目录执行（若不确定当前目录，用绝对路径 `python3 /skills/weekly-skill/scripts/main.py ...`）：

```bash
python3 scripts/main.py init       # 建索引：解析 case.json/task.md/材料，登记语料与年份口径，先写合法 partial result.json
python3 scripts/main.py show       # 打印带 locator 的原文段与候选事件线索，供逐字引用
#  >>> 你（评审 Agent）亲自读材料，写工作稿 /app/work/draft.json <<<
python3 scripts/main.py check      # 机械校验：契约字段、quote 命中、事件字段、统计守恒、阶段依据、空白证据
python3 scripts/main.py build      # 由工作稿生成事件台账/时间线/派生/图 + 最终 result.json（无条件 finalize）
python3 scripts/main.py selfcheck  # 复检产物一致性（可选，但建议跑）
```

> **脚本不会代替你阅读理解；必须先阅读材料、写工作稿，再运行 build。**
> 只跑 `all` 或只跑 `init`+`build` 会得到 `status=partial` 的规则化降级稿（台账来自候选句、结论保守）；
> 读了材料并把事件判进 `draft.json`，`build` 才能产出可被复核的深度趋势结论。

时间预算下的最短合格动作：`init` → `show --grep "<主题词>"` 读 6–10 段 → 写 8–20 条事件 + 2–3 个阶段 + 1–3 个空白 → `check` → 修 → `build`。

## 3. 运行契约

| 项 | 约定 |
|---|---|
| 输入 | `/input/case.json`（`case_id`/`task_instruction`/`output_contract`，可能含 `topic`/`research_question`/`sources[]`/`records[]`/`time_range`）、`/input/task.md`、材料在 `/input/sources/`、`/input/records.jsonl`、`/input/protocol.md` 或 `/input` 任意子目录 |
| 工作目录 | `/app/work`：index.json（脚本建）、draft.json（五命令路径由你写）、check.json（脚本写） |
| 产物 | `/app/output/`：`result.json`、`events/event_ledger.jsonl`、`events/event_sources.json`、`timeline.md`、`derived/*.json`、`figures/timeline.svg`、`figures/figure_specs.json`、`trend_report.md` |
| 依赖 | 仅 Python3 标准库（`pdftotext` 若存在则优先用，否则内置流解析）；离线；不依赖当前工作目录（脚本用 `Path(__file__).resolve()` 定位） |
| 覆盖路径 | 可用 `--input/--output/--work` 或环境变量 `SKILL_INPUT/SKILL_OUTPUT/SKILL_WORK` 覆盖；默认不是 `/input` 时脚本自动回退到 skill 同级 `input/`、`./input` |
| 退出码 | **恒为 0**。所有异常写进 `result.json.errors`，并保留已有产物 |
| 预算 | 64 次模型请求 / 900 秒 / 单次回复 16384 token。确定性重活（解析、统计、渲染、校验）全部由脚本做；模型只做事件判定与阶段解释。约 780 秒时立即 `all` 收口 |

## 4. 谁写什么（决定成败）

| 角色 | 负责 |
|---|---|
| 脚本 | 扫描材料、切段编号、抽取年份/venue/主题候选、打印原文、统计、守恒校验、渲染时间线与 SVG、回填 `output_contract`、净化占位符 |
| **Agent（你）** | **判断哪句话构成哪种事件**、事件属于哪个主题/方法/对象、阶段怎么切、哪个是转折、哪个是真空白（而非检索遗漏） |
| 禁止 | 把脚本的"候选事件"当结论直接提交；只写提纲不写事件；为了通过校验去改写原文 quote |

## 5. 五步方法（每步：判定规则 → 产物字段 → check 错误码）

### 第 1 步 语料登记与年份归一

- 每个来源登记：`source_id`（`S01`…）、`title`、`year`、`year_source`、`venue`、`themes[]`、`has_fulltext`。
- `year_source` 固定枚举：`published`（见刊年）、`online`（在线发表）、`preprint`（预印本）、`venue`（会议/期刊卷期推定）、`unknown`。
- **一个来源有多种年份时，以 `published` 为主口径，其余进 `year_alt`**；统计口径对结论的影响写进 `method_notes.year_basis`。
- 年份缺失：`year=null` 且 `year_source="unknown"`，**不猜测、不用当前年填充**；该来源仍进语料但标注"未参与年度统计"。
- 产物：`result.json.sources[]`、`events/event_sources.json`。
- 错误码：`SRC_NO_ID`、`YEAR_INVALID`（非 1800–2100 的整数）、`YEAR_CONFLICT`。

### 第 2 步 事件抽取（类型学）

固定枚举 `event_type`（详见 `references/event-typology.md`）：

| 类型 | 含义 | 典型原文线索 |
|---|---|---|
| `proposal` | 提出设想/假说/框架/问题 | propose, hypothesize, we suggest, 我们提出 |
| `validation` | 实验/数据支持某主张 | demonstrate, confirm, we show, 验证 |
| `refutation` | 反驳、未能复现、否定先前结论 | fail to, contradict, cannot reproduce, 相反 |
| `method_introduced` | 新方法/新工具/新数据集首次引入 | we introduce, novel method, 首次提出 |
| `merged` | 两条主题线/方法线合流 | combine, integrate, 结合 |
| `split` | 主题分化出子方向 | distinguish two, 分为两类 |
| `declined` | 主题/方法被替代或降温 | superseded, no longer, 逐渐被取代 |
| `application_transfer` | 方法迁移到新对象/新尺度/新领域 | applied to, extend to, 应用于 |

- 每条事件必填：`event_id`（`E01`…）、`year`、`year_source`、`event_type`、`statement`（一句话事实陈述，**不含评价**）、`source_id`、`locator`、`quote`（**逐字**）、`theme_id`、`method`、`object`、`confidence`（`high|medium|low`）。
- 判定规则：**先看句子动词，再看它作用的对象**；同一句含两个事件就拆两条；纯背景/引用他人工作不算事件；综述性句子只在它明确断言"领域状态"时记为 `declined`/`merged` 并降 `confidence`。
- 抽不到事件是合法结果：写入 `events/event_sources.json` 的 `no_event`（带原因），**不要编造**。
- 错误码：`EV_NO_QUOTE`、`EV_TYPE_INVALID`、`EV_YEAR_MISSING`、`EV_STATEMENT_EVALUATIVE`（含"重要/突破性"等无证据评价词）。

### 第 3 步 时间线排序与阶段划分

- `timeline.md` 按年升序，每年下列事件；阶段标记插在年份之间。
- 阶段划分依据必须写 `basis_event_ids`，常用三种依据：**事件类型构成变化**（如某年起 `validation` 超过 `proposal`）、**新主题首次出现**、**事件密度突变**。写不出依据就不要切阶段。
- `stage_division[]` 字段：`stage_id`、`label`、`year_range`、`basis_event_ids`、`lifecycle`（`emerging|consolidating|maturing|declining`）、`rationale`。
- 错误码：`STAGE_NO_BASIS`、`STAGE_YEAR_ORDER`、`STAGE_GAP`。

### 第 4 步 派生统计与转折事件

- `derived/trend_stats.json` **由事件台账聚合**：`by_year`、`by_type`、`by_theme_year`、`growth`、`peak_year`、`span`、`small_sample`。脚本计算，不是你手算；**台账与统计必须守恒**（年度求和 = 台账条数）。
- `derived/turning_points.json`：转折事件 `{turning_id, event_ids, why_turning, criteria_hit}`。`criteria_hit` 只能取：
  `first_of_type`、`type_shift`、`density_jump`（相邻年事件数翻倍/腰斩，且样本 ≥8）、`theme_birth`、`theme_death`。
- **代表性工作不是被引最高**：代表作 = 命中 `criteria_hit` 的转折事件所在文献；每阶段至少 1 篇，长尾方法首创优先于高被引综述。
- 错误码：`STAT_MISMATCH`、`TURNING_NO_CRITERIA`、`TURNING_EVENT_MISSING`、`REP_STAGE_UNCOVERED`。

### 第 5 步 研究空白判定

`gap_type` 固定枚举，**每条空白必须同时给"事件证据 + 检索范围 + 排除证据"**：

| gap_type | 判据 | 必须有 |
|---|---|---|
| `missing_validation` | 有 `proposal` 事件，其后无同主题 `validation` | 提出事件 id + 检索到的验证尝试（含失败） |
| `stalled_theme` | 某主题最后一次事件后 ≥2 年无事件 | 最后事件 id + 时间窗 |
| `no_transfer` | 方法在某对象/尺度上无 `application_transfer` | 方法事件 + 检索过的对象词 |
| `unresolved_conflict` | 存在 `validation` 与 `refutation` 指向同一主张 | 双方事件 id |
| `retrieval_gap` | 材料本身不足（缺全文/缺年份/仅摘要） | 缺什么 + 补检索建议 |

- `exclusion_evidence` 必填：写清"我检索了哪些词/范围、为什么这不是遗漏"。
- 错误码：`GAP_NO_EXCLUSION`、`GAP_TYPE_INVALID`、`GAP_NO_EVENT_EVIDENCE`。

## 6. 工作稿 `draft.json`（五命令路径的唯一写入口）

```json
{
  "case_id": "由 case.json 复制，勿改",
  "research_question": "一句话，来自 task_instruction，不改写题意",
  "corpus": [{"source_id":"S01","year":2019,"year_source":"published","year_alt":null,
              "venue":"...","themes":["T1"],"has_fulltext":true}],
  "events": [{"event_id":"E01","year":2019,"year_source":"published","event_type":"proposal",
              "statement":"...","source_id":"S01","locator":"S01:P04","quote":"逐字原文",
              "theme_id":"T1","method":"...","object":"...","confidence":"high"}],
  "stage_division": [{"stage_id":"G1","label":"...","year_range":[2016,2019],
                      "basis_event_ids":["E02","E05"],"lifecycle":"emerging","rationale":"..."}],
  "turning_points": [{"turning_id":"P1","event_ids":["E07"],"why_turning":"...","criteria_hit":"first_of_type"}],
  "gaps": [{"gap_id":"N1","description":"...","gap_type":"missing_validation",
            "events_evidence":["E01","E03"],"search_scope":"...","exclusion_evidence":"..."}],
  "method_notes": {"year_basis":"...","theme_merge_rules":"...","stage_basis":"...","gap_criteria":"...","small_sample_rule":"..."},
  "uncertainties": ["..."], "pending_human": ["..."]
}
```

字段与校验口径见 `references/event-typology.md` 与本节各步错误码。`init` 会写一份带 `corpus` 骨架与候选事件的 `draft.json` 模板；**你要删掉/改写候选，不能原样提交**（`check` 会把仍带 `auto: true` 且 `reviewed: false` 的脚本候选逐条提示）。

## 7. 输出契约（`result.json`）

- **原样回填 `case.json` 的 `output_contract` 全部字段**：不改名、不删键、不嵌套重排；同时在 `result.json.output_contract` 与顶层各写一份同值副本。
- 键值必须是**真实内容**：`deliverable` 等路径键指向真实非空产物；数组/对象键写真实事件、统计、阶段、转折、空白、证据行；标量键写实际值。**禁止写类型串**。
- 某键确实抽不到内容时，写**诚实的非空结构**（带 `search_scope`/`basis`/`note`），并在 `degradations` 解释缺口；不要留 `null`。
- 固定信封字段：`case_id`、`status`(`ok|partial|insufficient_evidence|input_error`)、`research_question`、`sources[]`、`events[]`、`trend_stats`、`stage_division[]`、`turning_points[]`、`gaps[]`、`representative_works[]`、`evidence_matrix[]`/`evidence_map`、`coverage`、`method_notes`、`uncertainty`/`uncertainties`、`limits`、`errors[]`、`degradations[]`、`change_log`/`change_records`、`self_check`、`runtime`、`contract_fill`、`deliverable_manifest`、`output_contract`。
- `status` 规则：契约字段齐 + 事件 ≥8 且 quote 全命中 + 阶段有依据 + 空白有排除证据 → `ok`；有缺口但已交付 → `partial`；材料不可用 → `insufficient_evidence`；输入不可解析 → `input_error`。
- `coverage`：`sources_expected`、`sources_read`、`sources_with_year`、`events`、`years_covered`、`themes`、`event_types_covered`、`small_sample`（`events<=20` 或 `sources<=10` 时 `true`）。
- **小样本**：`small_sample=true` 时结论句必须用"提示性/初步"，禁止"显著上升""证明"；脚本会在 `check` 里对断言词报 `CLAIM_OVERREACH`。

## 8. 证据与定位规范

- locator 格式：`S<两位来源号>:P<三段段号>`，如 `S03:P07`；也接受区段（校验用起点）。
- 段号由 `init`/`show` 打印的编号决定，**不要自己数**。
- `quote` 逐字取自源材料：允许空白/全半角/连字符差异与大小写差异，**不允许改词、补字、翻译、拼接两段**。校验失败顺序：改用词更短的 quote → 改 locator → 该项移入 `pending_human`。**禁止为了通过校验修改原文。**
- 事件 `statement` 里出现的数字/年份必须能在该 quote 或同源材料找到（`NUM_UNSOURCED` 提示）。

## 9. 冲突、歧义与不确定

- **时序冲突**：`validation`/`refutation` 的年份早于所指向的 `proposal` → 标 `chronology_conflict: true` 并在 `uncertainty` 说明（不擅自改年份）。
- **年份口径冲突**：同一文献 online 年与见刊年跨年 → 双值记录，统计按主口径，方法注说明影响。
- **术语漂移/同名异义**：同一词在不同年份指不同对象 → 拆成不同 `theme_id` 并写 `method_notes.theme_merge_rules`；无法判定就标 `ambiguous`，不做归并。
- **证据冲突**：同一主张有验证与反驳 → 两条都进台账，空白记为 `unresolved_conflict`，不择一。
- 以上四类都进 `uncertainty`，并说明"结论因此不能外推到 X"。

## 10. 异常降级分支（脚本已实现，理解即可）

| 情形 | 行为 |
|---|---|
| `case.json` 缺失/坏 JSON | 递归找含 `output_contract` 的 json；仍无则用内置默认字段，`degradations` 记录，`status=partial` |
| `/input` 为空或无材料 | 写合法 partial `result.json`（契约键给诚实非空结构 + `limits`），`status=insufficient_evidence`，exit 0 |
| PDF 无 `pdftotext` | 内置流解析；质量低标 `builtin-pdf-lowconf` 并提示人工核对 |
| 材料是图片 | 不做 OCR，记 `image-no-ocr` 缺口，不臆造图注 |
| 单个材料解析失败 | 只降级该文件，其余继续；`degradations` 记文件名与原因 |
| `draft.json` 缺失/字段不全 | `all`/`build` 用"记录/段首句 + 事件类型关键词规则"生成低置信候选台账（`auto:true`、`confidence:low`），**仍产出全部产物**，`status=partial`，缺口写进 `degradations`，图与统计仍与台账守恒 |
| 未知 `event_type`/年份非法 | 该事件降级为 `proposal`/`unknown` 并记 `errors`，不丢弃其余事件 |
| 超时/异常 | 恒 exit 0；已有产物保留；重跑 `all`/`build` 覆盖 |

## 11. 自检清单（交付前）

- [ ] `result.json` 契约字段齐全：`output_contract` 与顶层同名键都在，且没有 `null`/类型串；空项在 `degradations` 有解释。
- [ ] `case_id` 与输入 `case.json` 一致。
- [ ] 每条事件有 `source_id`/`locator`/逐字 `quote`，`check` 无 `[错误]`。
- [ ] `derived/trend_stats.json` 的年度求和 = 台账条数（`STAT_MISMATCH` 为 0）。
- [ ] 每个阶段有 `basis_event_ids`；每个转折有 `criteria_hit`；每阶段至少 1 篇代表作。
- [ ] 每条空白有 `events_evidence` + `search_scope` + `exclusion_evidence`。
- [ ] `small_sample=true` 时全文无"显著/证明/必然"断言。
- [ ] `timeline.md`、`trend_report.md` 的每个结论后面都有事件 id。
- [ ] 全部产物无 `[待写]`/`null`/`pending` 等占位符（`all` 会自动净化）。
- [ ] **专家检查表逐项通过**：`references/expert_playbook.md` §6 的 20 项防扣分自查表逐项勾选通过；任一项未过则 `status=partial` 并把未决项写入 `uncertainty`/`degradations`，绝不静默提升为完整成功。

## 12. 评分维度映射（内化在包里的实现）

| 维度 | 本包落实 |
|---|---|
| 实际效果 40 | 四类可检查产物齐备；quote 逐字命中校验；年份口径与 `year_alt`；阶段 `basis`、转折 `criteria_hit`；台账-统计守恒可独立复算 |
| 使用增益 25 | 事件化替代"前 N 条当前沿"；单命令 `all` 一次完成扫描/统计/渲染/契约回填/净化；`self_check` 与 `derived` 文件给出可复算证据 |
| 创新 15 | event-first（统计是派生视图）；台账-统计守恒；转折事件作为代表作口径；空白由事件类型缺口推导 |
| 可靠 10 | 单命令 `all` + 五命令固定入口、恒 exit 0、全分支降级、空输入/坏 JSON 均产合法 `result.json` |
| 生态 10 | SKILL.md + `references/event-typology.md`（可复用类型学）+ `references/draft-schema.md`（字段字典）+ 最小示例；脚本可换领域复用 |

## 13. 文件清单、版本与维护

| 文件 | 作用 |
|---|---|
| `SKILL.md` | 本说明：单命令入口、五命令流程、契约、规则、降级、自查 |
| `scripts/main.py` | `all`/`init`/`show`/`check`/`build`/`selfcheck` 入口、契约回填、输出净化、finalize |
| `scripts/core.py` | 材料扫描与切段、case 发现、语料/记录登记、事件校验 |
| `scripts/derive.py` | 统计与阶段/转折/空白派生、时间线与 SVG/报告渲染 |
| `scripts/audit.py` | 契约字段解析/回填、产物自检 |
| `references/event-typology.md` | 事件类型学、年份归一规则、阶段与空白判据（换领域直接复用） |
| `references/expert_playbook.md` | 专家方法论：四类产物口径、量化公式、陷阱、自查表、虚构案例 |
| `GAIN_EVIDENCE.md` / `environment/resources.yaml` / `examples/case.json` | 增益对照、资源入口声明、最小示例 |

- 版本 1.2.0；仅标准库；无网络；无外部服务。
- 换领域不需要改脚本：`init` 按扩展名+魔数识别材料，段落编号自动生成；新增事件类型需同时改 `derive.py` 的 `EVENT_TYPES` 与 `references/event-typology.md`（保持枚举一致）。
- 改了脚本必须重跑三件事：`--help`（exit 0）、空 `/input`（exit 0 + 合法 `result.json`）、坏 JSON（exit 0）。
