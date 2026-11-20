---
name: search-coverage-gap-auditor
description: Audit the coverage and misses of a documented literature search against a frozen known-relevant reference set. From case materials (reference/known-relevant list, database result snapshots, query logs with fields and time windows, citation graph, import state) it freezes a versioned reference set, matches it record-by-record to retrieved records with three graded rules (identifier / bibliographic / adjudication), computes an auditable coverage and miss rate over an explicit denominator policy, attributes every missed reference to an actionable cause with a verbatim evidence locator, plans targeted supplemental queries and measures their marginal yield against a stop rule, and emits a recomputable audit trail. Use when asked 检索覆盖率/遗漏分析/漏检归因/补检收益, "did the search miss known papers", "why did the query miss X", "how much does the supplementary search help", to build a coverage + gap report for a review/guideline search, or to check whether a reported recall figure is self-referential. Outputs hit ledger, gap atlas, supplement plan and recomputable audit trail under /app/output with result.json.
version: 1.0.0
license: MIT
---

# 检索覆盖率与遗漏分析审计器（search-coverage-gap-auditor）

## 0. 60 秒上手：五命令主路径

```bash
python3 scripts/main.py init       # 建索引：解析 case.json/task.md/材料 → 冻结参考集 → 先写一份合法 partial result.json
python3 scripts/main.py show       # 打印带 locator 的参考集/检索记录池/查询式/字段与时间窗，供你逐字引用
#  >>> 你（评审 Agent）亲自读 show 的输出与材料原文，写工作稿 /app/work/draft.json
python3 scripts/main.py check      # 机械校验：契约键、台账覆盖、quote 逐字命中、归因证据、覆盖恒等式
python3 scripts/main.py build      # 由工作稿生成七件套主产物 + finalize result.json（缺稿也兜底，无条件产出）
python3 scripts/main.py selfcheck  # 复检：产物存在性、CSV 可复算、契约回填、再次运行一致性
```

> **脚本不会代替你阅读理解；必须先阅读材料、写工作稿，再运行 build；禁止只跑 build 就结束。**
> `build` 在缺工作稿时仍会产出一份"完整但降级"的交付（status=partial + degradations 写清缺口），
> 这是兜底，不是合格答案：`build` 的日志里 `agent_decisions` 占比越低，说明你读得越少。

命令都用 `python3 scripts/main.py <子命令>`（等价 `python3 -B scripts/main.py`）。全部退出码 0，任何异常都不崩。

## 1. 用途与适用条件

本 Skill 回答一个具体问题：**一份已经跑过的文献检索，相对一批"已知应该被找到"的文献，漏了什么、为什么漏、补检有没有用。**

| 适用 | 不适用 |
|-|-|
| 材料里已有参考集/专家清单/综述纳入文献 + 检索结果快照 + 查询式记录 | 让你"上网实时检索"（本 Skill 不联网；只在给定材料内计算） |
| 要做覆盖率/遗漏率、漏检归因、补检边际收益 | 做系统综述的正式纳排、偏倚评价、meta 分析 |
| 要判断某个覆盖率数字是否"以结果定义分母" | 做全文阅读、PDF 内容抽取式综述 |
| 要把一次检索的筛选依据留档、可独立复算 | 替代数据库接入或订阅权限问题 |

设计前提（也是本 Skill 的核心立场）：

1. **分母必须来自参考集，不能来自检索结果本身**。用检索结果反推应检文献，覆盖率会接近 100%，这是失效模式之一；本 Skill 强制把分母锁定为冻结参考集并输出分子/分母 id 列表。
2. **没找到 ≠ 不相关**。未命中条目全部保留在台账里，逐条给归因，禁止从清单里划掉。
3. **归因必须落到具体查询式/字段/时间窗/来源**，禁止"数据库覆盖不足""关键词不够好"这类无证据泛化。
4. **补检要看新增命中集合是否真的变化**。换同义词重跑、命中集合不变却宣称遗漏下降，属于空转。

## 2. 运行契约（官方 Harness）

- 输入：`/input/case.json`（含 `case_id` / `task_instruction` / `output_contract` 等）+ `/input/task.md` + `/input/materials/**`（PDF/JSON/JSONL/CSV/MD/TXT/HTML）。
- 工作目录：`/app/work`（工作稿 `draft.json`、状态 `state.json`、校验报告 `check_report.json`）。
- 产物目录：`/app/output`（含 `result.json`）。
- 只用 Python ≥3.8 标准库；**不联网**；脚本用 `Path(__file__)` 定位自身与 `references/`，**不依赖 CWD**。
- 退出码**恒 0**；`init` 第一步就写一份合法 partial `result.json`；`build` 结束时无条件 finalize 覆盖它。
- 预算：64 次模型请求 / 900 秒 / 单次响应 16384 token。本 Skill 的确定性计算是秒级；模型预算应主要花在"读 `show` 输出 + 写 `draft.json`"。
- 目录不可写时依次回退：`--output` → `/app/output` → `./output`；`--work` → `/app/work` → `./work`（回退写进 `degradations`）。
- 兼容安装位置 `/skills/weekly-skill`：脚本不假设包根绝对路径。

## 3. 调用方式

```bash
python3 scripts/main.py --help                     # 子命令与参数
python3 scripts/main.py init   [--input /input] [--work /app/work] [--output /app/output]
python3 scripts/main.py show   [--section all|materials|refs|pool|queries|sources] [--limit N] [--ref R-003]
python3 scripts/main.py check  [--strict]
python3 scripts/main.py build  [--policy dedup_exclude_unavailable] [--no-draft]
python3 scripts/main.py selfcheck
```

- `--input/--work/--output` 对每个子命令都有效（默认 `/input`、`/app/work`、`/app/output`）。
- `show` 的默认输出约 12k 字符量级（`--limit` 控制每节条数），是给你读的**材料投影**，不是全文替代：需要逐字证据时按 locator 回读原文件。
- `check` 打印 `[PASS]/[WARN]/[FAIL]` 逐项结果并写 `/app/work/check_report.json`；`--strict` 把 WARN 当 FAIL 显示（不影响退出码）。

分工：`main.py` = 五命令编排、状态持久化、兜底 finalize；`ledger.py` = 材料发现与解析、参考集冻结、三级命中判定、台账 CSV；`audit.py` = 覆盖口径、双维归因、补检收益、审计链、契约键解析；`render.py` = 口径卡/图谱/补检计划/报告渲染；`verify.py` = 共享计算 + `check`/`selfcheck`。

## 4. 输入发现（语义识别，不假设键名）

`case.json` 先找 `/input/case.json`，再递归 `case*.json`，再退回含 `case_id` 的任意 JSON；解析失败只记 `errors`，继续用 `task.md` 与材料推进。

材料按**内容形态**识别，不依赖文件名约定（文件名只作为加权证据）：

| 对象 | 识别规则（脚本内实现） |
|-|-|
| 参考集 refs | 容器路径或文件名命中 `reference|known|seed|gold|anchor|include|expert|do_not_miss|参考|专家|必检`，且条目像书目记录（题名 + DOI/年份/作者任一项）；也接受 `case.json` 里 `reference_set/known_relevant/seed_papers` 一类列表；CSV 按表头同义词；MD 按"带 DOI 的行"或"作者(年份) 题名"行 |
| 检索记录池 pool | 任意位置的书目记录（标题 + DOI/PMID/作者/年份/期刊任一），记录 `container`（crossref `message.items`、europepmc `resultList.result`、local）与来源文件 |
| 查询日志 queries | 条目含 `query/q/query_string/term/expression/strategy/搜索式` 任一；附带 `field/fields/search_field`、`date_from/date_to/start/end/window`、`source/database/provider`、`iteration/round/step` |
| 来源 sources | 上述查询声明的库；`import_state`/`imported`/`incremental`/`last_run` 一类状态对象单列 |
| 引文图 | 条目含 `reference/cites/cited_by/references` 列表的节点，记为 `graph_note`，只作辅助清单与冲突线索 |

**参考集为空是硬缺口**：没有分母就不算覆盖率。这种情况下 `build` 仍产出七件套，但 `status=insufficient_evidence`，`scope_card.md` 写明"无参考集，覆盖率未定义"，并在 `pending_human` 请求补参考集。绝不虚构分母。

## 5. 输出契约

固定七件套 + `result.json` + `self_check.json`（全部写 `/app/output`）：

| 产物 | 内容 | 完成标准 |
|-|-|-|
| `scope_card.md` | **口径卡**：研究问题、参考集来源与冻结指纹、分母口径（三套候选口径与选定理由）、覆盖率/遗漏率公式、命中判定三级规则、时间窗、字段、单位与限制 | 任何人读一页即可复算覆盖率 |
| `hit_ledger.csv` | **命中台账**：行=参考集条目；列=`ref_id,title,doi,year,first_author,usable,usability_reason,hit_status,matched_id,match_rule,certainty,evidence_locator,evidence_quote,decision_source,needs_human` | 每行可单独核对；覆盖率可由本表重算 |
| `gap_matrix.csv` | **遗漏分类矩阵**：行=未命中条目，列=`ref_id,primary_category,co_factors,why,fixability,affected_query_ids,action` | 每条漏检至少一类，类名来自受控词表 |
| `gap_atlas.json` | **漏检图谱**：按类别聚类 `{category,count,ref_ids,affected_query_ids,evidence[],why,fixability,verdict}` + `residual` + `uncovered_refs` | 每个类别有证据 locator + 受影响的查询 id |
| `supplement_plan.md` | **补检计划与收益表**：目标遗漏类 → 新查询式 → 字段/时间窗 → 实际新增命中 → 边际收益 → 累计覆盖率 → 停止理由；附残余遗漏声明 | 收益表能被重算；停止理由落到阈值 |
| `coverage_report.md` | **主产物（人读报告）**：结论摘要（四个数）、三口径表、命中台账摘要、遗漏图谱、逐条遗漏、补检收益、不确定性与限制 | 一页读懂并可回查证据 |
| `audit_trail.json` | **可复算审计链**：公式、分子/分母 id 列表、每步 sha256、独立重算结果、抽检样本与一致性、确定性哈希 | 重算值 = 报告值 |
| `result.json` | 契约回填 + 信封字段（见下） | `output_contract` 键 100% 存在 |
| `self_check.json` | 机器可读自检（产物存在性、契约键、CSV 复算、quote 命中、一致性） | `verdict` 与 `check` 结论一致 |

`result.json` 信封（固定存在）：

```
case_id, status(ok|partial|insufficient_evidence|input_error), skill, skill_version,
output_contract_values{...}, counts{...}, coverage{...}, gap_summary{...},
supplement{...}, sources[], uncertainty[], pending_human[], errors[], degradations[],
assumptions[], changes[], products{...}, runtime{...}
```

`output_contract` 回填规则：**键名不改、不漏键**；能映射到本 Skill 产物的键填实际值（文件类键填相对路径，指标类键填数字/字典，文字类键填结论摘要），映射不到的键填 `null` 并在 `output_contract_values.<key>.note` 说明；每个键的填法都记 `kind` 与 `provenance`，便于复核"没有硬凑字段"。原始完整数据另存在 `products` 与 `payload` 段，不因契约字段类型不确定而丢信息。

## 6. 工作稿 schema（`/app/work/draft.json`）

这是**你**的答题区。脚本只做结构化、补缺与校验；判断类内容（相关性、可用性、归因、补检设计、结论）由你写。

```json
{
  "research_question": "一句话：这次检索要覆盖什么，边界是什么",
  "scope": {
    "denominator_policy": "dedup_exclude_unavailable",
    "time_window": "2015-2024",
    "fields": "title/abstract",
    "coverage_definition": "matched_usable / usable_refs",
    "notes": "为什么这样定分母；不可用条目怎么处理"
  },
  "ref_decisions": [
    {"ref_id": "R-001", "usable": true, "reason": "原始研究，DOI 与题名一致，2019 年", "merge_into": null}
  ],
  "hit_decisions": [
    {"ref_id": "R-002", "status": "hit", "matched_id": "P-013", "rule": "id_doi",
     "certainty": "high", "locator": "src-02:L41", "evidence": "与材料中该 DOI 行逐字一致", "note": ""},
    {"ref_id": "R-005", "status": "miss", "matched_id": null, "rule": null,
     "certainty": "high", "locator": "src-01:L18", "evidence": "该题名不在任何结果快照内", "note": ""}
  ],
  "gap_notes": [
    {"category": "query_term_missing", "why": "fixable_by_query", "ref_ids": ["R-005"],
     "affected_query_ids": ["Q-002"],
     "evidence": [{"doc_id": "src-02", "locator": "src-02:L7", "quote": "TS=(perovskite AND stability)"}],
     "verdict": "查询式只含 stability，未含 durability 同义表达"}
  ],
  "supplement": [
    {"target_gap": "query_term_missing", "planned_query": "TS=(perovskite AND (stability OR durability))",
     "fields": "title/abstract", "window": "2015-2024", "expected_new": 1, "rationale": "补同义表达"}
  ],
  "residual_notes": [
    {"ref_id": "R-009", "reason": "source_not_indexed", "explanation": "该刊不在声明的三个库内，补检无法覆盖"}
  ],
  "conflicts": [{"item": "R-004", "detail": "同一题名两个 DOI，需人工裁决"}],
  "spot_check": [{"ref_id": "R-002", "agree": true, "note": "复核命中规则与证据"}],
  "status_note": "剩余不确定点一句话"
}
```

字段字典、受控词表、示例见 `references/draft-and-fields.md`；方法与判据见 `references/method-and-rubric.md`。
可以不写全：脚本会按"缺哪补哪"补齐并在 `degradations` 与 `decision_source` 里标明 `auto`。但 `hit_decisions` 与 `gap_notes` 是最核心的两块，缺了就直接降档。

## 7. 核心方法（六步闭环）

### 步骤 1：参考集冻结（freeze）

脚本把参考集条目编号 `R-001…`，计算 `nkey`（DOI 归一 / 题名归一），按 DOI 优先、题名次之标记重复（`dup_of`），标出可用性标记：

- `retracted`：撤稿/withdrawn/retraction notice
- `no_fulltext`：材料自述无全文/无法获取
- `id_conflict`：同题名不同 DOI、或 DOI 与 PMID 指向不一致
- `meta_incomplete`：缺年份或缺题名

记录 `sha256(ref_id|doi|ntitle)` 序列指纹作为**冻结版本号**（`refset_fingerprint`），口径卡与审计链都引用它，保证"同一版本才算同一覆盖率"。

### 步骤 2：命中判定三级规则（match）

| 级别 | 规则名 | 判定 | 置信 |
|-|-|-|-|
| L1 | `id_doi` / `id_pmid` | DOI 归一后完全相等；或 PMID/PMCID 相等 | high |
| L2 | `bib_title_author_year` / `bib_title_year` | 题名相似度 ≥0.92 且（第一作者姓氏命中或年份相差 ≤1） | high（≥0.97）/ medium |
| L3 | `bib_borderline` | 题名相似度 0.80–0.92 | low → `needs_human=true` |
| — | `none` | 低于 0.80 或仅共享通用词 | miss |

题名相似度用 `difflib.SequenceMatcher` 对归一化题名计算（去标点、去大小写、折叠空白、去 `retracted:` 前缀）；作者用姓氏 token 交集；年份从 `2019`、`2019-05-01`、`May 2019` 里抽取。脚本先给出"建议匹配"，你在 `hit_decisions` 里确认、改判或提升为 `pending`；改判必须写明理由。

### 步骤 3：覆盖测量（coverage）

三套候选口径同时算，**全部**写进口径卡与审计链：

- `S_all`：参考集全部条目
- `S_dedup`：去重后（每组只算 1 条）
- `S_usable`：去重后再按可用性剔除（默认剔 `retracted` 与 `no_fulltext`；`--policy` 可改为 `dedup_only` 或 `all`）

$$
\mathrm{coverage}=\frac{\left|\,\text{hit}\cap S_{\text{policy}}\,\right|}{\left|S_{\text{policy}}\right|},\qquad
\mathrm{miss\_rate}=1-\mathrm{coverage}
$$

分子分母的 **id 列表**必须出现在 `audit_trail.json`，任何人可重算。口径卡必须回答四个数：**分母几条 / 命中几条 / 遗漏几条 / 补检后还剩几条**。

### 步骤 4：漏检双维归因（gap）

每条未命中条目给 `category`（发生在哪：可操作原因）+ `why`（能不能修：可修复性），并**必须**带 `affected_query_ids` 与逐字 `evidence`。

`category` 受控词表（前 5 条来自题面要求，第 6 条为本 Skill 增补）：

| category | 可操作判定（脚本给出候选 + 你确认） | 典型证据 |
|-|-|-|
| `query_term_missing` | 题名里的判别性词（非停用词、非通用词）不出现在任何查询式中 | 查询式原文 + 缺失词 + 该词所在的参考集题名行 |
| `field_too_narrow` | 查询字段被限制（如仅 `TI`），而该记录只在更宽字段/别处可见 | 字段声明原文 + 查询 id |
| `time_window_cut` | 参考集年份落在查询声明的时间窗外 | 时间窗原文 + 该条年份 |
| `source_not_indexed` | 参考集所属库/期刊不在查询声明的来源内，且本地记录池也没有它 | 来源声明原文 + 参考集来源字段 |
| `ref_record_anomaly` | 参考集条目自身异常：缺 DOI、同题双 DOI、题名含特殊字符或撤稿 | 参考集该行原文 |
| `ranking_depth`（增补） | 记录确实在池中（别的来源/迭代里有），但目标查询的返回集合里没有它——即返回条数上限或排序截断 | 池中同题记录 locator + 该查询的 `max_results/limit` 声明 |

`why` ∈ `fixable_by_query` | `needs_new_source` | `data_defect` | `definition_mismatch`。
映射：`query_term_missing`/`field_too_narrow`/`ranking_depth`/`time_window_cut` → `fixable_by_query`；`source_not_indexed` → `needs_new_source`；`ref_record_anomaly` → `data_defect`；口径差异（如撤稿条目该不该计入）→ `definition_mismatch`。

完整性要求：**每条 miss 至少一个 category**；一个条目可有 `co_factors`（次要原因），但主因只写一个。`gap_matrix.csv` 与 `gap_atlas.json` 的集合必须等于 `hit_ledger.csv` 里 `hit_status=miss` 的集合，`check` 会比对。

### 步骤 5：定向补检与边际收益（supplement）

针对 `fixable_by_query` 与 `needs_new_source` 的类别设计新查询式（或新来源），逐条登记。脚本在**本地记录池**上重放你的查询式（不对远程库发请求，结果可复现）：

1. 从 `planned_query` 解析词项（去布尔算子、去字段标签、保留引号短语 ≥3 字符）；
2. 词项覆盖率 = `|词项 ∩ 该参考集题名词| / |词项|` ≥ 0.5 即判该条被补检命中；
3. `actual_new_hits` = 新命中的未覆盖条目数；`new_records` = 该查询在池中额外捞到的唯一记录数；
4. `marginal_yield = actual_new_hits / 查询条数`；`cumulative_coverage_after = (已命中 + 累计新增) / 分母`；
5. 停止规则：`marginal_yield ≤ 0.5` 连续一轮，或剩余未覆盖条目全部属于 `data_defect`/`needs_new_source`，或已无可用新词项 → 停，并写明是哪条触发。

**空转检测**：若某补检 `actual_new_hits = 0` 且 `new_records = 0`，`build` 会标 `no_gain=true` 并在报告里写"该补检未改变命中集合，不应计入遗漏下降"。报告里禁止把这种补检算成收益。

### 步骤 6：闭环复核（verify）

- 机械复核：`check` 校验 quote 逐字命中、台账/矩阵集合一致、覆盖率恒等式、契约键齐全。
- 人工抽检：你对低置信（L3/`certainty=low`）与 `needs_human` 行抽检，写进 `draft.spot_check`；脚本报告 `agreement`（抽检一致率）。没有抽检记录就写 `null`，不编造。
- 确定性：同一输入连跑两次，`audit_trail.json` 的 `recompute.coverage` 与 `determinism_hash` 必须一致；`selfcheck` 会独立重算并打印比对结果。

## 8. 失败处理与降级分支

| 情况 | 处置 | 记录位置 |
|-|-|-|
| `case.json` 缺失/坏 JSON | 递归兜底；仍无则用 `task.md` + 材料推进 | `errors[]`，`status=partial` |
| 无 `output_contract` | 用 `products` 与 `coverage` 自述，`output_contract_values` 为空并在文档说明 | `assumptions[]` |
| 参考集为空 | 不算覆盖率，七件套仍产出，写"分母未定义" | `status=insufficient_evidence`，`pending_human[]` |
| 检索结果为空 | 台账全部 miss，归因给 `source_not_indexed`/`query_term_missing`，标明"无结果集，不能区分二者" | `uncertainty[]` |
| 查询日志为空 | 归因降级为"仅能按参考集自身判定"，`affected_query_ids=[]` 并在 `verdict` 写明无法定位查询 | `degradations[]` |
| 参考集只有题名（缺 DOI/年份） | 只用 L2/L3 判定，`certainty≤medium`，`meta_incomplete` 计数 | `degradations[]` |
| 单条目解析异常 | 该条目隔离为 `usable=false, reason=parse_error`，其余继续 | `errors[]` |
| PDF 无文本层 | 记降级，只用文件名/题注，不臆测内容 | `degradations[]` |
| 工作稿缺失/坏 JSON/超时 | `build` 全自动兜底，`decision_source=auto`，七件套齐全，`status=partial` | `degradations[]` |
| 输出目录不可写 | 回退 `./output`、`./work` | `degradations[]` |
| 预算接近耗尽（`elapsed>780s`） | 立即 finalize | `runtime{}` |

## 9. 自查清单（`check` 输出怎么读）

- `[PASS] contract_keys`：`output_contract` 每个键在 `result.json` 顶层存在（缺值 `null`）。
- `[PASS] ledger_rows`：`hit_decisions` 覆盖 `R-*` 全集，无悬空 `ref_id`。
- `[PASS] miss_covered`：每条 miss 在 `gap_notes` 里至少一类。
- `[PASS] quote_verbatim`：每条证据 `quote` 能在对应 `doc_id` 原文里逐字找到。
- `[PASS] identity`：`hit + miss == 分母`；`coverage == hit/分母`（容差 1e-9）。
- `[PASS] category_vocab`：`category`/`why` 全在受控词表内。
- `[WARN] agent_decisions`：自动填补占比 >30% → 说明工作稿太薄，回去读材料。
- `[WARN] no_gain`：补检收益为 0 的条目数。
- `[WARN] needs_human`：低置信待裁决行数。

最终交付前人工确认：口径卡四个数与 `audit_trail` 一致；每条漏检都能读出"哪次查询/哪个字段/哪个来源"；补检表的 `actual_new_hits` 不是手填的期望值。

## 10. 最小调用示例（示例，非正式案例结果）

输入：`case.json`（3 个 `output_contract` 字段）+ `task.md` + `materials/refset.json`（4 条参考集）+ `materials/results.json`（2 条检索记录）+ `materials/queries.json`（2 条查询式）。

```bash
python3 scripts/main.py init            # 冻结 4 条参考集(R-001..R-004)，池 2 条，查询 2 条，写 partial result.json
python3 scripts/main.py show --section refs
#   R-001 10.1000/aaa  "Perovskite durability under humidity"  2019  usable
#   R-002 10.1000/bbb  "Moisture stability of perovskite films" 2021 usable
#   ...
# 写 draft.json（1 条命中、2 条遗漏分别归因、1 条撤稿不可用）
python3 scripts/main.py check           # 6 PASS / 2 WARN
python3 scripts/main.py build           # coverage=1/3=0.3333（撤稿条目单列），gap_atlas 2 类
python3 scripts/main.py selfcheck       # 产物 8/8 存在；CSV 复算 coverage=0.3333（一致）
```

示例里的 id、数字仅用于说明接口，**不是**任何正式案例的答案。

## 11. 文件清单、版本与限制

| 文件 | 作用 |
|-|-|
| `SKILL.md` | 本说明：用途/契约/方法/降级/自查/限制 |
| `scripts/main.py` | 五命令编排：`init`（含 partial `result.json` 落盘）、`show`、`build`、状态持久化、兜底 finalize |
| `scripts/ledger.py` | 材料发现与解析（JSON/JSONL/CSV/MD/PDF/DOCX）、参考集冻结、三级命中判定、台账/矩阵 CSV |
| `scripts/audit.py` | 覆盖口径、双维归因、补检收益与停止规则、审计链、契约键解析 |
| `scripts/render.py` | 人读产物渲染：口径卡、漏检图谱、补检计划、覆盖率报告 |
| `scripts/verify.py` | 共享计算 + `check`（九项机械校验）+ `selfcheck`（复算/一致性） |
| `references/method-and-rubric.md` | 方法与判据：失效模式对策、阈值依据、口径敏感性、归因优先级、停止规则、评分维度映射 |
| `references/draft-and-fields.md` | `draft.json` 字段字典、受控词表、CSV 列字典、`result.json` 信封与契约回填规则、错误码、复用指南 |

五个脚本靠 `Path(__file__)` 互相导入，不依赖 CWD；`main.py` 是唯一入口，其余四个不作为 CLI 单独调用。

版本 `1.0.0`；Python ≥3.8 标准库；无第三方依赖、不联网、不读 CWD、不写包外路径。改版本时同步 `scripts/main.py:V`、`scripts/ledger.py:V`、`scripts/audit.py:V`。

**已知限制**：① 不联网，补检只在本地记录池上重放，等价于"若该查询式存在，它能捞到本地已有的哪些记录"，不能替代真实远程检索；② 题名相似度是字面相似，跨语言（中英混排）与缩写题名会低估，需人工裁决；③ 覆盖率只衡量"记录级可见性"，不衡量全文质量与纳入排除的正确性；④ 参考集本身若有偏（专家清单不全），覆盖率会高估整体召回，本 Skill 只能报"对给定参考集的覆盖率"；⑤ 归因是证据约束下的最可能解释，`certainty=low` 的行需要人工确认。
