---
name: federated-search-reconcile
description: Reconcile multi-database literature search snapshots into one deduplicated, field-traceable candidate set. Parses Crossref / EuropePMC / OpenAlex / Scopus / WoS / publisher JSON, HTML and CSV-JSONL exports, fingerprints each response, maps every field to its raw source path, clusters duplicate records by evidence voting, resolves field conflicts by declared precedence, and reports a database-by-field coverage gap matrix plus failed-query degradation notes. Use when asked to 多数据库联合检索、跨库去重合并、字段归一映射、保留筛选与来源依据、覆盖缺口与失败降级说明、把多份文献库响应合成一份可核验清单.
version: 1.0.0
license: MIT
---

# 多库联合检索对账器（search-05）

## §0 30 秒上手

```bash
python3 -B scripts/main.py init     # 解析 /input，建材料台账 + 记录索引，先写合法 partial result.json
python3 -B scripts/main.py show     # 打印库/记录/候选对/字段视图（带 locator），供逐字引用
#   ↓ 你（Agent）亲自读材料，写工作稿 /app/work/draft.json
python3 -B scripts/main.py check    # 机械校验：契约键、locator 命中、聚类覆盖、矩阵完整性
python3 -B scripts/main.py build    # 由工作稿装配五件套 + 最终 result.json（无条件 finalize）
python3 -B scripts/main.py selfcheck  # 复检（可选）
```

> **脚本不会代替你阅读理解；必须先阅读材料、写工作稿，再运行 build；禁止只跑 build 就结束。**
> `build` 在没有工作稿时确实能产出"契约齐备但降级"的结果（这是防 0 分的兜底，不是推荐路径）。兜底结果里每条记录的 `relevance.verdict` 会是 `unscreened`、`status=partial`、`degradations` 写明"未记录相关性判断"。这样的一份清单在"结果正确性/完整性/可核验"上都会明显低于你亲自读过材料后的版本。

## §1 你必须自己做的 7 个判断（脚本只给证据，不替你判断）

| # | 判断 | 脚本给什么 | 你写进 draft.json 的哪里 |
|---|---|---|---|
| 1 | 这个案例的研究问题与检索边界是什么 | `show` 打印 `case.task_instruction`、`task.md` 可引用行 | `research_question` / `scope` |
| 2 | 每份响应属于哪个库、用了什么查询语法（字段域、时间窗、分页、额度） | `show --view queries` 给每个文件的库猜测、响应形状指纹、内嵌 query 证据 | `query_matrix_notes[]` |
| 3 | 各库同名字段语义是否等价（如 publisher `published` vs Crossref `issued` vs EuropePMC `pubYear`） | `show --view rules` 给字段的原始路径与取值 | `normalization_overrides[]` |
| 4 | 两条记录是不是同一篇文献 | `show --view pairs` 给候选对 + 四路投票明细分 | `cluster_decisions[]` |
| 5 | 同一篇文献的冲突字段该取哪个值 | `show --view conflicts` 给成员取值与默认优先级 | `conflict_resolutions[]` |
| 6 | 哪些候选真的切题，排序依据是什么 | `show` 给标题/摘要/来源 locator，不发相关性判断 | `screening[]` / `ranked[]` |
| 7 | 哪些缺口是"材料没给"、哪些是"库里确实缺" | `show --view coverage` 给解析结果与失败库 | `coverage_notes[]` / `gaps[]` |

判断 1/6 是纯语义工作，脚本一律留白（`unscreened`），不会替你猜相关性；判断 2/3/7 脚本给证据、由你确认或改写；判断 4/5 脚本给可复算的投票分与优先级，你只需要对有争议的少数对/字段签字。

## §2 五命令与运行契约

```bash
python3 -B scripts/main.py init   [--input /input] [--work /app/work] [--output /app/output]
python3 -B scripts/main.py show   [--view all|files|records|pairs|rules|coverage|queries|conflicts|contract]
python3 -B scripts/main.py check  [--draft /app/work/draft.json]
python3 -B scripts/main.py build  [--draft /app/work/draft.json]
python3 -B scripts/main.py selfcheck
```

- **输入**：`/input/case.json`（`case_id` / `task_instruction` / `output_contract`）+ `/input/task.md` + `/input/**` 材料（Crossref `message.items`、EuropePMC `resultList.result`、OpenAlex `results`、Scopus `search-results.entry`、WoS `Records`、出版商 JSON/HTML meta、CSV/JSONL 导出、纯文本）。
- **工作区**：`/app/work`（`index.json` 缓存、`draft.json` 工作稿、`check_report.json`、`selfcheck.json`）。
- **产物**：`/app/output/` 五件套 + `result.json`。
- **兜底**：`init` 先写一份合法 `partial result.json`；`build` 结束时无条件 finalize 覆盖；任何异常都被捕获并降级，**退出码恒 0**。
- **路径**：脚本用 `Path(__file__).resolve().parent` 定位自身，装到 `/skills/weekly-skill` 或任意目录都可运行，不依赖 CWD；输入/输出目录可用参数覆盖，默认 `/input`、`/app/work`、`/app/output`，不可写时回退到包内 `./_work`、`./_output` 并记 `degradations`。
- **依赖**：仅 Python ≥3.8 标准库，不联网、不读密钥、不写包外路径。
- **预算**：全流程确定性计算，秒级；`runtime.elapsed_s > 780` 时后续阶段直接跳到 finalize。

## §3 产物族与契约映射

| 产物 | 内容 | 对应交付要求 |
|---|---|---|
| `intake_ledger.md` | 材料台账：每份响应的路径/字节/sha256/格式指纹/库归属/解析出的记录数/HTTP 与错误标记/字段可得性 | 输入标识、状态说明 |
| `query_matrix.csv` | 查询矩阵：行=库，列=主题词/字段域/时间窗/分页/查询原文/证据 locator/返回数/去重后条数/状态；并做**查询趋同性审计**（同一查询串被原样复制的库会被标记） | 检索范围、查询依据、效率证据 |
| `normalize_rules.json` | 跨库字段映射规则：规则 id、字段、语义、适用库、优先级、证据原始路径、`unknown` 与 `missing` 的判定口径，以及 Agent 的覆盖规则 | 字段归一、可复用配置 |
| `merge_cluster.jsonl` | 每行一个 canonical 记录：`cluster_id`/`rank`/`relevance`/`canonical{field:value+src_db+locator+rule}`/`members[]`（每条含 `rid`/`db`/`locator`/`raw_sha`/投票明细）/`merge_reason`/`conflicts[]` | 去重、合并、来源回溯、候选集 |
| `reconciliation.md` | 对账报告：检索问题与范围、库×字段覆盖缺口矩阵、单库独有记录、系统性缺字段、失败库降级、去重对账数字（raw→pairs→dup→maybe→canonical）、排序候选表、缺口与未完成项、复算入口 | 完整性、遗漏说明、可核验 |
| `result.json` | `output_contract` **全部键原样回填**（不改名、不漏键，缺值 `null`/`[]`）+ `case_id`/`status`/`counts`/`errors`/`degradations`/`assumptions`/`sources`/`uncertainty`/`runtime`/`contract_map` | 结构化结果、运行状态、不确定性 |

`result.json` 的契约回填是**语义映射**而不是按顺序塞值：每个 contract 键按词元与类型声明匹配到上面某个数据块，映射依据写进 `contract_map[{key, target, basis}]`，评审可逐键核对"为什么这个键拿到这个值"。未匹配到任何数据块的键给 `null`（列表型键给 `[]`），并在 `assumptions` 记一条。

## §4 库适配手册（摘要）

完整表见 `references/playbook.md` A 部分（库识别两条证据 → 记录列表路径 → 字段路径 → 语义陷阱 → 额度/授权口径 → 加库步骤）。
最容易踩的三个语义差异：

| 差异 | 正确做法 |
|---|---|
| 年份口径不同（Crossref `issued` 最早公开年 / EuropePMC `pubYear` / Scopus `coverDate` / 出版商 `published`） | 统一按版本年，冲突写 `conflicts[]`，不静默取第一个（N-03） |
| 作者与刊名表示不同（`family`+`given` vs `fullName` vs 整串；全称 vs 缩写刊名） | 作者归一为 `Family, Given`；刊名取完整者；比较只用首作者姓（N-02/N-04） |
| DOI 前缀与大小写、标识符嵌层（`externalIds.DOI`、`ids.pmid`） | DOI 归一为小写裸值，Crossref 形态优先；标识符各留各的，不做跨族换算（N-05/N-07） |

字段状态口径（关键，务必分清）：

| 状态 | 含义 |
|---|---|
| `present` | 解析出值且通过形状检查 |
| `suspect` | 有值但形状可疑（年份越界、DOI 不合规、作者是占位符、标题残留 HTML） |
| `missing` | 该库 schema 本应有此字段而本记录没有（含显式空串/null）——**库确实没给** |
| `unknown` | 响应结构未识别或记录被截断，**无法判断有没有**——不是"没有" |

## §5 方法说明

1. **入库（init）**：递归扫描 `/input`，按扩展名+解析结果识别格式；对每份响应算 sha256、识别库归属（文件名词元 + 响应形状指纹双向投票）与记录列表路径；逐条记录抽取字段，字段值记录 `src_field`（原始路径）与 `raw_sha`（记录规范化 JSON 指纹），使"库—查询—原始响应—字段"链路可回放。
2. **候选对与投票（show/check 可见）**：先分块（共享 DOI 归一值 / 首作者姓+年 / 标题词元重叠 ≥0.5 / 共享标识符族），再四路投票：DOI 相同 +3；标识符族相同（pmid/pmcid/arxiv）+2；标题相似 ≥0.92 记 +2、0.80–0.92 记 +1；首作者姓+年一致 +1。总分 ≥4 判 `duplicate`，=3 判 `maybe`（留人工/Agent 仲裁），≤2 判 `distinct`。
3. **合并（build）**：并查集聚类；每个字段按 `normalize_rules.json` 的优先级取 canonical 值（非可疑 > 库优先级 > 完整度），成员取值不一致即登记 `conflicts[]`，Agent 的 `conflict_resolutions[]` 优先于规则。
4. **覆盖（build）**：聚合成 库×字段 矩阵（present/missing/suspect/unknown 计数），列出单库独有记录与跨库系统性缺字段；失败库单独成行并带失败原因。
5. **可核验（check/selfcheck）**：`check` 用**原始文件重新解析**来复核每条 locator：JSON 类 locator 回放指针并比对 `raw_sha`，文本类 locator 做逐字子串命中；不通过的记录标 `locator_ok=false` 写进 `check_report.json` 与 `degradations`。同时校验 canonical 字段值能否在某个成员原始记录里找到（值级溯源），抓"编造字段"。

## §6 失败处理与降级

| 情形 | 处置 | 记录位置 |
|---|---|---|
| `case.json` 缺失 | 依次回退 `case*.json` → 含 `case_id` 的任意 json → 用 `task.md` 建骨架（契约键为空） | `errors[]`，`status=partial` |
| `case.json` 坏 JSON | 保留原文做文本证据，契约键回退空表 | `errors[]` |
| `output_contract` 为 list/str/嵌套 dict | 三种形态都展开成键集合再回填 | `assumptions[]` |
| 某库响应 429/403/500/超时/错误 JSON | 该库在 `query_matrix.csv` 标 `FAILED(reason)`，`coverage` 记失败，`reconciliation.md` 写缺口段落，`degradations[]` 三处一致 | `errors[]`/`degradations[]` |
| 单条记录结构异常 | 逐条 `try/except` 隔离，跳过并计数，不中断整库 | `degradations[]` |
| 材料目录为空 | 五件套仍生成（空表 + 明确说明），`status=insufficient_evidence` | `degradations[]` |
| 工作稿缺失/不完整 | `build` 仍产出完整最小交付：记录表 + 覆盖矩阵 + 规则 + 台账 + 对账，`status=partial`，`degradations` 写清缺哪几类判断 | `degradations[]` |
| 输出目录不可写 | 回退 `./_output`，重试一次；仍失败则把 `result.json` 打印到 stdout | `degradations[]` |
| 时间逼近预算 | 跳过剩余阶段直接 finalize | `runtime` |

**不编造**：不补造文献、字段值、覆盖率、失败原因；材料没给就写 `unknown`/`null` 并在 `gaps[]` 说明；冲突未消解就保留冲突并标 `unresolved`。

## §7 自查清单（selfcheck 会逐条打勾）

- [ ] `result.json` 的键集合 ⊇ `output_contract` 键集合，且 `case_id` 与输入一致。
- [ ] 五件套存在且非空；`query_matrix.csv` 行数 = 识别到的库数（含失败库行）。
- [ ] `merge_cluster.jsonl` 行数 = canonical 记录数 = `coverage.dedup.canonical`。
- [ ] 每条 canonical 字段都有 `src_db` + `locator`，且 `locator` 回放通过。
- [ ] 每条记录的关键字段值能在成员原始响应中找到（值级溯源），否则标 `untraced_fields`。
- [ ] 重复判定可复算：`merge_cluster.members[].votes` 明细求和 = 记录的 `score`。
- [ ] 失败库在 query_matrix / coverage / reconciliation / degradations 四处表述一致。
- [ ] `status` 与实际完成度一致（缺工作稿判断不得写 `ok`）。
- [ ] `python3 scripts/main.py selfcheck` 输出 `verdict=PASS`（或列出未通过项及原因，不删项凑 PASS）。

## §8 最小调用示例（示例，非正式案例结果）

见 `references/playbook.md` 的 B5：一个最小 `/input`（`case.json` 3 个契约键 + 2 份库响应）、五条命令、产物清单、`result.json` 关键字段片段。其中的标题、年份、DOI 仅用于演示接口。

## §9 文件清单、版本与限制

| 文件 | 作用 |
|---|---|
| `SKILL.md` | 本说明：用途/判断清单/五命令/产物与契约/库适配/降级/自查 |
| `scripts/main.py` | CLI 五子命令、路径解析、缓存、partial 先写、finalize、退出码恒 0（23.6KB） |
| `scripts/ledger.py` | 输入发现、格式与库识别、记录抽取、字段归一与状态判定、证据指纹 |
| `scripts/matrix.py` | 候选对分块、四路投票、并查集聚类、字段优先级合并、覆盖矩阵、查询证据 |
| `scripts/render.py` | 五件套渲染（台账/矩阵/规则/聚类/对账）与 `output_contract` 语义回填 |
| `scripts/pack.py` | 筛选排序记账、缺口核算、bundle 装配、`selfcheck` 复检 |
| `references/playbook.md` | A 部分：库适配表、字段同义词表、语义陷阱、额度与授权口径、扩展新库的方法；B 部分：工作稿 schema、投票与优先级规则、check 项、最小调用示例、常见错误 |

**已知限制**：① 不联网，只对给定快照负责，不做"当前最新/全局新颖性"声明；② PDF 文本抽取是启发式（无 OCR），扫描件只能记 `unknown`；③ 标题相似度用 `difflib`，跨语言（中/日/俄）标题只靠标识符与作者姓年份投票；④ `maybe` 档对必须由 Agent 或人工签字才会合并，脚本不擅自裁定；⑤ 相关性判断不自动化。

版本 `1.0.0`；Python ≥3.8 标准库；无第三方依赖。
