# 核验规则表、字段字典与工作稿 schema

本文件是 `sci-lit-bilingual-audit` 的规范附件，被 `SKILL.md` 引用。三类读者：

- **执行 Agent**：写 `draft.json` 前看 §4/§5，知道每个字段怎么填才会被判为 `locked`；
- **脚本维护者**：改判定口径时看 §2/§3/§6，规则与代码一一对应；
- **评审/复核人**：看 §2/§7，知道每个 fail 是怎么来的、能不能机械复算。

---

## 1. 对象模型

一次运行产生 4 层对象，全部围绕"原文可定位"这一条：

| 层 | 对象 | 标识 | 由谁产生 |
|---|---|---|---|
| 材料 | source（文件） | 相对 `/input` 的路径 | `init`（`index.json.sources`） |
| 页面 | page | 自 1 递增的序号 | `init`（`index.json.pages`） |
| 段落 | segment | `S001`…（3 位，按阅读顺序） | `init` 切段规则 R1–R7 |
| 译段 | pair | 与 segment 同 sid | Agent 写 `draft.json`，`build` 渲染 |

`locator` 形如 `p3:S012`；跨页续段写成 `p3-4:S012`，同时 `bridged=true`。
**sid 只由脚本分配**，Agent 不得新增、重排或跳号——`sid_integrity` 会检查。

段落 `type` 取值：`heading` / `abstract`（章节语境）/ `body` / `caption_figure` /
`caption_table` / `formula` / `reference`。`section` 记录所属章节语境
（`abstract` / `introduction` / `references` 等），用于判定"参考文献段保留原文"。

---

## 2. 保护性 span 字典

`init` 抽取、`audit` 校验的是同一套规则（`align.SPAN_RULES`）。含义：
**这些片段在译文中必须逐字等值**（中文语境允许把 `Fig. 2` 写成 `图2`，但编号必须一致）。

| kind | 匹配对象 | 例子 | 缺失判定 |
|---|---|---|---|
| `pct` | 百分数 | `87.3%`、`4.2 %` | fail |
| `pvalue` | p 值 | `p < 0.05`、`P=0.01` | fail |
| `stat` | 统计量 | `r = 0.82`、`F = 3.41` | fail |
| `pm` | 误差 | `± 0.5` | fail |
| `num_unit` | 数字+单位 | `12 kHz`、`5 dB`、`37 °C` | fail |
| `cite_bracket` | 方括号引用 | `[12]`、`[3,5]`、`[7–9]` | fail |
| `cite_author` | 作者-年份 | `(Smith et al., 2020)` | fail（数量减少即 fail） |
| `eq_tag` | 公式编号 | `(1)`、`(12a)` | fail |
| `fig_ref` | 图表/公式/章节指向 | `Fig. 2`、`Table 1`、`Eq. (3)`、`Section 4.1` | fail |
| `greek` | 希腊字母与数学符号 | `α`、`±`、`≈` | 仅记录，不单独判 fail |

比对方式：原文 span 集合（多重集合，保留重复计数）减去译文 span 集合，差集非空即
`protected_numbers`/`citations`/`figure_table_refs`/`equation_tags` 判 fail，条目里带段号
与缺失值。译文**多出**原文没有的数字 → `warn`（可能是译者补的章节号或编号，需人工确认）。

数字归一化：千分位逗号删除（`1,200` → `1200`）、小数点保留、尾随 `.0` 归整、全角转半角。
不做四舍五入、不做单位换算——换算即视为篡改。

---

## 3. 核验项清单（15 项）

`status` 取值 `pass` / `fail` / `warn` / `skip`。`fail` 必须回改；`warn` 进
`pending_human`；`skip` 表示该案例不适用（如原文无否定句）。

| # | check | 严重度 | 判定 | 典型修复 |
|---|---|---|---|---|
| 1 | `sid_integrity` | fail | 段号重复 / 索引中不存在 / 未覆盖 | 只用 `show` 给出的 sid |
| 2 | `source_verbatim` | fail | 工作稿 `source` 与索引原文不一致 | 从 `SRC` 逐字复制 |
| 3 | `coverage` | fail | 有段落无译文或只有 `〔待补〕` | 补译，或标 `〔未译:原因〕` |
| 4 | `glossary_quote` | fail | 术语有译名但无逐字命中原文的 `quote` | 补真实 quote 或降级为 `proposed` |
| 5 | `glossary_lock` | fail | 锁定术语在其出现的段落里未使用锁定译名 | 统一译名后重跑 |
| 6 | `glossary_drift` | warn | 同一源术语在工作稿里出现多种译名 | 择一锁定，另一条删掉或改 term |
| 7 | `protected_numbers` | fail | 数字/单位/百分数/p 值/统计量缺失 | 回填原值，不改量级 |
| 8 | `citations` | fail | 引用编号或作者-年份标记丢失 | 原样保留标记 |
| 9 | `figure_table_refs` | fail | 图表/公式/章节编号不一致 | 编号照抄，只译"图/表"字样 |
| 10 | `equation_tags` | fail | 公式编号 `(n)` 丢失 | 保留编号 |
| 11 | `negation` | fail | 源句含否定/限制成分，对应译文无否定标记 | 补"不/未/无/仅/无法"等 |
| 12 | `hedge` | warn | 源句含限定/可能性成分，译文疑似强化为断言 | 补"可能/提示/相关" |
| 13 | `placeholder_policy` | warn/fail | `answered` 状态下仍含占位符 / `〔存疑〕` 未配 `uncertain` | 清零或降级 status |
| 14 | `target_language` | fail | 译文缺目标语言字符（参考文献段豁免） | 补译 |
| 15 | `repeated_target` | warn | 多段译文完全相同（疑似复制填充） | 逐段重译 |

句子级检查（11/12）的配对方式：源句按 `[.!?]` 切分，目标句按 `。！？；` 切分，
按 `tgt_i = round(i·(nt-1)/(ns-1))` 做保序比例映射。**这是近似对齐**——句数差异大时
检查会漏判或误判，所以只对 fail 的段给提示、由 Agent 复核，人工可据此定位重译。

---

## 4. 术语表规范

工作稿里写 `glossary`，每条：

```json
{"term": "few-shot", "target": "少样本", "basis": "S003 首次定义", "sid": "S003",
 "quote": "few-shot fault diagnosis", "expansion": ""}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `term` | 是 | 原文术语，逐字取自原文（大小写不敏感匹配，按词边界） |
| `target` | 是 | 锁定译名；留空则不参与回扫 |
| `basis` | 建议 | 译法依据（定义位置、领域惯例、与上位术语的关系） |
| `sid` | 是 | 证据所在段号 |
| `quote` | 是 | 该段中包含 `term` 的**逐字**片段（10–120 字符为宜） |
| `expansion` | 否 | 缩写全称，用于首现规则 |

判定树：

```
有 target ?
 ├─ 否 → proposed（不参与回扫，进 uncertainties）
 └─ 是 → quote 在 sid 原文逐字命中 ?
          ├─ 是 → 同 term 只有一种 target ? → locked
          │                              └→ conflict（多种译名，先统一）
          └─ 否 → proposed + glossary_quote fail
```

- **首现缩写规则**：`full name (ACRONYM)` 首现处译作「全称（缩写）」，其后各段只留缩写。
- **术语条数**：10–40 条。少于 10 条通常说明没做术语工作；多于 40 条会稀释回扫信号。
- **全篇回扫**：每个 `locked` 术语在其出现的**所有**段落检查 `target` 是否出现；
  `consistency_rate = 命中次数 / 出现次数`，写入 `audit_report.rates.glossary_consistency`。
- **跨篇复用**：把上次的 `output/glossary.json` 拷成 `work/glossary_seed.json`，新篇仍需
  自己的 `quote` 才能 `locked`——seed 只提供译名候选，不提供证据。

---

## 5. 工作稿 draft.json schema

路径 `work/draft.json`，可分批写成 `work/draft_part_01.json`、`draft_part_02.json`…
（按文件名排序合并，同 sid / 同 term 后者覆盖前者）。也接受 `work/plan.json`。

```json
{
  "case_id": "CASE-01",
  "task_understanding": "一句话说明任务边界与翻译口径",
  "glossary": [ {"term": "...", "target": "...", "basis": "...", "sid": "S003", "quote": "..."} ],
  "segments": [
    {"sid": "S003", "source": "原文逐字", "target": "译文", "term_hits": ["few-shot"],
     "notes": "译法说明", "uncertain": false, "basis": "为什么这样译"}
  ],
  "result_fields": {"<output_contract 的字段名>": "该字段的值"},
  "uncertainties": ["S011 的 association 关系未敢断言为因果"],
  "decisions": ["参考文献段按策略保留原文"]
}
```

| 字段 | 必填 | 校验点 |
|---|---|---|
| `case_id` | 否 | 与 case.json 不一致时以 case.json 为准 |
| `task_understanding` | 建议 | 进 result.json 同名信封字段，供评审看任务理解 |
| `glossary[]` | 建议 | 见 §4；条目 schema 已在上表 |
| `segments[].sid` | 是 | 必须存在于索引 |
| `segments[].source` | 建议 | 与索引原文逐字比对（`source_verbatim`） |
| `segments[].target` | 是 | 空 → `〔待补〕`；含 `〔存疑〕` → 需 `uncertain=true` |
| `segments[].notes` | 建议 | 译法依据/取舍；进 `paragraph_pairs.jsonl` 与核验缺口说明 |
| `segments[].uncertain` | 否 | 默认 false；true 时该段计入 `coverage.uncertain` |
| `result_fields` | 否 | 契约字段优先取这里的值，再退回语义映射（见 §6） |
| `uncertainties` | 否 | 字符串或对象数组，进 result.json |

体积控制：单条 `source` 建议 ≤600 字符（整段原文由脚本入库，不必重复粘贴长段可省 token）。

---

## 6. result.json 契约回填

`output_contract` 的键**原样**出现在 `result.json` 顶层，不改名、不漏键。取值优先级：

1. `draft.result_fields[key]`（Agent 显式给值且非空）；
2. 按键名语义映射到本 Skill 产物（下表，前缀匹配、大小写不敏感）；
3. 契约声明为 array → `[]`；否则 `null`（并在 `degradations` 记 `contract_fields_null`）。

| 键名包含 | 回填内容 |
|---|---|
| `glossary` / `terminolog` / `术语` | 术语表（含 status、quote_verified、occurrences） |
| `coverage` / `completeness` / `覆盖` | 覆盖账本（total/translated/missing/skipped/uncertain/rate） |
| `audit` / `verif` / `check` / `核验` | 核验摘要 + 指标率 + fail 明细 |
| `evidence` / `locator` / `quote` / `证据` | 证据表（术语引文、段落证书、审计失败项，均带 locator） |
| `uncertain` / `pending` / `manual` / `不确定` | 不确定项与待人工确认项 |
| `translat` / `bilingual` / `pair` / `segment` / `对照` | 段落对数组（与 `paragraph_pairs.jsonl` 同源） |
| `status` / `state` / `状态` | 推导出的 status（禁用更乐观的覆盖） |
| `case` | `case_id` |
| `note` / `method` / `understanding` / `说明` | `task_understanding` |
| `language` / `lang` | 目标语言代码 |
| `output` / `artifact` / `file` | 产物路径表 |
| `source` / `input` / `material` | 材料清单（路径、类型、提取器、页数、字符数） |
| `summary` / `摘要` | 段落数/已译数/术语锁定数/审计通过数 |
| 其它 | `null` 或 `[]`，并记入 degradations |

若 `case.json` 坏掉，`salvage_case()` 会从原始文本抢救 `case_id` 与 `output_contract`
顶层键名（只取深度 1 的 `"key":`，不会把嵌套的 `"type"` 当成契约字段）。

---

## 7. 占位符与状态推导

三类占位符**语义不同、计数分开**，脚本按字面识别：

| 写法 | 含义 | 覆盖账本 |
|---|---|---|
| `〔待补:S012〕` | 还没译（缺工/超预算） | `missing` |
| `〔未译:S013:reference〕` | 按策略不译（参考文献/纯符号） | `skipped`（不计缺失） |
| `〔存疑:S014:术语待定〕` | 已译但不确信 | `translated` + `uncertain` |

状态推导（`audit.derive_status`）：

```
无段落 → insufficient_evidence（有材料）/ input_error（材料都读不到）
coverage_rate = 1.0 且 fail = 0 → answered
否则 → partial
```

`build --status` 只能取**更保守**的方向（`enforce_status`）：
`answered(3) > partial(2) > insufficient_evidence(1) > input_error(0)`，
请求等级高于推导等级会被拒绝并记 `status_note`；反之允许，用于"核验有 warn 未人工确认时
主动降级"。

`degradations` / `errors` / `uncertainties` / `pending_human` 的分工：

- `errors`：输入层故障（`case_json_missing`、`material_read_failed`、`input_dir_missing`）；
- `degradations`：能力边界（`draft_missing`、`segments_untranslated:27`、`audit_fail:4`、
  `contract_fields_null:1:xxx`、`builtin_pdf_extractor`、`two_column_split`）；
- `uncertainties`：内容层面不确定（术语译名未定、语义关系不敢断言）；
- `pending_human`：核验 warn 的可执行清单（检查项 + 段号 + 说明）。

---

## 8. 指标定义（都可机械复算）

| 指标 | 计算式 | 位置 |
|---|---|---|
| `coverage_rate` | 有实质译文的段数 / 总段数 | `rates.coverage_rate` |
| `coverage_rate_incl_skipped` | (译文段 + 策略跳过段) / 总段数 | `coverage` |
| `glossary_consistency` | locked 术语在出现段中命中锁定译名的次数 / 出现次数 | `rates.glossary_consistency` |
| `span_retention` | 1 − 缺失 span 数 / 原文 span 总数 | `rates.span_retention` |
| `negation_rate` | 保留否定标记的句子数 / 含否定的源句数 | `rates.negation_rate` |
| `hedge_rate` | 保留限定标记的句子数 / 含限定的源句数 | `rates.hedge_rate` |
| `quote_verbatim` | quote 逐字命中的术语条数 / 术语总条数 | `rates.quote_verbatim` |

复算方式：`build` 后重跑 `check`，两者 rates 应完全一致（同源同规则）；
`selfcheck` 会比对产物与索引的段数、契约键、locked 术语的 quote 命中。

---

## 9. 已知限制（写进结论时要带上）

1. **句级否定/限定检查是比例对齐的近似**：源句与目标句数不等时会错配，只作提示，
   不能当作"译文语义正确"的证明。
2. **内置 PDF 解析器**：只解 FlateDecode 文本层，复杂编码（Type0/CID、自定义 CMap）
   可能出乱码；此时 `text_quality` 报 `low_quality` 并降级，不猜内容。页号按 content
   stream 顺序估计，`source` 里会标 `builtin:*`。
3. **双栏检测是启发式**：靠 ≥3 字符连续空白槽 + 60% 覆盖；表格页、单栏窄版式可能漏判
   或误判，误判时 `warnings` 有记录，译文顺序需人工顺读确认。
4. **`eq_tag` 与括号数字同形**：`33(2): 145-158` 这类卷期号会被当成公式编号；因对
   原文/译文同一规则，不影响一致性判定。
5. **表格结构（列头/单元格）不重建**：只按文本流切段，表注可作为 `caption_table` 段落
   翻译，表体逐行内容按段落处理。
6. **术语译名优劣不由脚本判定**：脚本只判定"是否一致、是否有逐字证据"；译名是否学术
   妥当需评审判断，`basis` 字段就是留给这个判断的。
