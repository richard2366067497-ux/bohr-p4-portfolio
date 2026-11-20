---
name: reading-card-desk
description: Turn a research reading library (PDF with /Annots, DOCX comments and highlights, HTML clips, MD/TXT, annotation exports) into a grounded knowledge-card desk - deterministic annotation extraction with physical/printed page, char offsets and verbatim anchor quotes, agent-authored judgment cards bound to anchors, explainable topic edges, question-to-card retrieval, duplicate/alias/version consolidation with a repair log, and a contract-filling result.json with provenance, rerun consistency and explicit degradation. Five subcommands - init, show, check, build, selfcheck.
version: 1.0.0
---

# reading-card-desk（阅读批注 → 知识卡工作台）

## 1. 用途与适用条件

把一份**已有的阅读资料库**整理成"可复用判断"的交付：每条批注（高亮/划线/页边注/手写/网页剪藏/Word 批注）都回收成带
`文件 + 版本 + 物理页 + 印刷页 + 字符区间 + 逐字原文` 的锚点；每张知识卡是一句**判断**，必须挂锚点、写强度与边界；
卡之间只有可解释依据才连边；问题能检索到卡；全过程留哈希、脚本版本、二次运行一致率与恢复记录。

**做**：多文件库盘点（路径/哈希/权限/元数据）；PDF `/Annots` 与内容流文本；DOCX `comments.xml`/高亮/修订痕迹；HTML 剪藏；
MD/TXT 段落化；独立批注导出（annotations.json）按逐字原文回位；重复/别名/版本合并；知识卡与主题图；`result.json` 契约回填。
**不做**：文献检索与选题、对论文内容做学术判断、代写综述、目录治理与长期归档；不生成原文之外的引文；无文本层扫描件不做 OCR 造假。
**适用**：`/input` 下有 `case.json` + 材料（1–N 个 PDF/DOCX/HTML/MD/TXT，可含批注导出与元数据表）。
**不适用**：加密且无法解密、损坏、无可读文本层且无批注导出的材料——如实登记跳过，不猜测内容。

## 2. 五命令主路径（**第一步，照顺序执行，不得跳步**）

```bash
python3 /skills/weekly-skill/scripts/main.py init    # 1. 建索引：解析 case.json/output_contract/task.md 与全部材料，先写合法 partial result.json
python3 /skills/weekly-skill/scripts/main.py show    # 2. 打印带 locator 的文档清单、锚点候选与原文段落，供你逐字引用
#    3. 你亲自读 show 的输出与材料原文，把判断写进 /app/work/draft.json（schema 见 §7）
python3 /skills/weekly-skill/scripts/main.py check   # 4. 机械校验：契约字段、quote 逐字命中、卡自足、边有据、问题可检索
python3 /skills/weekly-skill/scripts/main.py build   # 5. 生成 cards/anchors/views/provenance 四层产物 + 最终 result.json（无条件 finalize）
python3 /skills/weekly-skill/scripts/main.py selfcheck  # 6. 复检：重跑一致率、契约覆盖、逐字复核抽样
```

> **脚本不会代替你阅读理解；必须先阅读材料、写工作稿，再运行 build；禁止只跑 build 就结束。**
> 脚本只做确定性重活（解析、哈希、定位、去重、校验、渲染）。"哪句原文值得成卡、这张卡是 method 还是 to_verify、
> 强度多高、边界在哪、两条卡凭什么相关"——这些判断只能由你在 `draft.json` 里写出来。`build` 缺工作稿时只会落一份
> **诚实的降级交付**（status=partial，卡为 anchor-only 占位），不会有真正的知识卡。

节奏建议（900 秒 / 64 请求内）：`init`（数秒）→ `show --section anchors` 读候选 → `show --anchor <id>` 核对原文 →
写 8–15 张卡 + 边 + 问题映射 → `check` → 修 → `build` → `selfcheck`。每写完一批卡就 `build` 一次，保证任何时刻
`/app/output` 都有合法可交付结果。

## 3. 运行契约（Harbor）

| 项 | 值 |
|---|---|
| 输入 | `/input/case.json`、`/input/task.md`、`/input/**` 材料 |
| 工作目录 | `/app/work`（脚本状态 `desk/`；工作稿 `draft.json`） |
| 产物 | `/app/output/`（`result.json` 必在其中） |
| 参数 | `--input`（`/input`）、`--output`（`/app/output`）、`--work`（`/app/work`）、`--draft`、`--section`、`--anchor`、`--limit` |
| 退出码 | **恒为 0**（异常捕获进 `errors`，不抛栈给 Harness） |
| 依赖 | Python ≥3.10 标准库；不联网；不依赖 CWD；`pdftotext` 仅可选增强，缺失自动回退并记 `degradations` |
| 幂等 | 同输入重复 `build` 逐字相同（时间戳除外）；锚点 ID 由哈希+页+页内序号推导，可跨机复跑 |

`init` 一落盘就写合法 `result.json`；`build` 结尾**无条件**重写（含异常分支），因此任何时刻中断都有可交付结果。

## 4. 输入发现（语义识别，不假设键名）

1. **案例**：`/input/case.json` → 递归 `case*.json` → 缺失则 `UNKNOWN-CASE`。取 `case_id`、`task_instruction|instruction|task`、
   `output_contract|outputContract`（原样透传）、`questions|searches|queries`、`topics`、`aliases`、`version_notes`、`color_legend`。
   JSON 非法时按文本抢救 `case_id` 与契约键名（`case_json_salvaged`），不让契约键消失。
2. **材料根**：`case.json` 声明目录 → `/input/library` → `/input/annotations` → `/input/artifacts` → `/input` 全树；
   跳过题面文件（`task.md`、`case.json`、`output-contract.md`、`environment/*`）。
3. **载体按内容识别不信后缀**：`%PDF-`→PDF；ZIP 含 `word/document.xml`→DOCX；`<html`→HTML；`.json` 含批注数组→批注导出；其余按文本。
4. **批注来源优先级**：独立导出（可带人工标签/颜色含义）> PDF `/Annots` > 文档内嵌标记（DOCX comment/highlight、HTML `<mark>`）
   > 正文锚定（`quote_search`）> 坐标近似（`quad_align`/`nearest_line`）。同一处批注被多来源命中时合并为一条，
   其余来源记入 `anchor.sources`（不覆盖、不重复计数）。
5. **缺什么写什么**：无材料 → `status=partial`、`uncertainties` 逐条写明缺哪个目录/载体，不构造正文。

## 5. 输出契约（`/app/output`）

```
result.json                     主产物：output_contract 全字段回填 + 信封字段
card_desk.md                    人读版卡片桌（卡→锚点→原文摘录，逐条可回查）
cards/knowledge_cards.jsonl     主结构：一卡一行（§6.2）
anchors/anchor_ledger.jsonl     证据底账：一锚点一行（§6.1）
library_index.json              资料结果：文件清单、元数据、哈希、权限、重复/别名/版本组
views/retrieval_view.md         问题 → 命中的卡 → 锚点（含未命中说明与召回不足处理）
views/topic_graph.json          主题/实体图：节点 + 边（每条边带 basis 与 confidence）
views/topic_index.json          主题/标签/类型/文献/锚点 → card_id 的倒排
provenance/provenance.json      脚本版本、输入哈希、运行参数、一致率、覆盖统计
provenance/skipped.json         跳过/低置信/冲突/无权限/旧版本批注的逐条登记
provenance/operation_log.jsonl  操作日志（解析→索引→校验→渲染）
provenance/recovery_log.jsonl   重复/别名/版本的恢复动作（canonical 选择、归并规则）
```

**信封字段恒定存在**：`case_id`、`status`(`ok|partial|failed`)、`result`、`sources`、`errors`、`degradations`、
`uncertainties`、`changes`、`runtime`；错误类条目每项都带 `kind`。
`output_contract` 的**每个键都出现**：键名不改、不裁剪、缺值 `null`/`[]`；语义可识别的键填真实内容（`cards`→卡片、
`anchors`/`批注`/`evidence`→锚点、`library`/`清单`→资料结果、`versions`→版本组、`retrieval`/`问题`→检索视图、
`coverage`→覆盖、`provenance`→溯源、`skipped`→跳过、`recovery`→恢复），无法识别者保留 `null` 并记
`contract_field_unmapped:<key>`（不猜、不硬塞）。

## 6. 数据结构（字段级 schema：`references/card_schema.md`）

### 6.1 锚点 `anchors/anchor_ledger.jsonl`

`anchor_id, doc_id, file, file_sha256, source_version, type, page_physical, page_printed, locator, paragraph_id,
char_start, char_end, quoted_text, quote_verified, color, color_hex, color_meaning, color_meaning_source, note,
author, created, anchor_method, anchor_confidence, context_before, context_after, sources[], merged_from[]`

`type` 取九类之一（类型不合并）；`locator` 形如 `p3:p3.2:c120-c188`（`c` 为规范化页文本偏移；DOCX/HTML/MD 为
`p1:p1.12:…`）；`anchor_confidence ∈ [0,1]` 由方法档位给出，`<0.5` 必须在 `skipped.json` 登记 `low_confidence`。

### 6.2 知识卡 `cards/knowledge_cards.jsonl`

`card_id, kind(question|method|result|conclusion|reusable|to_verify), claim, anchor_ids[], source_version,
strength(strong|moderate|weak), boundary, reuse_hint, status(grounded|partial|unsupported), created_from,
evidence_note, counter_evidence, tags[], topic, anchor_refs[]`

卡是**判断**不是摘抄：`claim` 不得等于任何锚点 `quoted_text`（C203）。`grounded` 才进 `result.cards_grounded`；
`partial`（缺 boundary/强度/部分锚点未验证）与 `unsupported`（无锚点或引文未命中）单列并在 `uncertainties` 写明缺口。

## 7. 工作稿 `/app/work/draft.json`（你的判断落点）

```json
{"case_id": "...",
 "cards": [{"card_id": "c01", "kind": "method", "claim": "……判断……",
            "anchor_ids": ["a-…", "a-…"], "source_version": "v1",
            "strength": "moderate", "boundary": "仅在……条件下成立", "reuse_hint": "写讨论时可直接引用",
            "status": "grounded", "evidence_note": "两条锚点分别支撑前/后半句",
            "counter_evidence": "另一版本给出相反比例", "tags": ["yield"], "topic": "drought yield"}],
 "topic_edges": [{"from": "c01", "to": "c04", "relation": "same_method|same_quote|explicit_citation|contradicts|extends|same_dataset|same_entity",
                  "basis": "两卡锚点共享同一段原文 p1:p1.1:c0-c59", "confidence": 0.8,
                  "evidence_anchor_ids": ["a-…"]}],
 "questions": [{"id": "q1", "question": "……", "card_ids": ["c01"], "not_found_reason": null}],
 "topics": [{"topic": "……", "card_ids": ["c01", "c07"]}],
 "aliases": [{"alias": "paper (1).pdf", "canonical": "paper.pdf"}],
 "skipped": [{"file": "scan.pdf", "reason": "no_text_layer", "detail": "0 字符"}],
 "notes": "取舍说明：为什么这些原文值得成卡，哪些批注被弃用及原因"}
```

`check` 默认读 `--draft` → `<work>/draft.json` → `plan.json` → `desk/draft.json` → `cards.json`。

## 8. 五道关卡（Gate 1–5）：规则 / 字段 / 错误码

| Gate | 名称 | 判定规则 | 落点 | 错误码 |
|---|---|---|---|---|
| G1 | 锚点可信 | 有 `file`+`file_sha256`+`type`(词典内)+`page_physical`+`locator`+`quoted_text`；`quoted_text` 必须**重新**在该页文本逐字命中（`check` 不信解析期标志，会重定位）；颜色含义须标来源 | `anchors/*.jsonl` | `A101` 缺 quote / `A102` 未命中 / `A103` 类型非法 / `A104` 缺页或 locator / `A105` 低置信(警告) |
| G2 | 卡自足 | `claim` 非空且非摘抄；`kind` 合法；`anchor_ids` ≥1 且存在；`strength`/`boundary`/`reuse_hint` 齐全；`status` 与证据强度一致（取更严者） | `cards/*.jsonl` | `C201` 无 claim 或无锚点 / `C203` claim 等于摘抄或过短 / `C204` 缺 boundary 或 strength / `C205` 引用不存在的锚点 |
| G3 | 关联有据 | 每条边有 `basis`（同一段原文/同一方法显式表述/显式引用），且能指到锚点或原文；仅共享单一术语不连边；单卡度数 ≤6 | `views/topic_graph.json` | `E301` 无 basis 或仅词面重合 / `E302` 过连接 / `E303` 关系类型非法 |
| G4 | 可检索 | 案例问题逐条给 `card_ids`；无命中必须写 `not_found_reason`；命中附 `matched_terms` 供辨别误召回 | `views/retrieval_view.md`、`result.retrieval` | `Q401` 问题未处理(警告) / `Q402` 命中卡不存在 / `Q403` 未命中且无原因 |
| G5 | 可复现 | `provenance` 有脚本版本、输入 sha256、参数、锚点 ID 稳定性、覆盖统计；跳过项逐条有 `reason` | `provenance/*` | `P501` 缺哈希 / `P502` 缺版本 / `P503` 一致率无法计算 |

`check` 打印每关 `PASS/WARN/FAIL` 与错误码并写 `desk/check_report.json`；`FAIL` 不阻断 `build`（build 会降级登记），
但 `result.status` 因此最多为 `partial`——宁可变 partial，也不把未通过写成通过。

## 9. 降级分支表（异常处理，全部 exit 0）

| 情况 | 识别 | 处置 | 可见结果 |
|---|---|---|---|
| 加密 PDF | 尾部 `/Encrypt` | 不解密即跳过该文件 | `skipped: encrypted_pdf` |
| 损坏 PDF | 无对象/流解压全失败 | 跳过，保留哈希与字节数 | `skipped: corrupt_pdf` 或 `parse_failed` |
| 无文本层/扫描件 | 页均字符 <40 或无 `/Contents` | 不造正文；`/Annots` 仅可对齐时记低置信 `region_mark` | `skipped: no_text_layer` |
| 编码乱码（CID 字体） | 可读字符占比 <0.75 | 标 `text_layer=garbled`，只引用逐字命中片段 | `skipped: garbled_text_layer` |
| 坐标漂移 | quad 与文本项不相交 | 回退 `nearest_line`（±30pt）降置信；仍失败记 `note_only` | `anchor_method` + `A105` |
| 双栏/跨页 | 同一 y 带两簇 x | 按 x 簇切列、按列顺序拼段；跨页引文按页拆条 | `locator` 与 `paragraph_id` |
| 低置信批注 | `anchor_confidence<0.5` | 保留但只在 `partial` 卡里可用 | `skipped: low_confidence` |
| 旧版本批注 | 版本组内非 canonical | 锚点保留 `source_version`；引用时 `boundary` 须写版本差异 | `uncertainties: stale_version_annotation` |
| 重复文件/别名 | sha256 相同或 shingle 容器率 ≥0.85 | 归并为版本组，canonical 规则见 §10，别名入 `library_index.aliases` | `recovery_log.jsonl` |
| 权限不足 | `os.access` 失败或读抛错 | 登记路径与 errno | `skipped: permission_denied` |
| 导出批注指向不存在的文件 | 路径不匹配 | 按文件名/标题唯一匹配，否则记孤儿 | `skipped: orphan_annotation` |
| 工作稿缺失/损坏 | 无 `draft.json` 或 JSON 非法 | 兜底：anchor-only 占位卡（`claim=null, status=unsupported`）+ 全量锚点底账 + 检索视图写未命中原因 | `status=partial` + `degradations: draft_missing` |
| 契约键无法识别 | 键名不匹配语义表 | 保留键名给 `null` | `degradations: contract_field_unmapped:<key>` |
| 单文件解析异常 | 任一 `try` 抛错 | 只降该文件，其余继续 | `errors` + 该文件 `skipped` |

## 10. 重复、别名与版本合并规则

1. **完全重复**：`sha256` 相同 → 同内容组；canonical = 文件名最短且不含 `(1)|copy|副本|~$` 者（并列取版本秩）。
2. **别名**：`case.json.aliases` 显式映射 > 文件名规范化（去 ` (1)`、`copy of`、`副本`）> 标题/DOI 匹配。别名不删文件，
   只写 `library_index.aliases[]` 与 `recovery_log`。
3. **版本**：同 work（同标题/同 DOI/文本容器率 ≥0.85）内按 `版本秩 = (显式版本号, final|终稿 标记, 管理性说明加成, 是否副本, mtime)` 排序；
   最高秩为 canonical，其余标 `v*`。`case.json.version_notes`（`supersedes/replaces/取代/最新`）优先于机械排序。
4. **跨版本批注归并**：同 work 内 `quoted_text` 规范化后相同的锚点互标 `cross_version_peer`，卡可同时引用多条；
   锚点底账**永不删条目**（合并只在同文件同位置同引文、来源不同时发生，且保留 `merged_from`）。

## 11. 预算与断点

`init` 通常 <10 秒（9 文档级），`build` <3 秒；单文件 40MB / 400 页封顶，超出记 `degradations: page_cap`。
任何命令都先写/后写 `result.json`，中途崩溃仍有合法结果；`desk/index.json` 缓存解析，`--reindex` 强制重建。

## 12. 自查清单（交付前逐条过）

1. 五个子命令均 exit 0；`init` 后 `result.json` 已存在且合法。
2. 契约键齐全、`case_id` 原样、信封字段齐全、错误项都带 `kind`。
3. 四层产物非空：`cards/`、`anchors/`、`views/`、`provenance/`。
4. 抽 3 条锚点：`show --anchor <id>` 的该页原文里能找到 `quoted_text`，页码/locator 一致。
5. 每张 `grounded` 卡的 `claim` 不等于任何锚点原文，且 ≥1 个锚点通过 G1。
6. 每条边有 `basis`；每个问题有命中或 `not_found_reason`。
7. `provenance.json` 有版本/哈希/一致率；`skipped.json` 每条有 reason。
8. 空输入 / 坏 JSON / 缺工作稿均 exit 0 且结果合法（partial，缺口写明）。
9. 包内无硬编码答案、无 `__pycache__`/`.pyc`。

## 13. 最小调用示例（示例数据，非正式案例结果）

`/input/case.json`（节选）：

```json
{"case_id": "EXAMPLE-DESK-01",
 "task_instruction": "整理库内批注，产出可复用知识卡，并回答：qDTY12.1 在干旱下是否稳定提高产量？",
 "output_contract": {"case_id": "原样保留", "status": "ok|partial|failed", "cards": "知识卡",
                     "anchors": "锚点底账", "library": "资料清单与版本", "retrieval": "问题→卡",
                     "coverage": "覆盖统计", "provenance": "溯源"},
 "questions": [{"id": "q1", "question": "qDTY12.1 在干旱下是否稳定提高产量？"}]}
```

```bash
python3 scripts/main.py init --input /input --output /app/output --work /app/work
python3 scripts/main.py show --section anchors --limit 12
# 读原文后在 /app/work/draft.json 写 3 张卡
python3 scripts/main.py check && python3 scripts/main.py build && python3 scripts/main.py selfcheck
```

示意输出（示例，非正式案例结果）：

```json
{"case_id": "EXAMPLE-DESK-01", "status": "partial",
 "result": {"cards_grounded": [{"card_id": "c01", "kind": "result", "status": "grounded",
   "claim": "携带 qDTY12.1 的品系在旱季优于对照，但优势随地点变化",
   "anchor_ids": ["a-1f3c9b2e-p1-01"], "strength": "moderate", "boundary": "仅限该试验两个旱季点位"}]},
 "anchors": [{"anchor_id": "a-1f3c9b2e-p1-01", "file": "paper.pdf", "type": "highlight",
   "page_physical": 1, "locator": "p1:p1.1:c0-c56", "quote_verified": "exact",
   "quoted_text": "Rice lines carrying qDTY12.1 showed 28% higher grain yield."}],
 "degradations": [{"kind": "no_text_layer", "file": "scan_fig.pdf", "detail": "0 字符，已跳过"}],
 "uncertainties": [{"kind": "stale_version_annotation", "detail": "v1 批注未在 v2 命中"}]}
```

## 14. 文件清单与维护

| 文件 | 作用 |
|---|---|
| `SKILL.md` | 本文件：用途、五命令主路径、契约、五关卡、降级表、自查 |
| `scripts/main.py` | CLI 与编排：`init/show/check/build/selfcheck`、契约回填、无条件 finalize、兜底 |
| `scripts/extract.py` | 载体解析：PDF 内容流+`/Annots`、DOCX comments/highlight/修订、HTML、MD/TXT；归一化与颜色词典 |
| `scripts/library.py` | 库模型：发现、装配、锚点生成与逐字校验、覆盖统计 |
| `scripts/versions.py` | 重复/别名/版本归并与恢复动作 |
| `scripts/gates.py` | G1–G5 关卡校验与 gate 派生视图 |
| `scripts/render.py` | 四层产物渲染 + `result.json` 组装 |
| `references/card_schema.md` | 全部产物与 `draft.json` 的字段级 schema、错误码表、归一化约定 |

约定：新增字段只加不改名；`schema` 字符串（`reading-card-desk/{anchors,cards,graph,library,provenance}@1`）用于版本识别。
改锚点算法须同步 `references/card_schema.md` §4 与 SKILL §8；改字段须同步 §6 与 schema 文档。
已知限制：不内置 OCR（无文本层只登记不猜）；PDF 文本坐标是内容流近似值，双栏用 x 聚类校正而非精确排版；
DOCX 无固定分页，故 `page_physical=1` 且以段落定位；印刷页只在页眉页脚有独立页码时可得；实体/方法级关联依赖工作稿显式声明。
