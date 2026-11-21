---
name: research-file-locator
description: 科研文件库的定位级检索与回链：脚本对材料库做章节/段落切分、编码判定、别名与同义扩展、哈希去重与版本链识别、硬过滤执行与页码映射，生成逐 query 的候选工作稿；Agent 裁决后在 build 中逐字校验引文与 locator，产出 answers/hits/dedupe/failures/filters_log/location_report/result.json，并把 output_contract 每个键回填到顶层与嵌套。Use when a case ships a research file library (PDF/Word/Excel/PPT/扫描件/重名副本) plus search queries and hard filters, and asks for section-level located evidence with verbatim quotes and page/paragraph locators.
version: 1.1.0
---

# 科研文件库定位检索（research-file-locator）

## 0. 本包声明的契约（output_contract）与单命令入口

`result.json` 必须回填下面每个键（键名不改、不并、不删）；案例自带 `case.json → output_contract` 时以案例为准，本声明只在案例未声明契约时生效（见 §7）。

```json
{"output_contract": {"id": "string", "root": "string", "terminology": "string",
  "aliases": "string", "encoding": "string", "not_applicable": "string",
  "container": "string", "older_version_of": "string", "evidence_ban": "string",
  "impact": "string"}}
```

**单命令入口**（single command / 一次性跑完全管道）——不写任何工作稿也能一次产出全部交付物与完整契约回填：

```bash
python3 -B /skills/weekly-skill/scripts/main.py all --input /input --out /app/output --work /app/work
```

`all` 依次做 `init`（建索引 + 先写合法 partial `result.json` + 生成候选工作稿）→ `build`（裁决 → 全部交付物 + 最终 `result.json`）→ `selfcheck`（契约键/产物/异常路径复检），恒 exit 0；缺 `draft.json` 时走 §8 兜底，产出「完整但降级」，绝不产出空目录。等价入口是 `build`。

## 1. 适用条件与三条红线

把「文件库 + 检索提问 + 硬过滤」变成**章节级定位结果**：每 query 给出直接答案或如实标记 `not_found`/`blocked_by_filter`，附逐字 `quote` 与 locator。适用：PDF（印刷页/物理页不一致）、Word/Excel/PPT、CSV、扫描件、无权限文件、重名副本与多版本同文；提问要求定位到章节段落并给页码；带硬过滤（年份/版本/批次/项目/权限）。不适用：翻译、写作润色、统计、建模、排版。

**① 不虚报定位**：`quote` 必须逐字一致，页码/段落编号错了就降为 `partially_answered` 并记 `rejected_evidence`。**② 不放宽过滤**：被硬过滤挡住的 query 必须如实写 `blocked_by_filter`。**③ 不覆盖原始文件**：材料只读，`init` 计 sha256，`build` 复算，不一致记 `source_mutated`。

## 2. 运行契约

| 项 | 值 |
|---|---|
| 入口 | 单命令 `python3 scripts/main.py all`；Agent 路径 `python3 scripts/main.py <init\|show\|check\|build\|selfcheck\|fixtures>` |
| 参数 | `--input /input`、`--out /app/output`、`--work /app/work`、`--case`、`--draft`、`--doc`/`--grep`/`--limit`/`--full`（show 过滤）、`--quiet` |
| 依赖 | 仅 Python 3 标准库；不联网；不依赖 CWD |
| 退出码 | **恒为 0**；失败写进 `result.json` 的 `errors`/`degradations`，不抛栈给 Harness |
| 第一落盘 | 处理前先写 **合法 partial** `result.json`（契约键全回填），结束时无条件 finalize |
| 日志 / 预算 | `work/run.log` 追加 `命令/耗时/摘要`；900 秒、64 次模型请求（脚本侧 0 次） |

## 3. 两态入口

```bash
python3 scripts/main.py init       # 建索引 + 生成 work/draft.candidates.json（逐 query 预填候选引文与过滤状态）
python3 scripts/main.py show       # 打印带 locator 的候选清单与原文片段，供 Agent 逐字引用
#  Agent 亲自读材料，把候选复核/改写成 work/draft.json（未写则 build 走候选兜底）
python3 scripts/main.py check      # 机械校验：契约键、locator 可回链、quote 逐字、过滤执行、覆盖完整性
python3 scripts/main.py build      # 由工作稿生成主产物 + 最终 result.json
python3 scripts/main.py selfcheck  # 复检：契约键回填、产物齐全、异常路径（fixtures）自动验证
```

`init` 只发现不结论；`show` 让 Agent 引用**逐字原文**（locator 形如 `materials/guide.md#pD1-p3@0`：文件 → 段落 → 页码）；`check` 是机械门禁；`build` 无工作稿也必产出完整最小交付（§8）；`selfcheck` 用独立路径重数一遍，写 `verify_report.json`。

## 4. 输入发现、目录模板与元数据金标准

1. 读 `/input/case.json`；缺失则递归找 `*case*.json`；坏 JSON 记 `errors` 并继续扫材料。
2. 保留 `case_id` 与 `output_contract` **原样**；库根缺省按 `materials|library|corpus|docs|files` 语义择根并记 `root_source`。
3. 递归 `/input/**` 分类：**PDF**（对象流 + Flate 解压取文本层）、**OOXML** `.docx/.xlsx/.pptx`（zip + XML 直读）、`.csv/.txt/.md/.html`、**扫描件**（无文本层）、**legacy** `.doc/.xls/.ppt`（`unsupported_legacy`）；`.pyc/.git/node_modules` 跳过。
4. 编码判定 `utf-16(BOM) → utf-8-sig → utf-8 → gb18030 → cp1252 → latin-1`，按替换字符数与 mojibake 标记数打分取最优并记 `encoding`。
5. **目录模板**（可复用题集布局）：

```text
/input
├── case.json                # case_id, language, materials_root, output_contract, queries[], filters[]
├── task.md                  # 任务说明（可选，语义识别，不假设文件名）
└── materials/               # 库根；子目录任意，名称即定位的一部分
    ├── doc.pdf|.docx|.xlsx|.pptx|.csv|.md
    └── archive/doc-v2.pdf   # 旧版：进版本链，不进证据
```

**元数据金标准**（`index.json → docs[]`）：`doc_id`、`path`、`type`、`bytes`、`sha256_16`、`encoding`、`status`、`sections[]`（`section_id`/`title`/`level`/`container`）、`paragraphs[]`（`paragraph_id`/`text`/`page_physical`/`page_printed`）、`aliases[]`、`version`、`representative`、`pages{count,label_source}`。

## 5. 索引与检索模型

**切分**：按标题层级（`#`、编号、`第X章/节`、全大写行）切**章节**，再按空行/句末标点切**段落**并编号；双粒度保证引用可回链。**页码映射**：PDF 优先 `/PageLabels`，退化链「源码页码声明 → 页脚抽样 → 物理页偏移 `assumed_equal`」；无固定页容器（PPT/CSV/纯文本）记 `not_applicable`，改用章节+段落。**同义/别名**：内置 `SYN` + 案例 `synonyms`，按词频与标题加权打分，`aliases` 参与打分但不改写原文。**去重与版本链**：同哈希 → `identical_copy`；同族近似 → `version_chain`，只留 `representative` 进证据，其余进 `excluded_evidence` 并记 `evidence_ban`。**硬过滤**：全局与 query 级 `filters` 逐条求值并写 `filters_log.json`；不可满足时标 `blocked_by_filter` 并列出被挡候选（`rejected_evidence.reason=violates_filters`）。

## 6. 工作稿 `work/draft.json`（Agent 写入）

```json
{"case_id": "string",
 "queries": [{"query_id": "string", "question": "string",
              "status": "answered|partially_answered|not_found|blocked_by_filter",
              "answer": "string",
              "evidence": [{"path": "materials/x.pdf", "section": "3.2", "paragraph_id": "p7",
                            "page_physical": 12, "page_printed": 10, "quote": "逐字原文"}],
              "filters_applied": ["year=2023"], "notes": "string"}],
 "excluded_evidence": [{"path": "materials/archive/x-v2.pdf", "reason": "evidence_ban"}],
 "method_notes": {"index_granularity": "section+paragraph"},
 "uncertainties": [{"item": "string", "detail": "string"}]}
```

`init` 生成 `work/draft.candidates.json`（每 query 预填最高分候选的逐字 quote 与 locator，`notes` 标注 `candidate_evidence_only`）与 `work/draft.template.json`；Agent 只确认或修改即可，降低漏答与错答。

## 7. 定位、回链与契约回填

每条 `evidence` 在 `build` 中逐字校验：`quote` 必须能在该段落文本中按空白归一后**完全匹配**；`path` 必须在索引内；`paragraph_id`/页码必须与索引一致；容器无页时页码写 `not_applicable` 并改记段落号。任一不成立则该条进 `rejected_evidence`（`reason` ∈ `document_not_found|document_<status>|non_representative_document|violates_filters|quote_<原因>`），并可能把该 query 从 `answered` 降为 `partially_answered`。每条证据带 `sha256_16`、来源路径与操作日志，可独立复核。

契约回填：十键同时写入 `result.json` 顶层与 `result.json → output_contract`；每键的值是一条实质投影（非空 dict，含 `source`/`field`/`rows`），不是占位符：

| 键 | 投影来源 | 含义 |
|---|---|---|
| `id` | `index.docs[].doc_id` | 文档唯一标识 |
| `root` | `index.library_root` + `scan_stats` | 库根与扫描数 |
| `terminology` | `rules.SYN` + `synonyms` | 术语与同义变体、命中文件 |
| `aliases` | `index.docs[].aliases` | 文档别名 |
| `encoding` | `index.docs[].encoding` | 编码判定结果 |
| `not_applicable` | `docs[].pages.label_source` | 无固定页容器的页码不适用声明 |
| `container` | `docs[].sections[].container` | 章节所属容器（章节/页/工作表/幻灯片） |
| `older_version_of` | `dedupe.groups[kind=version_chain]` | 旧版 → 代表版本 |
| `evidence_ban` | `index.excluded_evidence[]` | 被禁引用的副本/旧版及原因 |
| `impact` | `index.failures[].impact` | 解析失败的后果 |

## 8. 交付产物与降级矩阵（`draft.json` 缺失也必须成立）

**`/app/output`**：`result.json`（主产物）、`index.json`、`answers.json`、`hits.jsonl`、`dedupe.json`、`failures.json`、`filters_log.json`、`location_report.md`、`verify_report.json`。**`/app/work`**：`draft.candidates.json`、`draft.template.json`、`queries.json`、`filters_ledger.json`、`index.json`、`fixtures/`、`fixtures_report.json`、`check_report.json`、`selfcheck_report.json`、`run.log`。

| 情况 | 行为 | 记录 |
|---|---|---|
| 无 `draft.json` | 候选检索兜底：取最高分段落作逐字引文，`status=partially_answered`，`notes=candidate_evidence_only` | `degradations[].item=draft` |
| 候选也定位不到 | 写候选清单（top3）但 `status=not_found`，`notes=candidate_only` | `errors` + `uncertainties` |
| 不得放宽过滤 | 返回 `blocked_by_filter` 并列出被挡候选 | `rejected_evidence` |
| 加密/无文本层/损坏/空/legacy | 不进证据，进 `failures.json` + `excluded_evidence` | `impact` 键投影 |
| 权限受限文件 | 只登记路径与大小，不进证据 | `status=permission_denied` |

## 9. 最小调用示例（示例，非正式案例结果）

```bash
python3 -B scripts/main.py all --input /input --out /app/output --work /app/work
python3 scripts/main.py init
python3 scripts/main.py show --grep 批号 --limit 40
#  读 show 输出，写 ./work/draft.json
python3 scripts/main.py check
python3 scripts/main.py build
python3 scripts/main.py selfcheck
```

示意输出（示例）：`[build 1.1.0] case=demo status=partial queries=3 evidence=1 quote_hit_rate=1.0 fails=[]`。

## 10. 评估、自查与边界

同库同问同权限下基础 Agent 与本 Skill 的命中率、定位准确率、回链可靠性与耗时对照见 `references/eval.md`；`verify_report.json` 记录独立复核数（引文逐字率、locator 一致率、过滤执行率），`runtime.budget` 记录调用预算。`selfcheck` 自动核对契约十键（顶层+嵌套）、产物齐全、引文可回链、异常路径（加密/扫描件/损坏/空/legacy/权限/重名副本，见 `work/fixtures_report.json`，`all_expected` 与 `duplicate_ok` 均为真）。边界：超大二进制只登记不读取；页码不可得时声明 `not_applicable`；重复运行 `index_digest` 稳定。维护见 `SELFTEST.md`、`README.md`、`GAIN_EVIDENCE.md`。
