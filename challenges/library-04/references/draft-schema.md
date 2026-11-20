# `draft.json` 字段字典与契约映射

工作稿是唯一的判断载体：脚本只把材料切成带 locator 的段落并校验，判断全部写在这里。路径 `/app/work/draft.json`（也可 `--draft` 指定）。

## 1. 顶层结构

```json
{
  "case_id": "与 /input/case.json 一致",
  "library": {"documents": [], "families": [], "duplicates": [], "repair_actions": []},
  "questions": [],
  "exhibits": [],
  "version_witness": [],
  "search_scope": {},
  "conflicts": [],
  "limitations": [],
  "uncertainty": []
}
```

## 2. `library.documents[]`（每个输入文件一条）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `doc_id` | str | ✓ | `D1..Dn`，必须来自 `show` 的登记表 |
| `family_id` | str | | 同一资料的版本家族，`show --families` 给出初值 |
| `version` | str | ✓ | 该文件的版本标识（`v1`/`v2`/`preprint`/`2021-05-01`），回答"哪一版"必须用到 |
| `version_rank` | int | | 家族内新旧排序（大 = 新） |
| `role` | str | ✓ | `authoritative`/`superseded`/`duplicate`/`supplementary`/`unreadable`/`unrelated`/`unknown` |
| `title` | str | | 从原文读到的标题（不用文件名臆测） |
| `metadata` | obj | | `authors`/`year`/`doi`/`venue` 等；不可得留空字符串 |
| `notes` | str | | 版本说明、勘误、别名、权限问题 |

## 3. `library.families[]` / `duplicates[]` / `repair_actions[]`

```json
{"family_id":"F1","canonical_doc":"D3","members":["D1","D3"],
 "basis":"文件名 _v2 + 文本相似度 0.97 + 管理性说明 D3 supersedes D1"}
```
```json
{"keep":"D3","drop":["D1"],"basis":"sha256 相同（字节一致）"}
```
```json
{"action_id":"A1","op":"dedupe","target":"D4","to":"","reason":"与 D2 字节一致",
 "evidence":["E7"],"reversible":true}
```
`op` ∈ `rename|move|dedupe|tag|relink|flag|quarantine|index|repair`。动作只记录、不执行：脚本不会改动 `/input` 里的任何文件。

## 4. `questions[]`

| 字段 | 说明 |
|---|---|
| `qid` | 与 `show` 打印的一致（`Q1..`） |
| `question` | 问题原文 |
| `answer_draft` | 答案正文，**逐句带 `[E#]`**；不能引用的句子不要写 |
| `issues[]` | 1–5 个争点 |

`issues[]` 字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `issue_id` | str | `Q1-I1`，全库唯一 |
| `issue_text` | str | 一个争点只问一件事 |
| `verdict` | str | `supported`/`contradicted`/`contradicted_with_reason`/`insufficient`/`out_of_scope` |
| `positive_exhibits` | [str] | 支持该争点的 exhibit_id |
| `counter_exhibits` | [str] | 反证 exhibit_id |
| `missing_evidence` | str | `insufficient`/`out_of_scope` 必填：缺哪类证据 |
| `reasoning` | str | 判断依据；`contradicted_with_reason` 必填（≥20 字） |

## 5. `exhibits[]`

| 字段 | 必填 | 说明 |
|---|---|---|
| `exhibit_id` | ✓ | `E1..En`，全库唯一 |
| `doc_id` | ✓ | 登记表里的 D 编号 |
| `version` | ✓ | 与 `library.documents[doc_id].version` 一致 |
| `locator` | ✓ | `show` 打印的定位：`p3#para7`（PDF 页）、`t1#para5`（文本）、`t1#row12`（表格行）、`s1#para3`（docx）、`sl2#para1`（PPT 页） |
| `quote` | ✓ | 逐字引文（≥6 字符，脚本按归一化子串判定） |
| `kind` | | `fact`/`number`/`method`/`conclusion`/`metadata`/`version_note` |
| `polarity` | | `support`/`counter` |
| `page_printed` | | 原文印刷页码（PDF 有页脚页码时填，便于人工对照） |
| `page_physical` | | 物理页序 |
| `section` | | 章节名（Methods/Results/附录/说明） |

## 6. `version_witness[]`

```json
{"family_id":"F1",
 "versions":[{"doc_id":"D1","version":"v1",
   "claims":[{"field_or_claim":"sample_size","statement":"n=40","locator":"p2#para5","exhibit_id":"E3"}]},
  {"doc_id":"D3","version":"v2",
   "claims":[{"field_or_claim":"sample_size","statement":"n=52","locator":"p3#para2","exhibit_id":"E4"}]}],
 "conflicts_between_versions":[{"claim":"sample_size",
   "v_a":{"doc_id":"D1","statement":"n=40"},"v_b":{"doc_id":"D3","statement":"n=52"},
   "likely_cause":"v2 补做样本并更新 Methods"}]}
```
用途：回答"哪一版说的"时逐版取证，避免版本串味（把 v1 的数值安到 v2 上）。

## 7. `search_scope{}`（按 qid）

```json
{"Q2":{"files":["D1","D3","D5"],"keywords":["sample size","n =","例数"],
  "synonyms":["受试者","participants","cohort"],"chunks_scanned":37,
  "not_found_note":"三份材料的 Methods 均未报告该指标，只报告了终点值"}}
```
`insufficient`/`out_of_scope` 必须同时有 `files` 与 `keywords`；`chunks_scanned` 建议填（体现检索强度）。

## 8. `conflicts[]`

```json
{"conflict_id":"X1","topic":"处理组效应方向",
 "side_a":{"doc_id":"D5","exhibit_id":"E9","statement":"升高"},
 "side_b":{"doc_id":"D7","exhibit_id":"E12","statement":"无显著变化"},
 "likely_cause":"version|condition|method|sample|unknown",
 "handling":"不取平均；按剂量与时长分层报告"}
```
`likely_cause` 取值固定，便于统计；无法归因写 `unknown` 并在 `limitations` 说明。

## 9. `output_contract` 语义映射（build 使用）

| 契约键匹配 | 回填内容 |
|---|---|
| `case`/`id` | `case_id` |
| `status` | `ok`/`partial`/`failed` |
| `index`/`inventory`/`manifest`/`library`/`file_list`/`files` | 文件登记表（含 sha256/mode/readable/family/version/role） |
| `duplicate`/`dedup` | 重复组（keep/drop/basis） |
| `version`/`revision`/`lineage`/`supersede`/`history` | 版本证人表 |
| `metadata`/`meta_` | 每文件标题与元数据 |
| `permission`/`access`/`readable` | 路径、权限位、可读性 |
| `answer`/`qa`/`question`/`finding` | 问答（含每问争点与裁决） |
| `exhibit`/`evidence`/`quote`/`citation` | 证据登记册（含核验状态） |
| `conflict`/`contradict` | 冲突清单 |
| `not_found`/`missing`/`gap`/`unsupported` | 缺证清单（缺什么 + 检索范围） |
| `repair`/`recover`/`action`/`log`/`skip`/`fail` | 整理与恢复动作 |
| `coverage`/`stat`/`count` | 覆盖统计（文档/问题/争点/证据/裁决分布/引文命中率） |
| `summary`/`report`/`narrative` | `report.md` 正文（截断 12000 字符） |
| `method`/`repro`/`procedure` | 方法说明 |
| `artifact`/`output_file` | 产物清单 |
| `uncertain`/`limitation` | 不确定性 |
| `pending`/`human` | 待人工确认项 |
| `source`/`provenance` | 来源与哈希 |

类型处理：契约声明为数组/对象/字符串/数值时按声明强制转换；无法匹配内容的键回填 `null`/`[]`/`{}` 并写入 `degradations`，不改键名、不丢键。

## 10. 最小可用工作稿（骨架）

```json
{"case_id":"demo-01",
 "library":{"documents":[{"doc_id":"D1","version":"v1","role":"authoritative"}],
            "families":[],"duplicates":[],"repair_actions":[]},
 "questions":[{"qid":"Q1","question":"样本量是多少？","answer_draft":"样本量为 40 例 [E1]。",
   "issues":[{"issue_id":"Q1-I1","issue_text":"研究纳入了多少受试者","verdict":"supported",
              "positive_exhibits":["E1"],"counter_exhibits":[],"missing_evidence":"",
              "reasoning":"Methods 明确报告最终分析 40 例"}]}],
 "exhibits":[{"exhibit_id":"E1","doc_id":"D1","version":"v1","locator":"p2#para5",
              "quote":"A total of 40 participants were analysed.","kind":"number","polarity":"support"}],
 "version_witness":[],"search_scope":{"Q1":{"files":["D1"],"keywords":["participants","n"],
   "synonyms":["受试者"],"chunks_scanned":12,"not_found_note":""}},
 "conflicts":[],"limitations":[],"uncertainty":[]}
```
