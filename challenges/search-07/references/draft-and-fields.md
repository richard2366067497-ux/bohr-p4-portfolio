# 字段字典 · 工作稿 schema · 错误码

本文件是 `SKILL.md` 的配套字典。所有字段名在脚本里按原样读取，改名不会生效；缺字段按"自动填补 + 降级"处理，不会崩溃。

## 1. `draft.json`（你写的工作稿）

路径 `/app/work/draft.json`。类型约定：`[]` 列表、`{}` 对象、`s` 字符串、`n` 数字、`b` 布尔。

| 字段 | 类型 | 必填 | 说明 |
|-|-|-|-|
| `research_question` | s | 建议 | 一句话写清检索目标与边界；会进 `scope_card.md` §1 |
| `scope.denominator_policy` | s | 建议 | 取值 `all` / `dedup_only` / `dedup_exclude_unavailable`；不写则用最后一项 |
| `scope.time_window` / `fields` | s | 可选 | 覆盖口径卡里"来自查询日志"的自动值；写了以你为准 |
| `scope.coverage_definition` | s | 可选 | 一句话公式说明（默认 `matched_usable / usable_refs`） |
| `scope.notes` | s | 建议 | 为什么这样定分母、不可用条目怎么处理；直接进口径卡"选定口径"的理由 |
| `ref_decisions[]` | list | 建议 | `{ref_id, usable:b, reason:s, merge_into:s|null}`；`usable=false` 的条目退出分母但保留台账 |
| `hit_decisions[]` | list | **核心** | `{ref_id, status:hit\|miss\|pending, matched_id, rule, certainty, locator, evidence, note}` |
| `hit_decisions[].rule` | s | 命中时 | `id_doi` / `id_pmid` / `bib_title_author_year` / `bib_title_year` / `bib_borderline` |
| `hit_decisions[].locator` | s | 命中/遗漏都要 | 形如 `src-03:L12`（文档 id + 1-based 行号），`check` 会用它回读原文核对 `evidence` |
| `hit_decisions[].evidence` | s | 建议 | 命中写"与哪一行一致"，遗漏写"该题名不在结果集内"；给 locator 时会被逐字校验 |
| `gap_notes[]` | list | **核心** | `{category, why, ref_ids[], affected_query_ids[], evidence[], verdict}` |
| `gap_notes[].evidence[]` | list | 必填 | `{doc_id, locator, quote}`；`quote` 必须能在源文件里逐字找到（空格折叠后比较） |
| `supplement[]` | list | 建议 | `{target_gap, planned_query, fields, window, expected_new, rationale}` |
| `residual_notes[]` | list | 可选 | `{ref_id, reason, explanation}`；残余遗漏的逐条解释 |
| `conflicts[]` | list | 可选 | `{item, detail}`；进 `uncertainty`，不静默吞掉 |
| `spot_check[]` | list | 可选 | `{ref_id, agree:b, note}`；没写则审计链的 `agreement` 为 null，不猜 |
| `status_note` | s | 可选 | 一句话说明剩余不确定点 |

一条 `gap_notes` 可以覆盖多条 `ref_ids`（同类合并）；脚本随后会按类聚合成 `gap_atlas.json`。**每条 `miss` 至少被一条 `gap_notes` 覆盖**，否则 `check` 的 `miss_covered` 项 FAIL，`build` 会用自动归因兜底并在 `degradations` 记明。

## 2. 受控词表

`category`（发生在哪，6 类，前 5 条来自题面，`ranking_depth` 为本 Skill 增补）：

| 值 | 何时用 | 必备证据 |
|-|-|-|
| `query_term_missing` | 题名判别词不在任何查询式里 | 查询式原文 + 缺失词 |
| `field_too_narrow` | 查询字段过窄（如仅 `TI`） | 字段声明原文 |
| `time_window_cut` | 参考集年份落在时间窗外 | 时间窗原文 + 该条年份 |
| `source_not_indexed` | 声明来源不含该记录所属库/刊 | 来源声明原文 |
| `ref_record_anomaly` | 参考集条目自身异常（缺 DOI/双 DOI/撤稿/题名畸形） | 参考集该行原文 |
| `ranking_depth` | 词项与字段都覆盖了，但记录不在返回集合里（条数上限/排序截断） | 池中同题记录 locator |

`why`（能不能修，4 类）：`fixable_by_query`（改查询式/字段/时间窗）、`needs_new_source`（需换源）、`data_defect`（数据缺陷）、`definition_mismatch`（口径差异）。默认映射：前四类 category → `fixable_by_query`；`source_not_indexed` → `needs_new_source`；`ref_record_anomaly` → `data_defect`。

`status`：`hit` / `miss` / `pending`（低置信、需人工裁决，计入"待裁决"而非命中）。

## 3. `hit_ledger.csv` 列

| 列 | 含义 |
|-|-|
| `ref_id` | `R-001…`，参考集冻结编号 |
| `title` / `doi` / `year` / `first_author` | 参考集书目信息（原样取自材料，不改写） |
| `usable` | `True/False`；False 表示退出分母（撤稿/无全文/不可解析） |
| `usability_reason` | 判定理由；来自你的 `ref_decisions` 或标记词 |
| `hit_status` | `hit` / `miss` / `pending` |
| `matched_id` | 命中时对应的池记录 `P-0001…`；遗漏留空 |
| `match_rule` | 三级规则名；遗漏留空 |
| `certainty` | `high` / `medium` / `low`；low 会进 `needs_human` |
| `evidence_locator` / `evidence_quote` | 证据位置 + 逐字引用（`check` 回读核对） |
| `decision_source` | `agent`（工作稿确认）/ `auto`（脚本建议未确认） |
| `needs_human` | `True` 表示需要人工裁决 |

复算方式：`usable=True` 的行数 = 分母（`all`/`dedup_only` 口径下取全表），其中 `hit_status=hit` 的行数 = 分子。

## 4. `gap_matrix.csv` 列

`ref_id, title, primary_category, co_factors, why, fixability, affected_query_ids, action, evidence_locator`。
一行一条未命中条目；`co_factors` 用 `;` 分隔次要原因；`action` 是该条的处置说明（来自 `verdict`）。

## 5. `result.json` 信封

固定字段：`case_id, status, skill, skill_version, output_contract_values, counts, coverage, gap_summary, supplement, sources, uncertainty, pending_human, errors, degradations, assumptions, changes, products, payload, runtime`。

- `status`：`ok`（工作稿覆盖 ≥80%、证据全命中、分母非空）/ `partial`（产物齐全但有缺口）/ `insufficient_evidence`（无参考集，分母未定义）/ `input_error`（无可读材料）。
- `output_contract` 回填：键名不改、不漏键。文件类键填相对路径，指标类键填数字或字典，文字类键填结论摘要；映射不到的键填 `null`，并在 `output_contract_values.<key>.note` 写明原因，`kind`/`provenance` 记录填法来源。
- **键名冲突**：若契约键与本信封同名字段（如 `status`、`coverage`、`supplement`），信封字段保留自身语义，契约值仍完整保存在 `output_contract_values.<key>.value`，不丢信息。
- `payload` 内嵌参考集、台账、类别、补检行、quote 校验结果，便于只读 `result.json` 也能复核。

## 6. 错误与降级码（`errors[]` / `degradations[]` 的 `stage`）

| stage | 含义 | 影响 |
|-|-|-|
| `case` | case.json 缺失或解析失败（已按原文抢救 `case_id`/契约键名） | 契约键可能为空，`status=partial` |
| `parse` | 某材料 JSON 解析失败（退回文本扫描） | 该文件记录可能有遗漏 |
| `read` | 文件读取失败或 PDF 文本层过薄 | 该文件只用文件名/题注 |
| `discover` | 输入目录无可读材料 | `status=input_error` |
| `queries` | 未识别查询日志 | 归因无法定位查询式，`affected_query_ids=[]` |
| `gap` | 工作稿里的类别不在词表或 `ref_ids` 无效 | 该条按默认类处理并记录 |
| `draft` | 工作稿缺失/坏 JSON | 全自动填补，`decision_source=auto`，`status=partial` |
| `quote` | 证据 quote 未能逐字命中 | 该行标 pending，需核对 locator |
| `paths` | 目录不可写，已回退 `./output`、`./work` | 产物位置变化 |
| `products` | 某产物渲染异常（已写占位） | 对应文件内容为错误说明 |

## 7. 命令与退出码

| 命令 | 作用 | 关键参数 |
|-|-|-|
| `init` | 建索引 + 冻结参考集 + 写 partial `result.json` | `--input --work --output` |
| `show` | 打印材料投影（带 locator） | `--section all\|materials\|refs\|pool\|queries\|sources`、`--limit N` |
| `check` | 机械校验工作稿 | `--strict`（WARN 也显示为 FAIL 提示，不改退出码） |
| `build` | 生成 7 件产物 + finalize `result.json` | `--policy`、`--no-draft` |
| `selfcheck` | 复检产物/复算/一致性 | 同上 |

所有命令退出码恒为 `0`；`--help` 打印接口自述。脚本互不依赖 CWD，用 `Path(__file__)` 定位。

## 8. 最小工作稿示例（示例数据，非正式案例结果）

```json
{"research_question": "X 主题的检索覆盖率",
 "scope": {"denominator_policy": "dedup_exclude_unavailable", "notes": "撤稿条目退出分母"},
 "ref_decisions": [{"ref_id": "R-001", "usable": true, "reason": "原始研究"}],
 "hit_decisions": [{"ref_id": "R-001", "status": "hit", "matched_id": "P-0001", "rule": "id_doi",
                    "certainty": "high", "locator": "src-04:L2", "evidence": "DOI 与结果记录一致"},
                   {"ref_id": "R-002", "status": "miss", "matched_id": null, "rule": null,
                    "certainty": "high", "locator": "src-03:L3", "evidence": "结果快照无此题名"}],
 "gap_notes": [{"category": "query_term_missing", "why": "fixable_by_query", "ref_ids": ["R-002"],
                "affected_query_ids": ["Q-001"],
                "evidence": [{"doc_id": "src-02", "locator": "src-02:L2", "quote": "TS=(perovskite AND stability)"}],
                "verdict": "缺 durability 同义表达"}],
 "supplement": [{"target_gap": "query_term_missing", "planned_query": "TS=(perovskite AND (stability OR durability))",
                 "fields": "title/abstract", "window": "2015-2024", "expected_new": 1}]}
```

## 9. 复用到新主题的改法

1. 换材料即可：参考集文件、结果快照、查询日志三者放同一 `/input` 下，命名随意（按内容识别）。
2. 参考集若不是 JSON 列表（而是综述正文的参考文献段），仍可直接用：带 DOI 或"作者(年份)题名"的行会被识别为条目；识别不全时优先补一份结构化清单。
3. 若某主题的库不支持公告字段，把 `field_too_narrow` 的证据换成数据库文档里的字段定义行即可，逻辑不变。
4. 想改覆盖率口径：`--policy` 或 `draft.scope.denominator_policy`，三套口径始终同时输出，便于横向比较。
