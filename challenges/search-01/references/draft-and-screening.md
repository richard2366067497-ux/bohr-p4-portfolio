# 工作稿 schema 与筛选/覆盖口径（playbook）

本文件两部分：**A. 工作稿 draft.json 怎么写**（判断落点）；**B. 筛选、去重、排序与覆盖口径**（`check`/`selfcheck` 的判据）。

工作稿是**判断的落点**：脚本不理解材料，只把你写下的判断变成结构化产物。位置 `/app/work/draft.json`（也接受 `plan.json`、`draft.min.json`）。

## 1. 最小骨架

```json
{
  "schema": "retrieval-draft/1",
  "case_id": "C01",
  "research_question": "研究问题一句话（含对象、方法、边界）",
  "summary": "给读者看的结论摘要：检索了什么、保留多少条、覆盖如何、缺口在哪",
  "queries": [],
  "selections": [],
  "coverage_judgement": [],
  "conflicts": [],
  "gaps": [],
  "uncertainties": []
}
```

只有 `selections` 是硬性必需项；其余缺失会降级（见 §4），但会直接损失「证据记录/覆盖说明」相关得分。

## 2. 字段规则

| 字段 | 类型 | 必填 | 规则 |
|---|---|---|---|
| `research_question` | str | 建议 | 界定主题 + 范围（对象/方法/时间/语言）。写清边界，别写成检索式 |
| `summary` | str | 建议 | 3–6 句：检索策略、保留数、覆盖结论、主要缺口。写入 `report.md` 与 `result.summary` |
| `queries[]` | list | 建议 | 每项 `{query_id, query, source, intent}`。`query_id` 要和 `selections[].query_ids` 对得上，否则 `search_log` 的 `selected` 计数为 0 |
| `queries[].query` | str | 是 | 实际使用的检索式（布尔式/字段限定均可）。脚本按引号短语与纯词统计命中数 |
| `queries[].intent` | str | 建议 | 该查询想解决什么问题（核心主题/机制/应用分支/阴性对照） |
| `selections[]` | list | **是** | 一行一个筛选决定 |
| `selections[].object_id` | str | 是 | `show` 打印的 `O0001…`。也接受 `id`/`record_id`/`object`，或改用 `doi` 定位 |
| `selections[].decision` | str | 是 | `include` / `exclude` / `uncertain`（同义：keep/drop/maybe） |
| `selections[].relevance` | number | include/uncertain 必填 | 0–1。**是排序键，不是概率**；越界会被 `check` 警告，非数字报错 |
| `selections[].tier` | str | 建议 | `core` / `supporting` / `peripheral`；参与次级排序 |
| `selections[].basis` | str | include 必填 | 相关性/排除理由，须指向具体证据（报告的结果、方法属性、主题偏差），不要写「看起来相关」 |
| `selections[].quote` | str | include 必填 | 该对象 `title/abstract/venue/authors` 中的**逐字子串**；允许 `...` 省略中段（两段分别命中即通过） |
| `selections[].query_ids` | list | 建议 | 召回该记录的查询 id |
| `selections[].metadata_notes` | str | 可选 | 缺 DOI/年份冲突/预印本等元数据备注 |
| `coverage_judgement[]` | list | 有必需文献时必填 | `{ref_id, status, object_id, note}`；`status` 用「已覆盖/未覆盖/无法判断」或 `covered/missing/undetermined` |
| `conflicts[]` | list | 可选 | `{field, object_ids, values?, note}`。同一文献跨来源取值不一致时登记，双方并列，不折中 |
| `gaps[]` | list | 建议 | `{kind, detail, impact}`；`kind` 例：`import_lag`、`metadata_missing`、`empty_response`、`rate_limited`、`forbidden`、`language_bias` |
| `uncertainties[]` | list | 建议 | 字符串或对象；写清"为什么这里不能确定" |

## 3. 写法要求

1. **先读再写**：`show` 只给定位与摘要；判断前请打开对应素材文件（`locator` 已给出文件与指针/行号）。
2. **一条也不许漏**：至少覆盖所有与你主题相关的对象；无关对象不必逐条登记，但**被排除的相关候选**必须写进 `exclude` 并给理由——筛选依据本身是交付物。
3. **quote 逐字**：从 `show` 的 `title`/`abstract` 复制，不要翻译、不要合并两句、不要补标点。跨句引用用 `...` 连接两段原文。
4. **不确定性要显式**：预印本、无同行评议、样本单一、只覆盖到某个导入日期，都写进 `basis` 或 `uncertainties`，而不是靠分数暗示。
5. **不补造**：素材没有的 DOI/年份/作者不要凭印象填写；需要时在 `metadata_notes` 写「素材缺 XX」。

## 4. 工作稿缺陷 → 后果

| 缺陷 | `check` 反馈 | `build` 后果 |
|---|---|---|
| 无 `draft.json` | `[error] draft_missing` | 兜底：关键词族重叠排序，`status=partial`，`judgement=deterministic_fallback` |
| `selections` 为空 | `[error] no_selection` | 同上 |
| `object_id` 写错 | `[error] unknown_object` | 该条被丢弃，计入 `errors` |
| `decision` 非枚举 | `[error] bad_decision` | 按 `uncertain` 处理 |
| `relevance` 非数字 / 越界 | `[error] relevance_not_number` / `[warn] relevance_range` | 缺失按 0 排序；越界被截断到 [0,1] |
| include 缺 `basis` | `[error] missing_basis` | 该行 `basis=null`，可核验性受损 |
| 引文不命中 | `[error] quote_not_found`（含 locator） | `quote_verified=false`，整份 `status=partial` |
| 无 `queries` | `[warn] no_query_plan` | `search_log` 展示建议查询并记 `query_plan_generated` |
| 有必需文献但无 `coverage_judgement` | `[warn] no_coverage_judgement` | `coverage.agent_notes=null`，只有脚本口径 |
| 保留数 < target_k | `[warn] below_target_k` | `status=partial` |

## 5. 完整示例（**示例数据，非正式案例结果**）

```json
{
  "schema": "retrieval-draft/1",
  "research_question": "Graphene oxide membranes for water treatment/desalination: interlayer channel control and antifouling modification, 2015-2024, top 5.",
  "summary": "检索 GO 膜在水处理与脱盐中的应用，覆盖层间通道调控与抗污染改性两个分支；候选来自 Crossref、Europe PMC 与出版商 HTML 快照，去重后按相关性排序。",
  "queries": [
    {"query_id": "Q1", "query": "\"graphene oxide\" AND membrane AND desalination", "source": "crossref", "intent": "核心主题"},
    {"query_id": "Q2", "query": "\"graphene oxide membrane\" AND review", "source": "europepmc", "intent": "机制与综述覆盖"},
    {"query_id": "Q3", "query": "\"graphene oxide\" AND antifouling", "source": "crossref", "intent": "抗污染分支"},
    {"query_id": "Q4", "query": "graphite AND electrode", "source": "crossref", "intent": "阴性对照：同材料族、不同应用"}
  ],
  "selections": [
    {"object_id": "O0006", "decision": "include", "relevance": 0.93, "tier": "core",
     "basis": "题名与摘要直接报告 GO 膜层间间距调控与脱盐性能（42 L m-2 h-1，99.4% NaCl 截留）",
     "quote": "We tune the interlayer spacing of graphene oxide membranes", "query_ids": ["Q1"]},
    {"object_id": "O0010", "decision": "uncertain", "relevance": 0.35, "tier": "peripheral",
     "basis": "预印本（medRxiv），主题相关但未经同行评议，保留待确认",
     "quote": "Biofouling of graphene oxide membranes in drinking water treatment", "query_ids": ["Q2"]},
    {"object_id": "O0008", "decision": "exclude", "relevance": 0.05, "tier": "peripheral",
     "basis": "石墨电极腐蚀，无膜传输或水处理内容",
     "quote": "Graphite electrodes degrade under high voltage", "query_ids": ["Q4"]}
  ],
  "coverage_judgement": [{"ref_id": "REQ01", "status": "已覆盖", "object_id": "O0006", "note": "同 DOI 多来源已去重"}],
  "conflicts": [{"field": "venue", "object_ids": ["O0006", "O0009"], "note": "Crossref 全称 vs Europe PMC 缩写"}],
  "gaps": [{"kind": "import_lag", "detail": "publisher 2024 期次未导入", "impact": "2024 年出版商侧文献可能缺失"}],
  "uncertainties": ["基于离线快照，未做在线补检"]
}
```

对应命令：

```bash
python3 -B scripts/main.py check    # 期望 ok: True，无 [error]
python3 -B scripts/main.py build
```

## 6. 交叉引用

- 契约字段、产物结构与降级码：`references/io-contract.md`
- 契约字段、产物结构与降级码：`references/io-contract.md`

---

# B. 筛选、去重、排序与覆盖口径（规则表）

本文件规定「哪条留下、按什么顺序、覆盖怎么算、缺什么怎么写」。它同时是 `check`/`selfcheck` 的判据来源。

### 1. 相关性判定（Agent 侧）

分三档，档位写进 `selections[].tier`，分数写进 `relevance`。分数只为排序服务，不代表概率。

| tier | 判定标准（满足其一即可归入，但须在 `basis` 写清是哪一条） | 参考区间 |
|---|---|---|
| `core` | 题名+摘要直接回答研究问题（同一对象、同一方法/机制、报告可比较的结果或机制） | 0.80–1.00 |
| `supporting` | 覆盖研究问题的一个分支、一种改性策略、一个应用场景，或提供方法/机制支撑 | 0.45–0.79 |
| `peripheral` | 同材料族/同术语但对象或应用不同；预印本、会议摘要等证据强度弱；元数据不足无法判断 | 0.00–0.44 |

硬性红线：

- 只有关键词重叠、对象或应用不同 → 最多 `peripheral`，**不得**进 `core`（这正是"看起来相关"的典型误判）。
- 证据强度差异（预印本/无同行评议/单一场景）必须在 `basis` 或 `uncertainties` 显式写明，不能只靠打折分数暗示。
- `exclude` 也要给理由：排除依据与保留依据同等重要。

### 2. 决策语义

| decision | 含义 | 产物位置 |
|---|---|---|
| `include` | 进入候选集，按分数排序 | `candidates[]`，`status=included` |
| `uncertain` | 相关但证据/元数据不足，**保留待人工确认**（不隐藏） | `candidates[]` 末尾，`status=included_pending_confirmation` |
| `exclude` | 不进入候选集，但保留排除理由与引文 | `excluded[]` |

不写 `exclude` 的相关候选会被视为漏筛；只保留"看起来最好"的几条会直接损失召回与可复核性。

### 3. 去重规则

1. 有 DOI → 以 DOI（小写归一）为簇键。
2. 无 DOI → 题名指纹：小写、去标点空白、取前 90 字符。
3. 同簇内 keeper = `metadata_completeness` 最高者（五字段：作者/年份/期刊/DOI/摘要齐全度），并列取摘要更长者。
4. 合并信息写进 keeper 的 `merged_from`（来源 `source_id` 列表）与 `screening.notes`，**不删除**任何原始记录（`sources[]` + locator 仍可回溯）。
5. `coverage.duplicates_merged` = 去重前对象数 − 去重后簇数（+ 保留集合内合并数），用于说明多库重叠规模。

### 4. 元数据冲突

同一簇内 `year` 或 `venue` 出现多个不同非空取值 → 记 `conflicts[]`：`{field, kind: metadata_conflict, values: [...], objects: [...]}`。

- 双方取值并列保留，**不得**取平均、不得只留一个而不说明；
- keeper 仍按完整性选择，冲突进入 `uncertainties` 或 `conflicts[].note`；
- 常见来源差异：Crossref 用期刊全称、Europe PMC 用缩写（`Journal of Membrane Science` vs `J Membr Sci`）；在线优先/印刷年份差 1 年。

### 5. 排序（确定性）

```
key = (relevance desc, tier_weight desc[core=2, supporting=1, peripheral=0], doi asc, object_id asc)
```

- 无随机、无时间依赖 → 同输入两次运行结果完全一致（「增益可验证」的依据）。
- `rank` 从 1 连续编号，`record_id = R{rank:02d}`。
- `relevance.score` 缺失按 0 处理，不会被"提到前面"。

### 6. 覆盖与召回

| 指标 | 计算 | 说明 |
|---|---|---|
| `target_k` | `case.json` 的 `top_k/k/limit/...`，否则从题面正则（`top_k=5`、`前 20 篇`、`至少 15`），否则默认 20 | 来源写 `assumptions[target_k].source` |
| `selected_count` | `candidates` 行数（含 uncertain） | |
| `distinct_after_dedup` | 去重后行数 | 与 `selected_count` 差值即簇内合并量 |
| `required_total` | 必需文献/关键文献/参考图检查点条目数 | 有 `required_references/key_papers/...` 时用其；否则用参考图节点 |
| `required_matched` | DOI 相等；或题名词元覆盖 ≥0.75 的候选 | 匹配到具体 `object_id`/`record_id` |
| `required_missing` | 未匹配者，含 `ref_id`/`doi`/`title` | 同步写入 `missing[]`（`kind=required_reference_not_found`） |
| `recall_against_required` | matched / total | total=0 时为 `null`，不写 0 或 1 |
| `family_coverage[]` | 每个种子关键词族在候选中的命中数 | 无种子关键词时用研究问题词元兜底 |

`status` 判定顺序（先命中先返回）：

1. 对象池为空或全部被排除 → `insufficient_evidence`；
2. 兜底路径（无工作稿）、或保留数 < `min(target_k, 可用对象数)` → `partial`；
3. 存在 `quote_verified=false` 的保留行 → `partial`（+ `unverified_quote_present`）；
4. 否则 `answered`；若同时存在输入级 `errors` → 视材料可用性降为 `partial`/`input_error`。

### 7. 可核验契约

每条保留/排除记录必须同时具备：

1. `source_id`：哪份素材（`sources[].source_id` 可对照原文件）；
2. `locator`：文件内定位（`#/message/items/3`、`#row=12`、`#meta`、`#article=2`、`#L7`）；
3. `relevance.quote`：逐字片段，`quote_verified=true`。

引文校验口径：小写 + 空白归一 + 统一引号/破折号后做子串匹配；含 `...` 时按段分别匹配（`quote_field=text_elided`）。不通过时**不改原文凑通过**，标 `false` 并让整份结果降级。

### 8. 降级矩阵（与 SKILL.md §8 一致）

| 触发 | 产物影响 | status |
|---|---|---|
| 无 draft | 候选来自关键词族重叠；`judgement=deterministic_fallback`；两类降级码 | `partial` |
| 引文不命中 | `quote_verified=false` + 降级码 | `partial` |
| 保留数不足 target_k | `coverage` 如实记数 + `below_target_k` 警告 | `partial` |
| 必需文献缺失 | `missing[]` + `coverage.required_missing` | 视其余情况 |
| 材料为空 | `candidates=[]`；`missing` 说明未取得 | `insufficient_evidence` |
| 声明材料缺失 / 二进制未解析 | `degradations` + `missing[]` | `partial` |
| 来源快照含 429/403/error | 该来源 `role` 与 `missing[]` 说明；不推测其内容 | `partial` |
| 未预期异常 | crash guard 重写合法 `result.json` | `partial` |

### 9. 自查 grep 清单

```bash
python3 -m json.tool /app/output/result.json > /dev/null && echo "result.json OK"
python3 -c "import json;r=json.load(open('/app/output/result.json'));print(len(r['candidates']),r['status'])"
grep -c . /app/output/candidates.jsonl          # 行数应与 candidates 一致
grep -o '"locator": "[^"]*"' /app/output/result.json | sort -u | head
```

人工抽查三条候选：`title` 与素材逐字一致；`locator` 打开后能看到该记录；`quote` 在该记录文本里能 grep 到。

### 10. 方法边界（写进不确定性，不要越过）

- 只覆盖 `/input` 快照里的来源；不做在线补检、不声称全局新颖性或"最新进展"。
- 覆盖受组织方导入状态限制（`search_log.import_states`），结论只在快照范围内成立。
- 引用次数、影响因子、期刊分区等快照未提供的指标不推测。
- PDF/图片未解析时，相关判断只能基于题录与元数据，须在 `uncertainties` 写明。
