# 判定规则表（裁决 / 证据 / 版本 / 去重 / 覆盖）

本文件与 `scripts/lib_check.py` 的检查项一一对应。`check` 报的每个错误码都在第 6 节有修法。

## 1. 争点（issue）拆分规则

| 问题类型 | 典型问法 | 拆成哪些争点 |
|---|---|---|
| 事实型 | "X 的取值/结论是什么" | ①事实是否存在 ②数值/表述是什么 |
| 比较型 | "A 与 B 谁更高/差异多少" | ①A 的取值 ②B 的取值 ③两者是否可比（口径/条件） |
| 方法型 | "用了什么方法/参数" | ①方法名称 ②关键参数/设置 ③适用范围 |
| 溯源型 | "哪一版这么写/哪个文件是原始版" | ①版本身份（哪份是哪版） ②该版的具体陈述 ③版本差异及原因 |
| 存在性型 | "库里有没有 X 的依据" | ①是否存在可读证据 ②证据定位 ③若无，缺什么类型证据 |

硬性：一个争点只问一件事；能由 1–3 条 exhibit 支持或推翻；争点编号 `QID-I1..I5`，全库唯一。每个问题 1–5 个争点，超过 5 个说明问题本身需要再拆。

**写成命题，不要写成疑问**：`issue_text` 是可判定的一句话，`verdict` 判它。比较型问题尤其要小心——问"两版是否一致"，命题应写"两版不一致（v1=40，v2=52）"并判 `supported`；若把疑问句直接当命题，会出现"证据显示不一致 → 判 contradicted"的自相矛盾。

## 2. exhibit（证据）规则

1. `quote` 必须逐字来自该 doc 的抽取文本。脚本用"归一化后子串"判定：统一全角/半角、弯引号、连字符、多余空白后必须完全命中。允许归一化不等于允许改写：删词、改数、翻译、拼接都会失败。
2. `locator` 必须指向**真正含这句引文**的段落。仅"引文存在 + locator 乱填"会报 `locator_mismatch`——这是本题最容易被评审抓住的失败（引用指向的文件/段落/版本对不上）。
3. `version` 必须与 `library.documents[doc_id].version` 一致。同一段文字可能在两版中都存在，此时按你**实际读的那一版**登记，并在 `reasoning` 说明是哪一版。
4. `kind` 取值：`fact`（事实陈述）、`number`（数值/统计量）、`method`（方法/参数）、`conclusion`（作者结论）、`metadata`（标题/作者/年份/DOI/期刊）、`version_note`（管理性版本说明：勘误、替代、别名、作废）。
5. `polarity`：与争点结论同向 → `support`；相反或来自另一版本且结论冲突 → `counter`。反证也必须逐字、也必须带 locator。
6. 一条 exhibit 只服务一个方向；同一句既能支持又能推翻时，拆成两条并在 `reasoning` 说明语境差别。

## 3. 裁决（verdict）判据

```
命题被证据支持，无反证                     → supported
有支持证据，有反证，但反证来自被取代版本     → contradicted_with_reason（写清"以 v2 为准，v1 已作废"）
有支持证据，有反证，无法判断哪方成立        → insufficient（写缺什么：版本裁定依据/第三方数据）
只有反证，无支持证据                      → contradicted
材料根本没涉及该主题                      → out_of_scope（写检索范围）
文件不可读/无文本层，无法取证              → insufficient（缺"可读文本层或 OCR"）
```

禁止事项：把 `insufficient` 写成模糊的"可能/大概"；把 `conflicting` 的两侧数值取平均；用常识补齐材料没写的数值。

## 4. 版本与去重规则

脚本提供的四类线索（`init` 打印、`index.json.families`）：

| 线索 | 字段 | 含义 |
|---|---|---|
| 哈希一致 | `duplicates[].basis = sha256 identical` | 字节级同一文件（重复副本/别名副本） |
| 文本相似 | `families[].basis = text_similarity_0.xx` | 内容近乎相同，可能仅格式/OCR/页眉差异 |
| 版本标记 | `docs[].version_hint = ["v2","final",...]` | 文件名里的 `v1/v2/rev/draft/preprint/final/修订/终稿/2021-05-01` |
| 管理性说明 | `admin_notes[]` | 正文里"以 X 为准 / Y 已作废 / Z 是别名 / 请勿使用旧版"这类段落，带 locator 可直接引用 |

判定顺序建议：先看管理性说明（作者/管理员明确说了算）→ 再看版本标记与文件日期 → 再看内容差异（样本量、结论方向）。三者冲突时，裁决写 `contradicted_with_reason` 并说明取舍依据。

去重判定：`sha256` 相同即可判重复；哈希不同但相似度 ≥ 0.96 视为同一内容的不同副本；0.72–0.96 归入同一家族但**不判重复**（可能是修订版），要进 `version_witness` 记录差异。`check` 对相似度 < 0.90 且哈希不同的"去重"声明报 `dedupe_unsupported`。

## 5. 六维覆盖规则（对应评分"完整性"）

| 维度 | 必须落到产物 | 判据 |
|---|---|---|
| 文件类型 | `library_index.csv` 的 `kind` 列 | 每种实际类型都出现，含 pdf/docx/xlsx/csv/md/txt/pptx |
| 元数据字段 | `library.documents[].metadata` | 至少覆盖 title/year/authors/doi/venue 中可得的项；不可得写空并说明 |
| 目录层级 | `library_index.csv` 的 `rel_path` | 保留相对路径，报告给出层级分布 |
| 重复文件 | `library.duplicates` | 每个重复组都有 keep/drop + 依据 |
| 版本差异 | `version_witness` + `conflicts.json` | 多成员家族逐版记录主张；冲突列双方 exhibit |
| 权限与来源 | `library_index.csv` 的 `mode`/`readable` + `sources` | 不可读/无权限文件必须显式标注 |

## 6. 错误码与修法

| 码 | 触发条件 | 修法 |
|---|---|---|
| `no_draft` | 工作稿不存在 | `show --template` 生成骨架后填写 |
| `draft_json_invalid` | JSON 解析失败 | 去尾逗号/注释/中文引号 |
| `empty_draft_sections` | 既无 exhibits 也无 questions | 至少产出一个问题的争点 |
| `exhibit_missing_id` / `exhibit_duplicate_id` | 编号缺失/重复 | 用 E1..En 唯一编号 |
| `doc_unknown` | 引用了不存在的 doc_id | 用 `show` 打印的 D1..Dn |
| `quote_not_found` | 引文不在该 doc 文本中 | 从 `show --doc` 逐字复制（可用 `--emit` 生成） |
| `locator_missing` | 无 locator | 补 `p3#para7` 形式 |
| `locator_mismatch` | 声称的段落不含该引文 | 改成报错里给出的真实 locator |
| `version_mismatch` | exhibit.version 与登记表不一致 | 对齐登记表，或先改 `library.documents` |
| `verdict_invalid` | 枚举外取值 | 五个取值之一 |
| `supported_without_evidence` | 裁决有方向但无证据 | 补 exhibit 或改 `insufficient` |
| `contradicted_without_counter` | contradicted 类裁决无反证 | 登记 counter exhibit |
| `counter_ignored` | 有 counter 却判 supported | 改 `contradicted_with_reason` 并写 reasoning |
| `reasoning_thin` | 取舍理由 < 20 字 | 说明为什么采纳一方（版本/条件/口径） |
| `empty_draft_sections` | 工作稿既无 exhibits 也无 questions | 至少给一个问题立案 |
| `case_json_repaired` | case.json 残缺，脚本救回首对象 | 核对回填的契约键 |
| `no_materials` | 输入无可用材料 | 报空库，不造清单 |
| `insufficient_no_scope` | 缺 `missing_evidence` 或 `search_scope[qid].files/keywords` | 两者都补齐 |
| `question_missing` | 输入问题未出现在 draft | 补 qid 与争点 |
| `question_no_issues` | 问题下没有争点 | 拆 1–5 个争点 |
| `issue_duplicate_id` | 争点编号重复 | 改唯一编号 |
| `conflict_incomplete` | 冲突任一方无 doc/exhibit | 补齐双方 |
| `dedupe_unsupported` | 去重声明缺乏哈希/相似度支持 | 改判或补依据 |
| `number_unanchored` | 答案里的数值不在被引引文中 | 补引文或改数值 |
| `contract_type_coerced`（build） | 回填类型与契约声明不一致 | 调整内容结构；已按声明强制转换 |
| `contract_key_missing`（selfcheck） | 契约键缺失 | 检查 `output_contract` 键名是否被改写 |

提示级（`note`）：`orphan_exhibit`、`unaddressed_duplicate`、`unreadable_unflagged`、`doc_not_classified`、`role_unknown`、`qid_unknown`、`exhibit_no_kind`、`version_conflict_no_cause`、`action_op_unknown`。

## 7. 降级判定表

| 现象 | 判据 | 产物处置 |
|---|---|---|
| 扫描件无文本层 | 抽取文本为空或 `no_text_layer` | `role=unreadable`，相关问题 `insufficient`，缺"可读文本层/OCR" |
| 权限不足 | 读取抛错 | `readable=false`，`repair_actions` 记 `flag`/`quarantine` |
| 无 `pdftotext` | 引擎显示 `builtin-zlib` | locator 用 `sN` 块号，说明页号不权威 |
| 表格型材料 | 引擎 `xlsx-xml`/`csv` | locator 到行（`t1#row12`），引用时把关键短语一起抄 |
| 无问题清单 | `question.source=derived_from_instruction` | 标注"派生问题"，并在 degradations 说明 |
| 材料与问题无关 | 检索无命中 | `insufficient` + 检索范围，不硬答 |

## 8. 复跑一致性要求

同一输入重跑必须得到同一 locator 与同一引文。因此：不改原始材料、不按文件修改时间排序、`doc_id` 按相对路径字典序分配（`init` 已固定），版本判定依据必须写在 `families[].basis` 里。
