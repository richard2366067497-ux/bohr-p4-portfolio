# checks.md — 六类台账口径、评分维度映射与字段字典

本文件回答三件事：机械检查到底查什么、会漏什么；每个评分维度对应哪个产物与哪个计数；
`result.json` 的字段与契约回填规则。口径变化时必须同步改这里，代码在 `scripts/audit.py`。

## 1. 六类台账：正则口径与误报边界

| 类别 | 抓什么 | 正负样本 | 误报边界（报告里必须保留的说明） |
|---|---|---|---|
| `term` | `expansion (ABBR)`、`ABBR (expansion)`、中文 `中文（ABBR）`；同一缩写多种展开；同一展开多种缩写；缩写先于定义使用 | 正：`fused deposition modelling (FDM)` 与 `FDM (fused deposition manufacturing)` | 只认括号写法；行文里"FDM 即熔融沉积"这类自由表述漏检 |
| `symbol` | `where X is …`、`式中 X 为 …`、`X =` 定义式；同符号多义、重复定义 | 正：同一 `L` 既指层高又指长度 | 不解析正文里的 `$X$` 数学块与希腊字母上下标 |
| `definition` | `X is defined as`、`X is/are defined as`、`X 定义为/是指/称为/记作` | 正：同一术语两处措辞不同的定义 | 长句改写、同义改写不触发；定义散落在图注时可能漏检 |
| `numbering` | `Figure/Fig./图 N`、`Table/表 N`、`Equation/Eq./式 (N)`；题注行（行首 `Figure 1.` / `表 1：`）；重号、断号、引用但无题注 | 正：正文引 `Figure 3`，只有 `Figure 1` 题注 | 合并题注（`Figure 1 and 2.`）只算 1；子图 `(a)(b)` 不计入 |
| `citation` | `[n]`（含 `3-5` 区间）、`(Author, 2020)`、文献表条目 `[n]`/`n.`、占位符 `[?]`/`TODO`/`待补` | 正：正文 `[5]` 而文献表无 5 | 无文献表时只报告"无法核对"，绝不推断缺失条目；作者年制不做完整比对 |
| `claim` | 含结论动词/情态词的句子（increase、improv*、表明、说明、显著…）；极性由否定词判定；是否带量值；跨材料同主题异极性（词重叠 ≥0.45 且共享 ≥4 tokens） | 正：结果章"显著提高"，讨论章"未见提高"且主语相同 | 否定词判定是近似；改写幅度大的句子会漏；不做蕴含判断 |
| `unit` | `数值 + 单位` 的量纲归并（`mm/min` ≈ `mm·min-1` ≈ `mm min-1`）；同一量纲多写法 | 正：同一篇里 `45.2 MPa` 与 `45.2MPa`、`mm/min` 与 `mm min^-1` | 只归一写法，**不做单位换算**，也绝不静默改数 |

统一约定：

- 台账每行都带 `locator`，必要时带 `quote`；`basis: computed` 表示"候选线索"。
- 报告里 `computed` 与 `agent_review` 分区，机械清单不作为科学结论。
- 空行 = 该模式未命中，不等于"没有问题"。

## 2. 评分维度 → 产物 → 可复算计数

| 维度（题面分值） | 主要产物 | 计数落点 |
|---|---|---|
| 实际效果·任务完成度 15 | `revised_manuscript.md`、`revision_records.json` | `coverage.effect.targets_done/total`、`annotations_applied` |
| 实际效果·正确性 15 | `evidence_map.json`、`consistency_report.md` | `verbatim=true` 条数、`reject=0`、`degradations=0` |
| 实际效果·完整性 5 | `preserved_facts.json` | `total - not_preserved`、`line_counts_before/after` |
| 实际效果·可核验 5 | `change_log.json`、`versions/*` | `rollback_equals_v1`、`reapply_equals_v2`、每块 `sha` |
| 使用增益·质量 15 | `consistency_tables.json` | `counts`（六类命中数）、`agent_findings` 数 |
| 使用增益·效率 5 | `check_report.json`、`show --find` | 一次索引覆盖的块数、`manual_passes_avoided` 说明 |
| 使用增益·可验证 5 | `run_manifest.json`、`self_check.json` | 输入/输出哈希、`selfcheck` 通过项 |
| 创新 15 | `revision_records[].affects`、报告第 3/4 节分区 | `impact_backlinks` 数、`basis` 分区 |
| 可靠 10 | `operation_receipts.json` | `fault_injections` 5 项状态、降级计数 |
| 生态 10 | `SKILL.md` + `references/` | 命令数、规则表数量、文档清单 |

`coverage_matrix.json` 是这些计数的汇总，属自查表，不是自评分。

## 3. `result.json` 字段字典

信封字段（总是存在）：

| 字段 | 类型 | 含义 |
|---|---|---|
| `case_id` | str | 案例标识，来自输入，原样 |
| `status` | str | `ok` / `partial` / `insufficient_evidence` / `input_error` |
| `deliverable` | obj/null | 主产物的路径、字符数、哈希、注记数、是否可编辑、原块是否零改动 |
| `preserved_facts` | list | 源内容单元清单：`unit_id/type/locator/chars/sha/preserved` |
| `preserved_summary` | obj | 计数汇总（总数、未保真数、按类型计数、行数前后） |
| `evidence_map` | list | 每条：`claim_id/kind/target_id/locator/quote/verbatim/sha256_16`（+ findings） |
| `change_log` | list | 每条：`change_id/target_id/action/locator/original_quote/annotation/reason/reversible/affects` |
| `annotations` | list | 已落位注记（含 `generated_by`、`needs_review`） |
| `workorder_execution` | obj | `workorder_id/mode/targets[]/requirements[]/requirements_met/boundaries` |
| `consistency` | obj | `counts/ledgers/computed_findings/agent_findings/basis_note/impact` |
| `coverage` | obj | 五维覆盖矩阵 |
| `sources` | list | 材料清单：`rel/kind/status/chars/sha256_16/note` |
| `uncertainty` | list | 逐条不确定性（启发式定位、缺条件、兜底等） |
| `pending_human` | list | `item/reason/action/severity` |
| `errors` | list | 真实错误与失败的不变量 |
| `degradations` | list | 降级说明（未解析格式、兜底注记、截断…） |
| `changes` | list | 本轮运行造成的改动摘要 |
| `contract_fields` | list | 本次回填的契约键名（顺序同 `output_contract`） |
| `runtime` | obj | skill/version/python/utc/elapsed/budget/network |

契约回填规则：

1. `output_contract` 支持三种形态：字典（取全部键）、字段名列表、带 `field`/`name`/`key`
   的列表；也接受逗号分隔字符串。
2. 每个键**原名回填**：先精确匹配同名字段，再按语义族匹配
   （`deliverable|manuscript` → `deliverable`；`evidence*` → `evidence_map`；
   `change|diff|revision*log` → `change_log`；`workorder|receipt` → `workorder_execution`；…）。
3. 匹配不到 → `null`；键名像列表（fact/evidence/log/record/list/items/…）→ `[]`。
4. 信封字段永远补齐，且**不得覆盖**契约键的原名。
5. `contract_fields` 记录回填了哪些键，`selfcheck` 逐键复查是否仍在。

## 4. 审查自查表（人工）

- [ ] 每个 target 恰一条注记，`locator` 与 `anchor_quote` 能对上原文块。
- [ ] 注记里有"条件/局限"，不是泛泛的写作建议。
- [ ] `findings[]` 非空；六类里至少覆盖材料中真实存在的类别。
- [ ] 报告第 3 节与第 4 节分区清楚，未把机械清单写成结论。
- [ ] 数值冲突两边都写了 locator + 引文，没有替作者裁决。
- [ ] `preserved_facts` 全 `true`；`rollback_check.json` 两个 `true`。
- [ ] `pending_human` 覆盖：缺材料、兜底注记、无法确认项。
- [ ] `result.json` 契约键齐全、键名未改、`case_id` 原样。

## 5. 维护与已知失败模式

- 只改一个口径时，同步改：本文件表格 → `scripts/audit.py` 常量 → 跑 `check` 看计数变化。
- 已知失败模式：把"源论文分章工作稿"当完整学位论文宣称完成；漏第二个 target；
  只做词频清单当科学核验；改动未指定段落；伪造回执；长文档截断后仍称全文完成；
  堆第三方依赖导致加载失败。本 Skill 对这六类都有显式降级或拒绝路径。
