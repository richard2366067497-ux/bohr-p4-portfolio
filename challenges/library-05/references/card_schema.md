# 字段字典与约定（reading-card-desk 1.0.0）

产物全 UTF-8；JSONL 一行一对象。字符偏移相对**规范化文本**（§5），故任何 `quoted_text` 都能在 `library_index.json`
同页 `norm` 文本中按 `char_start/char_end` 切片逐字命中。

## 1. 锚点 `anchors/anchor_ledger.jsonl`

| 字段 | 类型 | 说明 |
|---|---|---|
| `anchor_id` | str | `a-<sha256[:8]>-p<page>-<页内序号>`，内容定址，跨机复跑稳定 |
| `doc_id`/`file`/`file_sha256` | str | 所属文档；重复文件只从 canonical 副本抽锚点 |
| `source_version` | str | 版本标签 `v1`/`v2`/`canonical` |
| `type` | enum | `highlight underline strikethrough margin_note handwritten web_clip word_comment region_mark stamp` |
| `page_physical`/`page_printed` | int/null | 物理页；印刷页仅在页眉页脚有独立页码，否则 `null`（不推算） |
| `locator`/`paragraph_id` | str | `p<page>:<pid>:c<start>-c<end>`；无偏移时省略 `c` 段 |
| `quoted_text` | str/null | 逐字原文；`note_only` 时可为 null 或批注文本（`quote_source=annotation_note`） |
| `quote_verified` | enum | `exact fuzzy unverified note_text_fallback unverified_after_check` |
| `color`/`color_hex`/`color_meaning`/`color_meaning_source` | | 颜色取最近 RGB 词典；含义来源 `case_declared_legend`>`document_legend`>`annotation_export`>`default_convention` |
| `anchor_method` | enum | `pdf_annots_quad pdf_annots_rect docx_comment docx_highlight html_mark quote_search nearest_line note_only` |
| `anchor_confidence` | float | quad .92 / rect .85 / docx·html .90 / quote_search .95 / nearest_line .50 / note_only .20–.35 |
| `sources[]`/`merged_from[]` | list | 命中来源与并入锚点 id |
| `context_before`/`context_after` | str | 前后 90 字符，供 `show` 复核 |
| `cross_version_peer`/`duplicate_quote_group` | list/str | 同引文跨版本、同引文同伴 |

## 2. 知识卡 `cards/knowledge_cards.jsonl`

| 字段 | 类型 | 说明 |
|---|---|---|
| `card_id` | str | 工作稿给定或 `c01…` |
| `kind` | enum | `question method result conclusion reusable to_verify` |
| `claim` | str | **判断**；等于任何锚点引文则 `C203` |
| `anchor_ids[]` | list | ≥1 且须存在于底账（否则 `C205`） |
| `source_version` | str | 判断所依据版本 |
| `strength` | enum | `strong moderate weak` |
| `boundary`/`reuse_hint` | str | 适用条件、后续复用方式（缺 boundary → `C204`） |
| `status` | enum | `grounded`（逐字命中锚点 + claim + boundary + strength）/`partial`/`unsupported`，与证据冲突取更严 |
| `evidence_note`/`counter_evidence` | str | 哪条锚点支撑哪半句；反向/冲突证据 |
| `tags[]`/`topic` | list/str | 检索与图归属 |
| `anchor_refs[]` | list | 渲染期回填 `{anchor_id,file,locator,quoted_text}`，单行自证 |

## 3. 图与检索

`views/topic_graph.json`：`{schema,nodes[{id,type(card|topic),kind,label,degree}],edges[{from,to,relation,basis,
confidence,evidence_anchor_ids}],rejected_edges[{...,reason}],over_connected[],stats{nodes,edges,avg_degree,max_degree}}`；
`relation ∈ same_method same_quote explicit_citation contradicts extends same_dataset same_entity`；`basis` 必填且须指到
原文/锚点，仅词面重合 → `rejected_edges(basis_missing)`；度数 >6 → `over_connected`。
`views/topic_index.json`：`{by_kind,by_tag,by_topic,by_doc,by_anchor}`，值为 `card_id` 列表。
`result.retrieval.results[]`：`{id,question,hits[{card_id,score,matched_terms,via}],hit_card_ids[],not_found_reason}`；
阈值 0.18、停用词过滤，命中附 `matched_terms` 供识别误召回。

## 4. 溯源与关卡

`provenance/provenance.json`：`{schema,generated,script_version,case_id,inputs[{file,sha256,bytes,kind}],
input_count,params,anchor_id_rule,counts,coverage,gate_results,determinism{checked,anchor_ids_stable}}`。
`provenance/skipped.json`：`{items[{file,reason,detail,(anchor_id)}],counts{reason:n}}`；`reason ∈ encrypted_pdf
corrupt_pdf no_text_layer garbled_text_layer low_confidence quote_not_found orphan_annotation permission_denied
bad_json too_large unreadable parse_failed`。
`provenance/self_check.json`：`{anchor_ids_stable,anchors_compared,quotes_rechecked,quote_failures[],
contract_keys,contract_present,contract_unmapped[],gate_status{},overall(pass|fail)}`。
错误码：`A101 A102 A103 A104 A105`（G1）、`C201 C203 C204 C205`（G2）、`E301 E302 E303`（G3）、`Q401 Q402 Q403`
（G4）、`P501 P502 P503`（G5）；含 `FAIL` 或仅 `WARN` → `result.status=partial`。

## 5. 规范化与定位

`norm_map(s)`：全角→半角（U+FF01–FF5E）、弯引号→直引号、各类连字符→`-`、lower、连续空白折叠为单空格、软连字符丢弃；
返回 `(normalized, index_map)`。引文先在该页精确 `find`，失败再按首尾 5 词模糊定位（`fuzzy`），仍失败 → `unverified`，
保留原样并登记 `quote_not_found`，**绝不改原文凑通过**。

## 6. 工作稿 `draft.json` 兼容

`{case_id,cards[],topic_edges[],questions[],topics[],aliases[],skipped[],notes}`（字段见 §2/§3）。
兼容键：`cards|items`、`claim|statement`、`anchor_ids|anchors`、`topic_edges|edges`、`from|source`、`to|target`。
缺省路径：`--draft` → `<work>/draft.json` → `plan.json` → `desk/draft.json` → `cards.json`；全部缺失即
`degradations: draft_missing` 的降级交付。新增字段只加不改名，`schema` 字段用于版本识别。
