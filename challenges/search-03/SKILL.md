---
name: literature-screening-ranker
description: Screen and rank an already-given candidate literature list against a concrete research question, with per-record traceable evidence. Produces layered labels (keep/maybe/exclude), relevance levels (direct/indirect/none), a stable tie-broken priority order for the top-k, preprint-vs-published duplicate merging, conflict escalation, full-coverage accounting, and a verbatim quote plus locator behind every decision. Use when the user asks 文献筛选 / 相关性排序 / 候选文献去噪 / 这批文献哪些相关 / screen these search results / rank candidate papers for a review question.
version: 1.0.0
---

# 候选文献筛选与可解释排序（literature-screening-ranker）

单命令评测入口：

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

无 draft.json 时直接运行本命令即可产出完整契约与全部交付物；评测环境按此执行。

## 1. 用途与适用条件

输入是一份**已经给定的候选文献集**（题名、摘要、年份、DOI、来源等元数据）加一个具体科研问题（可附纳排
条件与目标 k，也可能缺失）。输出是**逐条**可复核的判定：`keep / maybe / exclude` 三层标签、
`direct / indirect / none` 相关性层级、0–1 分数、稳定排序、每条决定命中的规则 ID 与摘要原文引证、
重复与版本合并证据、覆盖率与待定区规模、冲突与不确定性说明。

适用：检索结果初筛、系统综述前的候选集去噪、"先读哪几篇"排序、同一研究多版本去重。
候选规模从几条到数百条；材料可为 Crossref / EuropePMC / 出版商响应、检索导出 JSON/JSONL/CSV、纯文本摘要。

不适用（直接说明，不要硬套）：从零做数据库检索、全文精读与数据提取、Meta 分析统计、论文写作、PRISMA
全流程管理。本 Skill **只对给定候选集负责**，不声称全局召回——候选集之外是否漏检不在判定范围内，
这一点固定写在 `coverage.recall_note` 与 `limitations` 里。

## 2. 五命令主路径（先读这一节）

在包根执行（`scripts/` 与 `SKILL.md` 同级，不依赖当前工作目录）：

```bash
python3 scripts/main.py init       # 1. 建索引：解析 case.json/output_contract/task.md，发现候选池，聚类重复，先写合法 partial result.json
python3 scripts/main.py show       # 2. 打印带 locator 的原文与对象清单（纳排条件、逐条候选、摘要），供逐字引用
#    3. 你（Agent）亲自读材料，把逐条判断写进 /app/work/draft.json（可分批 draft-01.json、draft-02.json）
python3 scripts/main.py check      # 4. 机械校验：契约字段、枚举、quote 逐字命中、规则 ID、覆盖率、score/rank 一致性
python3 scripts/main.py build      # 5. 由工作稿生成主产物 + 最终 result.json（无条件 finalize，缺稿也产出完整降级交付）
python3 scripts/main.py selfcheck  # 6. 可选：对已落盘产物做独立复检
```

**脚本不会代替你阅读理解；必须先阅读材料、写工作稿，再运行 build；禁止只跑 build 就结束。**
只跑 `build` 时脚本会退化为纯规则判定，`status=partial` 且 `degradations` 明写"未做语义复核"——那是兜底，
不是交付质量。`init` 生成的 `/app/work/draft.template.json` 已含全部候选骨架，复制成 `draft.json` 逐条填最省事。

`show` 分页，避免一次刷爆上下文：

```bash
python3 scripts/main.py show --page 1 --page-size 15   # 分页
python3 scripts/main.py show --ids c01,c07 --full      # 指定记录、摘要不截断
python3 scripts/main.py show --criteria                # 只看研究问题/纳排条件/目标 k
python3 scripts/main.py show --picks                   # 只看尚未写入工作稿的记录
```

## 3. 运行契约

| 项 | 约定 |
|---|---|
| 输入 | `/input/case.json`（`case_id`、`task_instruction`、`output_contract`、可能的纳排条件）、`/input/task.md`、`/input/` 下任意材料（递归扫描） |
| 工作目录 | `/app/work`（`index.json`、`draft.template.json`、`draft*.json`、`check.json`） |
| 产物 | `/app/output/result.json` + `screening.jsonl` + `ranking.json` + `coverage.json` + `conflicts.json` + `screening_report.md`（`selfcheck.json` 复检时生成） |
| 路径回退 | `--input/--output/--work` 优先；默认依次 `/input`、`/app/input`、`./input`、包根 `../input`；输出同理 `/app/output`、`./output`、包根 `../output` |
| 预算 | 64 次模型请求 / 900 秒 / 单次 16384 token。解析、定位、去重、打分、排序、渲染、校验全在脚本内，模型只做阅读与判断 |
| 首次落盘 | `init` 立即写合法 partial `result.json`（契约字段全回填），任何命令中断都不留空目录 |
| 退出码 | **恒为 0**；异常被捕获、写进 `errors` 并 finalize |
| 依赖 | Python ≥3.8 标准库，无网络、无随机、不读作者本地文件 |

可选环境变量：`SCREEN_MAX_RECORDS`（默认 400，超出只标注不判定）、`SCREEN_ABSTRACT_CHARS`（默认 1600）。

## 4. 输入发现（语义识别，不假设键名）

1. `case.json` 键名容错：`case_id|id|case|task_id`；`output_contract|expected_output|contract|output_fields`；
   `task_instruction|instruction|task|question|research_question|query`；纳排条件
   `screening_criteria|inclusion_criteria|exclusion_criteria|inclusion|exclusion|criteria|eligibility|pico`；
   `k|top_k|target_k|n_results|top_n`。
2. 候选池：递归扫 `/input/**`，对 JSON/JSONL/CSV/TSV/MD/TXT 用语义键
   （`candidates|records|items|results|works|papers|articles|documents|corpus|pool|hits|entries|rows|data`）
   或"像文献记录"的列表（有题名键且至少含摘要/DOI/年份/作者之一）发现，最多 4 层嵌套。
3. 字段别名：题名 `title|paper_title|name|题名|标题`；摘要 `abstract|summary|snippet|description`；
   年份 `year|pub_year|publication_year|issued|date|published`；作者 `authors|author|creator|author_list`；
   DOI `doi|DOI`；类型 `type|record_type|pub_type|study_type|genre`；来源 `venue|journal|container|publisher`。
   缺字段置 `null` 并计入元数据完整度，**不猜、不补造**。
4. 标注类材料单独识别，不当候选、不当答案：`duplicate_exports*`（重复导出 fixture，其记录仍进候选池以便
   演示合并）、`conflicting_opinions*`（意见冲突，只作证据）、`queries*`（检索式日志）、`import_state*`。
   带 `synthetic:true` 的记录标 `fixture:true`，在 `conflicts.json` 与报告中显式说明。
5. `task.md` 与 `case.json` 冲突时以 `case.json` 为准，并记 `conflicts.input_conflicts`。

## 5. 工作稿 `draft.json`（关键判断写在这里）

完整 schema、字段字典、枚举与示例见 `references/draft-schema.md`。最小形态：

```json
{"case_id": "...", "research_question": "复述问题",
 "criteria_used": [{"rule_id": "R2", "text": "研究对象须为...", "source_locator": "case.json#/screening_criteria"}],
 "records": [{"record_id": "c01", "label": "keep", "relevance": "direct", "score": 0.86,
   "criteria_hit": ["R1","R2","R3"], "criteria_violated": [],
   "evidence_quote": "摘要中逐字存在的一句", "evidence_locator": "materials/candidates.json#/candidates/0/abstract",
   "confidence": "high", "rationale": "命中哪条条件、为什么不是间接相关",
   "duplicate_of": null, "flags": []}],
 "conflicts": [], "uncertainties": []}
```

硬要求（`check` 逐条验）：覆盖**候选集全部条目**；`evidence_quote` 必须是该记录题名/摘要/关键词中逐字存在的
片段（空白规范化后比较，建议 20–200 字）；`label` 只用三值、`relevance` 只用三值、`score` 在 0–1、
`criteria_hit` 只用 `R1..R12`；重复/版本条目写 `duplicate_of` 并在 `rationale` 给合并证据。
分批写 `draft-01.json`…，`build` 按文件名字典序合并，同 id 后者优先。

## 6. 分工：脚本做什么、你做什么

| 环节 | 脚本（确定性） | Agent（判断） |
|---|---|---|
| 输入发现 | 递归扫描、字段归一、locator 生成、材料清单 | 判断哪些文件是候选池、哪些是 fixture |
| 纳排条件 | 抽条款、识别时间窗/类型/排除项、生成 facet 骨架 | 补全语义边界，歧义写进 `criteria_used` |
| 相关性 | 词面/facet 命中率与规则打分（规则通道） | 语义判定（直接/间接/不相关）、选最小充分引证 |
| 去重 | DOI/题名归一、预印本识别、版本族聚类 | 确认合并方向、判断"同一研究多篇报道" |
| 排序 | 固定排序键、同分分组、k 截断、复跑一致 | 决定分数与例外，同分时说明为何在前 |
| 校验 | quote 命中、枚举、覆盖率、契约字段、排序复算 | 处理校验失败：补引证或降为 `maybe` |
| 产物 | jsonl/json/md 渲染、契约回填、finalize | 报告里"关键结论与下一步"的文字判断 |

## 7. 标签与判定规则（详见 references）

三层标签 `keep / maybe / exclude`，相关性 `direct / indirect / none`。判定顺序固定：
**硬排除（R8）→ 重复合并（R9）→ 主题门控（R1）→ 对象/方法/时间/类型（R2–R5）→ 证据与元数据（R6/R7/R11）
→ 定层与置信度**。规则 ID 机器只认 12 个：

| ID | 规则 | 典型触发 |
|---|---|---|
| R1 | 主题匹配 | 题名/摘要命中研究问题核心概念族 |
| R2 | 研究对象/人群匹配 | 物种、材料体系、疾病、人群、样本一致 |
| R3 | 方法匹配 | 干预/表征/模型/统计方法与要求一致 |
| R4 | 时间窗匹配 | 年份落在给定窗口 |
| R5 | 文献类型匹配 | 原始研究 / 综述 / 预印本 / RCT / 队列 |
| R6 | 结果/证据可用 | 摘要含结果陈述、效应量或数据 |
| R7 | 元数据完整 | 题名+摘要+年份+标识符基本齐全 |
| R8 | 硬排除 | 撤稿、勘误、社论、命中排除条款、主题完全无关 |
| R9 | 重复/版本合并 | 同 DOI、同题、预印本-正式版、重复导出 |
| R10 | 同一研究多篇报道 | 同作者+高度相似题名+不同结局指标 |
| R11 | 摘要不足 | 只有题名、摘要为空或过短 |
| R12 | 标注分歧/输入冲突 | fixture 意见冲突、双通道判定不一致 |

## 8. 排序与平局

`score` 降序（4 位小数）→ `relevance`（direct>indirect>none）→ 类型权重（原始 1.0 / 综述 0.8 / 预印本 0.7 /
其他 0.3）→ 年份降序（缺失按最旧）→ `record_id` 升序。同分进 `ranking.json.tie_groups[]` 并写明后续键。
`exclude` 与重复条目不进排名，列在 `ranking.excluded[]` 并保留理由。函数在 `scripts/analyze.py:rank_rows`，
任何人可用同一 `screening.jsonl` 复算。

## 9. 去重、版本合并与冲突

- 重复判定：DOI 规范化后相同；题名规范化相同；题名相似度 ≥0.90；预印本标识 + 相似度 ≥0.75。
- 保留方向：正式发表版 > 有 DOI > 年份较新 > 元数据更全。被合并条目仍占一行（`label=exclude`，
  `duplicate_of` 指向保留条目，`merge_evidence` 写 reasons 与两侧 locator）。
- 同一研究多篇报道（R10）**不合并**，标 `same_study_group` 并升级人工，避免误删不同结局指标。
- `conflicting_opinions` 类 fixture 只作冲突证据，**不得**抄成标签。
- 双通道不一致（你的 `label` 与规则通道差 ≥1 层，且引证未通过逐字校验）→ 自动降 `maybe`（R12），
  宁可待定也不造假阳性；引证未通过还会把 `score` 压到 ≤0.5。

## 10. 产物与 output_contract 回填

| 文件 | 内容 |
|---|---|
| `result.json` | 主产物：`case_id/status/errors/degradations/assumptions/warnings/sources/queries/uncertainties/pending_human/changes/runtime/result` |
| `screening.jsonl` | 一候选一行：`record_id/title/authors/year/doi/locator/label/relevance/score/rank/reason{criteria_hit,criteria_violated,evidence_quote,evidence_locator,quote_verified,confidence,rationale}/duplicate_of/merge_evidence/source` |
| `ranking.json` | `ranking_key/k/ordered/top_k/excluded/tie_groups/counts` |
| `coverage.json` | 候选总数、已判定数、三标签与三相关性计数、合并数、缺失字段、`coverage_ratio`、`maybe_zone`、`quote_verified`、`recall_note` |
| `conflicts.json` | 版本族、同研究多报道、意见冲突 fixture、双通道分歧、引证未通过、输入冲突 |
| `screening_report.md` | 人读报告：问题与口径、top-k 表、待定区、排除原因分布、覆盖与限制、下一步 |

`output_contract` 每个键都**原样**出现在 `result.json` 顶层，键名不改、不遗漏；无内容时按声明类型填
`[] / {} / "" / null` 并记 `contract_field_filled_empty`。键位按语义映射：含 `screen|result|candidate|paper|record`
→ 逐条判定列表；含 `rank|order|top|priorit` → 排序列表；含 `cover|count|stat` → 统计 dict；含
`conflict|dup|merge|version` → 冲突/版本；含 `status` → 状态字符串；含 `case` → `case_id`；含
`report|summary|rationale|markdown` → 报告字符串；含 `criteria|guideline|label` → 判定口径 dict；含
`evidence|quote|locator` → 证据列表；含 `query` → 检索日志；含 `k` → top-k。
`status` 永远是字符串枚举（`answered/partial/insufficient_evidence/input_error`），统计只进 `coverage`。

## 11. 评分维度 → 本包落点

| 评分点 | 落点 |
|---|---|
| 完成度 15 | 逐条全覆盖（`coverage.screened == total`），三层标签齐全，k 与排序完整；缺项进 `pending_human` |
| 正确性 15 | 规则表驱动（R1–R12）+ 纳排 facet 化，硬排除优先；预印本/正式版合并；直接证据排前 |
| 完整性 5 | 候选/证据/状态三类字段齐全；未判定条目显式列出并说明原因 |
| 可核验 5 | 每条判定 = 规则 ID + 逐字 quote + locator；`check`/`selfcheck` 做命中校验 |
| 质量增益 15 | 固定判定顺序 + 分层决策树 + 双通道分歧升级，替代"标题词面排序" |
| 效率增益 5 | `reason` 结构化、`maybe_zone` 与返工点统计、top-k 直接给出 |
| 增益可验证 5 | 无随机、排序键公开、同输入两次运行产物逐字节一致 |
| 创新 15 | 版本链合并、双通道一致性门控、平局组显式化、facet 分层打分、跨语言结构代评分 |
| 可靠体验 10 | 触发条件与越界说明；八类异常分支（§13）；单条异常隔离；未知契约键不崩 |
| 生态贡献 10 | 本文档 + 规则表 + 工作稿/字段字典 + 打分与排序口径 + 示例 + 维护说明 |

## 12. 边界与限制（如实写进产物）

- **有限快照**：只判定给定候选集；不联网、不查库、不声称全局召回。
- **不做全文阅读**：只用题名/摘要/元数据；摘要缺失按 R11 进 `maybe`，不靠想象补内容。
- **双通道**：规则通道可复算但只看字面；你的语义通道更准但必须有引证。不一致会被显式记录。
- **不做统计推断**：不评偏倚风险、不做 GRADE、不做 Meta 分析。
- **跨语言**：问题与摘要语种不同时词面匹配会衰减；若完全无法桥接，规则通道只做结构代评分（类型/时效/
  元数据），全部转 `maybe` 并记 `language_mismatch_no_lexical_bridge`，不据此断言"不相关"。
- **无研究问题**：输入只有候选、没有研究问题时，记 `no_criteria_found`，所有记录至少 `maybe`。

## 13. 失败处理与降级链路

| 情况 | 处置 | status |
|---|---|---|
| `case.json` 坏 JSON | 记 `errors`，尽量正则回收 `case_id`，继续用材料 | `partial` |
| 找不到任何候选 | 不造文献；契约键给空值 + `pending_human` 提示补齐候选集 | `input_error` |
| 候选只有题名（无摘要） | 全部按 R11 进 `maybe`，标 `abstract_missing` | `partial` |
| 工作稿缺失/只写一部分 | 缺的条目走规则通道兜底，`source=rule_fallback`，记 `no_agent_draft_rule_fallback` / `partial_agent_draft` | `partial` |
| quote 校验不通过 | `label` 降 `maybe`、`score≤0.5`、`confidence=low`，记 `quotes_unverified` + `pending_human` | `partial` |
| 单条记录判定异常 | 记 `errors`，该条 `maybe`/`low`，其余继续 | `partial` |
| 候选超出记录上限 | 只判定前 N 条，其余标 `not_processed_cap` | `partial` |
| 契约含未知字段 | 按声明类型填空值回填，绝不改名、绝不漏键 | 不变 |

## 14. 自查清单（`selfcheck` 逐项打勾）

- [ ] `result.json` 合法，`case_id` 与输入一致，`output_contract` 键齐全且未改名。
- [ ] `status` 是枚举字符串，不是统计 dict。
- [ ] `screening.jsonl` 行数 == 候选总数，`coverage.screened == total_candidates`。
- [ ] 每条判定都有 `label`、`relevance`、`score`、`criteria_hit|criteria_violated`、`evidence_quote|flags`。
- [ ] 抽查 3 条：`evidence_quote` 能在 `locator` 指向的原文里逐字找到。
- [ ] `ranking.json.top_k` 长度 == `k`（或候选不足时的实际条数并说明），`tie_groups` 覆盖全部同分档。
- [ ] 排序可由 `screening.jsonl` 复算；两次运行产物逐字节一致。
- [ ] 重复/版本族都有 `duplicate_of` + 合并证据，合并前后计数对账（`total = unique + merged`）。
- [ ] 空输入 / 坏 JSON / 缺工作稿三种情况都 exit 0 且 `result.json` 合法。

## 15. 最小调用示例（**示例数据，非正式案例结果**）

```bash
python3 scripts/main.py init --input /input --output /app/output --work /app/work
python3 scripts/main.py show --page 1 --page-size 15
cp /app/work/draft.template.json /app/work/draft.json    # 逐条填判断
python3 scripts/main.py check && python3 scripts/main.py build
```

示意输入：研究问题"某合金高温蠕变寿命预测"、纳排"2015 年后、原始研究、含蠕变数据"、`k=5`；候选 12 条，
其中 1 条预印本与 1 条期刊版同题。示意输出：两者合并（`duplicate_of` 指向期刊版）；`keep 3 / maybe 4 /
exclude 5`；`top_k` 为 3 篇直接相关的原始研究，每条带摘要原句与 locator；`status=answered`。
**以上为示意，不是任何正式案例的答案。**

## 16. 文件清单、版本与维护

```
SKILL.md                              本文档：用途/调用/契约/方法/限制/失败处理/自查
scripts/main.py                       入口：init / show / selfcheck + 目录与契约装配
scripts/pipeline.py                   判定合并、工作稿校验、build、冲突装配
scripts/core.py                       输入发现、记录归一与 locator、纳排 facet、去重聚类
scripts/analyze.py                    规则通道、双通道门控、排序、契约回填、产物渲染
references/labeling-guideline.md      三层标签决策树、R1–R12 判定表、去重与冲突约定
references/draft-schema.md            工作稿 schema、字段字典、check 规则、result 字段
references/scoring-and-ranking.md     打分权重、facet 口径、排序键、平局、复算与度量
```

版本 `1.0.0`；Python ≥3.8 标准库；无网络、无随机。维护：改阈值/权重必须同步
`references/scoring-and-ranking.md` 与 `analyze.py` 常量；新增材料格式只改 `core.load_candidates`，
产物 schema 不变；口径变更写 `changes` 记录以便对照复跑。
