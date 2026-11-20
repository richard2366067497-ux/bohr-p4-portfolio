# 规则、评分映射与最小示例（research-file-locator 1.0.0）

## 1. 检索与语义对齐规则

| 环节 | 规则 | 可复核痕迹 |
|-|-|-|
| 查询词 | ASCII 词（≥3 字符）权重 1.3；CJK 二元组 1.0、整体短语 1.4（≤6 字）；数字（≥2 位）1.0 | `hits.jsonl.terms` |
| 同义/缩写/跨语言 | 内置中英词表（离心↔centrifugation、缓冲液↔buffer、方案↔protocol…）+ `case.json` 的 `synonyms/glossary/aliases`；两侧都展开 | `method_notes.synonym_strategy` |
| 词形 | 词面未命中且长度 ≥5 时按前 5 字符前缀匹配（degradation ↔ degraded） | 同上 |
| 段落打分 | Σ 命中权重×(1+0.2×重复)÷(1+长度/1200)，整句短语命中 +2 | `hits.jsonl.score` |
| 去泛词 | 不在查询级去词，靠长度归一化抑制长段落；泛词问题交给 Agent 判断 | — |
| 文档级线索 | 文档 `aliases` 命中直接加权，避免"只命中文件名" | `hits.jsonl.origin` |

**边界**：这是确定性的词面/词形检索，不是向量语义检索。完全换词的同义表述可能召回不到 —— 此时写 `not_found` 并说明检索范围，**不要用相近但不同的段落硬凑答案**。

## 2. 章节与页码规则

| 情况 | 处理 |
|-|-|
| 标题识别 | Markdown `#`、`1./1.1`、`第X章/节`、`一、`/`（二）`、Abstract/Introduction/Methods/Results/Discussion/Conclusion/References/附录 等 |
| 章节 id | `<doc_id>-sN`，按出现顺序；首个标题前的内容归 `[preamble]` |
| 段落 id | `<doc_id>-pN`，全文连续编号，跨章节不复位 |
| 表格/图注/附录 | 独立 `source`（`table`/`figure_caption`/`appendix`），可被引用但需在 `section` 注明 |
| 印刷页 vs 物理页 | 优先 PDF `/PageLabels`（`label_source=pagelabels`）；否则用页脚独立数字推算统一偏移（≥3 页且 ≥60% 一致，`footer_offset`，`page_offset=印刷号-物理号`）；都没有则 `assumed_equal`（两页码相同，**如实标注为推断**） |
| 页脚页码 | 抽取后剔除与物理页/印刷页相同的纯数字行，避免变成段落 |
| DOCX/XLSX/PPTX | 无可靠分页：两页码记 `null`，定位靠 `section`+`paragraph_id`+行号/幻灯片号（`container`） |

## 3. 过滤规则（硬约束）

| 支持键 | 别名 | 取值来源优先级 |
|-|-|-|
| `year` | 年份/date/time | case 声明 metadata > 路径中的 `20\d\d` > 文件 mtime |
| `type` | 类型/格式/ext/format | 扩展名（`doc→docx`、`xls→xlsx`、`ppt→pptx`、扫描件→pdf） |
| `project` | 项目/项目编号/project_id | 声明 > 路径 `P-2021`/`project-12` 等 |
| `batch` | 批次/实验批次/run/lot | 声明 > 路径 `batch`/`B7` |
| `version` | 版本/rev/revision | 声明 > 路径 `v2`/`rev3`/`final`/`终版` |
| `permission` | 权限/access/visibility | 声明（`denied`/`restricted` 即不读内容） |

运算符：`=` `!=` `>` `>=` `<` `<=` `in`。字符串比较大小写不敏感，数字按数值比，版本按自然序（v2 < v10）。

**硬执行**：属性缺失 → 不满足（`attribute_unknown`）；条件不可解析 → 不满足（`unparsed_condition`）；全库不满足 → 该问 `blocked_by_filter`，并在 `search_scope` 写"若放宽会命中 X"（**仅说明，不作答案**）。禁止静默放宽、禁止把放宽后的命中当结论。

## 4. 副本与版本规则

1. `sha256` 相同 → `identical_copy`：保留代表文档（优先 case 声明、路径不含 copy/副本、版本高、路径短），其余进 `excluded_evidence`（`evidence_ban=true`）。
2. 基名相同（去掉 copy/版本/final 记号）+ 文本相似度 ≥0.35 → `version_chain`：版本序最高者为代表（`final`/`终版`/`submitted` 最高），其余标 `older_version_of`。
3. 同名不同内容 → `dedupe.conflicts[].same_name_diff_content=true`，两条都保留、都可检索，但**引用时必须写明路径与版本**。
4. 引用被排除文档 ⇒ 该引文进 `rejected_evidence(reason=non_representative_document)`；确有必要时在工作稿里置 `allow_non_representative: true` 并说明理由。

## 5. 引文回环校验（本题核心增量）

```
draft.evidence.quote
  ├─ 精确子串命中该段           → match=exact，记录 char_start 与 locator
  ├─ 空白/引号/破折号归一后命中  → match=whitespace_normalised，回填原文字符偏移
  ├─ 命中相邻段落拼接           → match=spanning_paragraphs + changes 记录（提示拆分引文）
  └─ 都不命中                   → 拒收，reason=quote_not_found，附最接近段落建议
```

被拒收的引文**不进入** `evidence`，只进 `rejected_evidence`；若该问因此没有可用证据，状态降为 `partially_answered` 并写 `degradations`。`counts.quote_hit_rate = 通过/(通过+拒收)`，`selfcheck` 会从磁盘重算一遍。

## 6. 评分维度 → 产物/字段

| 评分点 | 落地位置 | 自检项 |
|-|-|-|
| 任务完成度 15 | 每问一条 `queries[]`；检索→定位→过滤→回链四段全在 `result` 里 | `queries_covered` |
| 结果正确性 15 | `evidence[]` 的 quote 逐字 + 页码回填 + 副本/旧版排除 | `quotes_verbatim` `pages_consistent` `no_banned_evidence` |
| 结果完整性 5 | `coverage`（文档/问题/章节/段落/页映射计数）+ `failures[]` | `coverage_present` |
| 结果可核验 5 | `locator`（path#page/pid@offset）+ `sources[].sha256_16` + `index_digest` + `verify_report.json` | `quotes_verbatim` |
| 质量增益 15 | `hits.jsonl`（脚本候选）与 `evidence`（Agent 裁决）分层，便于与基础 Agent 对照 | — |
| 效率增益 5 | `runtime.scan_stats`（文档/字节/节/段）+ 一次建索引多次复用 | `runtime_budget_present` |
| 增益可验证 5 | `index_digest` 稳定 + 复跑同一输入得到同一索引与同一 locator | 重跑对比 |
| 创新 15 | 章节级定位（印刷页/物理页 + PageLabels/页脚偏移）、同义/别名跨语言对齐、过滤台账、引文回环、版本链台账 | — |
| 可靠体验 10 | exit 0 + 单文件降级 + 缺工作稿兜底 + 空/坏输入不崩 | 冒烟四类 |
| 生态贡献 10 | `SKILL.md` + `schema.md` + 本文件 + 结构化产物（可被别人复用） | — |

## 7. 最小调用示例（**示例，不是任何正式案例的答案**）

材料（自拟，2 个文件）：`/input/case.json`（`library_root=library`，1 问「缓冲液 pH 是多少？」+ `filters.year=2021`）+ `/input/library/methods_v1.pdf`（含 `2.1 Buffer preparation` 与 `The pH was adjusted to 8.0 at room temperature before use.`）。

```bash
python3 -B scripts/main.py init      # case=demo docs=1 queries=1 digest=…
python3 -B scripts/main.py show --grep pH
# == D1 library/methods_v1.pdf type=pdf ver=v1 pages=3 label=footer_offset(2)
#    D1-p6 p2/pp4 [D1-s4] :: The pH was adjusted to 8.0 at room temperature before use.
```

工作稿（你写；`quote` 必须逐字复制）：

```json
{"case_id":"demo","queries":[{"query_id":"Q1","question":"缓冲液 pH 是多少？","answer":"pH 8.0（室温调节）。",
 "status":"answered","filters_applied":["year=2021"],
 "evidence":[{"path":"library/methods_v1.pdf","version":"v1","section":"2.1 Buffer preparation",
              "page_printed":4,"page_physical":2,"paragraph_id":"D1-p6",
              "quote":"The pH was adjusted to 8.0 at room temperature before use."}]}]}
```

```bash
python3 -B scripts/main.py check     # queries=1 rows=1 verified_evidence=1 fixes=0 → PASS
python3 -B scripts/main.py build     # status=ok evidence=1 quote_hit_rate=1.0 fails=[]
python3 -B scripts/main.py selfcheck
```

输出节选：`queries[0].evidence[0]` 形如
`{"path":"library/methods_v1.pdf","section":"2.1 Buffer preparation","page_physical":2,"page_printed":4,
"paragraph_id":"D1-p6","char_start":0,"quote_verified":true,"match":"exact","locator":"library/methods_v1.pdf#p2/D1-p6@0"}`，
`coverage` 给出 `docs_indexed/queries_answered/docs_with_page_mapping` 计数。

复现建议：用自己的材料跑 `init`，把 `work/draft.template.json` 复制成 `draft.json` 逐问填写；`check` 报 FIX 就改工作稿，改完再 `build`。同一材料重复 `init` 应得到相同的 `index_digest`。

## 8. 维护

- 新增文件类型：在 `extract.py` 的 `extract()` 分支里加解析器，返回同样的 `units` 结构即可复用全部下游逻辑。
- 调整检索权重：`rules.py` 的 `SYN`（词表）与 `score_para`（权重公式）。
- 改字段：先改 `schema.md`，再同步 `core.apply_contract` 与 `report.assemble`。
- 每次改动后必跑：`init → show → check → build → selfcheck`，并把 `verify_report.json` 的 `fails` 清零或写进 `degradations`。
