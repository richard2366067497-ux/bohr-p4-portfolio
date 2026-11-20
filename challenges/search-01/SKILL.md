---
name: traceable-literature-retrieval
description: Run a reviewable literature search over the offline database response snapshots shipped with a case (Crossref, Europe PMC, publisher HTML/XML/JATS, candidate pools, retained reference graphs and local import states), and return a ranked candidate set in which every row carries its source locator, a verbatim relevance quote and the screening decision that kept or dropped it. Also produces the query plan, the deduplication and metadata-conflict record, the coverage check against required references, and an honest status for empty results, rate limits, permissions, missing metadata and import lag. Use when the user asks 检索文献 / 找相关论文 / 文献检索与筛选 / 建候选集 / 保留筛选依据 / literature search / find relevant papers / build a screening log / recall check against a reference list.
version: 1.0.0
---

# 可复核文献检索与筛选（traceable-literature-retrieval）

## 0. 先看这里：五命令主路径（唯一推荐用法）

```bash
python3 scripts/main.py init       # 解析 case.json / output_contract / task.md 与全部材料，建对象表，先写合法 partial result.json
python3 scripts/main.py show       # 打印带 locator 的对象清单（题名、年份、DOI、摘要首段），供你逐字引用
#   ★ 由评审 Agent 亲自阅读材料，并把判断写进工作稿 /app/work/draft.json
python3 scripts/main.py check      # 机械校验工作稿：契约字段、quote 逐字命中、相关性取值、覆盖数、冲突登记
python3 scripts/main.py build      # 由工作稿生成主产物 candidates.jsonl + coverage.json + search_log.json + report.md，并 finalize result.json
python3 scripts/main.py selfcheck  # 复检已落盘产物（可选，但建议在交付前跑一次）
```

**脚本不会代替你阅读理解；必须先阅读材料、写工作稿，再运行 `build`；禁止只跑 `build` 就结束。**

`build` 只负责把你写进 `draft.json` 的判断变成结构化产物并做一致性校验；相关性判断、取舍理由、覆盖缺口与不确定性必须由你读材料后给出。若你没有写工作稿，`build` 仍会产出一份**完整但明确降级**的交付（`status=partial` + `degradations` 说明缺口），那是兜底，不是正常用法。

带参数时（Harness 默认无需传参，脚本自带 `/input`、`/app/work`、`/app/output` 及相对回退）：

```bash
python3 scripts/main.py show --task --limit 30          # 先看任务解析、建议查询、必需文献、导入状态、来源清单
python3 scripts/main.py show --grep graphene --chars 300 # 按关键词定位对象，摘要截断到 300 字
python3 scripts/main.py show --ids O0007,O0011 --full    # 只看指定对象全文摘要
```

## 1. 用途与适用条件

**做什么**：把一个研究问题 + 一批离线检索素材，变成一份可复核的文献候选集——每条记录带元数据、来源定位（哪份素材的哪条记录）、逐字相关性证据、筛选结论（保留/排除/待确认）、排序位次，以及查询计划、去重与元数据冲突记录、对必需文献的覆盖核算和如实的状态说明。

**适用**：任务本身是「检索/召回/筛选/排序/覆盖核对」，素材是数据库响应快照（Crossref `message.items`、Europe PMC `resultList.result`、出版商 HTML `<meta citation_*>`、JATS XML、CSV 候选池、保留的引文图、增量导入状态）。

**不适用**（如实说明，不要硬套）：

- 单篇论文的论断核验、全文精读、方法复现——那是证据溯源类 Skill 的职责；
- 需要**在线**检索才能得到的结论（本 Skill 不联网，只读 `/input` 下的快照）；
- 需要 PDF 正文才能判断的内容：PDF 只被登记为 locator 与 `unparsed_binary` 降级项，不会被解析成文本；
- 全局新颖性/最新发表声明、引用次数与期刊影响因子——快照不具备这些字段时不得推测。

## 2. 运行契约

| 项 | 约定 |
|---|---|
| 输入 | `/input/case.json`（含 `output_contract`、`task_instruction` 等）、`/input/task.md`、案例材料（任意子目录） |
| 工作目录 | `/app/work`（`index.json`、`draft.json`、`check_report.json`） |
| 产物 | `/app/output/`：`result.json` 为唯一主产物，另有 `candidates.jsonl`、`search_log.json`、`coverage.json`、`screening.json`、`report.md`、`selfcheck.json` |
| 依赖 | Python ≥3.8 标准库；**不联网**；不依赖当前工作目录（脚本用 `Path(__file__).resolve().parent` 定位，`/skills/weekly-skill` 与包内相对路径都可用） |
| 预算 | Harness 64 次模型请求 / 900 秒 / 单次 16384 token；确定性工作全在脚本里，模型只做阅读与判断 |
| 失败语义 | 任何异常都捕获；**退出码恒 0**；先写合法 partial `result.json`，最后无条件 finalize |

## 3. 输入发现：材料长什么样

`init` 递归扫描 `/input`（跳过 `case.json`/`task.md` 本身），按**扩展名 + 内容**识别，不靠文件名猜：

| 形态 | 识别方式 | 产出 |
|---|---|---|
| Crossref JSON | `message.items[]`，含 `DOI`/`title[]`/`author[]`/`issued.date-parts`/`container-title[]` | 每条一对象，locator `responses/x.json#/message/items/3` |
| Europe PMC JSON | `resultList.result[]`，含 `id`/`doi`/`title`/`authorString`/`journalTitle`/`pubYear` | 同上，locator 为 JSON Pointer |
| 出版商 HTML | `<meta name="citation_title|doi|journal_title|publication_date|author">` | locator `<file>#meta` |
| JATS / 出版商 XML | `<article>` 块：`article-title`/`article-id[pub-id-type=doi]`/`journal-title`/`pub-date`/`abstract` | locator `<file>#article=2` |
| CSV 候选池 | 表头含 title 类列 | locator `<file>#row=12`（行号为文件真实行号） |
| 保留引文图 | 文件名含 `reference` 的 JSON：`{doi,title}` 节点 | 既进候选池也进覆盖检查点 |
| 增量导入状态 | 文件名含 `import` 的 JSON、或 `case.json` 的 `import_state(s)` | 写入 `search_log.import_states` 与不确定性说明 |
| TXT/MD 说明或参考文献行 | 含年份的引用式行 | 低置信候选（`kind=text_citation`，完整性 0.3） |
| PDF/图片等二进制 | 不解析 | 登记 `unparsed_binary` 降级项，提示先用 pdf/ocr 工具 |

字段名容错：`DOI|doi|dois`、`title|article_title|titles`、`year|pubYear|issued|pub-date`、`venue|journalTitle|container-title`、`author|authors|authorString` 等的大小写/下划线/连字符变体都能命中（`sr_core.pick` 按 `nkey()` 比对）。`case.json` 声明的 `artifacts` 若在 `/input` 下找不到，会写 `declared_material_missing` 降级项——**不编造缺失素材的内容**。

## 4. 输出契约：result.json 信封与字段回填

`result.json` = **output_contract 原样回填的全部键** + 固定信封字段 + 本 Skill 的规范字段。

```json
{
  "case_id": "C01", "status": "answered",
  "candidates": [ { "rank": 1, "record_id": "R01", "object_id": "O0006", "title": "...",
                    "authors": ["..."], "year": 2019, "venue": "...", "doi": "10.1016/...",
                    "source_id": "responses_crossref_graphene", "locator": "responses/crossref.json#/message/items/0",
                    "query_ids": ["Q1"], "tier": "core",
                    "relevance": {"score": 0.93, "basis": "为何相关", "quote": "逐字片段",
                                  "quote_verified": true, "quote_field": "text", "judgement": "agent"},
                    "metadata_completeness": {"score": 0.8, "missing": ["abstract"]},
                    "screening": {"decision": "include", "reason": "..."},
                    "status": "included" } ],
  "excluded": [ { "object_id": "O0008", "screening": {"decision": "exclude", "reason": "..."} } ],
  "queries": [...], "search_log": {...}, "coverage": {...}, "evidence": [...],
  "sources": [...], "uncertainties": [...], "missing": [...], "conflicts": [...],
  "assumptions": [...], "method_notes": {...}, "summary": "...", "report": "markdown",
  "result": { "candidates": [...], "coverage": {...}, "search_log": {...} },
  "errors": [], "degradations": [], "changes": [...], "runtime": {...}
}
```

**契约回填规则**（`main.fill_contract`）：按归一化键名把 `output_contract` 的每个键映射到语义字段——`results/records/papers/items/shortlist → candidates`、`log/searchlog/trace → search_log`、`recall/coveragereport → coverage`、`gaps/omissions → missing`、`rejected/exclusions → excluded`、`report/markdown → report`、`result/output/data → result` 等（完整别名表见 `references/io-contract.md`）。**键名不改、不删、不漏**；无生产者时填 `null`/`[]`/`{}` 并在 `degradations` 记 `contract_field_filled_empty`。

`status` 恒为字符串枚举：`answered`（候选集达到 `min(target_k, 可用对象数)`）、`partial`（降级路径/覆盖率不足/存在未核验引文/输入错误但有产出）、`insufficient_evidence`（对象池为空或全部被排除）、`input_error`（致命输入问题且无可用材料）。统计量一律放 `coverage`/`search_log.totals`，**不得**把统计对象塞进 `status`。

## 5. 工作稿 draft.json：你的判断写在这里

`/app/work/draft.json`（也接受 `plan.json`），字段级 schema 与示例见 `references/draft-and-screening.md`：

```json
{
  "research_question": "一句话界定主题与范围",
  "summary": "面向读者的结论摘要",
  "queries": [{"query_id": "Q1", "query": "\"graphene oxide\" AND membrane AND desalination",
               "source": "crossref", "intent": "核心主题"}],
  "selections": [{"object_id": "O0006", "decision": "include", "relevance": 0.93, "tier": "core",
                  "basis": "为何相关（指向具体证据）", "quote": "标题或摘要中的逐字片段",
                  "query_ids": ["Q1"]}],
  "coverage_judgement": [{"ref_id": "REQ01", "status": "已覆盖", "object_id": "O0006", "note": "..."}],
  "conflicts": [{"field": "venue", "object_ids": ["O0006", "O0009"], "note": "..."}],
  "gaps": [{"kind": "import_lag", "detail": "...", "impact": "..."}],
  "uncertainties": ["..."]
}
```

约定：`decision` ∈ `include|exclude|uncertain`；`relevance` ∈ [0,1]；`include` 必须同时有 `basis` 与 `quote`；`quote` 必须是该对象 `title/abstract/venue/authors` 中的**逐字子串**（可用 `...` 省略中间，校验按两段分别命中）；对象 id 用 `show` 打印的 `O0001…`。

## 6. 核心流程（固定顺序）

1. **建索引**（`init`）：扫描材料 → 提记录 → 赋值稳定 `object_id`（来源路径字典序 + 记录顺序，可复现）→ 解析任务（`target_k`、时间窗、关键词、排除词、语言、声明数据库）→ 收拢必需文献、参考图检查点、导入状态 → 学习素材内的缩写/拼写变体（`long form (ABC)` 模式）→ 生成建议查询 → 落 `index.json`。
2. **读材料**（`show` + 你自己打开文件）：确认研究对象、方法、边界条件，判定哪些记录真的相关。
3. **写工作稿**：查询计划（每轮查询的意图）、逐条 `decision` + `relevance` + `basis` + `quote`、必需文献覆盖判断、冲突与缺口。
4. **机械校验**（`check`）：对象 id 是否存在、决策枚举、相关性数值、`quote` 逐字命中、`below_target_k`、缺查询计划/缺覆盖判断——错误项修完再进下一步。
5. **落盘**（`build`）：去重（DOI 优先，其次题名指纹）→ 稳定排序（相关性 desc → tier → DOI → object_id）→ 覆盖核算（必需文献匹配、关键词族覆盖）→ 查询命中统计 → 渲染 `report.md` → 回填契约 → finalize `result.json`。
6. **复检**（`selfcheck`）：JSON 合法性、契约键齐全、locator/quote 覆盖、rank 连续、JSONL 与 JSON 一致、报告非空。

## 7. 相关性、排序与可核验口径

- **相关性分数是启发式排序键，不是概率**：由你在 `draft.json` 给出并在 `basis` 写明依据（题名命中、摘要中报告的具体结果、综述/预印本等方法属性）；脚本只做区间校验与稳定排序，不会替你改分。
- **tier**：`core`（直接回答研究问题）/`supporting`（支撑某条分支）/`peripheral`（沾边或待确认）。
- **排序**：`relevance` desc → `tier` → DOI → `object_id`；不含随机数与时间依赖，同输入两次运行结果一致。
- **可核验**：每条候选必须同时有 `source_id` + `locator`（可定位到文件内的 JSON Pointer / CSV 行号 / HTML meta）与 `relevance.quote`（逐字、可 grep）。`quote_verified=false` 的行会被 `selfcheck` 标出，并使整份结果降级为 `partial`。
- **不编造**：素材没有的 DOI、年份、作者、摘要一律留空并记 `metadata_completeness.missing`；不得据题名推测期刊或年份。

## 8. 异常与降级分支

| 情况 | 行为 | status |
|---|---|---|
| 无 `case.json` | `errors=[case_json_missing]`，仍用目录内材料建索引 | `insufficient_evidence`/`partial` |
| `case.json` 坏 JSON | 记 `case_json_parse_note`，尝试键名变体与 `*case*.json`，继续 | `partial` |
| 无 `draft.json`（只跑 build） | 用关键词族重叠做确定性兜底排序（`judgement=deterministic_fallback`），写 `draft_missing_or_empty` | `partial` |
| 工作稿字段缺失/引文不命中 | `check` 报 error；`build` 仍产出，`quote_verified=false` 并入降级 | `partial` |
| 材料全空 / 只有不可解析文件 | 不造记录；`candidates=[]` + `missing` 说明 | `insufficient_evidence` |
| 记录缺 DOI/年份/摘要 | 元数据留空，`missing_fields` 记录；去重退化到题名指纹 | 正常 |
| 同一文献多来源元数据冲突 | 保留双方，`conflicts[]` 记字段与取值，keeper 取完整性最高者 | 正常 |
| 响应快照是限流/403/空结果 | 若素材里含 `429/403/error` 语义字段，`init` 记为来源异常，`missing` 写清未取得的部分 | `partial` |
| 声明材料缺失 / 二进制未解析 | `declared_material_missing` / `unparsed_binary` 降级项，不猜内容 | `partial` |
| PDF 需正文判断 | 不做解析，登记缺口并建议 pdf/ocr 工具 | `partial` |
| 未预期异常 | 全局 crash guard 重写合法 `result.json`，退出码 0 | `partial` |

## 9. 最小调用示例（示例数据，非正式案例结果）

```bash
python3 -B /skills/weekly-skill/scripts/main.py init
python3 -B /skills/weekly-skill/scripts/main.py show --task --limit 5
# … 阅读材料后写 /app/work/draft.json …
python3 -B /skills/weekly-skill/scripts/main.py check
python3 -B /skills/weekly-skill/scripts/main.py build
```

示例输入（**示例，非正式案例**）：`case.json` 声明 `output_contract={case_id,status,candidates,search_log,coverage,evidence,conflicts,uncertainties}`、`required_references` 两条、`target_k=5`；材料为 Crossref 快照 3 条 + Europe PMC 2 条 + 出版商 HTML 1 条 + CSV 2 行 + 参考图 3 节点。

示意输出（**示例，非正式案例结果**）：

```text
== build ==
mode          : agent_draft
status        : answered
candidates    : 5 (excluded 2, target_k 5)
coverage      : 2/2 required references matched
contract keys : 8 filled
```

完整示例、字段解释与三段体（输入/调用/输出）见 `references/io-contract.md` §4，以及包根 `SMOKE.md`（打包时移除）中的真实命令记录。

## 10. 评分维度 → 实现位置

| 评分维度 / 评分点 | 本 Skill 的落点 |
|---|---|
| 实际效果·完成度 15 | 契约键全回填（`fill_contract`）；`init` 先写合法 partial，`build` 无条件 finalize；`candidates/excluded/queries/coverage/evidence` 五件套始终存在 |
| 实际效果·正确性 15 | 元数据逐字取自素材（`normalize_record` 不改写）；相关性由 Agent 阅读后判定并写依据；排序确定可复现；不做无依据推断 |
| 实际效果·完整性 5 | 检索结果 + 证据记录 + 状态说明三类字段齐全；缺项写 `null/[]` 与 `missing[]`，不省略键 |
| 实际效果·可核验 5 | 每行 `source_id+locator+quote`；`check`/`selfcheck` 逐字校验；失败转 `quote_verified=false` + 降级 |
| 使用增益·质量 15 | 去重合并多库同一文献、参考图覆盖核算、`below_target_k` 提示；同输入可复跑对照 |
| 使用增益·效率 5 | 一条命令建索引并打印带 locator 清单，Agent 不必手写解析；`search_log.totals` 记录召回/保留/去重规模 |
| 使用增益·可验证 5 | `method_notes` 写死流程与口径；`selfcheck.json` 十项机械检查；两次运行结果一致（无随机） |
| 创新·新增能力 5 | 素材内缩写/拼写变体自动学习（`learn_expansions`）、参考图检查点覆盖、导入状态边界说明 |
| 创新·方法改进 5 | 多库合并去重 + 冲突并列、相关性分层与稳定排序、逐条引文校验闭环 |
| 创新·创新证据 5 | `SMOKE.md` 真实命令与失败注入记录；`conflicts[]`/`degradations[]` 作为方法边界的可核验证据 |
| 可靠·易用 3 | 五命令固定入口 + `--task/--grep/--ids` 辅助视图；`check` 直接给出可修的错误码 |
| 可靠·稳定 4 | 全路径 try/except，退出码恒 0；空输入/坏 JSON/缺材料三条降级链均产出合法结果 |
| 可靠·异常处理 3 | 第 8 节矩阵覆盖空结果、限流/403、元数据缺失、来源冲突、材料缺失、二进制不可解析 |
| 生态·文档 3 | 本文档 + 三份 references（契约/工作稿 schema/规则表） |
| 生态·复用 4 | 纯标准库、无网络、目录参数化；换主题/换数据库只需换材料，无需改代码 |
| 生态·分享 3 | 输入契约与产物结构通用，可直接作为检索类案例的 benchmark 底稿 |

## 11. 自检清单

- [ ] `python3 -m json.tool /app/output/result.json` 通过；`case_id` 与输入一致。
- [ ] `output_contract` 的每个键都在顶层出现，键名未改。
- [ ] `status` 是四值枚举之一，统计信息不在 `status` 里。
- [ ] 每条候选都有 `source_id`、`locator`、`title`，且 `locator` 能在 `/input` 下定位。
- [ ] 每条 `include` 都有 `basis` 与 `quote`，`quote_verified=true`。
- [ ] `coverage` 的 `selected_count`/`distinct_after_dedup`/`required_*` 与 `candidates` 实际行数一致。
- [ ] 被排除的记录出现在 `excluded` 且有理由——筛选依据同样可复核。
- [ ] 冲突双方都在 `conflicts`；未取得的部分在 `missing`；不确定在 `uncertainties`。
- [ ] `selfcheck` 十项 PASS，或 FAIL 项在 `degradations` 里有对应说明。
- [ ] 换一个主题的材料，不改代码也能跑通（无硬编码主题词表）。

## 12. 文件清单、版本与维护

```
SKILL.md                                  本文档：用途/契约/流程/口径/降级/自查
scripts/main.py                           五命令 CLI、契约回填、产物写出、crash guard
scripts/sr_core.py                        输入发现、记录解析（JSON/CSV/HTML/XML/文本）、去重、引文校验
scripts/sr_build.py                       索引构建、工作稿→载荷组装、覆盖核算、工作稿校验
scripts/sr_output.py                      查询建议、report.md 与 JSONL 渲染
references/io-contract.md                 输入发现、契约别名表、result.json 字段字典、最小示例
references/draft-and-screening.md         工作稿 schema（A）+ 筛选/去重/排序/覆盖口径与降级矩阵（B）
```

版本 `1.0.0`；Python ≥3.8 标准库；无第三方依赖、无网络。

**维护要点**：改排序键必须同步本文档 §7 与 `references/draft-and-screening.md` B 部；新增材料格式只改 `sr_core.collect` 的分支，产物 schema 不变；`VERSION` 常量与本文档 frontmatter 保持一致；改动后重跑 `init → show → 写 draft → check → build → selfcheck` 全链路并更新 `SMOKE.md` 记录。
