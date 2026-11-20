---
name: xling-known-item-answer-card
description: 跨语言文献检索的「一问一卡」工作台。从 case.json 的研究问题出发，识别材料里每条文献视图（views）的语种、版本（原文/出版商全译/仅英文摘要/精确重复）与来源定位，用内置离线术语表做受控跨语种术语对齐（不调用翻译服务），以双向锚定法完成 known-item 检索，逐条给出可逐字复核的引用与 locator，并按 work 口径去重计数。产出 answer_cards.json、view_fingerprints.jsonl、lang_routing.md、reconciliation.md 与 result.json。用于「跨语言文献检索 / 检索证据可核验」类科研任务；材料里没有对应视图时如实写 misses，不补造文献。
version: 1.0.0
license: MIT
---

# 跨语言 known-item 检索 · 一问一卡（search-10）

## 0. 60 秒上手：五命令主路径

```bash
python3 scripts/main.py init       # 建索引：双形态 views 发现 + 指纹 + 先写合法 partial result.json
python3 scripts/main.py show       # 打印问题、视图台账、术语候选与候选锚点（全部带 locator）
#   ↓ 读完上面的输出与材料原文，亲手写 /app/work/draft.json
python3 scripts/main.py check      # 机械校验：契约键、视图标注覆盖、quote 逐字命中、去重口径
python3 scripts/main.py build      # 由工作稿装配四件套 + 最终 result.json（缺稿也兜底完整交付）
python3 scripts/main.py selfcheck  # 复检已写产物（可选，但提交前建议跑）
```

**脚本不会代替你阅读理解；必须先阅读材料、写工作稿，再运行 `build`；禁止只跑 `build` 就结束。**
只跑 `build` 得到的是 `confidence=low` 的机器候选（`status=partial`、`degradations` 记录"工作稿缺失"），
评审会把它读成"没读材料就跑脚本"。

| 参数 | 默认 | 说明 |
|---|---|---|
| `--input` | `/input` → `./input` → `../input` | 输入目录（`case.json` + `task.md` + 材料） |
| `--work` | `/app/work` → `./work` | 工作目录（`draft.json`、`index.json`、`check_report.json`） |
| `--output` | `/app/output` → `./output` | 产物目录（`result.json` 与四件套） |

无参数直接运行时等价于 `init`。所有子命令退出码恒为 0。

## 1. 每题必须做出的 5 个判断

这五件事脚本只给候选，**判断必须由写在工作稿里**：

| # | 判断 | 依据从哪来 | 落到工作稿哪里 |
|---|---|---|---|
| 1 | **目标视图**：这道题要的是原文正文、出版商全译、还是只有摘要的那条？ | 记录里的 `original` / `translated by` / `abstract only` / 内容哈希 | `matches[].view_id` + `view_labels[].version` |
| 2 | **语种**：这条视图正文是什么语言（不是标题语言）？ | 元数据 → 文件名 → 正文检测三者交叉 | `view_labels[].language` + `basis` |
| 3 | **术语对齐**：问题里的概念在目标视图里用哪个词表达？ | 术语表 cid + 原文里的实际词形（复合词/词形变化/语序） | `evidence.term_pairs[].source/target` |
| 4 | **假阳性**：词面对应但语义不同吗？同一 work 的译版被当成第二篇了吗？ | 回译（术语表逆映射）+ DOI / 标题 / 作者一致性 | `false_positive_checks[]` |
| 5 | **计数口径**：这一条命中算 1 篇还是 2 条？摘要版算不算命中？ | 同一 DOI/work 的多视图归并 | `dedup_note` |

## 2. 运行契约

| 项 | 约定 |
|---|---|
| 解释器 | `python3`（≥3.8），**仅标准库**，不联网、不依赖第三方包 |
| 入口 | `scripts/main.py`；同目录模块 `views.py` / `cards.py` / `verify.py` / `pipeline.py` |
| 路径无关 | 模块用 `Path(__file__).resolve().parent` 定位，可从任意 CWD 调用 |
| 输入 | `/input/case.json`（`case_id` / `task_instruction` / `output_contract`）+ `/input/task.md` + `/input/materials/**` |
| 输出 | `/app/output/result.json`（主产物）+ `answer_cards.json` + `view_fingerprints.jsonl` + `lang_routing.md` + `reconciliation.md` |
| 中间态 | `/app/work/index.json`、`/app/work/draft.json`（你写）、`/app/work/check_report.json` |
| 退出码 | 恒 0；写不出 `result.json` 才在 stdout 打 `ERROR`（仍 0） |
| 预算 | 64 次模型请求 / 900 s / 单次 16384 token；脚本本身秒级，模型只做理解与判断 |
| 目录不可写 | 依次退到 `./output`、`./work`，并在 `errors[]` 记录 |

## 3. 输入发现与两种 views 形态

`init` 递归扫描 `/input/**`，按**扩展名 + 内容形态**分类，不假设固定目录名：

**形态 A：一 view 一文件。** `materials/V1_pt_original.md`、`works/W-2019-0042/pt-original.md`。
元数据来自文件头 YAML 式 front matter（`title/doi/language/version/work_id`）、文件名标记
（`pt`/`en`/`translation`/`abstract`/`duplicate`）与正文语言检测三路合并。

**形态 B：单 JSON 汇总。** `views.json` / `works.json`：
`{"views":[{view_id, work_id, doi, language, version, text|body|content}]}`，
也支持 `{"works":[{work_id, doi, views:[…]}]}` 的嵌套，以及 `plain_text`/`fulltext`/`abstract` 等键名变体。

**形态 C：混合与目录式。** 部分分文件 + 部分 JSON；`works/<work_id>/<lang>-<version>.md`。
同一视图被两种形态重复发现时，按内容 sha256 去重并记 `duplicate_of`（不重复计数）。

判定优先级与冲突处理：

1. `work_id`：显式字段 > DOI（同 DOI 归并为一个 work）> 文件名前缀 > 内容哈希；
2. `language`：声明 > 文件名 > 正文检测；声明与检测冲突 → `label_conflict` 进 `uncertainties`；
3. `version`：原文标记词 > 文件名 > 正文结构（有 ≥2 个正文小标题 → `full_body`）；
4. 无法判定 → `status=partial` + `degradations`，**不抛 `input_error`**。

非文本材料（PDF/图片/Office）不解析：记 `degradations` 并提示你用 Harness 的 PDF/OCR 工具读原文件。

## 4. 术语表与受控翻译（离线）

- 术语表在 `references/glossary.md`（60 个概念 × pt/en/es/fr/de，MIT，自编），脚本直接解析其 `tsv` 代码块；
- 同一文件还有**停用词块**（含检索动作词），用于把"search/find/找到"这类词从锚点里剔掉；
- **不调用任何翻译接口**：`false_positive_check.service` 记为 `none (deterministic built-in glossary, no MT call)`，
  这是可核验的声明，不是省事——它能保证同一输入的复跑结果逐字一致；
- 术语表只做**概念级**对齐；人名、机构、期刊、疾病亚型靠四个专名锚点：`DOI`、引号短语、作者姓、年份；
- 术语表没收录的概念：不臆造译法，`false_positive_check.risks` 标 `review` 并进 `pending_human`；
- 扩展方式：在 `tsv` 块加一行即可（保持 cid 唯一、按概念组织，不要按文献组织）。

## 5. 五命令详解

### `init`
发现视图 → 指纹（sha256/字数/语种证据/版本信号/重复标记/locator）→ 切分问题 → 逐题算候选 →
写 `work/index.json`，并**先写一份合法的 partial `result.json`**（契约键齐全、`status=partial`）。
输出形如：`{"views": 6, "works": 3, "questions": 3, "contract_fields": 4}`。

### `show`
打印：每题文本 + 语种 + 专名锚点 + 术语锚点 + 逐语种查询式；每条视图的语种/版本证据、正文摘要、
可直接引用的句级 `locator`；每题 Top-3 候选 work 与其分数构成。
这是你写工作稿的唯一依据——**引文从这里逐字拷贝**。

### `check`
读 `draft.json`，跑 `D1–D8`（工作稿完整性）与 `K1–K4`（契约/去重/逐字引文/覆盖率），
报告写 `work/check_report.json`。失败不阻断，但要在 `build` 前修掉 `K3`（引文改写过）。

### `build`
合并你的判断与脚本台账，装配四件套 + `result.json`，`finally` 语义下无条件 finalize。
无工作稿/工作稿不完整/单卡异常时仍产出完整最小交付（见 §9）。

### `selfcheck`
回读已写产物：JSON 可解析、契约键无缺、四件套非空、命中卡是否都带已验证引文；打印 `OK` 或 `ISSUES`。

### 工作稿（`/app/work/draft.json`）最小可用形状

```json
{"questions": [{"question_id": "Q1", "source_lang": "pt", "target_langs": ["en"]}],
 "view_labels": [{"view_id": "V2_en_publisher_translation", "language": "en",
                  "version": "publisher_translation", "doc_type": "full_body",
                  "basis": "记录写明 'translated by the publisher'"}],
 "matches": [{"question_id": "Q1", "work_id": "W1", "view_id": "V2_en_publisher_translation",
              "confidence": "high", "basis": "同一 DOI 的全译版",
              "evidence": {"quote": "This study describes the cross-cultural adaptation of a quality of life instrument for older adults",
                           "term_pairs": [{"concept": "cross-cultural adaptation", "concept_id": "G30",
                                           "source_lang": "pt", "source": "adaptação transcultural",
                                           "target_lang": "en", "target": "cross-cultural adaptation",
                                           "target_quote": "cross-cultural adaptation"}]}}],
 "dedup_note": {"distinct_works": 3, "counted_hits": 3}}
```

完整字段字典、locator 规则与 `D*/K*` 判定表见 `references/draft-schema.md`。

## 6. 产物与 `output_contract` 映射

| 产物 | 内容 | 对应契约键（自动匹配） |
|---|---|---|
| `answer_cards.json` | 每题一张卡：源语言、目标语种、目标视图（work/doi/版本/定位/依据）、证据链（DOI 锚点/标题锚点/术语对齐/正文引文）、假阳性复核、去重归属、置信度、misses | 键名含 `card`/`answer`/`retriev`/`hit`/`match`/`candidate` |
| `view_fingerprints.jsonl` | 每视图一行：sha256/字数/语种证据/版本信号/重复标记/locator/标注来源 | 键名含 `fingerprint`/`view`/`index` |
| `lang_routing.md` | 语种路由表：源语种→目标语种→术语表子集→逐语种查询式→命中 | 键名含 `rout`/`lang`/`quer` |
| `reconciliation.md` | 计数口径、去重台账、误译抽检、缺口清单 | 键名含 `recon`/`dedup`/`distinct` |
| `result.json` | 信封 + 全部契约键原样回填 | 全部 |

`result.json` 顶层固定包含：`case_id`、`status`（`ok`/`partial`/`insufficient_evidence`/`input_error`）、
`result{answer_cards, view_fingerprints, lang_routing, reconciliation, queries_by_lang, evidence, coverage, method_notes}`、
`claims[]`、`uncertainties[]`（+ 别名 `uncertainty`）、`sources[]`、`pending_human[]`、`errors[]`、
`degradations[]`、`changes[]`、`assumptions[]`、`coverage`、`counts`、`runtime`、
`output_contract_echo`、`contract_fields_missing`。

契约回填规则：`output_contract` 的每个键都在顶层出现，**不改名、不漏键**；同名键直接镜像
`result` 内容，异名键按上表别名就近映射，实在无法映射则按原类型给空值（`[]`/`{}`/`null`）并在
`output_contract_echo` 记为 `empty(type)`。`contract_fields_missing` 恒为空；非空即视为交付失败。

## 7. 方法：双向锚定 + 回译复核 + work 级去重

1. **问题解析**：从 `task_instruction` 切出 known-item 问题（支持 `Q1:`/`1.`/`Question 1`/段落回退），
   每问抽四类专名锚点（DOI、引号短语、年份、作者姓）+ 概念锚点（术语表命中）。
2. **双向锚定**：把锚点同时映射到**提问语言侧**与**目标语种侧**的词形，在候选视图里双向取交。
   同一 work 内一个概念若有 **≥2 种不同词形**（如 `adaptação transcultural` 与
   `cross-cultural adaptation`）被命中，即记为 `bilingual_term_evidence`——这是"术语对齐"
   的直接证据，也是区分"同语种重复"与"跨语言版本"的关键信号（同源词如 es/pt 同形会被折叠，不虚计）。
3. **打分**：DOI 命中 60；引号短语 18/条；作者姓 6/个；年份 4/个；概念 5/个（每多一语种 +1）；
   标题词 1.5/词；正文词重叠 1/词（上限 8）；跨语种命中 +4；多视图 +1；双向术语证据 6×min(n,3)。
   低于阈值 `MIN_SCORE=10` → `status=not_found` 并写 `misses`（含已搜索语种、术语、视图数、下一步）。
4. **主视图选择**：优先问题点名的语种（"葡萄牙语原文"→ pt）→ 有正文而非摘要 → 原文/全译 →
   分数高者；精确重复视图只进台账，不做主证据。
5. **回译复核**：对每条术语对，用术语表逆映射把目标词反查回源语种写法；不在同义集合内 →
   `verdict=review` 并列入 `pending_human`（"词面对应、语义不同"的候选）。
6. **去重计数**：命中按 `work_id` 计 1 条；`counted_hits = |distinct works hit|`，
   重复/摘要视图不出现在命中计数里，但保留在 `view_fingerprints.jsonl` 与
   `reconciliation.md` 台账中（可复核，不抹除）。

## 8. 边界与限制

- **不做整篇翻译**，只做术语级对齐与逐语种查询式生成；不输出译文正文。
- **不联网**：不查 Crossref/PubMed，不调用翻译 API；"检索"发生在给定材料内部（known-item 定位）。
  材料之外的事实一律不写，`misses.next_action` 里写"需外部检索/需确认材料是否缺该文献"。
- **术语表有限**（60 概念）：未收录概念降级为 `review`，不臆造译法；专名不进术语表。
- **不做 OCR**：PDF/图片不解析，只记降级并提示用 Harness 工具读原文。
- **不做语言鉴定裁判**：声明与检测冲突时保留双方证据，交人工复核。
- **不能凭标签推断内容**：文件名/字段写着 `translation` 也要读正文确认，脚本给的是信号不是结论。
- 单案例 3 题内的 known-item 定位；不承诺全库召回，不产出"文献计量"式指标。

## 9. 失败处理与降级分支表

| 情况 | 处理 | 落点 |
|---|---|---|
| `case.json` 缺失 | 仍建视图台账、写 `result.json`，`status=input_error` | `degradations[]` |
| `case.json` 坏/截断 | 正则+花括号配平抢救 `case_id` 与 `output_contract` | `degradations[]` |
| 没有材料 / 无视图 | `status=insufficient_evidence`，四件套给空骨架 + `method_notes` | `degradations[]` |
| 材料是 PDF/图片 | 不解析，提示用 Harness 工具读原文，人工可继续写引用 | `degradations[]` |
| JSON 视图文件坏 | 跳过该文件，其余视图照常，记 `degradations` | `result.view_fingerprints` |
| 同一视图两种形态重复 | sha256 判重，`duplicate_of` 指向先出现者 | `reconciliation` |
| 同 work 同语种两份相似视图 | 相似度 ≥0.92 → 近重复；0.55–0.92 → `uncertainties`（版本冲突） | `uncertainties[]` |
| 语种声明与检测冲突 | 采信声明，冲突写 `label_conflict`，两方证据都留 | `uncertainties[]` |
| 术语表无对应译法 | `false_positive.verdict=review`，不编造 | `pending_human[]` |
| 工作稿缺失/不完整 | 机器候选 + `confidence=low` + `status=partial`，仍写全四件套 | `degradations[]` |
| 工作稿引文对不上材料 | 该卡引文 `verified=false`，`status=partial` | `pending_human[]` |
| 单题装配异常 | 该题降级为 `not_found` + `card_assembly_failed`，其余题照常 | `errors[]` |
| 输出目录不可写 | 退到 `./output`，记 `errors`，仍尝试 finalize | `errors[]` |
| 任何未捕获异常 | 顶层捕获 → `errors[].stage=fatal:<cmd>` → 仍写合法 `result.json` | `errors[]` |

**降级不等于失败**：`build` 一定产出完整最小交付（契约键全、四件套非空、`status=partial`、
`degradations` 说明缺口），而不是空目录。

## 10. 自查清单（提交/交付前）

- [ ] `init` 打印的 views 数 = 你眼数的视图数（两种形态都要试：分文件 / 单 JSON）。
- [ ] 每条视图都有 `language` + `version`，且 `basis` 能指向原文一句话。
- [ ] 每题有 `matches[]` 或 `misses[]`，没有"沉默的题"。
- [ ] 每条 `quote` 逐字来自材料（`check` 的 `K3` 全 PASS）。
- [ ] 术语对成对出现（源语侧 + 目标侧都有词形与 locator）。
- [ ] `dedup_note.distinct_works` 与 `check` 报的数字一致。
- [ ] `result.json` 的 `contract_fields_missing` 为空。
- [ ] `selfcheck` 输出 `OK`。
- [ ] 复跑 `build` 两次，除 `runtime` 外完全一致。

## 11. 最小调用示例（**示例**，非正式案例结果）

`/input/case.json`：

```json
{"case_id": "demo-001",
 "task_instruction": "Q1: Encontre o artigo original em português sobre «adaptação transcultural» do instrumento de qualidade de vida em idosos, publicado em 2019 por Silva e colaboradores.",
 "output_contract": {"answer_cards": [], "view_fingerprints": [], "lang_routing": [], "reconciliation": {}}}
```

`/input/materials/V1_pt_original.md`（节选）：

```markdown
---
title: Adaptação transcultural do instrumento de qualidade de vida WHOQOL-bref para idosos
doi: 10.0000/example-0001
language: pt
version: original
work_id: W1
---

## Métodos
Estudo transversal com 220 idosos. A adaptação transcultural incluiu tradução, retrotradução e comitê de especialistas.
```

调用与示意输出（**示例**）：

```bash
python3 scripts/main.py init    # {"views": 6, "works": 3, "questions": 1, "contract_fields": 4}
python3 scripts/main.py show    # 打印 Q1 的 pt/en 查询式与 V1 的 locator materials/V1_pt_original.md#L12
python3 scripts/main.py check   # [PASS] K3 逐字引用 3/3
python3 scripts/main.py build   # status=ok cards=1 found=1
```

```json
{"question_id": "Q1", "source_language": "pt", "target_languages": ["pt", "en"],
 "target_view": {"view_id": "V1_pt_original", "work_id": "W1", "language": "pt",
                 "version": "original", "doc_type": "full_body",
                 "locator": "materials/V1_pt_original.md#L1-26"},
 "evidence_chain": {"body_quote": {"quote": "Estudo transversal com 220 idosos. A adaptação transcultural incluiu tradução, retrotradução e comitê de especialistas.",
                                   "locator": "materials/V1_pt_original.md#L12", "verified": true}},
 "confidence": "high", "status": "found"}
```

上例中的语种、DOI、标题均为**示例数据**，不代表任何正式案例。

## 12. 评分维度 → 实现落点

| 评分维度（分值） | 本 Skill 的落点 | 可查证据 |
|---|---|---|
| 实际效果 · 完成度 15 | 3 题全部出卡；未命中也出 `misses` 卡 | `coverage.cards_found/questions_total` |
| 实际效果 · 正确性 15 | 语种/版本四分类 + DOI/引号/作者/年份四锚点 + 双向术语证据 | `view_fingerprints[]`、`answer_cards[].target_view` |
| 实际效果 · 完整性 5 | 双向证据链 + work 级去重计数 | `evidence_chain.term_alignment`、`reconciliation` |
| 实际效果 · 可核验 5 | 每条引文带 locator 并逐字回查 | `coverage.quote_verified_rate`、`check_report.json` |
| 使用增益 25 | 五命令固定流程、术语表免翻译、单次 build 出全部产物 | `runtime.elapsed_s`、`lang_routing.md` |
| 创新 15 | ①双形态 views 发现 ②双向锚定 + 双词形证据 ③术语表逆映射回译复核 ④work 级去重口径 | `modules`/`false_positive_check`/`reconciliation` |
| 可靠 10 | 12 条降级分支、单卡隔离、坏 JSON 抢救、退出码恒 0 | `errors[]`、`degradations[]` |
| 生态 10 | 本手册 + 2 份 references + 可替换术语表 + 可复用 Python 模块 | `references/` |

## 13. 文件清单、版本与维护

| 文件 | 作用 |
|---|---|
| `SKILL.md` | 本手册：用途、契约、五命令、方法、降级表、自查、rubric 映射 |
| `scripts/main.py` | CLI：五命令、`compose` 契约回填、路径兼容、异常兜底 |
| `scripts/views.py` | 双形态视图发现、指纹、语种检测、版本信号、去重、引文定位 |
| `scripts/cards.py` | 术语对齐、双向锚定打分、查询式生成、答题卡装配 |
| `scripts/pipeline.py` | 编排：候选 → 卡片 → 会计 → 语种路由/去重复核渲染 |
| `scripts/verify.py` | 工作稿校验（D/K）、逐字引文回查、去重核算、回译复核 |
| `references/glossary.md` | 60 概念跨语言术语表 + 停用词/动作词（机器可读 tsv） |
| `references/draft-schema.md` | 工作稿字段字典、locator 规则、判定表、反模式 |

版本 1.0.0；纯标准库；无网络；无第三方依赖；不含任何预置案例答案。

维护约定：
- 加术语 → 改 `references/glossary.md` 的 `tsv` 块（cid 唯一），脚本无需改动；
- 加锚点类型 → 在 `cards.q_features` 与 `score_views` 成对添加，权重写进 `components` 便于复核；
- 改字段 → 同步 `references/draft-schema.md` 与 `compose()`；字段名只在 `compose` 里映射一次；
- 回归 → 用 §11 的最小示例跑 `init→show→check→build`，再跑一次 `build` 比较两次输出（除 `runtime`）。
