---
name: research-file-locator
description: 科研文件库的章节级检索与证据回链。对一个已入库的科研文件库（PDF/Word/Excel/PPT/CSV/TXT，含改名副本、修订版、扫描件、权限受限文件）建立带段落编号与印刷页/物理页映射的索引，把提问落到具体文件的章节·页·段落，硬执行年份/项目/类型/批次/版本/权限过滤，输出带逐字原文引文与可复核 locator 的答案，并记录无权限、加密、无文本层、重名副本、旧版本、空结果与恢复动作。适用于「这段话在哪个项目/哪一版/哪一页」、跨文件同名概念检索、版本与副本辨别、按条件筛选后定位；不适用于开放网络文献检索、论文综述写作、存储权限系统建设。
version: 1.0.0
---

# research-file-locator（library-02 科研文件智能检索）

把**已经在库里的科研文件集合**变成可复核的检索结论：文件 → 章节 → 页码（印刷页与物理页分列）→ 段落 → 逐字引文。

## 1. 第一步：五命令主路径（照此执行，不要跳步）

```bash
python3 -B scripts/main.py init       # 建索引：读 /input/case.json + /input/task.md + 全部材料，先写合法 partial result.json
python3 -B scripts/main.py show       # 打印带 locator 的原文/对象清单，供你逐字引用（不靠猜）
#   —— 你（评审 Agent）亲自读材料与 show 输出，写工作稿 /app/work/draft.json ——
python3 -B scripts/main.py check      # 机械校验：契约字段、quote 是否逐字命中、覆盖数、过滤是否被放宽、工作稿 schema
python3 -B scripts/main.py build      # 由工作稿生成主产物 + 最终 result.json（无条件 finalize）
python3 -B scripts/main.py selfcheck  # 复检并打印 verification 摘要
```

**脚本不会代替你阅读理解；必须先阅读材料、写工作稿，再运行 build；禁止只跑 build 就结束。**

| 谁 | 负责什么 |
|-|-|
| 脚本 | 解析抽取、章节切分、页码映射、候选定位、同义/别名扩展、过滤硬执行、哈希去重与版本链、引文逐字校验、契约回填、降级兜底 |
| **你（Agent）** | 判断"命中的那一段是否真的回答了问题"、写答案结论、写 `not_found` 的检索范围、写方案取舍与 `method_notes`、判定哪些副本/旧版本不能当独立证据 |

`build` 有兜底：工作稿缺失/不合格时仍产出完整最小交付（合法 `result.json`、`status=partial`、`degradations` 写清缺口、退出码 0）。但**只有脚本候选、没有你的裁决，答案就是降级的**，得分明显低于正常路径。

## 2. 调用方式

```bash
python3 -B scripts/main.py <init|show|check|build|selfcheck>
  --input DIR(=/input)  --out DIR(=/app/output)  --work DIR(=/app/work)
  --case FILE  --draft FILE(=<work>/draft.json)
  show: --doc ID  --grep TEXT  --limit N(160)  --full  --open
  全部子命令: --quiet  --version  --help
```

- 无参数也能跑：按 `/input`、`/app/output`、`/app/work` 探测，不可写时回退 `./input`、`./output`、`./work`。
- 依赖：Python 3.8+ 标准库，不联网，不依赖当前工作目录（资源用 `Path(__file__).resolve().parent` 定位）；可选外部工具 `pdftotext`（有则优先，无则用内置 PDF 解析）。
- 退出码**恒为 0**；异常写入 `errors`/`degradations`，不抛栈。

## 3. 输入契约

| 输入 | 说明 |
|-|-|
| `/input/case.json` | 识别 `case_id`、`task_instruction`、`output_contract`、`library_root`、`queries`/`searches`/`questions`、`filters`、`documents`（含 `path`/`version`/`aliases`/`permission`/`metadata`）。键名容错表见 `references/schema.md` §1 |
| `/input/task.md` | 任务说明，问题与过滤条件的补充来源（`init` 会打印正文供你读） |
| 材料 | 优先 `case.json.library_root`，其次 `/input/library`、`/input/artifacts`、`/input/files`，最后 `/input` 全树（跳过 case.json/task.md/rubric/gold 等评分文件） |

声明与磁盘按路径合并：声明了但不存在 → `failures[reason=path_missing]`；磁盘有但未声明 → 仍入库（`declared=false`）。

**工作稿 `/app/work/draft.json`（你手写，schema 见 `references/schema.md` §3）**：

```json
{"case_id": "...",
 "queries": [{"query_id": "Q1", "question": "...", "answer": "结论",
   "status": "answered|partially_answered|not_found|blocked_by_filter",
   "filters_applied": ["year=2021"],
   "evidence": [{"path": "library/a.pdf", "version": "v2", "section": "2.1",
                 "page_printed": 4, "page_physical": 2, "paragraph_id": "D2-p6",
                 "quote": "逐字原文片段"}],
   "search_scope": "not_found/blocked 时必填", "notes": ""}],
 "excluded_evidence": [{"path": "library/a_copy.pdf", "reason": "duplicate_of:D2"}],
 "filters": [{"filter": "year=2023", "kept": 0, "removed": 8, "satisfiable": false}],
 "method_notes": {"index_granularity": "段落", "synonym_strategy": "...", "filter_order": "..."},
 "uncertainties": []}
```

`init` 会生成 `<work>/draft.template.json`（`query_id`/`question`/`filters_applied` 预填、答案为空），复制成 `draft.json` 再填。也接受 `answers` 作为 `queries` 的等价键名。

## 4. 输出契约

主产物 `/app/output/result.json`：**原样回填 `output_contract` 的每一个键**（键名不改、不漏键，缺值 `null`/`[]`），并带信封 `case_id`、`status`(`ok|partial|failed`)、`summary`、`result{queries,hits,filters,excluded_evidence,coverage,failures,index_summary,method_notes}`、同名镜像、`sources`、`evidence`、`uncertainties`、`errors`、`degradations`、`changes`、`counts`、`verification`、`runtime`、`contract_keys`、`primary_result`。

同目录副产物：`index.json`（文档/章节/段落/页码/哈希/代表版本）、`answers.json`、`hits.jsonl`（脚本候选与 locator）、`filters_log.json`（每条过滤的保留/剔除/可满足性）、`dedupe.json`（副本组、版本链、冲突）、`failures.json`、`verify_report.json`、`location_report.md`（人读交接报告）。字段与枚举全表见 `references/schema.md` §2/§4/§5。

## 5. 核心流程

1. **盘点**：`init` 逐文件记录 `sha256`、字节、类型、声明元数据、权限、可读性；写 `index.json`/`failures.json`；**先写合法 partial `result.json`**。
2. **抽取**：txt/md/csv/json/tex 直读；PDF 先试 `pdftotext`，否则内置解析（zlib 解 FlateDecode 内容流 → `Tj/TJ` 取词 → `Td/T*/Tm` 断行 → 逐页成文）；DOCX/XLSX/PPTX 用 `zipfile`+XML 取标题样式、段落、表格行、幻灯片。加密/无文本层/损坏 → 该文件降级记录，**不假装读到**。
3. **章节与页码**：按标题层级切分，段落全局编号 `<doc>-pN`；`page_physical` 为 PDF 物理页，`page_printed` 优先 `/PageLabels`，否则用页脚独立数字推算统一偏移（≥3 页且 ≥60% 一致），否则等于物理页并标 `assumed_equal`。
4. **候选定位**：同义/缩写/中英/别名扩展 + 段落打分 + 文档频次抑制，输出带 locator 的候选供你裁决；只命中文件名时同时给正文候选。
5. **过滤硬执行**：年份/项目/类型/批次/版本/权限逐条求值，属性缺失即不可满足，**不静默放宽**。
6. **去重与版本**：`sha256` 分完全副本，基名+相似度识别版本链，选代表文档，其余进 `excluded_evidence`。
7. **你写工作稿**：读 `show`，逐问写 `answer`/`status`/`evidence`（`quote` 逐字复制）/`excluded_evidence`/`filters`/`method_notes`。
8. **`check`**：逐条定位 quote（精确 → 空白归一 → 跨段），不命中给 FIX 与最接近段落；同时查契约键、覆盖、过滤放宽、副本/旧版证据、`not_found` 是否写检索范围。
9. **`build`**：把工作稿变成产物；未通过校验的引文进 `rejected_evidence` 并从答案证据剔除（答案降级 + `degradations`），**未通过校验的引文绝不留在答案里**。
10. **`selfcheck`**：从磁盘重读 `result.json`，重算引文命中率、契约覆盖、页码一致性、去重约束，写 `verification`。

## 6. 证据与定位规范

- `quote` 必须是该文档该段落原文的**逐字子串**：不翻译、不改写、不拼接、不加省略号；建议 20–200 字符。
- 定位五元组：`path` + `version` + `section` + `page_physical`/`page_printed` + `paragraph_id`，附 `char_start`；`locator` 形如 `library/02_methods.pdf#p5/D2-p17@1240`。
- 印刷页与物理页分列；两者不同是正常情况（封面、勘误、扫描页），不要只写一个。DOCX/XLSX/PPTX 两页码为 `null`，用 `section`+`paragraph_id` 定位。
- 表格/图注/附录以 `source` 区分（`table|figure_caption|appendix`），可引用但要在 `section` 标明。
- 副本（`sha256` 相同）与旧版本不能当独立证据；必须引用时显式写 `version` 并在 `notes` 说明。

## 7. 过滤与版本

- 过滤是**硬约束**：不可满足时该问 `status=blocked_by_filter`，`search_scope` 写清"若放宽会命中哪个文件"，但不把放宽后的命中当答案。
- 属性来源优先级：`case.json` 声明 > 路径记号（`20\d\d`、`v2/rev3/_final/终版`、`B\d+`）> mtime；来源写进 `filters_log.json`。
- 版本自然序比较（`v2 < v10`），`final`/`终版`/`submitted` 最高；无法比较时保留两条并记 `uncertainties[].type=version_ambiguous`。

## 8. 失败处理

| 情况 | 行为 | 痕迹 |
|-|-|-|
| 无 case.json / 坏 JSON | 不崩，`status=failed` | `errors[stage=load_case]`，契约键以 `null`/`[]` 占位 |
| 材料目录不存在 | 空索引 | `failures[reason=library_missing]`、`status=partial` |
| 无权限文件 | 不读内容 | `failures[reason=permission_denied]`、`excluded_evidence` |
| 加密 PDF | 不解密 | `failures[reason=encrypted]` |
| 无文本层/扫描件 | 不编造文字（不做 OCR） | `failures[reason=no_text_layer]`、`uncertainties` |
| 文件损坏/解析异常 | 只降级该文件 | `failures[reason=corrupt]` |
| 重名不同内容 | 两条独立入库 | `dedupe.conflicts[].same_name_diff_content=true` |
| 空结果 | `not_found` + 检索范围 | `search_scope`、`counts.not_found` |
| 工作稿缺失/坏 JSON | 兜底完整最小交付 | `status=partial`、`degradations[item=draft]` |
| 引文未命中 | 剔除并降级 | `rejected_evidence`、`degradations[item=<Q>:evidence]` |

## 9. 自查清单

```bash
python3 -B scripts/main.py selfcheck
```

- [ ] `result.json` 合法，`output_contract` 每键在顶层且键名未改；
- [ ] 每问一条 `queries[]`（含 `not_found`/`blocked_by_filter`），`status` 属四值枚举（**不要写 `partial`**，请写 `partially_answered`）；
- [ ] 每条 `evidence.quote` 逐字命中该文档该段，`quote_hit_rate=1.0`（未命中项已在 `rejected_evidence`）；
- [ ] `page_printed`/`page_physical` 分列，`label_source` 有记录；
- [ ] `filters_log.json` 无静默放宽：`satisfiable=false` 的问题必须是 `blocked_by_filter`；
- [ ] `excluded_evidence` 里的文档没有出现在任何答案证据中；
- [ ] 无权限/加密/无文本层/缺路径/空结果逐条记录；
- [ ] `status=partial` 时 `degradations` 非空，不把未完成写成完成。

## 10. 评分维度落地

| 维度 | 本包对应 |
|-|-|
| 实际效果 40 | 检索→定位→过滤→回链四段都在主路径；每问 `status`+`evidence`+locator；`coverage`/`counts` 给完成与覆盖计数 |
| 使用增益 25 | 一次建索引多次复用（`runtime.scan_stats`）；`hits.jsonl`+`show` 减少翻文件；`index_digest`+`verification` 使增益可复算 |
| 创新增益 15 | 章节级定位（印刷页/物理页 + PageLabels/页脚偏移推断）、同义/别名/跨语言对齐、过滤硬执行台账、引文回环校验、副本与版本链台账 |
| 可靠体验 10 | 五命令契约清晰；单文件失败只降级该文件；空输入/坏 JSON/缺工作稿都 exit 0 且产物合法 |
| 生态贡献 10 | `references/schema.md`（字段/枚举/契约）、`references/guide.md`（规则表/评分映射/最小示例） |

## 11. 文件清单与维护

| 文件 | 作用 |
|-|-|
| `SKILL.md` | 入口：主路径、契约、流程、规则、降级、自查 |
| `scripts/main.py` | CLI 五子命令、目录探测、init/show/check、产物落盘 |
| `scripts/report.py` | 候选定位、引文回环校验、工作稿裁决、build/selfcheck |
| `scripts/rules.py` | 路径元数据、过滤硬执行、副本/版本链、检索词与打分 |
| `scripts/core.py` | 输入发现、索引装配、契约回填、落盘工具 |
| `scripts/extract.py` | PDF/OOXML/文本抽取，章节与页码结构 |
| `references/schema.md` | `case.json`/`index.json`/`draft.json`/`result.json` 字段字典与枚举 |
| `references/guide.md` | 检索/定位/过滤/版本规则表、评分映射、最小调用示例 |

版本 `1.0.0`。维护：改字段先改 `schema.md` 再改脚本；新增文件类型在 `extract.extract()` 分支注册；调整权重在 `rules.SYN`/`rules.score_para`；改完重跑 `init→show→check→build→selfcheck` 并记录 `verify_report.json`。

## 12. 已知限制

- 语义对齐靠"词表 + 词形 + 别名"，完全换词的同义表述可能漏检；此时按 `not_found` 处理并写检索范围，不猜。
- 内置 PDF 解析不含 CMap/ToUnicode 还原：中文 CID 字体页或扫描件可能取不到文本 → 记 `no_text_layer`，**不编造内容**；有 `pdftotext` 时优先用它。
- DOCX/XLSX/PPTX 无可靠分页，两页码记 `null`；版本比较依赖文件名/声明记号，缺失时给 `version_ambiguous` 而不擅自排序。
- 不做 OCR、不解密、不修复损坏文件，也不替代人工判断"这段是否真的回答了问题"——那是工作稿的职责。
