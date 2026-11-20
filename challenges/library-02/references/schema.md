# 字段字典与枚举（research-file-locator 1.0.0）

三个数据面：**输入** `case.json`、**中间** `index.json` 与 `draft.json`、**输出** `result.json`。改字段时先改本文件，再改脚本，最后重跑 `selfcheck`。

## 1. 输入 case.json（按语义识别，不假设键名）

| 语义 | 接受的键名 | 说明 |
|-|-|-|
| 案例标识 | `case_id` `caseid` `case_key` `id` | 原样回填进 `result.json.case_id` |
| 输出契约 | `output_contract` `contract` `output_contracts` `输出契约` | dict（键名+占位值）或 list（键名 list / `{name}` list）；全部键原样出现在结果顶层 |
| 任务说明 | `task_instruction` `instruction` `task` `prompt` `任务说明` | 仅作上下文，不当作答案 |
| 材料根 | `library_root` `library` `corpus_root` `materials_root` `root` | 相对 `/input` 或绝对路径；缺失则依次试 `library/`、`artifacts/`、`files/`、`/input` 全树 |
| 文档清单 | `documents` `docs` `files` `library` `materials` `file_list` `资料清单` | list[dict] 或 dict{id: dict/str} |
| 检索请求 | `queries` `searches` `questions` `search_requests` `请求` `问题清单` | list[str] 或 list[dict]；顺序即输出顺序 |
| 过滤条件 | `filters` `constraints` `conditions` `过滤条件` | 全局条件；每问的 `filters` 覆盖同名键 |
| 同义词 | `synonyms` `glossary` `aliases` `terminology` | dict{词: [同义]} 或 list[{term, synonyms}] |

`documents[]` 每项可带：`doc_id` `path` `version` `aliases` `permission` `metadata{year, project, batch, author, tags}`。

## 2. index.json（脚本产出，Agent 与自检的事实底座）

```
{case_id, built_at, library_root, root_source, index_digest,
 docs:[doc], dedupe:{groups, conflicts}, excluded_evidence:[x], failures:[f], scan_stats}
```

| 对象 | 字段 | 说明 |
|-|-|-|
| doc | `doc_id` `path` `path_input` `path_abs` `declared` `type` `ext` `version` `aliases` | `path` 相对材料根，`path_input` 相对 `/input`（引文路径用后者） |
| doc | `permission` `status` `notes` `sha256` `sha256_16` `bytes` `text_chars` `encoding` | `status` 见枚举表 |
| doc | `pages{count,label_source,page_offset}` | `label_source`：`pagelabels` / `footer_offset` / `assumed_equal` / `not_applicable` |
| doc | `sections[{section_id,title,level,page_physical,page_printed,container,paragraph_ids}]` `paragraphs[]` | `section_id=<doc>-sN` |
| para | `pid` `doc_id` `section_id` `section` `text` `kind` `source` `page_physical` `page_printed` `container` | `pid=<doc>-pN`；`source`∈`body\|table\|figure_caption\|reference\|appendix` |
| doc | `representative` `duplicate_of` `older_version_of` | 代表文档为 `true`；后两者非空则该文档**不得作为独立证据** |
| x | `doc_id` `path` `reason` `detail` `evidence_ban` | `reason`：`duplicate_of:<id>` / `older_version_of:<id>` |
| f | `doc_id` `path` `reason` `detail` `impact` | `reason` ∈ `permission_denied\|encrypted\|no_text_layer\|low_text_quality\|corrupt\|empty_file\|path_missing\|unsupported_legacy\|library_missing` |

## 3. draft.json（**Agent 手写**，check 校验、build 消费）

```json
{"case_id": "...",
 "queries": [{"query_id": "Q1", "question": "...", "answer": "结论",
   "status": "answered|partially_answered|not_found|blocked_by_filter",
   "filters_applied": ["year=2021"],
   "evidence": [{"path": "library/a.pdf", "version": "v2", "section": "2.1",
                 "page_printed": 4, "page_physical": 2, "paragraph_id": "D2-p6",
                 "quote": "逐字原文片段", "allow_non_representative": false}],
   "search_scope": "not_found/blocked 时必填", "notes": ""}],
 "excluded_evidence": [{"path": "...", "reason": "duplicate_of:D2"}],
 "filters": [{"filter": "year=2023", "kept": 0, "removed": 8, "satisfiable": false}],
 "method_notes": {"index_granularity": "...", "synonym_strategy": "...", "filter_order": "..."},
 "uncertainties": [{"type": "version_conflict", "detail": "..."}]}
```

| 规则 | 说明 |
|-|-|
| 别名键 | `queries` ≡ `answers` ≡ `results`；`evidence` ≡ `citations` ≡ `refs` |
| 唯一必填 | `query_id`/`question`（可省略 question，按 id 或顺序匹配）、`status`、`evidence` |
| `quote` | 必须是该文档该段原文的逐字子串（空白差异可归一，**语义转述一律拒收**） |
| 页码 | 可留空，脚本按索引回填并记录 `changes`；写错会被纠正并记录 |
| `not_found`/`blocked_by_filter` | `search_scope` 必填，否则 check 出 FIX |
| `allow_non_representative` | 仅当必须引用旧版本时置 `true`，并写清理由 |

## 4. result.json（主产物）

**顶层**：`case_id` `status` `summary` `queries` `hits` `filters` `excluded_evidence` `coverage` `evidence` `sources` `uncertainties` `errors` `degradations` `changes` `counts` `method_notes` `verification` `runtime` `contract_keys` `primary_result` `result{}`，外加 `output_contract` 的**每一个键**（未覆盖的键以 `null`/`[]` 占位）。

| 枚举 | 允许值 | 判定 |
|-|-|-|
| `status`（整体） | `ok` / `partial` / `failed` | ok=工作稿已裁决且全部证据可核验且无拒收；partial=有交付但降级；failed=无可用案例/输入 |
| `queries[].status` | `answered` / `partially_answered` / `not_found` / `blocked_by_filter` | 不得出现 `ok`/`unknown`/`N/A`/`partial`（`partial` 会被拒绝，请写 `partially_answered`） |
| `verification.checks[].ok` | bool | 12 项机械检查，全 true 才算 `ok` |
| `degradations[].item` | 问题号或 `draft`/`verification`/`result.json` | 与 `reason` 一起说明缺口 |

| 逐问字段 | 含义 |
|-|-|
| `answer` | 结论文字（Agent 写），空字符串表示未作答 |
| `evidence[]` | `path` `doc_id` `version` `section_id` `section` `page_physical` `page_printed` `paragraph_id` `char_start` `source` `quote` `quote_verified` `match` `locator` |
| `rejected_evidence[]` | `reason`∈`quote_not_found\|quote_too_short\|document_not_found\|document_<status>\|non_representative_document\|violates_filters` + `detail`/`suggestion` |
| `filters_applied[]` | 该问实际执行的过滤表达式（`key op value`） |
| `search_scope` | 检索范围（文件数、关键词、过滤结果、放宽会命中什么） |
| `candidates[]` | 仅兜底路径：脚本候选定位（无 Agent 裁决时） |
| `locators[]` | 证据 locator 列表，形如 `library/a.pdf#p2/D2-p6@80` |

`coverage`：`docs_expected` `docs_declared` `docs_indexed` `docs_failed` `queries_expected` `queries_answered` `queries_partial` `queries_not_found` `queries_blocked` `sections_indexed` `paragraphs_indexed` `docs_with_page_mapping` `failures[]`。

`counts`：`queries` `answered` `partially_answered` `not_found` `blocked_by_filter` `evidence` `evidence_rejected` `docs_total` `docs_indexed` `docs_failed` `sections` `paragraphs` `duplicates_excluded` `quote_hit_rate` `pages_mapped`。

`runtime`：`version` `script_seconds` `model_requests_by_script` `python` `draft_present` `draft_error` `index_digest` `scan_stats` `budget{wall_limit_s,model_requests_limit,note}`。

## 5. 副产物

| 文件 | 关键字段 |
|-|-|
| `answers.json` | `case_id` `status` `queries` `coverage` `counts` |
| `hits.jsonl` | 每行 `query_id` `doc_id` `path` `paragraph_id` `page_physical` `page_printed` `score` `terms` `origin`(`script\|script_candidate\|agent`) `locator` |
| `filters_log.json` | `global_filters[]`（`filter` `kept` `removed` `kept_docs` `removal_reasons` `satisfiable` `relaxation_note`）+ `per_query[]` |
| `dedupe.json` | `groups[]`（`kind=identical_copy\|version_chain` `representative` `members` `similarity`）`conflicts[]` `excluded_evidence[]` |
| `failures.json` | `failures[]` `degradations[]` `errors[]` |
| `verify_report.json` | `ok` `checks[]` `fails[]` `unmatched_quotes[]` `page_mismatch[]` `quote_hit_rate` |
| `location_report.md` | 人读版：每问结论 + locator + 引文 + 检索范围 + 过滤台账 + 排除清单 |
