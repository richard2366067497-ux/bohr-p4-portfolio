# 字段字典与规范（field-dictionary.md）

配套 `patent-search-dossier` v1.0.0。本文件是**人与脚本共用的口径表**：工作稿 `draft.json` 写什么、
六件产物里字段叫什么、号码怎么规范化、状态与许可怎么分级。改口径优先改这里，再改脚本。

## 1. 工作稿 `draft.json` 字段字典

| 字段 | 类型 | 必填 | 取值 / 说明 |
|---|---|---|---|
`query` | object | ✔ | `kind` ∈ `number｜topic｜both`；`statement` 检索式或意图原文；`targets` 号码数组（number 类必填）；`scope` 覆盖的检索面；`excluded` 显式排除的对象与原因 |
`number_decisions[]` | list | ✔ | `raw` 原文号码；`norm` 规范化（**必须与脚本一致**）；`doc_type`；`parse_status` ∈ `parsed｜ambiguous｜unparsed`；`decision` ∈ `confirm｜reject｜ambiguous｜unreviewed`；`note` |
`patent_objects[]` | list | ✔ | `patent_id`（P1…）；`number_norm`；`title`；`assignee`；`filing_date`；`priority_date`；`ipc[]`；`screening` ∈ `include｜exclude`；`why`；`evidence[]`（`source_id`+`locator`+`quote`） |
`field_extraction[]` | list | ○ | 逐字段抽取：`patent_id`、`field`、`value`、`source_id`、`locator`、`quote` |
`family_edges[]` | list | ○ | `from`/`to`（patent_id）；`link_type` ∈ `observed｜shared_priority｜continuation｜divisional｜pct_national_phase`；`family_scope` ∈ `simple｜extended`；`evidence_locator`（`M#/p#`）；`quote`；`claim_scope_note` |
`status_entries[]` | list | ✔ | `patent_id`；`value`（枚举见 §3）；`as_of`（`YYYY-MM-DD`）；`source_kind`（枚举见 §3）；`source_id`；`locator`；`needs_official_verification`（布尔）；`note` |
`claims_versions[]` | list | ○ | `patent_id`；`version`（v1/v2）；`quote` 逐字；`locator`；`ocr_boundary`（无边界写 `none`）；`scope_explained`（默认 false） |
`technical_papers[]` | list | ○ | `paper_id`；`title`；`doi`；`year`；`relevance` ∈ `high｜medium｜low`；`why_relevant`；`source_id`；`locator`；`quote` |
`license_decisions[]` | list | ✔（材料含许可表时） | `source_id`；`source_name`；`tier` ∈ `green｜yellow｜red`；`display_scope`；`degrade_plan`；`excluded_from_output`（red 必为 true）；`reason` |
`boundaries[]` | list | ✔（≥3 条） | `type`（§6 枚举）；`item`；`detail`；`impact` |
`conflicts[]` | list | ○ | `item`；`sources[]`；`handling` |
`gaps[]` | list | ○ | `item`；`why`；`needed_by` |
`status_note` | string | ○ | 完成度与未完成部分的自我说明（进 `dossiers.md` §9） |

## 2. 号码规范化（脚本确定性执行，`number_registry.json` 记录规则链）

| 输入 | `norm` | `doc_type` | 说明 |
|---|---|---|---|
`US 10,123,456 B2`｜`US10123456B2` | `US10123456B2` | us_grant | 授权号 |
`US 2017/0123456 A1`｜`US20170123456A1` | `US20170123456A1` | us_publication | 11 位且前 4 位为 1960–2035 年 → 公开号 |
`US 15/234,567` | `US15234567` | us_application | 含 `/` → 申请号（系列码 + 6 位序号） |
`US 62/132,456` | `US62132456` | us_application | 临时申请（优先权基础），**不是授权号** |
`WO 2018/123456 A1`｜`WO2018123456` | `WO2018123456A1`｜`WO2018123456` | pct_publication | WO + 年份 + 序号 |
`PCT/US2018/012345` | `WO2018012345` | pct_application | PCT 前缀 → WO 号，原国别记入规则链 |
`EP 3 456 789 A1` | `EP3456789A1` | ep_publication | 国别 + 7 位序号 |
`CN 110123456 A` | `CN110123456A` | national_publication | 其他国别按 kind code 分 publication/grant |
`10,123,456`（无国别） | `US10123456` | us_grant | 位数推断 → `parse_status=ambiguous`，附 `inferred_country:US` |
`JP 2019-123456 A` | `JP2019123456A` | national_publication | 保留年份在序号中 |

规则顺序：`strip_separators`（NFKC + 去空格/逗号/点/连字符） → `cc:*`（国别前缀） →
`kind:*`（尾部 kind code，剥离后剩余长度须 ≥5） → 位数判类型 → `inferred_country:*`（无国别推断）。
`parse_status`：`parsed`（国别与类型都确定）/ `ambiguous`（靠位数或国别推断）/ `unparsed`（位数不足或无语境）。

**纪律**：公开号、申请号、授权号、优先权号各自登记，不互相冒充；同一数字不同文书类型算不同号码；
无法解析保留原串并进 `boundaries.metadata_missing`。

## 3. 法律状态：取值枚举与来源分级

`value` 枚举：`unknown`｜`granted`｜`pending`｜`expired`｜`abandoned`｜`withdrawn`｜`rejected`｜`not_in_force`｜`revoked`。

| `source_kind` | 含义 | 结论强度 | 强制字段 |
|---|---|---|---|
`official_register` | 官方登记页/官方抄录 | 可直接陈述（仍需 `as_of`） | `as_of`、`source_id`、`locator` |
`facsimile_ocr` | 影印件 OCR | 仅历史快照 | `needs_official_verification=true` |
`observed_link` | 观察到的链接页/二手页 | 仅线索 | `needs_official_verification=true` |
`aggregator` | 聚合站/转载 | 仅线索，`confidence=low` | `needs_official_verification=true` |

纪律：① 材料没有官方登记 → `value=unknown`，**不得推断"已授权/已失效"**；② `as_of` 用查询日或材料标注日；
③ 同一专利出现两个不同状态 → 写 `conflicts[]` 并进 `boundaries`，不擅自二选一；
④ 影印件上的 `(45) Date of Patent` 只说明当年授权公告，不等于现行有效性。

## 4. 同族口径

| `family_scope` | 判据 | 允许的表述 |
|---|---|---|
`simple` | 材料给出相同优先权号/日期 | "同优先权，可推定简单族" |
`extended` | 仅有 observed 链接（续案/分案/指定国） | "按 observed 链接归组，不推定权利要求等同" |
`not_exhaustive` | 恒为 `true` | "本族可能不完整" |

族边必须有 `evidence_locator` + 逐字 `quote`；关键词命中 ≠ 同族；族内范围差异只按可见证据陈述。

## 5. 许可分级模板（`license_gate.md` 表头与降级句）

表头：`| 来源 | 库名/版本 | 分级 | 可展示字段范围 | 降级方案 | 排除出主结果 | 依据 |`

| 分级 | 判据 | 可做 | 降级方案（可直接抄） |
|---|---|---|---|
`green` | 材料明确允许检索与展示 | 引用原文、展示字段 | — |
`yellow` | 内部使用/有限展示/未声明 | 引用结论与字段名 | "仅给结论 + `source_id/locator`，不给长段原文" |
`red` | 需登录/受限/保密/禁止再分发 | 仅登记已排除 | "不抓取、不引用；记录已排除原因与所需授权" |

材料未声明许可 → 按 `yellow` 处理并写入 `gaps`（`why=来源许可未声明`）。red 来源的原文一律不进主结果。

## 6. 边界类型字典（`boundaries[].type`）

| type | 触发条件 | 示例句（可直接改写） |
|---|---|---|
`legal_status_unknown` | 任一状态为 unknown | "材料未提供官方登记页，P1/P2 状态保持 unknown，不得用于有效性判断。" |
`family_not_exhaustive` | 存在族边 | "仅观察到 N 条链接，族可能不完整。" |
`ocr_merged_page` | 材料含影印件/合并页 | "第 4/5 页 OCR 合并，claim 4 截断，未纳入摘录。" |
`claim_scope_unexplained` | 只摘录未解释 | "仅摘录权利要求原文，未做范围解释或等同判断。" |
`patent_vs_paper_scope` | 同时检索专利与文献 | "专利按号码/族定位，文献按 DOI/主题匹配，未混排排序。" |
`license_restricted` | 存在 yellow/red | "商业库导出行标注禁止再分发，未抓取未引用。" |
`metadata_missing` | 字段缺失 | "EP 成员缺生效国与审查状态字段。" |
`coverage_gap` | 检索面未覆盖 | "未获得完整同族表，族结论限于 observed 范围。" |

## 7. 产物字段

- `number_registry.json`：`entries[]{raw,norm,country,kindcode,serial,year,doc_type,parse_status,decision,rules[],located_at[],context}` + `counts` + `rule_version`。
- `family_graph.json`：`nodes[]{id,number_norm,title}`、`edges[]{from,to,link_type,family_scope,evidence_locator,quote,claim_scope_note}`、`works[]{work_id,members,family_scope,not_exhaustive,claim_scope_note}`。
- `status_provenance.csv`：`patent_id,status_value,as_of,query_date,source_kind,source_id,locator,confidence,needs_official_verification,note`。
- `license_gate.md`：分级表 + 被排除数据与原因 + 未声明许可的来源 + 边界。
- `boundary_log.json`：`entries[]{index,type,item,detail,impact,source}`、`by_type{}`、`conflicts[]`、`gaps[]`。
- `result.json`：`case_id`、`status`、`skill`、`deliverable`、`output_contract`（**原样回填全部键**）、`number_registry`、`family_graph`、`status_provenance`、`claims_versions`、`technical_papers`、`license_gate`、`boundary_log`、`candidates`、`queries`、`evidence_map`、`coverage`、`counts`、`risk_register`、`summary`、`sources`、`conflicts`、`gaps`、`assumptions`、`errors`、`degradations`、`runtime`、`artifacts`。

## 8. 检索式模板

| 类型 | 模板 | 说明 |
|---|---|---|
号码式 | `(US10123456B2 OR family:US10123456B2)` | 先定位号，再按族扩展 |
主题式 | `("sulfide solid electrolyte" OR "Li2S-P2S5") AND IPC:H01M10/0562` | 关键词 + 分类号组合，写清同义词 |
申请人式 | `pa:"Example Energy" AND ipc:H01M10/05` | 竞品监控 |
引证式 | `cited_by:US10123456B2` / `cites:US10123456B2` | 前后向引证，区分方向 |
文献式 | `doi:10.1016/...` 或 `"interfacial stability" AND sulfide` | 技术文献与专利分开检索、分开排序 |

## 9. 常见错误（`check` 会直接报）

1. `norm` 自己改写（去掉 kind code、补零）→ R2 不一致。
2. 把公开号 `US2018/0123456A1` 当授权号陈述保护范围。
3. 状态写 `granted` 但来源是聚合站 → R6 风险；缺 `needs_official_verification` → R6 错误。
4. 引文改写/拼接（OCR 噪声也照抄）→ R4 未命中。
5. 关键词命中两件不同专利即当作同族 → R7 无 `evidence_locator`。
6. 漏 `boundaries` → R11 错误；漏 `license_decisions` 分级 → R10 错误。
